"""Versionierter CSV-Export (F_OM_013) und Datensicherung (NF_004)."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from ..core.plan import kontext_aus_db, plan_aus_db
from ..core.protokoll import protokollieren
from ..core.security import aktueller_benutzer
from ..db.database import daten_verzeichnis, db_datei, engine, get_session
from ..db.models import Benutzer, ExportLauf, Planungsstand
from ..io.exporter import plan_als_csv
from .jahrgaenge import jahrgang_laden, konfiguration_laden

router = APIRouter(
    prefix="/api", tags=["Export"],
    dependencies=[Depends(aktueller_benutzer)],
)


def _export_verzeichnis():
    pfad = daten_verzeichnis() / "exporte"
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


@router.post("/jahrgaenge/{jahrgang_id}/export")
def export_erstellen(
    jahrgang_id: int,
    stand_id: int | None = None,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    """Erzeugt einen neuen, versionierten Export des (letzten) Planungsstands.
    Wiederholte Exporte nach Neuberechnung sind ausdrücklich vorgesehen."""
    jahrgang = jahrgang_laden(session, jahrgang_id)
    if stand_id is None:
        stand = session.exec(
            select(Planungsstand).where(Planungsstand.jahrgang_id == jahrgang_id)
            .order_by(Planungsstand.version.desc())
        ).first()
    else:
        stand = session.get(Planungsstand, stand_id)
        if stand is not None and stand.jahrgang_id != jahrgang_id:
            stand = None
    if stand is None:
        raise HTTPException(status_code=404, detail="Kein Planungsstand vorhanden — zuerst berechnen.")

    konfiguration = konfiguration_laden(session, jahrgang_id)
    kontext = kontext_aus_db(session, jahrgang_id, konfiguration)
    plan = plan_aus_db(session, stand.id)

    letzte = session.exec(
        select(ExportLauf).where(ExportLauf.jahrgang_id == jahrgang_id)
        .order_by(ExportLauf.version.desc())
    ).first()
    version = (letzte.version + 1) if letzte else 1

    csv_text = plan_als_csv(plan, kontext, jahrgang.bezeichnung, export_version=version)
    dateiname = (
        f"zuteilung_{jahrgang.bezeichnung.replace('/', '-').replace(' ', '_')}"
        f"_v{version:03d}.csv"
    )
    pfad = _export_verzeichnis() / dateiname
    # UTF-8 mit BOM: Access/Excel erkennen Umlaute korrekt
    pfad.write_bytes(csv_text.encode("utf-8-sig"))

    lauf = ExportLauf(jahrgang_id=jahrgang_id, planungsstand_id=stand.id,
                      version=version, dateiname=dateiname)
    session.add(lauf)
    session.commit()
    protokollieren(session, "Export erstellt", benutzer=benutzer.benutzername,
                   jahrgang_id=jahrgang_id, version=version,
                   planungsstand_version=stand.version, datei=dateiname)
    return {"id": lauf.id, "version": version, "dateiname": dateiname,
            "planungsstand_version": stand.version}


@router.get("/jahrgaenge/{jahrgang_id}/export/laeufe")
def export_laeufe(jahrgang_id: int, session: Session = Depends(get_session)):
    jahrgang_laden(session, jahrgang_id)
    staende = {
        p.id: p.version for p in session.exec(
            select(Planungsstand).where(Planungsstand.jahrgang_id == jahrgang_id)
        )
    }
    return [
        {"id": e.id, "version": e.version, "dateiname": e.dateiname,
         "erstellt_am": e.erstellt_am,
         "planungsstand_version": staende.get(e.planungsstand_id)}
        for e in session.exec(
            select(ExportLauf).where(ExportLauf.jahrgang_id == jahrgang_id)
            .order_by(ExportLauf.version.desc())
        )
    ]


@router.get("/export/{export_id}/datei")
def export_herunterladen(export_id: int, session: Session = Depends(get_session)):
    lauf = session.get(ExportLauf, export_id)
    if lauf is None:
        raise HTTPException(status_code=404, detail="Export nicht gefunden.")
    pfad = _export_verzeichnis() / lauf.dateiname
    if not pfad.is_file():
        raise HTTPException(status_code=410, detail="Exportdatei liegt nicht mehr vor — neuen Export erstellen.")
    return FileResponse(pfad, media_type="text/csv", filename=lauf.dateiname)


@router.post("/backup")
def backup_erstellen(
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    """Sicherung der Datenbankdatei (NF_004: Backup/Wiederanlauf)."""
    ziel_verzeichnis = daten_verzeichnis() / "backups"
    ziel_verzeichnis.mkdir(parents=True, exist_ok=True)
    zeitstempel = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ziel = ziel_verzeichnis / f"bls_{zeitstempel}.db"
    # WAL-Inhalte in die Hauptdatei überführen, dann kopieren
    with engine().connect() as verbindung:
        verbindung.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    shutil.copy2(db_datei(), ziel)
    protokollieren(session, "Backup erstellt", benutzer=benutzer.benutzername,
                   datei=ziel.name)
    return {"datei": ziel.name}


@router.get("/backup/liste")
def backup_liste(_: Benutzer = Depends(aktueller_benutzer)):
    ziel_verzeichnis = daten_verzeichnis() / "backups"
    if not ziel_verzeichnis.is_dir():
        return []
    return sorted(
        (p.name for p in ziel_verzeichnis.glob("bls_*.db")), reverse=True
    )
