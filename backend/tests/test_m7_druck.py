"""M7-Tests: Laufzettel und Raumschilder (F_DM_001/002)."""

from __future__ import annotations

import pytest

from app.core import grouping, solver
from app.core.konfiguration import standard_konfiguration
from app.io import pdf
from tests.conftest import verfahren_erzeugen

KLEIN = dict(
    anzahl_bewerber=24, anzahl_senior=12, anzahl_junior=4,
    raeume_klein=6, raeume_gross=3, befangenheit_anzahl=0,
)


@pytest.fixture(scope="module")
def geloest(tmp_path_factory):
    konf = standard_konfiguration()
    konf.solver.schritt_budget_sekunden = 10
    verfahren = verfahren_erzeugen(tmp_path_factory.mktemp("m7"), konf, **KLEIN)
    einteilung = grouping.gruppen_einteilen(verfahren.kontext, seed=5)
    kontext = grouping.kontext_mit_gruppen(verfahren.kontext, einteilung)
    ergebnis = solver.berechnen(kontext)
    verfahren.session.close()
    assert ergebnis.konflikte == []
    return kontext, ergebnis.plan


def test_laufzettel_bewerbende_html(geloest):
    kontext, plan = geloest
    html_text = pdf.laufzettel_bewerbende_html(plan, kontext, "Test 2026/2027")
    # Eine Seite je planbarer Person, alle Formate benannt
    assert html_text.count('class="seite"') == len(kontext.planbare_bewerber())
    for begriff in ("Laufzettel", "Thesenvortrag", "Gruppenvortrag/Gruppenarbeit",
                    "Einzelgespräch 1", "Prüfungstag"):
        assert begriff in html_text


def test_laufzettel_pruefende_html(geloest):
    kontext, plan = geloest
    html_text = pdf.laufzettel_pruefende_html(plan, kontext, "Test 2026/2027")
    eingesetzte = {p for z in plan.zuweisungen for p in z.pruefer_ids}
    assert html_text.count('class="seite"') == len(eingesetzte)
    assert "Einsatzplan" in html_text and "Senior" in html_text


def test_raumschilder_html(geloest):
    kontext, plan = geloest
    html_text = pdf.raumschilder_html(plan, kontext, "Test 2026/2027")
    genutzte_raum_tage = {(z.raum_id, z.tag) for z in plan.zuweisungen}
    assert html_text.count("raumschild'") + html_text.count('raumschild"') >= 1
    assert html_text.count("Raum ") >= len({r for r, _ in genutzte_raum_tage})


def test_pdf_wandlung(geloest):
    kontext, plan = geloest
    try:
        pdf_bytes = pdf.html_zu_pdf(pdf.raumschilder_html(plan, kontext, "Test"))
    except pdf.PdfNichtVerfuegbar:
        pytest.skip("WeasyPrint-Systembibliotheken lokal nicht verfügbar (im Docker enthalten).")
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_aktualisierung_nach_neuberechnung(geloest):
    """F_DM_001 AK: Druckdaten sind nach Neuberechnung aktualisierbar —
    die Erzeugung arbeitet direkt auf dem (neuen) Planungsstand."""
    kontext, plan = geloest
    ergebnis = solver.berechnen(kontext, bestand=plan)
    html_neu = pdf.laufzettel_bewerbende_html(ergebnis.plan, kontext, "Test 2026/2027")
    assert html_neu.count('class="seite"') == len(kontext.planbare_bewerber())
