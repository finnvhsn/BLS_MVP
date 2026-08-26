"""M4-Tests: Neuberechnung mit Warmstart/Bestandserhalt (W6, F_OM_011) —
alle 5 Änderungsszenarien aus Kap. 5 der Spec als Integrationstests.

Muster je Szenario: Basisplan → Datenänderung → Neuberechnung mit ``bestand``
→ (a) Änderung fachlich korrekt umgesetzt, (b) keine Konflikte,
(c) maximaler Erhalt bestehender Zuweisungen (Stabilitätsmetrik)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core import grouping, solver
from app.core.konfiguration import standard_konfiguration
from app.core.plan import BewerberInfo
from app.db.models import Rueckmeldestatus, Tag
from tests.conftest import verfahren_erzeugen

KOMPAKT = dict(
    anzahl_bewerber=120, anzahl_senior=24, anzahl_junior=10,
    raeume_klein=12, raeume_gross=5, befangenheit_anzahl=6,
)


def _konfiguration():
    konf = standard_konfiguration()
    konf.solver.schritt_budget_sekunden = 20
    return konf


@pytest.fixture(scope="module")
def basis(tmp_path_factory):
    verfahren = verfahren_erzeugen(tmp_path_factory.mktemp("m4"), _konfiguration(), **KOMPAKT)
    einteilung = grouping.gruppen_einteilen(verfahren.kontext, seed=42)
    kontext = grouping.kontext_mit_gruppen(verfahren.kontext, einteilung)
    ergebnis = solver.berechnen(kontext)
    verfahren.session.close()
    assert ergebnis.konflikte == []
    return kontext, ergebnis


def _stabil(ergebnis, basis_plan, mindestens: float = 0.6) -> None:
    """(c) Bestandserhalt: deutlich mehr erhalten als geändert (W6)."""
    stab = ergebnis.kennzahlen["w6_stabilitaet"]
    assert stab["erhalten"] >= mindestens * len(basis_plan.zuweisungen), stab


# ---------------------------------------------------------------------------
# Szenario 1: Kurzfristige Absage Prüfer:in
# ---------------------------------------------------------------------------

def test_szenario_1_pruefer_absage(basis):
    kontext, basis_ergebnis = basis
    # Eine:n stark eingebundene:n Prüfer:in absagen lassen
    pid = max(
        (p for z in basis_ergebnis.plan.zuweisungen for p in z.pruefer_ids),
        key=lambda p: len(basis_ergebnis.plan.fuer_pruefer(p)),
    )
    geaendert = replace(kontext, pruefer={
        **kontext.pruefer, pid: replace(kontext.pruefer[pid], aktiv=False)
    })
    ergebnis = solver.berechnen(geaendert, bestand=basis_ergebnis.plan)
    assert ergebnis.konflikte == []
    # Betroffene Kontakte wurden auf andere Prüfende umverteilt (H1–H4 via Validator)
    assert all(pid not in z.pruefer_ids for z in ergebnis.plan.zuweisungen)
    _stabil(ergebnis, basis_ergebnis.plan)


# ---------------------------------------------------------------------------
# Szenario 2: Kurzfristige Absage Bewerber:in
# ---------------------------------------------------------------------------

def test_szenario_2_bewerber_absage(basis):
    kontext, basis_ergebnis = basis
    bid = min(b.id for b in kontext.planbare_bewerber(Tag.FR))
    info = kontext.bewerber[bid]
    geaendert = replace(kontext, bewerber={
        **kontext.bewerber,
        bid: replace(info, rueckmeldestatus=Rueckmeldestatus.ABSAGE, aktiv=False),
    })
    ergebnis = solver.berechnen(geaendert, bestand=basis_ergebnis.plan)
    assert ergebnis.konflikte == []
    # Slots der Person entfallen …
    assert all(bid not in z.bewerber_ids for z in ergebnis.plan.zuweisungen)
    # … die Gruppenformate ihrer Gruppe laufen mit reduzierter Größe weiter
    gruppen_ereignisse = [
        z for z in ergebnis.plan.zuweisungen if z.gruppe_id == info.gruppe_id
    ]
    assert len(gruppen_ereignisse) == 2  # Gruppenarbeit + Thesenvortrag
    assert all(len(z.bewerber_ids) >= 1 for z in gruppen_ereignisse)
    _stabil(ergebnis, basis_ergebnis.plan)


# ---------------------------------------------------------------------------
# Szenario 3: Nachrücken von der Reserveliste
# ---------------------------------------------------------------------------

def test_szenario_3_nachruecker(basis):
    kontext, basis_ergebnis = basis
    nachruecker = BewerberInfo(
        id=99999, name="Nachrücker", vorname="Nina", tag=Tag.SA, geschlecht="w",
        studiengang="Rechtswissenschaft", zugelassen=True, aktiv=True,
        rueckmeldestatus=Rueckmeldestatus.ZUSAGE, ruecksteller=False,
        gruppe_id=None, import_key="BW-9999",
    )
    geaendert = replace(kontext, bewerber={**kontext.bewerber, nachruecker.id: nachruecker})
    geaendert = grouping.gruppen_auffuellen(geaendert)
    assert geaendert.bewerber[nachruecker.id].gruppe_id is not None

    ergebnis = solver.berechnen(geaendert, bestand=basis_ergebnis.plan)
    assert ergebnis.konflikte == []
    # Vollständig eingeplant: alle Formate, 8 unterschiedliche Prüfende (W1)
    ereignisse = ergebnis.plan.fuer_bewerber(nachruecker.id)
    assert sorted(z.format_key for z in ereignisse) == sorted(
        f.key for f in kontext.konfiguration.formate
    )
    pruefer = set()
    for z in ereignisse:
        pruefer.update(z.pruefer_ids)
    assert len(pruefer) == 8
    _stabil(ergebnis, basis_ergebnis.plan)


# ---------------------------------------------------------------------------
# Szenario 4: Nachträglich bekannte Befangenheit
# ---------------------------------------------------------------------------

def test_szenario_4_nachtraegliche_befangenheit(basis):
    kontext, basis_ergebnis = basis
    # Eine real zugewiesene Paarung nachträglich als befangen markieren
    z0 = next(z for z in basis_ergebnis.plan.zuweisungen if z.pruefer_ids and z.bewerber_ids)
    pid, bid = next(iter(z0.pruefer_ids)), next(iter(z0.bewerber_ids))
    geaendert = replace(kontext, befangenheiten=kontext.befangenheiten | {(pid, bid)})

    ergebnis = solver.berechnen(geaendert, bestand=basis_ergebnis.plan)
    assert ergebnis.konflikte == []
    # Die Zuweisung wurde aufgelöst und systemgestützt ersetzt
    for z in ergebnis.plan.zuweisungen:
        assert not (pid in z.pruefer_ids and bid in z.bewerber_ids)
    _stabil(ergebnis, basis_ergebnis.plan)


# ---------------------------------------------------------------------------
# Szenario 5: Raumausfall / Ersatzraum
# ---------------------------------------------------------------------------

def test_szenario_5_raumausfall(basis):
    kontext, basis_ergebnis = basis
    # Ein belegter kleiner Raum fällt aus (bei großen Räumen ist die Kapazität
    # knapp bemessen — deren Totalausfall wird korrekt als H6-Konflikt gemeldet,
    # siehe test_unloesbar_wird_benannt in M3)
    from app.db.models import Raumgroesse

    rid = next(
        z.raum_id for z in basis_ergebnis.plan.zuweisungen
        if kontext.raeume[z.raum_id].groesse == Raumgroesse.KLEIN
    )
    geaendert = replace(kontext, raeume={
        **kontext.raeume, rid: replace(kontext.raeume[rid], aktiv=False)
    })
    ergebnis = solver.berechnen(geaendert, bestand=basis_ergebnis.plan)
    assert ergebnis.konflikte == []
    # Betroffene Slots liegen jetzt in verfügbaren, formatgeeigneten Räumen (H6)
    assert all(z.raum_id != rid for z in ergebnis.plan.zuweisungen)
    _stabil(ergebnis, basis_ergebnis.plan)


# ---------------------------------------------------------------------------
# Stabilität ohne Datenänderung: Neuberechnung ändert (fast) nichts
# ---------------------------------------------------------------------------

def test_neuberechnung_ohne_aenderung_ist_stabil(basis):
    kontext, basis_ergebnis = basis
    ergebnis = solver.berechnen(kontext, bestand=basis_ergebnis.plan)
    assert ergebnis.konflikte == []
    _stabil(ergebnis, basis_ergebnis.plan, mindestens=0.9)
