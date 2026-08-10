"""Auth als gekapseltes Modul (NF_002; SSO-fähig austauschbar, Kap. 10).

MVP: eine aktive Rolle „Verfahrensorganisation", Login mit individuellem
Passwort (bcrypt), Sitzungs-Token als HttpOnly-Cookie.
"""

from __future__ import annotations

import os
import secrets
from datetime import timedelta

import bcrypt
from fastapi import Cookie, Depends, HTTPException, Response
from sqlmodel import Session, select

from ..db.database import get_session
from ..db.models import Benutzer, Rolle, Sitzung, jetzt

SESSION_COOKIE = "bls_sitzung"
SITZUNGSDAUER = timedelta(hours=12)


def passwort_hashen(passwort: str) -> str:
    return bcrypt.hashpw(passwort.encode(), bcrypt.gensalt()).decode()


def passwort_pruefen(passwort: str, passwort_hash: str) -> bool:
    try:
        return bcrypt.checkpw(passwort.encode(), passwort_hash.encode())
    except ValueError:
        return False


def admin_anlegen(session: Session) -> None:
    """Legt beim ersten Start das Konto der Verfahrensorganisation an.

    Zugangsdaten per Umgebungsvariablen BLS_ADMIN_BENUTZER / BLS_ADMIN_PASSWORT
    (Defaults nur für lokale Entwicklung — für den Einsatz ändern!).
    """
    benutzername = os.environ.get("BLS_ADMIN_BENUTZER", "verfahren")
    if session.exec(select(Benutzer).where(Benutzer.benutzername == benutzername)).first():
        return
    passwort = os.environ.get("BLS_ADMIN_PASSWORT", "bls-auswahl")
    session.add(
        Benutzer(
            benutzername=benutzername,
            passwort_hash=passwort_hashen(passwort),
            rolle=Rolle.VERFAHRENSORGANISATION,
        )
    )
    session.commit()


def anmelden(session: Session, benutzername: str, passwort: str, response: Response) -> Benutzer | None:
    benutzer = session.exec(
        select(Benutzer).where(Benutzer.benutzername == benutzername, Benutzer.aktiv == True)  # noqa: E712
    ).first()
    if benutzer is None or not passwort_pruefen(passwort, benutzer.passwort_hash):
        return None
    token = secrets.token_urlsafe(32)
    session.add(Sitzung(token=token, benutzer_id=benutzer.id, gueltig_bis=jetzt() + SITZUNGSDAUER))
    session.commit()
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=int(SITZUNGSDAUER.total_seconds())
    )
    return benutzer


def abmelden(session: Session, token: str | None, response: Response) -> None:
    if token:
        sitzung = session.exec(select(Sitzung).where(Sitzung.token == token)).first()
        if sitzung:
            session.delete(sitzung)
            session.commit()
    response.delete_cookie(SESSION_COOKIE)


def aktueller_benutzer(
    session: Session = Depends(get_session),
    bls_sitzung: str | None = Cookie(default=None),
) -> Benutzer:
    """FastAPI-Dependency: erzwingt eine gültige Sitzung."""
    if bls_sitzung:
        sitzung = session.exec(select(Sitzung).where(Sitzung.token == bls_sitzung)).first()
        if sitzung is not None:
            gueltig_bis = sitzung.gueltig_bis
            if gueltig_bis.tzinfo is None:
                # SQLite speichert naive Zeitstempel — als UTC interpretieren
                from datetime import timezone

                gueltig_bis = gueltig_bis.replace(tzinfo=timezone.utc)
            if gueltig_bis >= jetzt():
                benutzer = session.get(Benutzer, sitzung.benutzer_id)
                if benutzer and benutzer.aktiv:
                    return benutzer
    raise HTTPException(status_code=401, detail="Nicht angemeldet.")
