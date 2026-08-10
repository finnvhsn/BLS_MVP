"""Stammdaten: CSV-Import, Ansicht und manuelle Nachpflege
(F_OM_001–003, F_OM_009)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from ..core.protokoll import protokollieren
from ..core.security import aktueller_benutzer
from ..db.database import get_session
from ..db.models import (
    Befangenheit,
    Benutzer,
    Bewerber,
    Geschlecht,
    Pruefer,
    Raum,
    Raumgroesse,
)
from ..io import importer
from .jahrgaenge import jahrgang_laden

router = APIRouter(
    prefix="/api/jahrgaenge/{jahrgang_id}", tags=["Stammdaten"],
    dependencies=[Depends(aktueller_benutzer)],
)

IMPORTER = {
    "bewerbende": importer.bewerbende_importieren,
    "pruefende": importer.pruefende_importieren,
    "raeume": importer.raeume_importieren,
    "befangenheiten": importer.befangenheiten_importieren,
}


@router.post("/import/{typ}")
async def csv_import(
    jahrgang_id: int,
    typ: str,
    datei: UploadFile,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    """CSV-Import mit Formatvalidierung; wiederholter Import (Re-Import) ist
    ausdrücklich vorgesehen (F_OM_001 AK3)."""
    jahrgang_laden(session, jahrgang_id)
    if typ not in IMPORTER:
        raise HTTPException(status_code=404, detail=f"Unbekannter Import-Typ {typ!r}.")
    inhalt = await datei.read()
    ergebnis = IMPORTER[typ](session, jahrgang_id, inhalt)
    protokollieren(
        session, f"Import {ergebnis.typ}", benutzer=benutzer.benutzername,
        jahrgang_id=jahrgang_id, datei=datei.filename,
        neu=ergebnis.anzahl_neu, aktualisiert=ergebnis.anzahl_aktualisiert,
        fehler=len(ergebnis.fehler),
    )
    return ergebnis.als_dict()


# ---------------------------------------------------------------------------
# Ansicht & manuelle Nachpflege
# ---------------------------------------------------------------------------

@router.get("/bewerbende")
def bewerbende(jahrgang_id: int, session: Session = Depends(get_session)):
    jahrgang_laden(session, jahrgang_id)
    return [
        {
            "id": b.id, "import_key": b.import_key, "name": b.name, "vorname": b.vorname,
            "tag": b.tag, "geschlecht": b.geschlecht, "studiengang": b.studiengang,
            "ruecksteller": b.ruecksteller_kennzeichen, "rangfolge": b.rangfolge,
            "rueckmeldestatus": b.rueckmeldestatus, "zugelassen": b.zugelassen,
            "aktiv": b.aktiv, "gruppe_id": b.gruppe_id,
            "planbar": b.zugelassen and b.aktiv and b.rueckmeldestatus == "Zusage",
        }
        for b in session.exec(
            select(Bewerber).where(Bewerber.jahrgang_id == jahrgang_id).order_by(Bewerber.name)
        )
    ]


class BewerberAenderung(BaseModel):
    aktiv: bool | None = None
    rueckmeldestatus: str | None = None


@router.patch("/bewerbende/{bewerber_id}")
def bewerber_aendern(
    jahrgang_id: int, bewerber_id: int, daten: BewerberAenderung,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    """Kurzfristige Absagen/Änderungen (Änderungsszenario 2/3)."""
    b = session.get(Bewerber, bewerber_id)
    if b is None or b.jahrgang_id != jahrgang_id:
        raise HTTPException(status_code=404, detail="Bewerber:in nicht gefunden.")
    if daten.aktiv is not None:
        b.aktiv = daten.aktiv
    if daten.rueckmeldestatus is not None:
        try:
            b.rueckmeldestatus = type(b.rueckmeldestatus)(daten.rueckmeldestatus)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Ungültiger Rückmeldestatus {daten.rueckmeldestatus!r}.")
    session.add(b)
    session.commit()
    protokollieren(session, "Bewerber:in geändert", benutzer=benutzer.benutzername,
                   jahrgang_id=jahrgang_id, bewerber=b.import_key or b.id,
                   **daten.model_dump(exclude_none=True))
    return {"status": "gespeichert"}


@router.get("/pruefende")
def pruefende(jahrgang_id: int, session: Session = Depends(get_session)):
    jahrgang_laden(session, jahrgang_id)
    return [
        {
            "id": p.id, "import_key": p.import_key, "name": p.name, "vorname": p.vorname,
            "geschlecht": p.geschlecht, "status": p.status,
            "verfuegbar_fr": p.verfuegbar_fr, "verfuegbar_sa": p.verfuegbar_sa,
            "aktiv": p.aktiv,
        }
        for p in session.exec(
            select(Pruefer).where(Pruefer.jahrgang_id == jahrgang_id).order_by(Pruefer.name)
        )
    ]


class PrueferAenderung(BaseModel):
    aktiv: bool | None = None
    verfuegbar_fr: bool | None = None
    verfuegbar_sa: bool | None = None


@router.patch("/pruefende/{pruefer_id}")
def pruefer_aendern(
    jahrgang_id: int, pruefer_id: int, daten: PrueferAenderung,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    """Manuelle Nachpflege von Zu-/Absagen — finale Liste erst 2–3 Tage vor
    dem Verfahren (F_OM_002, Änderungsszenario 1)."""
    p = session.get(Pruefer, pruefer_id)
    if p is None or p.jahrgang_id != jahrgang_id:
        raise HTTPException(status_code=404, detail="Prüfer:in nicht gefunden.")
    for feld, wert in daten.model_dump(exclude_none=True).items():
        setattr(p, feld, wert)
    session.add(p)
    session.commit()
    protokollieren(session, "Prüfer:in geändert", benutzer=benutzer.benutzername,
                   jahrgang_id=jahrgang_id, pruefer=p.import_key or p.id,
                   **daten.model_dump(exclude_none=True))
    return {"status": "gespeichert"}


@router.get("/raeume")
def raeume(jahrgang_id: int, session: Session = Depends(get_session)):
    jahrgang_laden(session, jahrgang_id)
    return [
        {
            "id": r.id, "raumnummer": r.raumnummer, "groesse": r.groesse,
            "verfuegbar_fr": r.verfuegbar_fr, "verfuegbar_sa": r.verfuegbar_sa,
            "sperrzeiten": r.sperrzeiten, "aktiv": r.aktiv,
        }
        for r in session.exec(
            select(Raum).where(Raum.jahrgang_id == jahrgang_id).order_by(Raum.raumnummer)
        )
    ]


class RaumDaten(BaseModel):
    raumnummer: str
    groesse: str  # "klein" | "gross"
    verfuegbar_fr: bool = True
    verfuegbar_sa: bool = True


@router.post("/raeume", status_code=201)
def raum_anlegen(
    jahrgang_id: int, daten: RaumDaten,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    """Manuelle Raumpflege (F_OM_003 — Alternative zum CSV-Import)."""
    jahrgang_laden(session, jahrgang_id)
    try:
        groesse = Raumgroesse(daten.groesse)
    except ValueError:
        raise HTTPException(status_code=422, detail="Raumgröße muss klein oder gross sein.")
    raum = Raum(jahrgang_id=jahrgang_id, raumnummer=daten.raumnummer, groesse=groesse,
                verfuegbar_fr=daten.verfuegbar_fr, verfuegbar_sa=daten.verfuegbar_sa)
    session.add(raum)
    session.commit()
    protokollieren(session, "Raum angelegt", benutzer=benutzer.benutzername,
                   jahrgang_id=jahrgang_id, raum=daten.raumnummer)
    return {"id": raum.id}


class RaumAenderung(BaseModel):
    aktiv: bool | None = None
    verfuegbar_fr: bool | None = None
    verfuegbar_sa: bool | None = None


@router.patch("/raeume/{raum_id}")
def raum_aendern(
    jahrgang_id: int, raum_id: int, daten: RaumAenderung,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    """Raumausfall / Ersatzraum (Änderungsszenario 5)."""
    r = session.get(Raum, raum_id)
    if r is None or r.jahrgang_id != jahrgang_id:
        raise HTTPException(status_code=404, detail="Raum nicht gefunden.")
    for feld, wert in daten.model_dump(exclude_none=True).items():
        setattr(r, feld, wert)
    session.add(r)
    session.commit()
    protokollieren(session, "Raum geändert", benutzer=benutzer.benutzername,
                   jahrgang_id=jahrgang_id, raum=r.raumnummer,
                   **daten.model_dump(exclude_none=True))
    return {"status": "gespeichert"}


# ---------------------------------------------------------------------------
# Befangenheiten (F_OM_009) — auch manuell pflegbar, nachträglich (Szenario 4)
# ---------------------------------------------------------------------------

@router.get("/befangenheiten")
def befangenheiten(jahrgang_id: int, session: Session = Depends(get_session)):
    jahrgang_laden(session, jahrgang_id)
    return [
        {"id": bef.id, "pruefer_id": bef.pruefer_id, "bewerber_id": bef.bewerber_id}
        for bef in session.exec(
            select(Befangenheit).where(Befangenheit.jahrgang_id == jahrgang_id)
        )
    ]


class BefangenheitDaten(BaseModel):
    pruefer_id: int
    bewerber_id: int


@router.post("/befangenheiten", status_code=201)
def befangenheit_anlegen(
    jahrgang_id: int, daten: BefangenheitDaten,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    jahrgang_laden(session, jahrgang_id)
    vorhanden = session.exec(
        select(Befangenheit).where(
            Befangenheit.jahrgang_id == jahrgang_id,
            Befangenheit.pruefer_id == daten.pruefer_id,
            Befangenheit.bewerber_id == daten.bewerber_id,
        )
    ).first()
    if vorhanden:
        return {"id": vorhanden.id}
    bef = Befangenheit(jahrgang_id=jahrgang_id, **daten.model_dump())
    session.add(bef)
    session.commit()
    # Datensparsam: Protokoll ohne Klarnamen-Paarung (H2/NF_001)
    protokollieren(session, "Befangenheit hinterlegt", benutzer=benutzer.benutzername,
                   jahrgang_id=jahrgang_id)
    return {"id": bef.id}


@router.delete("/befangenheiten/{befangenheit_id}")
def befangenheit_loeschen(
    jahrgang_id: int, befangenheit_id: int,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    bef = session.get(Befangenheit, befangenheit_id)
    if bef is None or bef.jahrgang_id != jahrgang_id:
        raise HTTPException(status_code=404, detail="Befangenheit nicht gefunden.")
    session.delete(bef)
    session.commit()
    protokollieren(session, "Befangenheit entfernt", benutzer=benutzer.benutzername,
                   jahrgang_id=jahrgang_id)
    return {"status": "gelöscht"}
