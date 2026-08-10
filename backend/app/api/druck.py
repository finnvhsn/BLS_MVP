"""Druckdaten-Endpunkte (F_DM_001/002): PDFs aus dem aktuellen Planungsstand —
nach jeder Neuberechnung einfach neu abrufbar."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select

from ..core.plan import kontext_aus_db, plan_aus_db
from ..core.protokoll import protokollieren
from ..core.security import aktueller_benutzer
from ..db.database import get_session
from ..db.models import Benutzer, Planungsstand
from ..io import pdf
from .jahrgaenge import jahrgang_laden, konfiguration_laden

router = APIRouter(
    prefix="/api/jahrgaenge/{jahrgang_id}/druck", tags=["Druck"],
    dependencies=[Depends(aktueller_benutzer)],
)

ARTEN = {
    "laufzettel-bewerbende": ("Laufzettel Bewerbende", pdf.laufzettel_bewerbende_html),
    "laufzettel-pruefende": ("Laufzettel Prüfende", pdf.laufzettel_pruefende_html),
    "raumschilder": ("Raumschilder", pdf.raumschilder_html),
}


@router.get("/{art}")
def druck(
    art: str,
    jahrgang_id: int,
    stand_id: int | None = None,
    session: Session = Depends(get_session),
    benutzer: Benutzer = Depends(aktueller_benutzer),
):
    if art not in ARTEN:
        raise HTTPException(status_code=404, detail=f"Unbekanntes Druckerzeugnis {art!r}.")
    jahrgang = jahrgang_laden(session, jahrgang_id)
    if stand_id is None:
        stand = session.exec(
            select(Planungsstand).where(Planungsstand.jahrgang_id == jahrgang_id)
            .order_by(Planungsstand.version.desc())
        ).first()
    else:
        stand = session.get(Planungsstand, stand_id)
    if stand is None:
        raise HTTPException(status_code=404, detail="Kein Planungsstand vorhanden — zuerst berechnen.")

    konfiguration = konfiguration_laden(session, jahrgang_id)
    kontext = kontext_aus_db(session, jahrgang_id, konfiguration)
    plan = plan_aus_db(session, stand.id)

    titel, erzeuger = ARTEN[art]
    html_text = erzeuger(plan, kontext, jahrgang.bezeichnung)
    try:
        pdf_bytes = pdf.html_zu_pdf(html_text)
    except pdf.PdfNichtVerfuegbar as e:
        raise HTTPException(status_code=501, detail=str(e))

    protokollieren(session, f"Druck: {titel}", benutzer=benutzer.benutzername,
                   jahrgang_id=jahrgang_id, planungsstand_version=stand.version)
    dateiname = f"{art}_{jahrgang.bezeichnung.replace('/', '-')}_v{stand.version}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{dateiname}"'},
    )
