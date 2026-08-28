"""M3-Tests: Gruppeneinteilung (Stufe 1), CP-SAT-Solver (Stufe 2),
Property-Test „Solver-Output besteht den Validator“, Rohexport.

Die schnellen Tests laufen auf einer kompakten Instanz (~60 Bewerbende);
der Volllast-Test (reales Mengengerüst, AK1/AK3) ist mit ``langsam`` markiert
und läuft über ``pytest -m langsam``.
"""

from __future__ import annotations

from collections import Counter

import pytest

from app.core import grouping, solver
from app.core.konfiguration import standard_konfiguration
from app.core.rules import w3_diversitaet_gruppe
from app.core.validator import plan_validieren
from app.db.models import Tag
from app.io.exporter import EXPORT_SPALTEN, plan_als_csv

KOMPAKT = dict(  # kompakte, aber strukturgleiche Instanz
    anzahl_bewerber=120, anzahl_senior=24, anzahl_junior=10,
    raeume_klein=12, raeume_gross=5, befangenheit_anzahl=6,
)


def _kompakte_konfiguration():
    konf = standard_konfiguration()
    konf.solver.schritt_budget_sekunden = 20  # genügt der kleinen Instanz
    return konf


@pytest.fixture(scope="module")
def geloest(tmp_path_factory):
    """Einmal je Modul lösen, mehrere Tests prüfen das Ergebnis."""
    from .conftest import verfahren_erzeugen

    verfahren = verfahren_erzeugen(
        tmp_path_factory.mktemp("m3"), _kompakte_konfiguration(), **KOMPAKT
    )
    einteilung = grouping.gruppen_einteilen(verfahren.kontext, seed=42)
    kontext = grouping.kontext_mit_gruppen(verfahren.kontext, einteilung)
    ergebnis = solver.berechnen(kontext)
    verfahren.session.close()
    return kontext, einteilung, ergebnis


# ---------------------------------------------------------------------------
# Stufe 1: Gruppeneinteilung
# ---------------------------------------------------------------------------

def test_gruppen_groesse_und_vollstaendigkeit(verfahren_bauen):
    verfahren = verfahren_bauen(**KOMPAKT)
    einteilung = grouping.gruppen_einteilen(verfahren.kontext, seed=1)
    for tag in (Tag.FR, Tag.SA):
        planbar = {b.id for b in verfahren.kontext.planbare_bewerber(tag)}
        eingeteilt = [bid for gruppe in einteilung[tag] for bid in gruppe]
        assert sorted(eingeteilt) == sorted(planbar)          # alle, keine doppelt
        groessen = {len(g) for g in einteilung[tag]}
        assert groessen <= {3, 4}                             # konfigurierte Größe, Rest -1


def test_gruppen_deterministisch_und_seedabhaengig(verfahren_bauen):
    verfahren = verfahren_bauen(**KOMPAKT)
    a = grouping.gruppen_einteilen(verfahren.kontext, seed=7)
    b = grouping.gruppen_einteilen(verfahren.kontext, seed=7)
    c = grouping.gruppen_einteilen(verfahren.kontext, seed=8)
    assert a == b            # reproduzierbar (NF_010)
    assert a != c            # zufallsbasiert (W3)


def test_gruppen_diversitaet_besser_als_zufall(verfahren_bauen):
    verfahren = verfahren_bauen(**KOMPAKT)
    kontext = verfahren.kontext
    optimiert = grouping.gruppen_einteilen(kontext, seed=3)
    roh = grouping.gruppen_einteilen(kontext, seed=3, verbesserungs_runden=0)

    def score(einteilung):
        gruppen = [g for tag in (Tag.FR, Tag.SA) for g in einteilung[tag]]
        return sum(w3_diversitaet_gruppe(g, kontext) for g in gruppen) / len(gruppen)

    assert score(optimiert) >= score(roh)


def test_kontext_mit_gruppen(verfahren_bauen):
    verfahren = verfahren_bauen(**KOMPAKT)
    einteilung = grouping.gruppen_einteilen(verfahren.kontext, seed=1)
    kontext = grouping.kontext_mit_gruppen(verfahren.kontext, einteilung)
    assert all(b.gruppe_id is not None for b in kontext.planbare_bewerber())
    tage = {kontext.gruppen[b.gruppe_id].tag for b in kontext.planbare_bewerber()}
    assert tage == {Tag.FR, Tag.SA}


# ---------------------------------------------------------------------------
# Stufe 2: Solver — Property-Test (Kern der Regel-Drift-Absicherung)
# ---------------------------------------------------------------------------

def test_property_solver_output_besteht_validator(geloest):
    """DER zentrale Test: Jeder Solver-Output läuft durch den kompletten
    Regelkatalog (rules.py) und muss 0 Verletzungen haben."""
    kontext, _, ergebnis = geloest
    assert ergebnis.status == "gueltig"
    assert ergebnis.konflikte == []
    assert plan_validieren(ergebnis.plan, kontext) == []


def test_alle_planbaren_vollstaendig_geplant(geloest):
    kontext, _, ergebnis = geloest
    format_keys = {f.key for f in kontext.konfiguration.formate}
    for info in kontext.planbare_bewerber():
        ereignisse = ergebnis.plan.fuer_bewerber(info.id)
        assert Counter(z.format_key for z in ereignisse) == Counter(format_keys)
        assert all(z.tag == info.tag for z in ereignisse)


def test_kennzahlen_ausgewiesen(geloest):
    """AK8: W1/W2-Abweichungen und Wartezeiten werden ausgewiesen."""
    _, _, ergebnis = geloest
    kz = ergebnis.kennzahlen
    assert kz["w1_zielwert"] == 8
    assert kz["w1_erfuellt"] == kz["anzahl_geplante_bewerber"]  # H1 erzwingt 8 Kontakte
    assert kz["w2_durchschnitt"] > 0
    assert "w5_wartezeit_summe_min" in kz and "w5_wartezeit_je_bewerber" in kz


def test_mindestpause_zwischen_allen_terminen(geloest):
    """Jede Person kommt von Raum A nach Raum B: zwischen zwei
    aufeinanderfolgenden Terminen liegt mindestens die Mindestpause.

    Der Nachweis, den zuvor nur ein Messlauf über das reale Mengengerüst
    lieferte (Konfiguration mit 0 ⇒ hunderte lückenlose Übergänge, mit 15 ⇒
    keiner). Hier deterministisch und in Sekunden — und über H10 im
    Regelkatalog auch gegen künftige Drift abgesichert.
    """
    kontext, _, ergebnis = geloest
    zm = kontext.konfiguration.zeitmodell
    uebergaenge = 0
    for info in kontext.planbare_bewerber():
        termine = sorted(ergebnis.plan.fuer_bewerber(info.id), key=lambda z: z.start_min)
        for vorher, nachher in zip(termine, termine[1:]):
            luecke = nachher.start_min - vorher.ende_min
            noetig = zm.mindestpause_min
            assert luecke >= noetig, (
                f"{info.anzeigename}: nur {luecke} min zwischen "
                f"{vorher.format_key} und {nachher.format_key} (nötig: {noetig})"
            )
            uebergaenge += 1
    # Ohne Übergänge wäre die Zusicherung wertlos: 4 Formate ⇒ 3 je Person
    assert uebergaenge == 3 * len(kontext.planbare_bewerber())
    assert zm.mindestpause_min > 0


def test_befangenheiten_niemals_zugewiesen(geloest):
    kontext, _, ergebnis = geloest
    for z in ergebnis.plan.zuweisungen:
        for pid in z.pruefer_ids:
            for bid in z.bewerber_ids:
                assert (pid, bid) not in kontext.befangenheiten


def test_rohexport_csv(geloest):
    kontext, _, ergebnis = geloest
    csv_text = plan_als_csv(ergebnis.plan, kontext, "Test 2026/2027", export_version=1)
    zeilen = csv_text.strip().splitlines()
    assert zeilen[0] == ";".join(EXPORT_SPALTEN)
    erwartet = sum(
        len(z.bewerber_ids) + len(z.pruefer_ids) for z in ergebnis.plan.zuweisungen
    )
    assert len(zeilen) - 1 == erwartet
    # Jede Zeile trägt Version, Jahrgang und eine Partner-Zuordnung (AK7)
    beispiel = zeilen[1].split(";")
    assert beispiel[0] == "1" and beispiel[1] == "Test 2026/2027"
    assert beispiel[-1] != ""


def test_unloesbar_wird_benannt(verfahren_bauen):
    """Kap. 4.3: kein nacktes „infeasible“, sondern benannte Konflikte."""
    verfahren = verfahren_bauen(
        anzahl_bewerber=40, anzahl_senior=4, anzahl_junior=2,
        raeume_klein=1, raeume_gross=1, befangenheit_anzahl=0,
    )
    einteilung = grouping.gruppen_einteilen(verfahren.kontext, seed=1)
    kontext = grouping.kontext_mit_gruppen(verfahren.kontext, einteilung)
    with pytest.raises(solver.KeinPlanMoeglich) as exc:
        solver.berechnen(kontext)
    regeln = {k.regel for k in exc.value.konflikte}
    assert regeln & {"H3", "H6", "H8"}
    assert all(k.meldung for k in exc.value.konflikte)


# ---------------------------------------------------------------------------
# Volllast: reales Mengengerüst (AK1, AK3 — pytest -m langsam)
# ---------------------------------------------------------------------------

@pytest.mark.langsam
def test_vollberechnung_reales_mengengeruest(verfahren_bauen):
    verfahren = verfahren_bauen()  # Defaults = 262/87/34, Kap. 3
    einteilung = grouping.gruppen_einteilen(verfahren.kontext, seed=42)
    kontext = grouping.kontext_mit_gruppen(verfahren.kontext, einteilung)
    ergebnis = solver.berechnen(kontext)
    assert ergebnis.laufzeit_sekunden <= 15 * 60      # NF_003
    assert ergebnis.konflikte == []
    assert ergebnis.kennzahlen["w1_erfuellt"] == ergebnis.kennzahlen["anzahl_geplante_bewerber"]
    assert plan_validieren(ergebnis.plan, kontext) == []
