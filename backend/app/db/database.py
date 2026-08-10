"""SQLite-Anbindung (WAL-Modus) und Session-Verwaltung."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

_engine = None


def daten_verzeichnis() -> Path:
    """Datenverzeichnis: per Umgebungsvariable übersteuerbar (Docker: /data)."""
    return Path(os.environ.get("BLS_DATEN_VERZEICHNIS", "data"))


def db_datei() -> Path:
    return daten_verzeichnis() / "bls.db"


def engine():
    global _engine
    if _engine is None:
        daten_verzeichnis().mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_datei()}",
            connect_args={"check_same_thread": False},
        )
        _wal_aktivieren(_engine)
    return _engine


def _wal_aktivieren(eng) -> None:
    @event.listens_for(eng, "connect")
    def _set_pragma(dbapi_conn, _record):  # pragma: no cover - trivial
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def schema_anlegen() -> None:
    from . import models  # noqa: F401 — Modelle registrieren

    SQLModel.metadata.create_all(engine())


def get_session() -> Iterator[Session]:
    """FastAPI-Dependency."""
    with Session(engine()) as session:
        yield session


def engine_zuruecksetzen() -> None:
    """Nur für Tests: erzwingt eine neue Engine (z. B. nach Wechsel des Datenpfads)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
