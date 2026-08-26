"""Planung: Gruppeneinteilung (F_OM_006), Berechnung (F_OM_007/011),
Planungsansicht (F_OM_014), Konflikte (F_OM_015), Umbuchung (F_OM_012/016)."""

from __future__ import annotations

import threading
import time
from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, delete, func, select

from ..core import grouping, solver
from ..core.konfiguration import hhmm, minuten
from ..core.plan import Plan, PlanZuweisung, kontext_aus_db, plan_aus_db, plan_speichern
from ..core.protokoll import protokollieren
from ..core.security import aktueller_benutzer
from ..core.validator import aenderung_validieren, plan_validieren
from ..db.database import engine, get_session
from ..db.models import (
    Benutzer,
    Bewerber,
    Gruppe,
    Planungsstand,
    PlanungsstandTyp,
    Tag,
    Zuweisung,
    ZuweisungBewerber,
    ZuweisungPruefer,
)
from .jahrgaenge import jahrgang_laden, konfiguration_laden

router = APIRouter(
    prefix="/api/jahrgaenge/{jahrgang_id}", tags=["Planung"],
    dependencies=[Depends(aktueller_benutzer)],
)

# Laufende Berechnungen je Jahrgang (In-Process; ein Nutzerkreis, NF_002)
_laeufe: dict[int, dict] = {}
_lauf_sperre = threading.Lock()


def berechnung_laeuft(jahrgang_id: int) -> bool:
    """Rechnet gerade ein Solver-Lauf an diesem Jahrgang? Wer die Datenbasis
    unter einem laufenden Lauf wegzieht, lässt ihn beim Speichern in einen
    Fremdschlüsselfehler laufen — Aufrufer müssen das abfangen."""
    with _lauf_sperre:
        return _laeufe.get(jahrgang_id, {}).get("status") == "laeuft"


# ---------------------------------------------------------------------------
# Gruppeneinteilung (Stufe 1)
# ---------------------------------------------------------------------------

class EinteilungsDaten(BaseModel):
    seed: int | None = None  # None ⇒ Seed aus der Konfiguration


@router.post("/gruppen/einteilen")
def gruppen_einteilen(
    jahrgang_id: int, daten: EinteilungsDaten,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    """Zufallsbasierte, diverse Gruppeneinteilung — eigenständig wiederholbar
    (jeder Aufruf mit anderem Seed mischt neu)."""
    jahrgang_laden(session, jahrgang_id)
    konfiguration = konfiguration_laden(session, jahrgang_id)
    kontext = kontext_aus_db(session, jahrgang_id, konfiguration)
    seed = daten.seed if daten.seed is not None else konfiguration.solver.seed
    einteilung = grouping.gruppen_einteilen(kontext, seed=seed)

    # Bestehende Gruppen ersetzen
    session.exec(delete(Gruppe).where(Gruppe.jahrgang_id == jahrgang_id))
    for b in session.exec(select(Bewerber).where(Bewerber.jahrgang_id == jahrgang_id)):
        b.gruppe_id = None
        session.add(b)
    session.flush()
    for tag, gruppen in einteilung.items():
        for nummer, mitglieder in enumerate(gruppen, start=1):
            gruppe = Gruppe(jahrgang_id=jahrgang_id, tag=tag, nummer=nummer)
            session.add(gruppe)
            session.flush()
            for bid in mitglieder:
                bewerber = session.get(Bewerber, bid)
                bewerber.gruppe_id = gruppe.id
                session.add(bewerber)
    session.commit()
    protokollieren(session, "Gruppen eingeteilt", benutzer=benutzer.benutzername,
                   jahrgang_id=jahrgang_id, seed=seed,
                   gruppen_fr=len(einteilung[Tag.FR]), gruppen_sa=len(einteilung[Tag.SA]))
    return {"gruppen_fr": len(einteilung[Tag.FR]), "gruppen_sa": len(einteilung[Tag.SA]),
            "seed": seed}


@router.get("/gruppen")
def gruppen_liste(jahrgang_id: int, session: Session = Depends(get_session)):
    jahrgang_laden(session, jahrgang_id)
    bewerber = list(session.exec(
        select(Bewerber).where(Bewerber.jahrgang_id == jahrgang_id)
    ))
    ergebnis = []
    for g in session.exec(
        select(Gruppe).where(Gruppe.jahrgang_id == jahrgang_id).order_by(Gruppe.tag, Gruppe.nummer)
    ):
        mitglieder = [
            {"id": b.id, "name": b.name, "vorname": b.vorname,
             "geschlecht": b.geschlecht, "studiengang": b.studiengang}
            for b in bewerber if b.gruppe_id == g.id
        ]
        ergebnis.append({
            "id": g.id, "tag": g.tag, "nummer": g.nummer,
            "bezeichnung": f"Gruppe {g.tag.value}-{g.nummer:02d}",
            "mitglieder": mitglieder,
        })
    return ergebnis


class VerschiebeDaten(BaseModel):
    bewerber_id: int
    gruppe_id: int


@router.post("/gruppen/verschieben")
def gruppe_verschieben(
    jahrgang_id: int, daten: VerschiebeDaten,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    """Manuelle Nachjustierung der Gruppeneinteilung (F_OM_006 AK)."""
    b = session.get(Bewerber, daten.bewerber_id)
    g = session.get(Gruppe, daten.gruppe_id)
    if b is None or b.jahrgang_id != jahrgang_id:
        raise HTTPException(status_code=404, detail="Bewerber:in nicht gefunden.")
    if g is None or g.jahrgang_id != jahrgang_id:
        raise HTTPException(status_code=404, detail="Gruppe nicht gefunden.")
    if g.tag != b.tag:
        raise HTTPException(
            status_code=422,
            detail=f"Gruppe {g.nummer} gehört zum Tag {g.tag.value}, "
                   f"{b.vorname} {b.name} ist aber dem Tag {b.tag.value} zugeteilt (H7).",
        )
    b.gruppe_id = g.id
    session.add(b)
    session.commit()
    protokollieren(session, "Gruppenzuordnung geändert", benutzer=benutzer.benutzername,
                   jahrgang_id=jahrgang_id, bewerber=b.import_key or b.id,
                   gruppe=f"{g.tag.value}-{g.nummer:02d}")
    return {"status": "gespeichert"}


# ---------------------------------------------------------------------------
# Berechnung (Vollberechnung & minimalinvasive Neuberechnung)
# ---------------------------------------------------------------------------

class BerechnungsDaten(BaseModel):
    neuberechnung: bool = True   # letzten Planungsstand als Bestand erhalten (W6)
    synchron: bool = False       # True: blockierend (Tests/Skripte)


def _letzter_planungsstand(session: Session, jahrgang_id: int) -> Planungsstand | None:
    # Zweitschlüssel id: bei gleicher Versionsnummer entscheidet der jüngere
    # Datensatz, sonst wäre "der aktuelle Plan" von der Sortierlaune der
    # Datenbank abhängig.
    return session.exec(
        select(Planungsstand).where(Planungsstand.jahrgang_id == jahrgang_id)
        .order_by(Planungsstand.version.desc(), Planungsstand.id.desc())
    ).first()


def _naechste_version(session: Session, jahrgang_id: int) -> int:
    """Fortlaufend je Jahrgang — auch für Vollberechnungen, die keinen Bestand
    erben. Andernfalls bekäme jede Vollberechnung erneut die Version 1 und der
    Jahrgang hätte mehrere gleich nummerierte Stände."""
    hoechste = session.exec(
        select(func.max(Planungsstand.version))
        .where(Planungsstand.jahrgang_id == jahrgang_id)
    ).one()
    return (hoechste or 0) + 1


def _berechnung_ausfuehren(jahrgang_id: int, neuberechnung: bool, benutzername: str) -> None:
    with Session(engine()) as session:
        try:
            konfiguration = konfiguration_laden(session, jahrgang_id)
            kontext = kontext_aus_db(session, jahrgang_id, konfiguration)
            kontext = grouping.gruppen_auffuellen(kontext)  # Nachrücker (Szenario 3)

            bestand_stand = _letzter_planungsstand(session, jahrgang_id) if neuberechnung else None
            bestand = plan_aus_db(session, bestand_stand.id) if bestand_stand else None

            def fortschritt_melden(nr: int, gesamt: int, text: str) -> None:
                """Schreibt den aktuellen Solver-Schritt in den Laufstatus, damit
                die Ansicht während der Minuten Wartezeit zeigt, woran gerade
                gerechnet wird. Die Startmarke bleibt dabei erhalten."""
                with _lauf_sperre:
                    lauf = _laeufe.get(jahrgang_id)
                    if lauf is not None and lauf.get("status") == "laeuft":
                        lauf["schritt"] = nr
                        lauf["schritte_gesamt"] = gesamt
                        lauf["schritt_text"] = text

            ergebnis = solver.berechnen(kontext, bestand=bestand,
                                        fortschritt=fortschritt_melden)

            # Neue Gruppen aus gruppen_auffuellen persistieren
            for gid, ginfo in kontext.gruppen.items():
                if session.get(Gruppe, gid) is None:
                    session.add(Gruppe(id=gid, jahrgang_id=jahrgang_id,
                                       tag=ginfo.tag, nummer=ginfo.nummer))
            for bid, info in kontext.bewerber.items():
                zeile = session.get(Bewerber, bid)
                if zeile is not None and zeile.gruppe_id != info.gruppe_id:
                    zeile.gruppe_id = info.gruppe_id
                    session.add(zeile)
            session.flush()

            version = _naechste_version(session, jahrgang_id)
            stand = Planungsstand(
                jahrgang_id=jahrgang_id, version=version,
                typ=PlanungsstandTyp.NEUBERECHNUNG if bestand else PlanungsstandTyp.VOLLBERECHNUNG,
                basis_planungsstand_id=bestand_stand.id if bestand_stand else None,
                seed=konfiguration.solver.seed,
                parameter=konfiguration.model_dump(),
                kennzahlen=ergebnis.kennzahlen,
                konflikte=[k.als_dict() for k in ergebnis.konflikte],
            )
            session.add(stand)
            session.flush()
            plan_speichern(session, stand.id, ergebnis.plan)
            protokollieren(
                session, "Berechnung abgeschlossen", benutzer=benutzername,
                jahrgang_id=jahrgang_id, version=version, status=ergebnis.status,
                laufzeit_sekunden=ergebnis.laufzeit_sekunden,
                konflikte=len(ergebnis.konflikte), hinweise=ergebnis.hinweise,
            )
            with _lauf_sperre:
                _laeufe[jahrgang_id] = {
                    "status": "fertig", "planungsstand_id": stand.id, "version": version,
                    "solver_status": ergebnis.status,
                    "laufzeit_sekunden": ergebnis.laufzeit_sekunden,
                    "konflikte": len(ergebnis.konflikte), "hinweise": ergebnis.hinweise,
                }
        except solver.KeinPlanMoeglich as e:
            protokollieren(session, "Berechnung nicht möglich", benutzer=benutzername,
                           jahrgang_id=jahrgang_id,
                           konflikte=[k.als_dict() for k in e.konflikte])
            with _lauf_sperre:
                _laeufe[jahrgang_id] = {
                    "status": "unloesbar",
                    "konflikte": [k.als_dict() for k in e.konflikte],
                }
        except Exception as e:  # pragma: no cover - Schutznetz
            with _lauf_sperre:
                _laeufe[jahrgang_id] = {"status": "fehler", "meldung": str(e)}


@router.post("/berechnen")
def berechnen(
    jahrgang_id: int, daten: BerechnungsDaten,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    jahrgang_laden(session, jahrgang_id)
    with _lauf_sperre:
        if _laeufe.get(jahrgang_id, {}).get("status") == "laeuft":
            raise HTTPException(status_code=409, detail="Es läuft bereits eine Berechnung für diesen Jahrgang.")
        # Startzeit serverseitig festhalten: nur so zeigt die Laufzeit auch nach
        # einem Reload oder Tabwechsel den echten Wert statt wieder bei 0 zu beginnen.
        _laeufe[jahrgang_id] = {"status": "laeuft", "gestartet_um": time.monotonic()}
    protokollieren(session, "Berechnung gestartet", benutzer=benutzer.benutzername,
                   jahrgang_id=jahrgang_id, neuberechnung=daten.neuberechnung)
    if daten.synchron:
        _berechnung_ausfuehren(jahrgang_id, daten.neuberechnung, benutzer.benutzername)
    else:
        threading.Thread(
            target=_berechnung_ausfuehren,
            args=(jahrgang_id, daten.neuberechnung, benutzer.benutzername),
            daemon=True,
        ).start()
    with _lauf_sperre:
        return _lauf_als_dict(_laeufe[jahrgang_id])


def _lauf_als_dict(lauf: dict) -> dict:
    """Nach außen: statt der internen Startmarke die bisherige Laufzeit.
    Für abgeschlossene Läufe steht dort bereits die gemessene Solver-Zeit."""
    d = dict(lauf)
    gestartet = d.pop("gestartet_um", None)
    if gestartet is not None:
        d["laufzeit_sekunden"] = round(time.monotonic() - gestartet, 1)
    return d


@router.get("/berechnen/status")
def berechnungs_status(jahrgang_id: int):
    with _lauf_sperre:
        return _lauf_als_dict(_laeufe.get(jahrgang_id, {"status": "keine"}))


# ---------------------------------------------------------------------------
# Planungsstände & Planungsansicht
# ---------------------------------------------------------------------------

@router.get("/planungsstaende")
def planungsstaende(jahrgang_id: int, session: Session = Depends(get_session)):
    jahrgang_laden(session, jahrgang_id)
    return [
        {"id": p.id, "version": p.version, "typ": p.typ, "erstellt_am": p.erstellt_am,
         "seed": p.seed, "kennzahlen": p.kennzahlen}
        for p in session.exec(
            select(Planungsstand).where(Planungsstand.jahrgang_id == jahrgang_id)
            .order_by(Planungsstand.version.desc())
        )
    ]


def _stand_laden(session: Session, jahrgang_id: int, stand_id: int | None) -> Planungsstand:
    if stand_id is None:
        stand = _letzter_planungsstand(session, jahrgang_id)
    else:
        stand = session.get(Planungsstand, stand_id)
        if stand is not None and stand.jahrgang_id != jahrgang_id:
            stand = None
    if stand is None:
        raise HTTPException(status_code=404, detail="Kein Planungsstand vorhanden — zuerst berechnen.")
    return stand


@router.get("/plan")
def plan_ansicht(
    jahrgang_id: int,
    stand_id: int | None = None,
    session: Session = Depends(get_session),
):
    """Planungsansicht (F_OM_014): Zuweisungen + Konflikte + Kennzahlen.

    Konflikte werden gegen den AKTUELLEN Datenstand berechnet — nachträgliche
    Datenänderungen (Absagen, Befangenheiten) werden sofort sichtbar (F_OM_015).
    """
    stand = _stand_laden(session, jahrgang_id, stand_id)
    konfiguration = konfiguration_laden(session, jahrgang_id)
    kontext = kontext_aus_db(session, jahrgang_id, konfiguration)
    plan = plan_aus_db(session, stand.id)
    konflikte = plan_validieren(plan, kontext)

    konflikt_zuweisungen: set[int] = set()
    konflikte_json = []
    for k in konflikte:
        db_ids = [plan.zuweisungen[i].db_id for i in k.zuweisungen]
        konflikt_zuweisungen.update(db_ids)
        konflikte_json.append({**k.als_dict(), "zuweisungen": db_ids})

    zuweisungen_json = []
    for z in plan.zuweisungen:
        fmt = konfiguration.format(z.format_key)
        raum = kontext.raeume.get(z.raum_id)
        gruppe = kontext.gruppen.get(z.gruppe_id) if z.gruppe_id else None
        zuweisungen_json.append({
            "id": z.db_id, "tag": z.tag, "format_key": z.format_key,
            "format_name": fmt.name, "format_typ": fmt.typ,
            "start": hhmm(z.start_min), "ende": hhmm(z.ende_min),
            "start_min": z.start_min, "ende_min": z.ende_min,
            "raum_id": z.raum_id,
            "raumnummer": raum.raumnummer if raum else str(z.raum_id),
            "gruppe": gruppe.bezeichnung if gruppe else None,
            "gruppe_id": z.gruppe_id,
            "manuell_geaendert": z.manuell_geaendert,
            "konflikt": z.db_id in konflikt_zuweisungen,
            "bewerber": [
                {"id": bid, "name": kontext.bewerber[bid].anzeigename}
                for bid in sorted(z.bewerber_ids) if bid in kontext.bewerber
            ],
            "pruefer": [
                {"id": pid, "name": kontext.pruefer[pid].anzeigename,
                 "status": kontext.pruefer[pid].status}
                for pid in sorted(z.pruefer_ids) if pid in kontext.pruefer
            ],
        })

    return {
        "planungsstand": {
            "id": stand.id, "version": stand.version, "typ": stand.typ,
            "erstellt_am": stand.erstellt_am, "kennzahlen": stand.kennzahlen,
        },
        "zeitmodell": {
            "start_min": konfiguration.zeitmodell.start_min,
            "ende_min": konfiguration.zeitmodell.ende_min,
        },
        "zuweisungen": zuweisungen_json,
        "konflikte": konflikte_json,
        "raeume": [
            {"id": r.id, "raumnummer": r.raumnummer, "groesse": r.groesse, "aktiv": r.aktiv}
            for r in sorted(kontext.raeume.values(), key=lambda r: r.raumnummer)
        ],
    }


# ---------------------------------------------------------------------------
# Umbuchung mit Live-Validierung (F_OM_012; erfüllt F_OM_016 als Dialog)
# ---------------------------------------------------------------------------

class UmbuchungsDaten(BaseModel):
    zuweisung_id: int
    raum_id: int | None = None
    start: str | None = None            # "HH:MM"
    pruefer_ids: list[int] | None = None
    bestaetigt: bool = False            # bewusste Bestätigung bei Regelverstoß


@router.post("/umbuchen")
def umbuchen(
    jahrgang_id: int, daten: UmbuchungsDaten,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    """Manuelle Nachbearbeitung: Was-wäre-wenn-Validierung, Übernahme nur wenn
    regelkonform ODER bewusst bestätigt; jede Übernahme erzeugt einen neuen,
    versionierten Planungsstand (NF_010) und wird protokolliert (F_OM_012)."""
    stand = _stand_laden(session, jahrgang_id, None)
    konfiguration = konfiguration_laden(session, jahrgang_id)
    kontext = kontext_aus_db(session, jahrgang_id, konfiguration)
    plan = plan_aus_db(session, stand.id)

    index = next(
        (i for i, z in enumerate(plan.zuweisungen) if z.db_id == daten.zuweisung_id), None
    )
    if index is None:
        raise HTTPException(status_code=404, detail="Zuweisung nicht gefunden (nur der aktuelle Planungsstand ist änderbar).")

    alt = plan.zuweisungen[index]
    aenderungen: dict = {"manuell_geaendert": True}
    if daten.raum_id is not None:
        aenderungen["raum_id"] = daten.raum_id
    if daten.start is not None:
        try:
            start_min = minuten(daten.start)
        except (ValueError, IndexError):
            raise HTTPException(status_code=422, detail=f"Ungültige Uhrzeit {daten.start!r} — erwartet HH:MM.")
        aenderungen["start_min"] = start_min
        aenderungen["ende_min"] = start_min + (alt.ende_min - alt.start_min)
    if daten.pruefer_ids is not None:
        unbekannt = [p for p in daten.pruefer_ids if p not in kontext.pruefer]
        if unbekannt:
            raise HTTPException(status_code=422, detail=f"Unbekannte Prüfer-IDs: {unbekannt}.")
        aenderungen["pruefer_ids"] = frozenset(daten.pruefer_ids)

    neu = replace(alt, **aenderungen)
    konflikte = aenderung_validieren(plan, kontext, index, neu)
    konflikte_json = [k.als_dict() for k in konflikte]

    if konflikte and not daten.bestaetigt:
        # F_OM_016: nicht regelkonforme Änderung nur nach bewusster Bestätigung
        return {"uebernommen": False, "konflikte": konflikte_json}

    # Übernahme: neuer, versionierter Planungsstand (Kopie mit Änderung)
    neuer_plan = plan.ersetzt(index, neu)
    stand_neu = Planungsstand(
        jahrgang_id=jahrgang_id, version=stand.version + 1,
        typ=PlanungsstandTyp.MANUELL, basis_planungsstand_id=stand.id,
        seed=stand.seed, parameter=stand.parameter,
        kennzahlen=stand.kennzahlen, konflikte=konflikte_json,
    )
    session.add(stand_neu)
    session.flush()
    plan_speichern(session, stand_neu.id, Plan(zuweisungen=[
        replace(z, db_id=None) for z in neuer_plan.zuweisungen
    ]))
    protokollieren(
        session, "Umbuchung", benutzer=benutzer.benutzername, jahrgang_id=jahrgang_id,
        zuweisung=daten.zuweisung_id, neue_version=stand_neu.version,
        raum_id=daten.raum_id, start=daten.start, pruefer_ids=daten.pruefer_ids,
        trotz_konflikt=bool(konflikte),
    )
    return {
        "uebernommen": True, "planungsstand_id": stand_neu.id,
        "version": stand_neu.version, "konflikte": konflikte_json,
    }
