"""Anmeldung/Abmeldung (NF_002)."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import Session

from ..core import security
from ..core.protokoll import protokollieren
from ..db.database import get_session
from ..db.models import Benutzer

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginDaten(BaseModel):
    benutzername: str
    passwort: str


@router.post("/login")
def login(daten: LoginDaten, response: Response, session: Session = Depends(get_session)):
    benutzer = security.anmelden(session, daten.benutzername, daten.passwort, response)
    if benutzer is None:
        raise HTTPException(status_code=401, detail="Benutzername oder Passwort falsch.")
    protokollieren(session, "Anmeldung", benutzer=benutzer.benutzername)
    return {"benutzername": benutzer.benutzername, "rolle": benutzer.rolle}


@router.post("/logout")
def logout(
    response: Response,
    session: Session = Depends(get_session),
    bls_sitzung: str | None = Cookie(default=None),
):
    security.abmelden(session, bls_sitzung, response)
    return {"status": "abgemeldet"}


@router.get("/ich")
def ich(benutzer: Benutzer = Depends(security.aktueller_benutzer)):
    return {"benutzername": benutzer.benutzername, "rolle": benutzer.rolle}
