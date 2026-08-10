"""M2-Tests: Regelkatalog H1–H9 (Positiv/Negativ je Regel) und W-Metriken.

Aufbau: ein kleines, vollständig gültiges Mini-Verfahren (4 Bewerbende einer
Gruppe am Fr, 12 Senior + 2 Junior, 2 kleine + 1 großer Raum). Jeder Testfall
bricht gezielt genau eine Regel und erwartet den benannten Konflikt.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.konfiguration import standard_konfiguration
from app.core.plan import (
    BewerberInfo,
    GruppeInfo,
    Plan,
    PlanKontext,
    PlanZuweisung,
    PrueferInfo,
    RaumInfo,
)
from app.core.rules import (
    kennzahlen_berechnen,
    w1_kontakte_je_bewerber,
    w1_zielwert,
    w2_auslastung_je_pruefer,
    w3_diversitaet_gruppe,
    w5_wartezeiten,
    w6_stabilitaet,
)
from app.core.validator import aenderung_validieren, plan_validieren
from app.db.models import PrueferStatus, Raumgroesse, Rueckmeldestatus, Tag


def _bewerber(bid: int, **kwargs) -> BewerberInfo:
    defaults = dict(
        id=bid, name=f"Bewerber{bid}", vorname="Test", tag=Tag.FR,
        geschlecht="w" if bid % 2 else "m", studiengang="Rechtswissenschaft",
        zugelassen=True, aktiv=True, rueckmeldestatus=Rueckmeldestatus.ZUSAGE,
        ruecksteller=False, gruppe_id=1, import_key=f"BW-{bid}",
    )
    defaults.update(kwargs)
    return BewerberInfo(**defaults)


def _pruefer(pid: int, junior: bool = False, **kwargs) -> PrueferInfo:
    defaults = dict(
        id=pid, name=f"Pruefer{pid}", vorname="Test",
        geschlecht="w" if pid % 2 else "m",
        status=PrueferStatus.JUNIOR if junior else PrueferStatus.SENIOR,
        verfuegbar_fr=True, verfuegbar_sa=True, aktiv=True, import_key=f"PR-{pid}",
    )
    defaults.update(kwargs)
    return PrueferInfo(**defaults)


def _raum(rid: int, gross: bool = False, **kwargs) -> RaumInfo:
    defaults = dict(
        id=rid, raumnummer=f"R-{rid}",
        groesse=Raumgroesse.GROSS if gross else Raumgroesse.KLEIN,
        verfuegbar_fr=True, verfuegbar_sa=True, sperrzeiten=(), aktiv=True,
    )
    defaults.update(kwargs)
    return RaumInfo(**defaults)


@pytest.fixture()
def kontext() -> PlanKontext:
    # Senior 1–12, Junior 13–14; Räume: 1+2 klein, 3 groß
    return PlanKontext(
        konfiguration=standard_konfiguration(),
        bewerber={i: _bewerber(i) for i in (1, 2, 3, 4)},
        pruefer={**{i: _pruefer(i) for i in range(1, 13)},
                 **{i: _pruefer(i, junior=True) for i in (13, 14)}},
        raeume={1: _raum(1), 2: _raum(2), 3: _raum(3, gross=True)},
        gruppen={1: GruppeInfo(id=1, tag=Tag.FR, nummer=1)},
        befangenheiten=frozenset(),
    )


def _z(format_key: str, start: int, dauer: int, raum: int,
       bewerber: set, pruefer: set, gruppe: int | None = None) -> PlanZuweisung:
    return PlanZuweisung(
        tag=Tag.FR, format_key=format_key, start_min=start, ende_min=start + dauer,
        raum_id=raum, bewerber_ids=frozenset(bewerber), pruefer_ids=frozenset(pruefer),
        gruppe_id=gruppe,
    )


@pytest.fixture()
def gueltiger_plan() -> Plan:
    """Vollständiger, regelkonformer Plan für die 4 Bewerbenden der Gruppe 1.

    8 Kontakte je Person: Einzel (2×1 Senior) + Gruppenarbeit (3er-Panel mit
    1 Junior) + Thesenvortrag (3er-Panel mit 1 Junior)."""
    return Plan(zuweisungen=[
        # Thesenvortrag: gesamte Gruppe, 2,5-h-Block (H8), Panel S9/S10/J13
        _z("thesenvortrag", 600, 150, 3, {1, 2, 3, 4}, {9, 10, 13}, gruppe=1),
        # Gruppenarbeit nach 15 min Kaffeepause, Panel S11/S12/J14
        _z("gruppenarbeit", 765, 45, 3, {1, 2, 3, 4}, {11, 12, 14}, gruppe=1),
        # Einzelgespräche: je Person 2 verschiedene Senior-Prüfende
        _z("einzel_1", 810, 30, 1, {1}, {1}),
        _z("einzel_2", 840, 30, 1, {1}, {5}),
        _z("einzel_1", 870, 30, 1, {3}, {3}),
        _z("einzel_2", 900, 30, 1, {3}, {7}),
        _z("einzel_1", 810, 30, 2, {2}, {2}),
        _z("einzel_2", 840, 30, 2, {2}, {6}),
        _z("einzel_1", 870, 30, 2, {4}, {4}),
        _z("einzel_2", 900, 30, 2, {4}, {8}),
    ])


def _regeln(konflikte) -> set[str]:
    return {k.regel for k in konflikte}


# ---------------------------------------------------------------------------
# Positivfall: Der gültige Plan hat keinerlei Konflikte
# ---------------------------------------------------------------------------

def test_gueltiger_plan_ohne_konflikte(gueltiger_plan, kontext):
    assert plan_validieren(gueltiger_plan, kontext) == []


# ---------------------------------------------------------------------------
# H1 — Keine Doppelbegegnung
# ---------------------------------------------------------------------------

def test_h1_doppelbegegnung(gueltiger_plan, kontext):
    # S1 prüft Bewerber 1 in beiden Einzelgesprächen
    plan = gueltiger_plan.ersetzt(3, replace(
        gueltiger_plan.zuweisungen[3], pruefer_ids=frozenset({1})
    ))
    konflikte = plan_validieren(plan, kontext)
    h1 = [k for k in konflikte if k.regel == "H1"]
    assert len(h1) == 1
    assert h1[0].pruefer_ids == [1] and h1[0].bewerber_ids == [1]
    assert "Doppelbegegnung" in h1[0].meldung
    assert sorted(h1[0].zuweisungen) == [2, 3]


def test_h1_gilt_ueber_formate_hinweg(gueltiger_plan, kontext):
    # Panel-Prüfer S9 (Thesenvortrag, sieht alle 4) zusätzlich im Einzelgespräch von 1
    plan = gueltiger_plan.ersetzt(3, replace(
        gueltiger_plan.zuweisungen[3], pruefer_ids=frozenset({9})
    ))
    assert "H1" in _regeln(plan_validieren(plan, kontext))


# ---------------------------------------------------------------------------
# H2 — Befangenheit
# ---------------------------------------------------------------------------

def test_h2_befangenheit(gueltiger_plan, kontext):
    kontext.befangenheiten = frozenset({(9, 2)})  # S9 befangen ggü. Bewerber 2
    konflikte = plan_validieren(gueltiger_plan, kontext)
    h2 = [k for k in konflikte if k.regel == "H2"]
    assert len(h2) == 1
    assert h2[0].zuweisungen == [0]  # Thesenvortrag
    assert "Befangenheit" in h2[0].meldung


# ---------------------------------------------------------------------------
# H3 — Prüfergruppen-Zusammensetzung
# ---------------------------------------------------------------------------

def test_h3_zu_viele_junioren(gueltiger_plan, kontext):
    plan = gueltiger_plan.ersetzt(1, replace(
        gueltiger_plan.zuweisungen[1], pruefer_ids=frozenset({11, 13, 14})
    ))
    konflikte = [k for k in plan_validieren(plan, kontext) if k.regel == "H3"]
    # 2 Junioren (max. 1) UND nur 1 Senior (min. 2)
    assert len(konflikte) == 2
    assert any("Junior" in k.meldung for k in konflikte)
    assert any("Senior" in k.meldung for k in konflikte)


def test_h3_gilt_nicht_fuer_einzel(gueltiger_plan, kontext):
    # Einzelgespräch mit 1 Senior verletzt H3 nicht (nur H4 relevant)
    assert "H3" not in _regeln(plan_validieren(gueltiger_plan, kontext))


# ---------------------------------------------------------------------------
# H4 — Einzelgespräche nur Senior
# ---------------------------------------------------------------------------

def test_h4_junior_im_einzelgespraech(gueltiger_plan, kontext):
    plan = gueltiger_plan.ersetzt(2, replace(
        gueltiger_plan.zuweisungen[2], pruefer_ids=frozenset({13})
    ))
    konflikte = [k for k in plan_validieren(plan, kontext) if k.regel == "H4"]
    assert len(konflikte) == 1
    assert konflikte[0].pruefer_ids == [13]
    assert "nur Senior" in konflikte[0].meldung


# ---------------------------------------------------------------------------
# H5 — Keine Doppelbelegung & Personen-Verfügbarkeit
# ---------------------------------------------------------------------------

def test_h5_bewerber_doppelt_verplant(gueltiger_plan, kontext):
    # Einzel 2 von Bewerber 1 parallel zu Einzel 1 (anderer Raum, andere:r Prüfer:in)
    plan = gueltiger_plan.ersetzt(3, replace(
        gueltiger_plan.zuweisungen[3], start_min=810, ende_min=840, raum_id=2
    ))
    konflikte = plan_validieren(plan, kontext)
    assert any(k.regel == "H5" and k.bewerber_ids == [1] for k in konflikte)


def test_h5_raum_doppelt_belegt(gueltiger_plan, kontext):
    # Einzel von Bewerber 3 in Raum 2, wo zeitgleich Bewerber 4 geprüft wird
    plan = gueltiger_plan.ersetzt(4, replace(
        gueltiger_plan.zuweisungen[4], raum_id=2
    ))
    konflikte = plan_validieren(plan, kontext)
    assert any(k.regel == "H5" and k.raum_id == 2 for k in konflikte)


def test_h5_pruefer_nicht_verfuegbar(gueltiger_plan, kontext):
    kontext.pruefer[1] = _pruefer(1, verfuegbar_fr=False)
    konflikte = plan_validieren(gueltiger_plan, kontext)
    assert any(k.regel == "H5" and k.pruefer_ids == [1] and "nicht verfügbar" in k.meldung
               for k in konflikte)


def test_h5_abgesagte_person_verplant(gueltiger_plan, kontext):
    kontext.bewerber[2] = _bewerber(2, rueckmeldestatus=Rueckmeldestatus.ABSAGE)
    konflikte = plan_validieren(gueltiger_plan, kontext)
    assert any(k.regel == "H5" and 2 in k.bewerber_ids and "nimmt aber nicht" in k.meldung
               for k in konflikte)


# ---------------------------------------------------------------------------
# H6 — Raumeignung & -verfügbarkeit
# ---------------------------------------------------------------------------

def test_h6_falsche_raumgroesse(gueltiger_plan, kontext):
    # Einzelgespräch im großen Raum
    plan = gueltiger_plan.ersetzt(2, replace(gueltiger_plan.zuweisungen[2], raum_id=3))
    konflikte = plan_validieren(plan, kontext)
    assert any(k.regel == "H6" and "ungeeignet" in k.meldung for k in konflikte)


def test_h6_sperrzeit(gueltiger_plan, kontext):
    kontext.raeume[1] = _raum(1, sperrzeiten=({"tag": "Fr", "von_min": 800, "bis_min": 830},))
    konflikte = plan_validieren(gueltiger_plan, kontext)
    assert any(k.regel == "H6" and k.raum_id == 1 and "nicht verfügbar" in k.meldung
               for k in konflikte)


def test_h6_raum_ausgefallen(gueltiger_plan, kontext):
    kontext.raeume[3] = _raum(3, gross=True, aktiv=False)
    konflikte = plan_validieren(gueltiger_plan, kontext)
    assert any(k.regel == "H6" and k.raum_id == 3 for k in konflikte)


# ---------------------------------------------------------------------------
# H7 — Vollständigkeit & Tagesbindung
# ---------------------------------------------------------------------------

def test_h7_falscher_tag(gueltiger_plan, kontext):
    kontext.bewerber[1] = _bewerber(1, tag=Tag.SA)  # Access sagt: Samstag
    konflikte = plan_validieren(gueltiger_plan, kontext)
    h7 = [k for k in konflikte if k.regel == "H7" and 1 in k.bewerber_ids]
    assert any("Tag" in k.meldung and "Sa" in k.meldung for k in h7)


def test_h7_fehlendes_format(gueltiger_plan, kontext):
    plan = Plan(zuweisungen=gueltiger_plan.zuweisungen[:-1])  # Einzel 2 von Bewerber 4 fehlt
    konflikte = plan_validieren(plan, kontext)
    h7 = [k for k in konflikte if k.regel == "H7"]
    assert len(h7) == 1
    assert h7[0].bewerber_ids == [4] and "Einzelgespräch 2" in h7[0].meldung


def test_h7_doppeltes_format(gueltiger_plan, kontext):
    plan = Plan(zuweisungen=gueltiger_plan.zuweisungen + [
        _z("einzel_1", 930, 30, 1, {1}, {12})
    ])
    konflikte = plan_validieren(plan, kontext)
    assert any(k.regel == "H7" and "2-mal" in k.meldung for k in konflikte)


# ---------------------------------------------------------------------------
# H8 — Formatdauern & Zeitmodell
# ---------------------------------------------------------------------------

def test_h8_falsche_dauer(gueltiger_plan, kontext):
    plan = gueltiger_plan.ersetzt(2, replace(gueltiger_plan.zuweisungen[2], ende_min=855))
    konflikte = plan_validieren(plan, kontext)
    assert any(k.regel == "H8" and "45 min" in k.meldung for k in konflikte)


def test_h8_ausserhalb_tagesfenster(gueltiger_plan, kontext):
    # Einzelgespräch endet 17:30 — Tagesende ist 17:15
    plan = gueltiger_plan.ersetzt(3, replace(
        gueltiger_plan.zuweisungen[3], start_min=1020, ende_min=1050
    ))
    konflikte = plan_validieren(plan, kontext)
    assert any(k.regel == "H8" and "Tagesfenster" in k.meldung for k in konflikte)


def test_h8_thesenvortrag_blockt_gesamte_gruppe(gueltiger_plan, kontext):
    plan = gueltiger_plan.ersetzt(0, replace(
        gueltiger_plan.zuweisungen[0], bewerber_ids=frozenset({1, 2, 3})
    ))
    konflikte = plan_validieren(plan, kontext)
    assert any(k.regel == "H8" and k.bewerber_ids == [4] for k in konflikte)


# ---------------------------------------------------------------------------
# W-Metriken
# ---------------------------------------------------------------------------

def test_w1_acht_kontakte(gueltiger_plan, kontext):
    assert w1_zielwert(kontext) == 8
    kontakte = w1_kontakte_je_bewerber(gueltiger_plan, kontext)
    assert kontakte == {1: 8, 2: 8, 3: 8, 4: 8}


def test_w2_auslastung(gueltiger_plan, kontext):
    auslastung = w2_auslastung_je_pruefer(gueltiger_plan, kontext)
    assert auslastung[9] == 4   # Panel sieht alle 4
    assert auslastung[1] == 1   # Einzelprüfer sieht 1


def test_w3_diversitaet():
    kontext = PlanKontext(
        konfiguration=standard_konfiguration(),
        bewerber={
            1: _bewerber(1, geschlecht="w", studiengang="A"),
            2: _bewerber(2, geschlecht="w", studiengang="A"),
            3: _bewerber(3, geschlecht="m", studiengang="B"),
            4: _bewerber(4, geschlecht="m", studiengang="B"),
            5: _bewerber(5, geschlecht="w", studiengang="A"),
            6: _bewerber(6, geschlecht="w", studiengang="A"),
        },
        pruefer={}, raeume={}, gruppen={}, befangenheiten=frozenset(),
    )
    assert w3_diversitaet_gruppe([1, 2, 3, 4], kontext) == 1.0   # perfekt gemischt
    assert w3_diversitaet_gruppe([1, 2, 5, 6], kontext) == 0.0   # homogen


def test_w5_wartezeiten(gueltiger_plan, kontext):
    wartezeiten = w5_wartezeiten(gueltiger_plan, kontext)
    # Bewerber 1: lückenlos (Pausen ≤ 15-min-Puffer) → 0 min
    assert wartezeiten[1] == 0
    # Bewerber 3: Lücke 810→870 = 60 min − 15 Puffer = 45 min
    assert wartezeiten[3] == 45


def test_w6_stabilitaet(gueltiger_plan):
    geaendert = gueltiger_plan.ersetzt(2, replace(
        gueltiger_plan.zuweisungen[2], pruefer_ids=frozenset({12})
    ))
    ergebnis = w6_stabilitaet(geaendert, gueltiger_plan)
    assert ergebnis == {"erhalten": 9, "entfallen": 1, "neu": 1}


def test_kennzahlen(gueltiger_plan, kontext):
    kennzahlen = kennzahlen_berechnen(gueltiger_plan, kontext)
    assert kennzahlen["w1_erfuellt"] == 4
    assert kennzahlen["w1_abweichler"] == {}
    assert kennzahlen["w5_wartezeit_max_min"] == 45
    assert kennzahlen["anzahl_geplante_bewerber"] == 4


# ---------------------------------------------------------------------------
# Live-Validierung (F_OM_012/F_OM_016)
# ---------------------------------------------------------------------------

def test_aenderung_validieren_meldet_konflikt(gueltiger_plan, kontext):
    # Umbuchung: S1 soll auch Einzel 2 von Bewerber 1 übernehmen → H1
    neue = replace(gueltiger_plan.zuweisungen[3], pruefer_ids=frozenset({1}))
    konflikte = aenderung_validieren(gueltiger_plan, kontext, 3, neue)
    assert "H1" in _regeln(konflikte)
    # Der Originalplan bleibt unangetastet
    assert plan_validieren(gueltiger_plan, kontext) == []


def test_aenderung_validieren_gueltige_umbuchung(gueltiger_plan, kontext):
    # S2 hat Bewerber 1 noch nie gesehen und ist um 840 frei → kein Konflikt
    neue = replace(gueltiger_plan.zuweisungen[3], pruefer_ids=frozenset({2}))
    assert aenderung_validieren(gueltiger_plan, kontext, 3, neue) == []
