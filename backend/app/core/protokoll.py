"""Lauf- und Änderungsprotokoll (NF_010, NF_002)."""

from __future__ import annotations

from sqlmodel import Session, select

from ..db.models import Protokoll


def protokollieren(
    session: Session,
    aktion: str,
    benutzer: str = "System",
    jahrgang_id: int | None = None,
    commit: bool = True,
    **details,
) -> None:
    """Schreibt einen Protokolleintrag. ``details`` müssen JSON-serialisierbar sein."""
    session.add(
        Protokoll(jahrgang_id=jahrgang_id, benutzer=benutzer, aktion=aktion, details=details)
    )
    if commit:
        session.commit()


def protokoll_lesen(session: Session, jahrgang_id: int | None = None, limit: int = 200) -> list[Protokoll]:
    stmt = select(Protokoll).order_by(Protokoll.id.desc()).limit(limit)
    if jahrgang_id is not None:
        stmt = select(Protokoll).where(Protokoll.jahrgang_id == jahrgang_id).order_by(Protokoll.id.desc()).limit(limit)
    return list(session.exec(stmt))
