"""Jahrgänge (NF_008) und Jahrgangs-Konfiguration (F_OM_010)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlmodel import Session, delete, select

from ..core.konfiguration import JahrgangsKonfiguration, standard_konfiguration
from ..core.protokoll import protokoll_lesen, protokollieren
from ..core.security import aktueller_benutzer
from ..db.database import get_session
from ..db.models import (
    Befangenheit,
    Benutzer,
    Bewerber,
    ExportLauf,
    Gruppe,
    Jahrgang,
    Konfiguration,
    Planungsstand,
    Pruefer,
    Raum,
    Zuweisung,
    ZuweisungBewerber,
    ZuweisungPruefer,
)

router = APIRouter(
    prefix="/api/jahrgaenge", tags=["Jahrgänge"],
    dependencies=[Depends(aktueller_benutzer)],
)


def jahrgang_laden(session: Session, jahrgang_id: int) -> Jahrgang:
    jahrgang = session.get(Jahrgang, jahrgang_id)
    if jahrgang is None:
        raise HTTPException(status_code=404, detail="Jahrgang nicht gefunden.")
    return jahrgang


def konfiguration_laden(session: Session, jahrgang_id: int) -> JahrgangsKonfiguration:
    zeile = session.exec(
        select(Konfiguration).where(Konfiguration.jahrgang_id == jahrgang_id)
        .order_by(Konfiguration.id.desc())
    ).first()
    if zeile is None:
        return standard_konfiguration()
    return JahrgangsKonfiguration.model_validate(zeile.daten)


class JahrgangAnlegen(BaseModel):
    bezeichnung: str
    vorlage_jahrgang_id: int | None = None  # Konfiguration als Vorlage übernehmen


@router.get("")
def liste(session: Session = Depends(get_session)):
    jahrgaenge = session.exec(select(Jahrgang).order_by(Jahrgang.id.desc())).all()
    return [
        {"id": j.id, "bezeichnung": j.bezeichnung, "aktiv": j.aktiv,
         "erstellt_am": j.erstellt_am}
        for j in jahrgaenge
    ]


@router.post("", status_code=201)
def anlegen(
    daten: JahrgangAnlegen,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    if not daten.bezeichnung.strip():
        raise HTTPException(status_code=422, detail="Bezeichnung darf nicht leer sein.")
    if session.exec(select(Jahrgang).where(Jahrgang.bezeichnung == daten.bezeichnung)).first():
        raise HTTPException(status_code=409, detail="Ein Jahrgang mit dieser Bezeichnung existiert bereits.")
    jahrgang = Jahrgang(bezeichnung=daten.bezeichnung.strip())
    session.add(jahrgang)
    session.commit()
    session.refresh(jahrgang)

    # NF_008: Konfiguration des Vorlage-Jahrgangs kopieren
    if daten.vorlage_jahrgang_id is not None:
        vorlage = konfiguration_laden(session, daten.vorlage_jahrgang_id)
        session.add(Konfiguration(jahrgang_id=jahrgang.id, daten=vorlage.model_dump()))
        session.commit()

    protokollieren(session, "Jahrgang angelegt", benutzer=benutzer.benutzername,
                   jahrgang_id=jahrgang.id, bezeichnung=jahrgang.bezeichnung)
    return {"id": jahrgang.id, "bezeichnung": jahrgang.bezeichnung}


@router.delete("/{jahrgang_id}")
def loeschen(
    jahrgang_id: int,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    """Löscht einen Jahrgang mit allen personenbezogenen Daten (NF_001:
    Lösch-/Aufbewahrungskonzept je Jahrgang)."""
    jahrgang = jahrgang_laden(session, jahrgang_id)
    staende = session.exec(
        select(Planungsstand.id).where(Planungsstand.jahrgang_id == jahrgang_id)
    ).all()
    zuweisungen = session.exec(
        select(Zuweisung.id).where(Zuweisung.planungsstand_id.in_(staende))  # type: ignore[union-attr]
    ).all() if staende else []
    if zuweisungen:
        session.exec(delete(ZuweisungBewerber).where(ZuweisungBewerber.zuweisung_id.in_(zuweisungen)))  # type: ignore[union-attr]
        session.exec(delete(ZuweisungPruefer).where(ZuweisungPruefer.zuweisung_id.in_(zuweisungen)))  # type: ignore[union-attr]
    for modell in (Zuweisung,) if staende else ():
        session.exec(delete(modell).where(Zuweisung.planungsstand_id.in_(staende)))  # type: ignore[union-attr]
    from ..db.models import Protokoll

    for modell in (ExportLauf, Planungsstand, Befangenheit, Bewerber, Gruppe,
                   Pruefer, Raum, Konfiguration, Protokoll):
        session.exec(delete(modell).where(modell.jahrgang_id == jahrgang_id))
    session.delete(jahrgang)
    session.commit()
    protokollieren(session, "Jahrgang gelöscht", benutzer=benutzer.benutzername,
                   bezeichnung=jahrgang.bezeichnung)
    return {"status": "gelöscht"}


@router.get("/{jahrgang_id}/konfiguration")
def konfiguration_lesen(jahrgang_id: int, session: Session = Depends(get_session)):
    jahrgang_laden(session, jahrgang_id)
    return konfiguration_laden(session, jahrgang_id).model_dump()


@router.put("/{jahrgang_id}/konfiguration")
def konfiguration_speichern(
    jahrgang_id: int,
    daten: dict,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    jahrgang_laden(session, jahrgang_id)
    try:
        konfiguration = JahrgangsKonfiguration.model_validate(daten)
    except ValidationError as e:
        fehler = "; ".join(
            f"{'.'.join(str(t) for t in f['loc'])}: {f['msg']}" for f in e.errors()
        )
        raise HTTPException(status_code=422, detail=f"Konfiguration ungültig: {fehler}")
    session.add(Konfiguration(jahrgang_id=jahrgang_id, daten=konfiguration.model_dump()))
    session.commit()
    protokollieren(session, "Konfiguration geändert", benutzer=benutzer.benutzername,
                   jahrgang_id=jahrgang_id)
    return {"status": "gespeichert"}


@router.get("/{jahrgang_id}/protokoll")
def protokoll(jahrgang_id: int, session: Session = Depends(get_session)):
    """Lauf- und Änderungsprotokoll (NF_010)."""
    jahrgang_laden(session, jahrgang_id)
    return [
        {"zeitpunkt": p.zeitpunkt, "benutzer": p.benutzer, "aktion": p.aktion,
         "details": p.details}
        for p in protokoll_lesen(session, jahrgang_id)
    ]
