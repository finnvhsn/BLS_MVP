"""Fachliche Regeln H1–H9 und W1–W6 — die **einzige Quelle der Wahrheit**.

Jede harte Regel existiert genau einmal: als Prüf-Funktion (pure function)
über einem Plan. Genutzt von
  - validator.py (Konfliktliste F_OM_015, Live-Validierung F_OM_012/016),
  - solver.py (Constraint-Aufbau — die Zuordnung Constraint ↔ Regel-ID ist
    dort kommentiert; der Property-Test „jeder Solver-Output besteht den
    Validator" sichert die Übereinstimmung ab),
  - den automatisierten Tests (Kap. 11 AK2).

Weiche Regeln W1–W6 sind Metrik-Funktionen; sie speisen sowohl die
Zielfunktion des Solvers als auch das Kennzahlen-Reporting (AK8).

Dokumentation für Anwender: /docs/regeln.md (NF_010).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import pstdev
from typing import Callable

from ..db.models import Tag
from .konfiguration import JahrgangsKonfiguration, hhmm
from .plan import Plan, PlanKontext, PlanZuweisung


# ---------------------------------------------------------------------------
# Konflikt: benannte Regelverletzung (Kap. 4.3 — kein stiller Regelbruch)
# ---------------------------------------------------------------------------

@dataclass
class Konflikt:
    regel: str                       # "H1" … "H9"
    meldung: str                     # deutsche Begründung
    zuweisungen: list = field(default_factory=list)   # betroffene Plan-Indizes
    bewerber_ids: list = field(default_factory=list)
    pruefer_ids: list = field(default_factory=list)
    raum_id: int | None = None

    @property
    def titel(self) -> str:
        """Klartext-Titel der verletzten Regel — die UI zeigt ihn statt der ID."""
        regel = HARTE_REGELN.get(self.regel)
        return regel.titel if regel else self.regel

    def als_dict(self) -> dict:
        return {
            "regel": self.regel,
            "titel": self.titel,
            "meldung": self.meldung,
            "zuweisungen": self.zuweisungen,
            "bewerber_ids": self.bewerber_ids,
            "pruefer_ids": self.pruefer_ids,
            "raum_id": self.raum_id,
        }


PruefFunktion = Callable[[Plan, PlanKontext], list[Konflikt]]


@dataclass(frozen=True)
class Regel:
    id: str
    titel: str
    beschreibung: str
    pruefen: PruefFunktion


def _bname(kontext: PlanKontext, bid: int) -> str:
    b = kontext.bewerber.get(bid)
    return b.anzeigename if b else f"Bewerber:in #{bid}"


def _pname(kontext: PlanKontext, pid: int) -> str:
    p = kontext.pruefer.get(pid)
    return p.anzeigename if p else f"Prüfer:in #{pid}"


def _rname(kontext: PlanKontext, rid: int) -> str:
    r = kontext.raeume.get(rid)
    return r.raumnummer if r else f"Raum #{rid}"


# ---------------------------------------------------------------------------
# H1 — Keine Doppelbegegnung
# ---------------------------------------------------------------------------

def pruefe_h1(plan: Plan, kontext: PlanKontext) -> list[Konflikt]:
    """Eine prüfende Person prüft dieselbe bewerbende Person höchstens einmal
    (über alle Formate und beide Tage)."""
    begegnungen: dict[tuple, list[int]] = defaultdict(list)
    for i, z in enumerate(plan.zuweisungen):
        for pid in z.pruefer_ids:
            for bid in z.bewerber_ids:
                begegnungen[(pid, bid)].append(i)
    konflikte = []
    for (pid, bid), indizes in sorted(begegnungen.items()):
        if len(indizes) > 1:
            konflikte.append(Konflikt(
                regel="H1",
                meldung=(
                    f"Doppelbegegnung: {_pname(kontext, pid)} prüft "
                    f"{_bname(kontext, bid)} {len(indizes)}-mal."
                ),
                zuweisungen=indizes, bewerber_ids=[bid], pruefer_ids=[pid],
            ))
    return konflikte


# ---------------------------------------------------------------------------
# H2 — Befangenheit
# ---------------------------------------------------------------------------

def pruefe_h2(plan: Plan, kontext: PlanKontext) -> list[Konflikt]:
    """Als befangen hinterlegte Paarungen werden niemals zugewiesen."""
    konflikte = []
    for i, z in enumerate(plan.zuweisungen):
        for pid in sorted(z.pruefer_ids):
            for bid in sorted(z.bewerber_ids):
                if (pid, bid) in kontext.befangenheiten:
                    konflikte.append(Konflikt(
                        regel="H2",
                        meldung=(
                            f"Befangenheit: {_pname(kontext, pid)} darf "
                            f"{_bname(kontext, bid)} nicht prüfen."
                        ),
                        zuweisungen=[i], bewerber_ids=[bid], pruefer_ids=[pid],
                    ))
    return konflikte


# ---------------------------------------------------------------------------
# H3 — Prüfergruppen-Zusammensetzung (Gruppenformate)
# ---------------------------------------------------------------------------

def pruefe_h3(plan: Plan, kontext: PlanKontext) -> list[Konflikt]:
    """Bei Gruppenprüfungen max. 1 Junior und min. 2 Senior je Prüfergruppe
    (Grenzen je Format konfigurierbar, Default gem. Spec)."""
    konflikte = []
    for i, z in enumerate(plan.zuweisungen):
        fmt = kontext.konfiguration.format(z.format_key)
        if fmt.typ == "einzel":
            continue  # Einzelformate regelt H4
        junioren = [pid for pid in z.pruefer_ids if kontext.pruefer[pid].ist_junior]
        senioren = [pid for pid in z.pruefer_ids if not kontext.pruefer[pid].ist_junior]
        if len(junioren) > fmt.max_junior:
            konflikte.append(Konflikt(
                regel="H3",
                meldung=(
                    f"Prüfergruppe im Format „{fmt.name}“ hat {len(junioren)} Junior-"
                    f"Prüfende (erlaubt: max. {fmt.max_junior})."
                ),
                zuweisungen=[i], pruefer_ids=sorted(junioren),
            ))
        if len(senioren) < fmt.min_senior:
            konflikte.append(Konflikt(
                regel="H3",
                meldung=(
                    f"Prüfergruppe im Format „{fmt.name}“ hat nur {len(senioren)} Senior-"
                    f"Prüfende (erforderlich: min. {fmt.min_senior})."
                ),
                zuweisungen=[i], pruefer_ids=sorted(z.pruefer_ids),
            ))
    return konflikte


# ---------------------------------------------------------------------------
# H4 — Einzelgespräche nur Senior
# ---------------------------------------------------------------------------

def pruefe_h4(plan: Plan, kontext: PlanKontext) -> list[Konflikt]:
    """Junior-Prüfende werden keinen Einzelgesprächen zugewiesen
    (allgemein: Formaten mit ``nur_senior``)."""
    konflikte = []
    for i, z in enumerate(plan.zuweisungen):
        fmt = kontext.konfiguration.format(z.format_key)
        if not fmt.nur_senior:
            continue
        for pid in sorted(z.pruefer_ids):
            if kontext.pruefer[pid].ist_junior:
                konflikte.append(Konflikt(
                    regel="H4",
                    meldung=(
                        f"{_pname(kontext, pid)} (Junior) ist dem Format "
                        f"„{fmt.name}“ zugewiesen — nur Senior-Prüfende zulässig."
                    ),
                    zuweisungen=[i], pruefer_ids=[pid],
                ))
    return konflikte


# ---------------------------------------------------------------------------
# H5 — Keine Doppelbelegung (Personen & Räume), Verfügbarkeit von Personen
# ---------------------------------------------------------------------------

def _ueberschneidung(a: PlanZuweisung, b: PlanZuweisung) -> bool:
    return a.tag == b.tag and a.start_min < b.ende_min and b.start_min < a.ende_min


def pruefe_h5(plan: Plan, kontext: PlanKontext) -> list[Konflikt]:
    """Jede Person und jeder Raum ist je Zeitfenster nur genau einmal verplant;
    verplante Personen müssen am Tag verfügbar sein (überschneidungsfreier
    Tagesplan)."""
    konflikte = []

    def ueberschneidungen(indizes: list[int]) -> list[tuple[int, int]]:
        paare = []
        for a_pos, i in enumerate(indizes):
            for j in indizes[a_pos + 1:]:
                if _ueberschneidung(plan.zuweisungen[i], plan.zuweisungen[j]):
                    paare.append((i, j))
        return paare

    nach_bewerber: dict[int, list[int]] = defaultdict(list)
    nach_pruefer: dict[int, list[int]] = defaultdict(list)
    nach_raum: dict[int, list[int]] = defaultdict(list)
    for i, z in enumerate(plan.zuweisungen):
        for bid in z.bewerber_ids:
            nach_bewerber[bid].append(i)
        for pid in z.pruefer_ids:
            nach_pruefer[pid].append(i)
        nach_raum[z.raum_id].append(i)

    for bid, indizes in sorted(nach_bewerber.items()):
        for i, j in ueberschneidungen(indizes):
            z1, z2 = plan.zuweisungen[i], plan.zuweisungen[j]
            konflikte.append(Konflikt(
                regel="H5",
                meldung=(
                    f"Doppelbelegung: {_bname(kontext, bid)} ist am {z1.tag.value} "
                    f"{hhmm(z1.start_min)}–{hhmm(z1.ende_min)} und "
                    f"{hhmm(z2.start_min)}–{hhmm(z2.ende_min)} gleichzeitig verplant."
                ),
                zuweisungen=[i, j], bewerber_ids=[bid],
            ))
    for pid, indizes in sorted(nach_pruefer.items()):
        for i, j in ueberschneidungen(indizes):
            z1, z2 = plan.zuweisungen[i], plan.zuweisungen[j]
            konflikte.append(Konflikt(
                regel="H5",
                meldung=(
                    f"Doppelbelegung: {_pname(kontext, pid)} ist am {z1.tag.value} "
                    f"{hhmm(z1.start_min)}–{hhmm(z1.ende_min)} und "
                    f"{hhmm(z2.start_min)}–{hhmm(z2.ende_min)} gleichzeitig verplant."
                ),
                zuweisungen=[i, j], pruefer_ids=[pid],
            ))
    for rid, indizes in sorted(nach_raum.items()):
        for i, j in ueberschneidungen(indizes):
            z1 = plan.zuweisungen[i]
            konflikte.append(Konflikt(
                regel="H5",
                meldung=(
                    f"Doppelbelegung: Raum {_rname(kontext, rid)} ist am {z1.tag.value} "
                    f"im Zeitfenster {hhmm(max(z1.start_min, plan.zuweisungen[j].start_min))} "
                    f"doppelt belegt (je Raum und Zeitslot genau eine Prüfung)."
                ),
                zuweisungen=[i, j], raum_id=rid,
            ))

    # Verfügbarkeit der verplanten Personen (Absage/Einzeltag)
    for i, z in enumerate(plan.zuweisungen):
        for pid in sorted(z.pruefer_ids):
            if not kontext.pruefer[pid].verfuegbar(z.tag):
                konflikte.append(Konflikt(
                    regel="H5",
                    meldung=(
                        f"{_pname(kontext, pid)} ist am {z.tag.value} nicht verfügbar, "
                        f"aber um {hhmm(z.start_min)} verplant."
                    ),
                    zuweisungen=[i], pruefer_ids=[pid],
                ))
        for bid in sorted(z.bewerber_ids):
            if not kontext.bewerber[bid].planbar:
                konflikte.append(Konflikt(
                    regel="H5",
                    meldung=(
                        f"{_bname(kontext, bid)} ist verplant, nimmt aber nicht am "
                        "Verfahren teil (Absage/Rücksteller/nicht zugelassen)."
                    ),
                    zuweisungen=[i], bewerber_ids=[bid],
                ))
    return konflikte


# ---------------------------------------------------------------------------
# H6 — Raumeignung & -verfügbarkeit
# ---------------------------------------------------------------------------

def pruefe_h6(plan: Plan, kontext: PlanKontext) -> list[Konflikt]:
    """Zuweisung nur in verfügbare, formatgeeignete Räume (klein = Einzel,
    groß = Gruppenformate; Verfügbarkeit je Tag und Zeitfenster)."""
    konflikte = []
    for i, z in enumerate(plan.zuweisungen):
        fmt = kontext.konfiguration.format(z.format_key)
        raum = kontext.raeume.get(z.raum_id)
        if raum is None:
            konflikte.append(Konflikt(
                regel="H6", meldung=f"Unbekannter Raum #{z.raum_id}.",
                zuweisungen=[i], raum_id=z.raum_id,
            ))
            continue
        if raum.groesse != fmt.raumgroesse:
            konflikte.append(Konflikt(
                regel="H6",
                meldung=(
                    f"Raum {raum.raumnummer} ({raum.groesse.value}) ist für das Format "
                    f"„{fmt.name}“ ungeeignet (erfordert: {fmt.raumgroesse.value})."
                ),
                zuweisungen=[i], raum_id=z.raum_id,
            ))
        if not raum.verfuegbar(z.tag, z.start_min, z.ende_min):
            konflikte.append(Konflikt(
                regel="H6",
                meldung=(
                    f"Raum {raum.raumnummer} ist am {z.tag.value} "
                    f"{hhmm(z.start_min)}–{hhmm(z.ende_min)} nicht verfügbar."
                ),
                zuweisungen=[i], raum_id=z.raum_id,
            ))
    return konflikte


# ---------------------------------------------------------------------------
# H7 — Vollständigkeit & Tagesbindung
# ---------------------------------------------------------------------------

def pruefe_h7(plan: Plan, kontext: PlanKontext) -> list[Konflikt]:
    """Jede planbare Person wird ausschließlich an ihrem zugeteilten Tag geprüft
    und durchläuft dort **alle** konfigurierten Formate genau einmal."""
    konflikte = []
    format_keys = [f.key for f in kontext.konfiguration.formate]

    for i, z in enumerate(plan.zuweisungen):
        for bid in sorted(z.bewerber_ids):
            info = kontext.bewerber.get(bid)
            if info is not None and info.planbar and info.tag != z.tag:
                konflikte.append(Konflikt(
                    regel="H7",
                    meldung=(
                        f"{_bname(kontext, bid)} ist dem Tag {info.tag.value} zugeteilt "
                        f"(Access-Import), aber am {z.tag.value} verplant."
                    ),
                    zuweisungen=[i], bewerber_ids=[bid],
                ))

    for info in sorted(kontext.planbare_bewerber(), key=lambda b: b.id):
        zaehler = Counter(
            z.format_key for z in plan.fuer_bewerber(info.id)
        )
        for key in format_keys:
            fmt = kontext.konfiguration.format(key)
            anzahl = zaehler.get(key, 0)
            if anzahl == 0:
                konflikte.append(Konflikt(
                    regel="H7",
                    meldung=(
                        f"Unvollständig: {info.anzeigename} hat kein Prüfungsereignis "
                        f"im Format „{fmt.name}“."
                    ),
                    bewerber_ids=[info.id],
                ))
            elif anzahl > 1:
                konflikte.append(Konflikt(
                    regel="H7",
                    meldung=(
                        f"{info.anzeigename} ist {anzahl}-mal im Format „{fmt.name}“ "
                        "verplant (erwartet: genau einmal)."
                    ),
                    zuweisungen=[
                        i for i, z in enumerate(plan.zuweisungen)
                        if info.id in z.bewerber_ids and z.format_key == key
                    ],
                    bewerber_ids=[info.id],
                ))
    return konflikte


# ---------------------------------------------------------------------------
# H8 — Formatdauern & Zeitmodell
# ---------------------------------------------------------------------------

def pruefe_h8(plan: Plan, kontext: PlanKontext) -> list[Konflikt]:
    """Konfigurierte Formatdauern werden eingehalten; alle Slots liegen
    vollständig im Tagesfenster (Default 10:00–17:15). Der Thesenvortrag
    blockt alle Gruppenmitglieder für den gesamten Block (ein Ereignis mit
    voller Dauer und allen Mitgliedern)."""
    konflikte = []
    zm = kontext.konfiguration.zeitmodell
    for i, z in enumerate(plan.zuweisungen):
        fmt = kontext.konfiguration.format(z.format_key)
        if z.ende_min - z.start_min != fmt.dauer_min:
            konflikte.append(Konflikt(
                regel="H8",
                meldung=(
                    f"Format „{fmt.name}“ dauert {z.ende_min - z.start_min} min "
                    f"(konfiguriert: {fmt.dauer_min} min)."
                ),
                zuweisungen=[i],
            ))
        if z.start_min < zm.start_min or z.ende_min > zm.ende_min:
            konflikte.append(Konflikt(
                regel="H8",
                meldung=(
                    f"Zuweisung {hhmm(z.start_min)}–{hhmm(z.ende_min)} liegt außerhalb "
                    f"des Tagesfensters {zm.tag_start}–{zm.tag_ende}."
                ),
                zuweisungen=[i],
            ))
        if fmt.typ == "thesen" and z.gruppe_id is not None:
            gruppen_mitglieder = {
                b.id for b in kontext.bewerber.values()
                if b.gruppe_id == z.gruppe_id and b.planbar
            }
            fehlend = gruppen_mitglieder - set(z.bewerber_ids)
            if fehlend:
                konflikte.append(Konflikt(
                    regel="H8",
                    meldung=(
                        f"Thesenvortrag blockt nicht die gesamte Gruppe: "
                        f"{', '.join(_bname(kontext, b) for b in sorted(fehlend))} fehlt/fehlen im Block."
                    ),
                    zuweisungen=[i], bewerber_ids=sorted(fehlend),
                ))
    return konflikte


# ---------------------------------------------------------------------------
# H9 — Regeln gelten für jede Konstellation
# ---------------------------------------------------------------------------

def pruefe_h9(plan: Plan, kontext: PlanKontext) -> list[Konflikt]:
    """Prüfergruppen dürfen sich über den Tag ändern; H1–H4 gelten für jede
    Konstellation. Strukturell erzwungen: alle Prüfungen H1–H4 arbeiten je
    Prüfungsereignis (= je Konstellation), nie je „fester Gruppe“. Diese
    Regel erzeugt daher selbst keine eigenen Konflikte."""
    return []


HARTE_REGELN: dict[str, Regel] = {
    r.id: r for r in [
        Regel("H1", "Keine Doppelbegegnung",
              "Eine prüfende Person prüft dieselbe bewerbende Person höchstens einmal "
              "(über alle Formate und beide Tage).", pruefe_h1),
        Regel("H2", "Befangenheit",
              "Als befangen hinterlegte Paarungen werden niemals zugewiesen.", pruefe_h2),
        Regel("H3", "Prüfergruppen-Zusammensetzung",
              "Bei Gruppenprüfungen max. 1 Junior und min. 2 Senior je Prüfergruppe.", pruefe_h3),
        Regel("H4", "Einzelgespräche nur Senior",
              "Junior-Prüfende werden keinen Einzelgesprächen zugewiesen.", pruefe_h4),
        Regel("H5", "Keine Doppelbelegung",
              "Jede Person und jeder Raum ist je Zeitfenster nur genau einmal verplant; "
              "verplante Personen sind am Tag verfügbar.", pruefe_h5),
        Regel("H6", "Raumeignung & -verfügbarkeit",
              "Zuweisung nur in verfügbare, formatgeeignete Räume.", pruefe_h6),
        Regel("H7", "Vollständigkeit & Tagesbindung",
              "Jede planbare Person wird nur an ihrem zugeteilten Tag geprüft und "
              "durchläuft dort alle konfigurierten Formate.", pruefe_h7),
        Regel("H8", "Formatdauern & Zeitmodell",
              "Formatdauern und Tagesfenster werden eingehalten; der Thesenvortrag "
              "blockt die gesamte Gruppe.", pruefe_h8),
        Regel("H9", "Regeln je Konstellation",
              "H1–H4 gelten für jede Prüfergruppen-Konstellation.", pruefe_h9),
    ]
}


# ---------------------------------------------------------------------------
# Weiche Regeln W1–W6: Metriken (Zielfunktion + Reporting)
# ---------------------------------------------------------------------------

def w1_kontakte_je_bewerber(plan: Plan, kontext: PlanKontext) -> dict[int, int]:
    """W1: Anzahl unterschiedlicher Prüfender je planbarer bewerbender Person
    (Ideal: Summe der Prüfergruppengrößen aller Formate, Default 8)."""
    ergebnis = {}
    for info in kontext.planbare_bewerber():
        pruefer: set[int] = set()
        for z in plan.fuer_bewerber(info.id):
            pruefer.update(z.pruefer_ids)
        ergebnis[info.id] = len(pruefer)
    return ergebnis


def w1_zielwert(kontext: PlanKontext) -> int:
    return sum(f.anzahl_pruefer for f in kontext.konfiguration.formate)


def w2_auslastung_je_pruefer(plan: Plan, kontext: PlanKontext) -> dict[int, int]:
    """W2: Anzahl unterschiedlicher Bewerbender je Prüfer:in (Ziel ~12,
    möglichst gleichmäßig)."""
    ergebnis = {p.id: 0 for p in kontext.pruefer.values() if p.aktiv}
    gesehen: dict[int, set] = defaultdict(set)
    for z in plan.zuweisungen:
        for pid in z.pruefer_ids:
            gesehen[pid].update(z.bewerber_ids)
    for pid, bewerber in gesehen.items():
        ergebnis[pid] = len(bewerber)
    return ergebnis


def w3_diversitaet_gruppe(mitglieder: list, kontext: PlanKontext) -> float:
    """W3: Diversitäts-Score einer Bewerbendengruppe (0 = homogen, 1 = maximal
    gemischt) über Geschlecht und Studiengang."""
    if len(mitglieder) < 2:
        return 1.0

    def mischung(werte: list[str]) -> float:
        zaehler = Counter(werte)
        haeufigster = zaehler.most_common(1)[0][1]
        # 1.0, wenn keine Ausprägung dominiert; 0.0, wenn alle gleich sind
        return (len(werte) - haeufigster) / (len(werte) - len(werte) // 2)

    geschlechter = [kontext.bewerber[b].geschlecht for b in mitglieder]
    studiengaenge = [kontext.bewerber[b].studiengang for b in mitglieder]
    return (min(1.0, mischung(geschlechter)) + min(1.0, mischung(studiengaenge))) / 2


def w4_diversitaet_pruefergruppen(plan: Plan, kontext: PlanKontext) -> float:
    """W4: Anteil der Gruppenformat-Ereignisse mit gemischter Prüfergruppe
    (mind. zwei Geschlechter)."""
    relevante = [
        z for z in plan.zuweisungen
        if kontext.konfiguration.format(z.format_key).typ != "einzel" and len(z.pruefer_ids) >= 2
    ]
    if not relevante:
        return 1.0
    gemischt = sum(
        1 for z in relevante
        if len({kontext.pruefer[p].geschlecht for p in z.pruefer_ids}) >= 2
    )
    return gemischt / len(relevante)


def w5_wartezeiten(plan: Plan, kontext: PlanKontext) -> dict[int, int]:
    """W5: Wartezeit in Minuten je bewerbender Person zwischen erster und
    letzter Prüfung (Lücken abzüglich des konfigurierten Puffers)."""
    puffer = kontext.konfiguration.zeitmodell.puffer_min
    ergebnis = {}
    for info in kontext.planbare_bewerber():
        ereignisse = sorted(plan.fuer_bewerber(info.id), key=lambda z: z.start_min)
        wartezeit = 0
        for vorher, nachher in zip(ereignisse, ereignisse[1:]):
            luecke = nachher.start_min - vorher.ende_min
            wartezeit += max(0, luecke - puffer)
        ergebnis[info.id] = wartezeit
    return ergebnis


def w6_stabilitaet(plan_neu: Plan, plan_alt: Plan) -> dict:
    """W6: Vergleich zweier Pläne — wie viele Zuweisungen blieben erhalten?"""
    alt = {z.schluessel for z in plan_alt.zuweisungen}
    neu = {z.schluessel for z in plan_neu.zuweisungen}
    return {
        "erhalten": len(alt & neu),
        "entfallen": len(alt - neu),
        "neu": len(neu - alt),
    }


def kennzahlen_berechnen(plan: Plan, kontext: PlanKontext, plan_alt: Plan | None = None) -> dict:
    """Qualitätskennzahlen für Protokoll und UI (AK8: W1/W2-Abweichungen und
    Wartezeiten werden ausgewiesen)."""
    w1 = w1_kontakte_je_bewerber(plan, kontext)
    ziel = w1_zielwert(kontext)
    w2 = w2_auslastung_je_pruefer(plan, kontext)
    w5 = w5_wartezeiten(plan, kontext)
    w2_werte = [n for n in w2.values()]
    kennzahlen = {
        "w1_zielwert": ziel,
        "w1_erfuellt": sum(1 for n in w1.values() if n >= ziel),
        "w1_abweichler": {
            str(bid): n for bid, n in sorted(w1.items()) if n < ziel
        },
        "w2_durchschnitt": round(sum(w2_werte) / len(w2_werte), 1) if w2_werte else 0,
        "w2_min": min(w2_werte, default=0),
        "w2_max": max(w2_werte, default=0),
        "w2_streuung": round(pstdev(w2_werte), 1) if len(w2_werte) > 1 else 0.0,
        "w4_gemischte_pruefergruppen": round(w4_diversitaet_pruefergruppen(plan, kontext), 2),
        "w5_wartezeit_summe_min": sum(w5.values()),
        "w5_wartezeit_max_min": max(w5.values(), default=0),
        "w5_wartezeit_je_bewerber": {str(k): v for k, v in sorted(w5.items())},
        "anzahl_zuweisungen": len(plan.zuweisungen),
        "anzahl_geplante_bewerber": len(kontext.planbare_bewerber()),
    }
    if plan_alt is not None:
        kennzahlen["w6_stabilitaet"] = w6_stabilitaet(plan, plan_alt)
    return kennzahlen
