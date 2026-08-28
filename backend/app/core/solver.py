"""Stufe 2 des Solvers: CP-SAT-Zuweisung (F_OM_005, F_OM_007, F_OM_008, NF_003).

Aufbau je Prüfungstag (die Tage sind durch H7 fachlich entkoppelt — nur die
Prüfer-Auslastung W2 wird als Lastvortrag von Tag 1 nach Tag 2 mitgenommen):

  Phase A  Zeit- und Kapazitätsplanung: wann findet welches Prüfungsereignis
           statt (Raster aus den konfigurierten Formatdauern, H8), ohne
           Doppelbelegung der Personen (H5) und innerhalb der Raum- und
           Prüfendenkapazitäten je Zeitpunkt (H5/H6-Kapazität). Ziel: W5
           (Wartezeiten) und W6 (Bestandserhalt der Zeiten).
  Raumvergabe  Konkrete Räume greedy auf die fixierten Zeiten (H6: Eignung
           und Verfügbarkeit; W6: möglichst vorheriger Raum).
  Phase B  Prüfendenzuordnung auf die fixierten Zeiten: H1 (keine
           Doppelbegegnung), H2 (Befangenheit), H3/H4 (Zusammensetzung),
           H5 (keine Überschneidung je Prüfer:in). Ziel: W2 (gleichmäßige
           Auslastung), W4 (gemischte Panels), W6 (Bestandserhalt).

Die Regel-IDs in den Kommentaren verweisen auf rules.py (Single Source of
Truth). Der Property-Test „jeder Solver-Output besteht den Validator" sichert
die Übereinstimmung von Constraints und Regelkatalog ab.

Infeasibility (Kap. 9): Constraints werden schrittweise relaxiert (Soft-H1,
Soft-H3), niemals stillschweigend — verletzte Regeln erscheinen als benannte
Konflikte über den Validator.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from ..db.models import PrueferStatus, Tag
from .konfiguration import RASTER_MIN, JahrgangsKonfiguration
from .plan import Plan, PlanKontext, PlanZuweisung
from .rules import Konflikt, kennzahlen_berechnen
from .validator import plan_validieren


@dataclass
class SolverErgebnis:
    plan: Plan
    kennzahlen: dict
    konflikte: list[Konflikt]
    status: str                      # "optimal" | "gueltig" | "relaxiert" | "unloesbar"
    laufzeit_sekunden: float
    hinweise: list[str] = field(default_factory=list)


def _solver_konfigurieren(seed: int, timeout_s: float) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_s
    solver.parameters.random_seed = seed
    solver.parameters.num_search_workers = 1   # Determinismus (NF_010)
    # Gute Lösung statt Optimalitätsbeweis: 5 % Gap genügen fachlich und
    # sparen den Großteil der Laufzeit (NF_003)
    solver.parameters.relative_gap_limit = 0.05
    return solver


class KeinPlanMoeglich(Exception):
    def __init__(self, konflikte: list[Konflikt]):
        self.konflikte = konflikte
        super().__init__("; ".join(k.meldung for k in konflikte))


# ---------------------------------------------------------------------------
# Ereignis-Struktur
# ---------------------------------------------------------------------------

@dataclass
class _Ereignis:
    key: tuple                # stabil über Läufe: ("einzel", bewerber_id, format_key)
    format_key: str           #                    ("gruppe", gruppe_id, format_key)
    typ: str
    dauer: int
    anzahl_pruefer: int
    bewerber_ids: frozenset
    gruppe_id: int | None
    starts: list[int]
    # Ergebnis:
    start: int | None = None
    raum_id: int | None = None
    pruefer_ids: frozenset = frozenset()


def _ereignisse_bauen(kontext: PlanKontext, tag: Tag) -> list[_Ereignis]:
    konf = kontext.konfiguration
    zm = konf.zeitmodell
    ereignisse: list[_Ereignis] = []

    def starts_fuer(dauer: int) -> list[int]:
        # H8: Slots liegen vollständig im Tagesfenster.
        return list(range(zm.start_min, zm.ende_min - dauer + 1, RASTER_MIN))

    gruppen_des_tages = sorted(
        (g for g in kontext.gruppen.values() if g.tag == tag), key=lambda g: g.nummer
    )
    for gruppe in gruppen_des_tages:
        mitglieder = frozenset(
            b.id for b in kontext.planbare_bewerber(tag) if b.gruppe_id == gruppe.id
        )
        if not mitglieder:
            continue
        for fmt in konf.formate:
            if fmt.typ == "einzel":
                continue
            ereignisse.append(_Ereignis(
                key=("gruppe", gruppe.id, fmt.key), format_key=fmt.key, typ=fmt.typ,
                dauer=fmt.dauer_min, anzahl_pruefer=fmt.anzahl_pruefer,
                bewerber_ids=mitglieder, gruppe_id=gruppe.id,
                starts=starts_fuer(fmt.dauer_min),
            ))
    for info in sorted(kontext.planbare_bewerber(tag), key=lambda b: b.id):
        for fmt in konf.formate:
            if fmt.typ != "einzel":
                continue
            ereignisse.append(_Ereignis(
                key=("einzel", info.id, fmt.key), format_key=fmt.key, typ=fmt.typ,
                dauer=fmt.dauer_min, anzahl_pruefer=fmt.anzahl_pruefer,
                bewerber_ids=frozenset({info.id}), gruppe_id=None,
                starts=starts_fuer(fmt.dauer_min),
            ))
    return ereignisse


def _raum_kapazitaet(kontext: PlanKontext, tag: Tag, groesse, tick: int) -> int:
    return sum(
        1 for r in kontext.raeume.values()
        if r.groesse == groesse and r.verfuegbar(tag, tick, tick + RASTER_MIN)
    )


# ---------------------------------------------------------------------------
# Vorab-Diagnose: benannte Konflikte statt nacktem „infeasible“ (Kap. 4.3)
# ---------------------------------------------------------------------------

def _diagnose(kontext: PlanKontext, tag: Tag, ereignisse: list[_Ereignis]) -> list[Konflikt]:
    konflikte: list[Konflikt] = []
    konf = kontext.konfiguration
    zm = konf.zeitmodell
    fenster = zm.ende_min - zm.start_min

    # H8: passt das Pflichtprogramm einer Person überhaupt in den Tag?
    programm = sum(f.dauer_min for f in konf.formate)
    if programm > fenster:
        konflikte.append(Konflikt(
            regel="H8",
            meldung=(
                f"Das Pflichtprogramm je Bewerber:in ({programm} min) übersteigt das "
                f"Tagesfenster ({fenster} min, {zm.tag_start}–{zm.tag_ende})."
            ),
        ))

    # H6: reicht die Raumkapazität für die Gesamtminuten je Raumgröße?
    for groesse in {f.raumgroesse for f in konf.formate}:
        bedarf = sum(e.dauer for e in ereignisse
                     if konf.format(e.format_key).raumgroesse == groesse)
        angebot = sum(
            fenster for r in kontext.raeume.values()
            if r.groesse == groesse and r.verfuegbar(tag, zm.start_min, zm.start_min + 1)
        )
        if bedarf > angebot:
            konflikte.append(Konflikt(
                regel="H6",
                meldung=(
                    f"Raumkapazität am {tag.value} reicht nicht: Formate der Größe "
                    f"„{groesse.value}“ benötigen {bedarf} Raum-Minuten, verfügbar sind "
                    f"{angebot}. Räume ergänzen oder Zeitmodell anpassen."
                ),
            ))

    # H3/H4: reichen die Prüfenden rechnerisch?
    senioren = [p for p in kontext.verfuegbare_pruefer(tag) if not p.ist_junior]
    bedarf_senior = sum(
        (e.anzahl_pruefer if konf.format(e.format_key).nur_senior
         else konf.format(e.format_key).min_senior) * e.dauer
        for e in ereignisse
    )
    angebot_senior = len(senioren) * fenster
    if bedarf_senior > angebot_senior:
        konflikte.append(Konflikt(
            regel="H3",
            meldung=(
                f"Senior-Kapazität am {tag.value} reicht nicht: benötigt werden "
                f"{bedarf_senior} Prüfer-Minuten (H3/H4), verfügbar {angebot_senior}."
            ),
        ))
    return konflikte


# ---------------------------------------------------------------------------
# Phase A: Zeitplanung
# ---------------------------------------------------------------------------

def _phase_a(
    kontext: PlanKontext,
    tag: Tag,
    ereignisse: list[_Ereignis],
    seed: int,
    timeout_s: float,
    bestand: dict[tuple, PlanZuweisung],
    mit_pruefer_kapazitaet: bool = True,
) -> bool:
    konf = kontext.konfiguration
    zm = konf.zeitmodell
    gewichte = konf.gewichte
    model = cp_model.CpModel()

    x: dict[int, dict[int, cp_model.IntVar]] = {}
    start_var: dict[int, cp_model.IntVar] = {}
    for i, e in enumerate(ereignisse):
        x[i] = {t: model.NewBoolVar(f"x_{i}_{t}") for t in e.starts}
        model.AddExactlyOne(x[i].values())        # H7: jedes Ereignis findet statt
        sv = model.NewIntVar(zm.start_min, zm.ende_min, f"s_{i}")
        model.Add(sv == sum(t * v for t, v in x[i].items()))
        start_var[i] = sv

    ticks = list(range(zm.start_min, zm.ende_min, RASTER_MIN))

    def occ(i: int, tick: int, vorlauf: int = 0):
        """Linearer Ausdruck: läuft Ereignis i zum Zeitpunkt tick?
        ``vorlauf`` erweitert die Belegung nach vorn (Kaffeepausen-Puffer)."""
        e = ereignisse[i]
        return sum(
            v for t, v in x[i].items() if t - vorlauf <= tick < t + e.dauer
        )

    # H5: keine Doppelbelegung je Bewerber:in. Jedes Ereignis belegt zusätzlich
    # die Mindestpause davor (Wegzeit für den Raumwechsel). Über den Vorlauf
    # erzwingt dieselbe Bedingung damit auch den Abstand zum Vortermin (H10).
    pause = zm.mindestpause_min

    nach_bewerber: dict[int, list[int]] = defaultdict(list)
    for i, e in enumerate(ereignisse):
        for bid in e.bewerber_ids:
            nach_bewerber[bid].append(i)
    for bid, indizes in nach_bewerber.items():
        for tick in ticks:
            model.Add(sum(occ(i, tick, vorlauf=pause) for i in indizes) <= 1)

    # H6 (Kapazität): je Zeitpunkt höchstens so viele Ereignisse je Raumgröße,
    # wie Räume verfügbar sind (konkrete Raumvergabe folgt nach Phase A)
    for groesse in {f.raumgroesse for f in konf.formate}:
        indizes = [i for i, e in enumerate(ereignisse)
                   if konf.format(e.format_key).raumgroesse == groesse]
        for tick in ticks:
            kapazitaet = _raum_kapazitaet(kontext, tag, groesse, tick)
            model.Add(sum(occ(i, tick) for i in indizes) <= kapazitaet)

    # H3/H4 (Kapazität): je Zeitpunkt genug Prüfende — Panels brauchen
    # min_senior Senioren, Einzelformate nur_senior
    if mit_pruefer_kapazitaet:
        verfuegbar = kontext.verfuegbare_pruefer(tag)
        anz_gesamt = len(verfuegbar)
        anz_senior = sum(1 for p in verfuegbar if not p.ist_junior)
        for tick in ticks:
            model.Add(sum(occ(i, tick) * ereignisse[i].anzahl_pruefer
                          for i in range(len(ereignisse))) <= anz_gesamt)
            model.Add(sum(
                occ(i, tick) * (
                    ereignisse[i].anzahl_pruefer
                    if konf.format(ereignisse[i].format_key).nur_senior
                    else konf.format(ereignisse[i].format_key).min_senior
                )
                for i in range(len(ereignisse))
            ) <= anz_senior)

    # W5: Wartezeiten minimieren — Zeitspanne je Bewerber:in
    spannen = []
    for bid, indizes in nach_bewerber.items():
        erster = model.NewIntVar(zm.start_min, zm.ende_min, f"min_{bid}")
        letzter = model.NewIntVar(zm.start_min, zm.ende_min, f"max_{bid}")
        model.AddMinEquality(erster, [start_var[i] for i in indizes])
        model.AddMaxEquality(letzter, [start_var[i] + ereignisse[i].dauer for i in indizes])
        spanne = model.NewIntVar(0, zm.ende_min - zm.start_min, f"spanne_{bid}")
        model.Add(spanne == letzter - erster)
        spannen.append(spanne)

    # W6: Bestandserhalt der Zeiten (Neuberechnung minimalinvasiv)
    bestand_treffer = []
    for i, e in enumerate(ereignisse):
        alt = bestand.get(e.key)
        if alt is not None and alt.start_min in x[i]:
            bestand_treffer.append(x[i][alt.start_min])
            model.AddHint(x[i][alt.start_min], 1)

    model.Minimize(
        gewichte.w5_wartezeit * sum(spannen)
        - gewichte.w6_bestandserhalt * sum(bestand_treffer)
    )

    solver = _solver_konfigurieren(seed, timeout_s)
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return False
    for i, e in enumerate(ereignisse):
        e.start = int(solver.Value(start_var[i]))
    return True


# ---------------------------------------------------------------------------
# Raumvergabe (greedy auf fixierte Zeiten)
# ---------------------------------------------------------------------------

def _raeume_zuweisen(
    kontext: PlanKontext, tag: Tag, ereignisse: list[_Ereignis],
    bestand: dict[tuple, PlanZuweisung], seed: int, budget: float = 30.0,
) -> None:
    """Konkrete Raumvergabe auf die fixierten Zeiten als kleines CP-SAT-Matching.

    Ziel: maximal viele Ereignisse behalten ihren bisherigen Raum (W6) — eine
    Greedy-Vergabe würde bei einem Raumausfall kaskadenartig fast alle Räume
    umverteilen. Fällt das Matching aus (sollte durch die Kapazitätsschranken
    der Phase A nicht vorkommen), greift eine Greedy-Rückfallebene; der
    Validator benennt dann entstehende H5/H6-Konflikte (kein stiller Bruch)."""
    konf = kontext.konfiguration
    model = cp_model.CpModel()
    y: dict[int, dict[int, cp_model.IntVar]] = {}
    machbar = True
    for i, e in enumerate(ereignisse):
        fmt = konf.format(e.format_key)
        kandidaten = [
            r for r in sorted(kontext.raeume.values(), key=lambda r: r.raumnummer)
            if r.groesse == fmt.raumgroesse and r.verfuegbar(tag, e.start, e.start + e.dauer)
        ]
        if not kandidaten:
            machbar = False
            break
        y[i] = {r.id: model.NewBoolVar(f"y_{i}_{r.id}") for r in kandidaten}
        model.AddExactlyOne(y[i].values())

    if machbar:
        # H5: je Raum und Zeitpunkt höchstens ein Ereignis
        zm = konf.zeitmodell
        for raum_id in {rid for zeile in y.values() for rid in zeile}:
            for tick in range(zm.start_min, zm.ende_min, RASTER_MIN):
                beteiligt = [
                    y[i][raum_id] for i, e in enumerate(ereignisse)
                    if raum_id in y.get(i, {}) and e.start <= tick < e.start + e.dauer
                ]
                if len(beteiligt) > 1:
                    model.AddAtMostOne(beteiligt)
        # W6: bisherige Räume behalten
        treffer = []
        for i, e in enumerate(ereignisse):
            alt = bestand.get(e.key)
            if alt is not None and alt.raum_id in y[i]:
                treffer.append(y[i][alt.raum_id])
                model.AddHint(y[i][alt.raum_id], 1)
        model.Maximize(sum(treffer))
        # Reines Matching auf fixierte Zeiten — deutlich einfacher als die
        # Phasen A/B, daher höchstens 30 s, bei kleinerem Budget entsprechend weniger.
        solver = _solver_konfigurieren(seed, timeout_s=min(budget, 30.0))
        solver.parameters.relative_gap_limit = 0.0
        if solver.Solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for i, e in enumerate(ereignisse):
                e.raum_id = next(rid for rid, v in y[i].items() if solver.Value(v))
            return

    # Rückfallebene: greedy, bestmöglich (Konflikte benennt der Validator)
    belegung: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for e in sorted(ereignisse, key=lambda e: (e.start, e.key)):
        fmt = konf.format(e.format_key)
        ende = e.start + e.dauer
        kandidaten = [
            r for r in sorted(kontext.raeume.values(), key=lambda r: r.raumnummer)
            if r.groesse == fmt.raumgroesse
            and r.verfuegbar(tag, e.start, ende)
            and all(not (e.start < b_ende and b_start < ende)
                    for b_start, b_ende in belegung[r.id])
        ]
        if kandidaten:
            e.raum_id = kandidaten[0].id
        else:
            ersatz = [r for r in kontext.raeume.values() if r.groesse == fmt.raumgroesse]
            e.raum_id = ersatz[0].id if ersatz else next(iter(kontext.raeume.values())).id
        belegung[e.raum_id].append((e.start, ende))


# ---------------------------------------------------------------------------
# Phase B: Prüfendenzuordnung
# ---------------------------------------------------------------------------

def _phase_b(
    kontext: PlanKontext,
    tag: Tag,
    ereignisse: list[_Ereignis],
    seed: int,
    timeout_s: float,
    bestand: dict[tuple, PlanZuweisung],
    kontakte_offset: dict[int, int],
    ziel_kontakte: dict[int, int],
    weich: bool = False,
) -> bool:
    """Weist Prüfende zu. ``weich=True`` relaxiert H1 und H3-min_senior mit
    hohen Strafgewichten (schrittweise Relaxierung statt Abbruch)."""
    konf = kontext.konfiguration
    gewichte = konf.gewichte
    model = cp_model.CpModel()
    STRAFE = 1_000_000

    verfuegbar = sorted(kontext.verfuegbare_pruefer(tag), key=lambda p: p.id)
    strafen = []

    z: dict[int, dict[int, cp_model.IntVar]] = {}
    for i, e in enumerate(ereignisse):
        fmt = konf.format(e.format_key)
        kandidaten = [
            p for p in verfuegbar
            # H4: nur Senior bei entsprechenden Formaten
            if not (fmt.nur_senior and p.ist_junior)
            # H2: Befangenheit ist niemals relaxierbar
            and not any((p.id, bid) in kontext.befangenheiten for bid in e.bewerber_ids)
        ]
        if len(kandidaten) < e.anzahl_pruefer:
            return False
        z[i] = {p.id: model.NewBoolVar(f"z_{i}_{p.id}") for p in kandidaten}
        # Vollständige Prüfergruppe je Ereignis (H7/Formatkonfiguration)
        model.Add(sum(z[i].values()) == e.anzahl_pruefer)

        # H3: Zusammensetzung der Prüfergruppen (Gruppenformate)
        if fmt.typ != "einzel":
            junioren = [z[i][p.id] for p in kandidaten if p.ist_junior]
            senioren = [z[i][p.id] for p in kandidaten if not p.ist_junior]
            if junioren:
                model.Add(sum(junioren) <= fmt.max_junior)
            if weich:
                slack = model.NewIntVar(0, fmt.min_senior, f"h3_{i}")
                model.Add(sum(senioren) + slack >= fmt.min_senior)
                strafen.append(STRAFE * slack)
            else:
                model.Add(sum(senioren) >= fmt.min_senior)

    # H5: keine Doppelbelegung je Prüfer:in (fixierte Zeiten ⇒ AtMostOne je Tick)
    zm = konf.zeitmodell
    for p in verfuegbar:
        for tick in range(zm.start_min, zm.ende_min, RASTER_MIN):
            beteiligt = [
                z[i][p.id] for i, e in enumerate(ereignisse)
                if p.id in z[i] and e.start <= tick < e.start + e.dauer
            ]
            if len(beteiligt) > 1:
                model.AddAtMostOne(beteiligt)

    # H1: keine Doppelbegegnung (über alle Formate; tagesübergreifend durch H7
    # strukturell ausgeschlossen, da Bewerbende nur einen Tag haben)
    nach_bewerber: dict[int, list[int]] = defaultdict(list)
    for i, e in enumerate(ereignisse):
        for bid in e.bewerber_ids:
            nach_bewerber[bid].append(i)
    for bid, indizes in nach_bewerber.items():
        for p in verfuegbar:
            beteiligt = [z[i][p.id] for i in indizes if p.id in z[i]]
            if len(beteiligt) > 1:
                if weich:
                    ueber = model.NewIntVar(0, len(beteiligt), f"h1_{bid}_{p.id}")
                    model.Add(sum(beteiligt) - ueber <= 1)
                    strafen.append(STRAFE * ueber)
                else:
                    model.AddAtMostOne(beteiligt)

    # W2: gleichmäßige Auslastung — Abweichung vom Zielwert (inkl. Lastvortrag
    # des anderen Tages) minimieren
    abweichungen = []
    max_kontakte = sum(len(e.bewerber_ids) * e.anzahl_pruefer for e in ereignisse)
    for p in verfuegbar:
        kontakte = sum(
            len(ereignisse[i].bewerber_ids) * z[i][p.id]
            for i in range(len(ereignisse)) if p.id in z[i]
        )
        ziel = max(0, ziel_kontakte.get(p.id, 0) - kontakte_offset.get(p.id, 0))
        dev = model.NewIntVar(0, max_kontakte, f"dev_{p.id}")
        model.Add(dev >= kontakte - ziel)
        model.Add(dev >= ziel - kontakte)
        abweichungen.append(dev)

    # W4: gemischte Prüfergruppen (Geschlecht) bei Gruppenformaten
    gemischt_bonus = []
    for i, e in enumerate(ereignisse):
        if konf.format(e.format_key).typ == "einzel":
            continue
        frauen = [z[i][pid] for pid in z[i]
                  if kontext.pruefer[pid].geschlecht == "w"]
        maenner = [z[i][pid] for pid in z[i]
                   if kontext.pruefer[pid].geschlecht == "m"]
        if not frauen or not maenner:
            continue
        gemischt = model.NewBoolVar(f"mix_{i}")
        model.Add(sum(frauen) >= 1).OnlyEnforceIf(gemischt)
        model.Add(sum(maenner) >= 1).OnlyEnforceIf(gemischt)
        gemischt_bonus.append(gemischt)

    # W6: Bestandserhalt der Prüfendenzuordnung
    bestand_treffer = []
    for i, e in enumerate(ereignisse):
        alt = bestand.get(e.key)
        if alt is None:
            continue
        for pid in alt.pruefer_ids:
            if pid in z[i]:
                bestand_treffer.append(z[i][pid])
                model.AddHint(z[i][pid], 1)

    model.Minimize(
        sum(strafen)
        + gewichte.w2_gleichverteilung * sum(abweichungen)
        - gewichte.w4_diversitaet_pruefer * sum(gemischt_bonus)
        - gewichte.w6_bestandserhalt * sum(bestand_treffer)
    )

    solver = _solver_konfigurieren(seed, timeout_s)
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return False
    for i, e in enumerate(ereignisse):
        e.pruefer_ids = frozenset(pid for pid, v in z[i].items() if solver.Value(v))
    return True


# ---------------------------------------------------------------------------
# Orchestrierung: beide Tage, Relaxierungs-Stufen, Kennzahlen
# ---------------------------------------------------------------------------

def berechnen(
    kontext: PlanKontext,
    bestand: Plan | None = None,
    fortschritt: Callable[[int, int, str], None] | None = None,
) -> SolverErgebnis:
    """Berechnet den Gesamtplan für beide Prüfungstage.

    ``bestand``: vorheriger Plan für minimalinvasive Neuberechnung (W6) —
    bestehende, weiterhin gültige Zuweisungen werden möglichst beibehalten.
    """
    konf: JahrgangsKonfiguration = kontext.konfiguration
    seed = konf.solver.seed
    beginn = time.monotonic()
    hinweise: list[str] = []
    relaxiert = False

    bestand_map: dict[tuple, PlanZuweisung] = {}
    if bestand is not None:
        for zw in bestand.zuweisungen:
            if zw.gruppe_id is not None:
                bestand_map[("gruppe", zw.gruppe_id, zw.format_key)] = zw
            elif len(zw.bewerber_ids) == 1:
                bid = next(iter(zw.bewerber_ids))
                bestand_map[("einzel", bid, zw.format_key)] = zw

    # W2-Ziel: Kontakte gleichmäßig über beide Tage (ca. 12 je Prüfer:in)
    alle_ereignisse = {tag: _ereignisse_bauen(kontext, tag) for tag in (Tag.FR, Tag.SA)}
    gesamt_kontakte = sum(
        len(e.bewerber_ids) * e.anzahl_pruefer
        for tage in alle_ereignisse.values() for e in tage
    )
    aktive_pruefer = [p for p in kontext.pruefer.values()
                      if p.verfuegbar(Tag.FR) or p.verfuegbar(Tag.SA)]
    ziel_gesamt = round(gesamt_kontakte / len(aktive_pruefer)) if aktive_pruefer else 0

    zuweisungen: list[PlanZuweisung] = []
    kontakte: dict[int, int] = defaultdict(int)
    schritt_budget = float(konf.solver.schritt_budget_sekunden)

    # Fortschritt: drei Schritte je Tag, der die Anzeige speist.
    TAGESNAME = {Tag.FR: "Freitag", Tag.SA: "Samstag"}
    zu_planen = [t for t in (Tag.FR, Tag.SA) if alle_ereignisse[t]]
    schritte_gesamt = len(zu_planen) * 3
    schritt_nr = 0

    def melden(tag: Tag, was: str) -> None:
        nonlocal schritt_nr
        schritt_nr += 1
        if fortschritt is not None:
            fortschritt(schritt_nr, schritte_gesamt, f"{TAGESNAME[tag]} · {was}")

    for tag in zu_planen:
        ereignisse = alle_ereignisse[tag]

        vorab = _diagnose(kontext, tag, ereignisse)
        if vorab:
            raise KeinPlanMoeglich(vorab)

        # Für Tag 1 ein Tagesziel, für Tag 2 den Rest zum Gesamtziel (Lastvortrag)
        if tag == Tag.FR:
            tages_kontakte = sum(len(e.bewerber_ids) * e.anzahl_pruefer for e in ereignisse)
            n = len(kontext.verfuegbare_pruefer(tag)) or 1
            ziel = {p.id: round(tages_kontakte / n) for p in kontext.verfuegbare_pruefer(tag)}
            offset: dict[int, int] = {}
        else:
            ziel = {p.id: ziel_gesamt for p in kontext.verfuegbare_pruefer(tag)}
            offset = dict(kontakte)

        # Phase A — mit Relaxierungs-Stufe (ohne Prüfer-Kapazitätsschranken)
        melden(tag, "Zeitplanung")
        if not _phase_a(kontext, tag, ereignisse, seed, schritt_budget, bestand_map):
            if not _phase_a(kontext, tag, ereignisse, seed, schritt_budget,
                            bestand_map, mit_pruefer_kapazitaet=False):
                raise KeinPlanMoeglich([Konflikt(
                    regel="H8",
                    meldung=(
                        f"Für den {tag.value} konnte kein überschneidungsfreier Zeitplan "
                        "im Tagesfenster gefunden werden. Zeitmodell (H8), Raum- (H6) "
                        "oder Prüfendenkapazität (H3/H4) prüfen."
                    ),
                )])
            relaxiert = True
            hinweise.append(
                f"{tag.value}: Zeitplanung ohne Prüfendenkapazitäts-Schranke gelöst — "
                "die Prüfendenzuordnung kann weiche Regelverletzungen enthalten."
            )

        melden(tag, "Raumvergabe")
        _raeume_zuweisen(kontext, tag, ereignisse, bestand_map, seed, schritt_budget)

        # Phase B — Relaxierungs-Stufe: H1/H3 weich mit hoher Strafe
        melden(tag, "Prüfendenzuordnung")
        if not _phase_b(kontext, tag, ereignisse, seed, schritt_budget,
                        bestand_map, offset, ziel):
            if not _phase_b(kontext, tag, ereignisse, seed, schritt_budget,
                            bestand_map, offset, ziel, weich=True):
                raise KeinPlanMoeglich([Konflikt(
                    regel="H1",
                    meldung=(
                        f"Für den {tag.value} konnte keine Prüfendenzuordnung gefunden "
                        "werden (H1/H2/H3/H4). Prüfendenliste und Befangenheiten prüfen."
                    ),
                )])
            relaxiert = True
            hinweise.append(
                f"{tag.value}: Prüfendenzuordnung nur mit Relaxierung von H1/H3 möglich — "
                "verletzte Regeln erscheinen in der Konfliktliste."
            )

        for e in ereignisse:
            for pid in e.pruefer_ids:
                kontakte[pid] += len(e.bewerber_ids)
            zuweisungen.append(PlanZuweisung(
                tag=tag, format_key=e.format_key, start_min=e.start,
                ende_min=e.start + e.dauer, raum_id=e.raum_id,
                bewerber_ids=e.bewerber_ids, pruefer_ids=e.pruefer_ids,
                gruppe_id=e.gruppe_id,
            ))

    plan = Plan(zuweisungen=zuweisungen)
    konflikte = plan_validieren(plan, kontext)  # Single Source of Truth (rules.py)
    kennzahlen = kennzahlen_berechnen(plan, kontext, plan_alt=bestand)
    laufzeit = time.monotonic() - beginn

    if konflikte:
        status = "relaxiert"
    elif relaxiert:
        status = "gueltig"
    else:
        status = "gueltig"
    return SolverErgebnis(
        plan=plan, kennzahlen=kennzahlen, konflikte=konflikte,
        status=status, laufzeit_sekunden=round(laufzeit, 1), hinweise=hinweise,
    )
