"""M5-Tests: REST-API entlang des geführten Prozesses (NF_009):
Anmeldung → Jahrgang → Import → Parametrierung → Gruppen → Zuweisung →
Kontrolle (Plan + Konflikte) → Umbuchung mit Live-Validierung."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.io import testdaten

KLEIN = dict(  # kleine Instanz für schnelle API-Tests
    anzahl_bewerber=60, anzahl_senior=16, anzahl_junior=6,
    raeume_klein=8, raeume_gross=4, befangenheit_anzahl=4,
)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os

    os.environ["BLS_DATEN_VERZEICHNIS"] = str(tmp_path_factory.mktemp("m5daten"))
    from app.db import database

    database.engine_zuruecksetzen()
    from app.main import app

    with TestClient(app) as c:
        r = c.post("/api/auth/login",
                   json={"benutzername": "verfahren", "passwort": "bls-auswahl"})
        assert r.status_code == 200
        yield c
    database.engine_zuruecksetzen()
    os.environ.pop("BLS_DATEN_VERZEICHNIS", None)


@pytest.fixture(scope="module")
def jahrgang_id(client, tmp_path_factory):
    r = client.post("/api/jahrgaenge", json={"bezeichnung": "API 2026/2027"})
    assert r.status_code == 201, r.text
    jid = r.json()["id"]

    pfade = testdaten.generieren(tmp_path_factory.mktemp("m5td"), seed=42, **KLEIN)
    for typ in ("bewerbende", "pruefende", "raeume", "befangenheiten"):
        r = client.post(
            f"/api/jahrgaenge/{jid}/import/{typ}",
            files={"datei": (f"{typ}.csv", pfade[typ].read_bytes(), "text/csv")},
        )
        assert r.status_code == 200, r.text
        assert r.json()["fehler"] == []
    return jid


@pytest.fixture(scope="module")
def berechnet(client, jahrgang_id):
    # Parametrierung: kurzer Solver-Timeout für den Test (F_OM_010)
    konf = client.get(f"/api/jahrgaenge/{jahrgang_id}/konfiguration").json()
    konf["solver"]["schritt_budget_sekunden"] = 15
    r = client.put(f"/api/jahrgaenge/{jahrgang_id}/konfiguration", json=konf)
    assert r.status_code == 200, r.text

    r = client.post(f"/api/jahrgaenge/{jahrgang_id}/gruppen/einteilen", json={})
    assert r.status_code == 200
    assert r.json()["gruppen_fr"] >= 1 and r.json()["gruppen_sa"] >= 1

    r = client.post(f"/api/jahrgaenge/{jahrgang_id}/berechnen",
                    json={"neuberechnung": False, "synchron": True})
    assert r.status_code == 200, r.text
    status = r.json()
    assert status["status"] == "fertig", status
    assert status["konflikte"] == 0
    return status


def test_auth_erzwungen(client, jahrgang_id):
    ohne_cookie = TestClient(client.app)
    assert ohne_cookie.get("/api/jahrgaenge").status_code == 401


def test_import_fehler_deutsch(client, jahrgang_id):
    kaputt = "bewerber_id;nachname\nBW-X;Muster\n".encode()
    r = client.post(
        f"/api/jahrgaenge/{jahrgang_id}/import/bewerbende",
        files={"datei": ("kaputt.csv", kaputt, "text/csv")},
    )
    assert r.status_code == 200
    fehler = r.json()["fehler"]
    assert any("Pflichtspalte" in f["meldung"] for f in fehler)


def test_konfiguration_validierung(client, jahrgang_id):
    konf = client.get(f"/api/jahrgaenge/{jahrgang_id}/konfiguration").json()
    konf["zeitmodell"]["tag_ende"] = "09:00"  # Ende vor Beginn
    r = client.put(f"/api/jahrgaenge/{jahrgang_id}/konfiguration", json=konf)
    assert r.status_code == 422
    assert "Konfiguration ungültig" in r.json()["detail"]


def test_plan_ansicht(client, jahrgang_id, berechnet):
    r = client.get(f"/api/jahrgaenge/{jahrgang_id}/plan")
    assert r.status_code == 200
    plan = r.json()
    assert plan["planungsstand"]["version"] == 1
    assert plan["konflikte"] == []
    assert len(plan["zuweisungen"]) > 0
    z = plan["zuweisungen"][0]
    for feld in ("tag", "format_name", "start", "ende", "raumnummer", "bewerber", "pruefer"):
        assert feld in z
    # Kennzahlen ausgewiesen (AK8)
    kz = plan["planungsstand"]["kennzahlen"]
    assert "w5_wartezeit_summe_min" in kz and "w1_erfuellt" in kz


def test_umbuchung_mit_live_validierung(client, jahrgang_id, berechnet):
    plan = client.get(f"/api/jahrgaenge/{jahrgang_id}/plan").json()
    einzel = [z for z in plan["zuweisungen"] if z["format_typ"] == "einzel"]
    z1 = einzel[0]
    # Prüfer:in eines anderen Einzelgesprächs derselben Person → H1-Konflikt
    andere = next(z for z in einzel
                  if z["bewerber"][0]["id"] == z1["bewerber"][0]["id"] and z["id"] != z1["id"])
    r = client.post(f"/api/jahrgaenge/{jahrgang_id}/umbuchen", json={
        "zuweisung_id": z1["id"],
        "pruefer_ids": [andere["pruefer"][0]["id"]],
    })
    assert r.status_code == 200
    antwort = r.json()
    assert antwort["uebernommen"] is False
    assert any(k["regel"] == "H1" for k in antwort["konflikte"])
    assert "Doppelbegegnung" in antwort["konflikte"][0]["meldung"]

    # Dieselbe Änderung mit bewusster Bestätigung wird übernommen (F_OM_016)
    r = client.post(f"/api/jahrgaenge/{jahrgang_id}/umbuchen", json={
        "zuweisung_id": z1["id"],
        "pruefer_ids": [andere["pruefer"][0]["id"]],
        "bestaetigt": True,
    })
    assert r.json()["uebernommen"] is True
    version_nach_konflikt = r.json()["version"]

    # Der Konflikt erscheint jetzt in der Kontrolle, Zuweisung ist markiert
    plan2 = client.get(f"/api/jahrgaenge/{jahrgang_id}/plan").json()
    assert plan2["planungsstand"]["version"] == version_nach_konflikt
    assert any(k["regel"] == "H1" for k in plan2["konflikte"])
    konflikt = next(k for k in plan2["konflikte"] if k["regel"] == "H1")
    markierte = [z for z in plan2["zuweisungen"] if z["konflikt"]]
    assert set(konflikt["zuweisungen"]) <= {z["id"] for z in markierte}

    # Regelkonforme Umbuchung zurück auf die ursprüngliche Prüferin
    r = client.post(f"/api/jahrgaenge/{jahrgang_id}/umbuchen", json={
        "zuweisung_id": next(
            z["id"] for z in plan2["zuweisungen"]
            if z["start"] == z1["start"] and z["raumnummer"] == z1["raumnummer"]
            and z["tag"] == z1["tag"]
        ),
        "pruefer_ids": [z1["pruefer"][0]["id"]],
    })
    assert r.json()["uebernommen"] is True
    plan3 = client.get(f"/api/jahrgaenge/{jahrgang_id}/plan").json()
    assert plan3["konflikte"] == []


def test_umbuchung_meldet_unterschrittene_mindestpause(client, jahrgang_id, berechnet):
    """H10 in der Live-Validierung: Der Solver hält die Wegzeit ein, ein
    Handeingriff darf sie nicht unbemerkt unterlaufen (F_OM_016)."""
    plan = client.get(f"/api/jahrgaenge/{jahrgang_id}/plan").json()
    einzel = [z for z in plan["zuweisungen"] if z["format_typ"] == "einzel"]

    # Zwei Termine derselben Person suchen und den späteren direkt an das Ende
    # des früheren legen — 0 Minuten für den Raumwechsel.
    z1 = einzel[0]
    bewerber_id = z1["bewerber"][0]["id"]
    eigene = sorted(
        (z for z in plan["zuweisungen"] if any(b["id"] == bewerber_id for b in z["bewerber"])),
        key=lambda z: z["start_min"],
    )
    vorher, nachher = eigene[0], eigene[1]

    from app.core.konfiguration import hhmm

    r = client.post(f"/api/jahrgaenge/{jahrgang_id}/umbuchen", json={
        "zuweisung_id": nachher["id"], "start": hhmm(vorher["ende_min"]),
    })
    assert r.status_code == 200, r.text
    antwort = r.json()
    assert antwort["uebernommen"] is False
    h10 = [k for k in antwort["konflikte"] if k["regel"] == "H10"]
    assert h10, antwort["konflikte"]
    assert h10[0]["titel"] == "Mindestpause zwischen Terminen"
    assert "Raumwechsel" in h10[0]["meldung"]


def test_planungsstaende_versioniert(client, jahrgang_id, berechnet):
    staende = client.get(f"/api/jahrgaenge/{jahrgang_id}/planungsstaende").json()
    versionen = [s["version"] for s in staende]
    assert versionen == sorted(versionen, reverse=True)
    assert {s["typ"] for s in staende} >= {"Vollberechnung", "Manuell"}


def test_protokoll_vollstaendig(client, jahrgang_id, berechnet):
    protokoll = client.get(f"/api/jahrgaenge/{jahrgang_id}/protokoll").json()
    aktionen = {p["aktion"] for p in protokoll}
    assert {"Import Bewerbende", "Konfiguration geändert", "Gruppen eingeteilt",
            "Berechnung gestartet", "Berechnung abgeschlossen", "Umbuchung"} <= aktionen


def test_gruppen_verschieben_haelt_tagesbindung(client, jahrgang_id, berechnet):
    gruppen = client.get(f"/api/jahrgaenge/{jahrgang_id}/gruppen").json()
    fr = next(g for g in gruppen if g["tag"] == "Fr")
    sa = next(g for g in gruppen if g["tag"] == "Sa")
    # H7: Verschieben in eine Gruppe des falschen Tages wird abgelehnt
    r = client.post(f"/api/jahrgaenge/{jahrgang_id}/gruppen/verschieben", json={
        "bewerber_id": fr["mitglieder"][0]["id"], "gruppe_id": sa["id"],
    })
    assert r.status_code == 422
    assert "H7" in r.json()["detail"]
    # Innerhalb des Tages funktioniert es
    fr2 = next(g for g in gruppen if g["tag"] == "Fr" and g["id"] != fr["id"])
    r = client.post(f"/api/jahrgaenge/{jahrgang_id}/gruppen/verschieben", json={
        "bewerber_id": fr["mitglieder"][0]["id"], "gruppe_id": fr2["id"],
    })
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Versionierung der Planungsstände
# ---------------------------------------------------------------------------

def _stand_anlegen(jahrgang_id: int, version: int):
    """Legt einen leeren Planungsstand direkt in der Datenbank an — die
    Versionskollision, die dieser Abschnitt prüft, lässt sich über die API
    nicht mehr herstellen."""
    from sqlmodel import Session

    from app.db.database import engine
    from app.db.models import Planungsstand, PlanungsstandTyp

    with Session(engine()) as session:
        stand = Planungsstand(jahrgang_id=jahrgang_id, version=version,
                              typ=PlanungsstandTyp.VOLLBERECHNUNG, seed=42,
                              parameter={}, kennzahlen={}, konflikte=[])
        session.add(stand)
        session.commit()
        session.refresh(stand)
        return stand.id


def test_naechste_version_zaehlt_ueber_vollberechnungen_weiter(client):
    """Der Bestandsfehler: eine zweite Vollberechnung erbt keinen Stand und
    bekam deshalb erneut die Version 1 — ein Jahrgang hatte dann mehrere
    gleich nummerierte Stände."""
    from sqlmodel import Session

    from app.api.jahrgaenge import naechste_version
    from app.db.database import engine

    jid = client.post("/api/jahrgaenge", json={"bezeichnung": "Versionen"}).json()["id"]
    with Session(engine()) as session:
        assert naechste_version(session, jid) == 1
    _stand_anlegen(jid, 1)
    with Session(engine()) as session:
        assert naechste_version(session, jid) == 2
    _stand_anlegen(jid, 2)
    _stand_anlegen(jid, 3)
    with Session(engine()) as session:
        assert naechste_version(session, jid) == 4


def test_gleiche_version_alle_wege_zeigen_denselben_stand(client):
    """Bei gleicher Versionsnummer entscheidet der jüngere Datensatz — und
    zwar überall gleich. Vorher hatte jeder Endpunkt seine eigene Abfrage
    ohne Zweitschlüssel, sodass Kontrolle, Export und Druck auseinanderlaufen
    konnten."""
    from sqlmodel import Session

    from app.api.jahrgaenge import letzter_planungsstand
    from app.db.database import engine
    from app.db.models import ExportLauf

    jid = client.post("/api/jahrgaenge", json={"bezeichnung": "Tiebreak"}).json()["id"]
    alt = _stand_anlegen(jid, 1)
    jung = _stand_anlegen(jid, 1)          # dieselbe Version, jüngerer Datensatz
    assert jung > alt

    with Session(engine()) as session:
        assert letzter_planungsstand(session, jid).id == jung

    plan = client.get(f"/api/jahrgaenge/{jid}/plan").json()
    assert plan["planungsstand"]["id"] == jung

    staende = client.get(f"/api/jahrgaenge/{jid}/planungsstaende").json()
    assert staende[0]["id"] == jung

    r = client.post(f"/api/jahrgaenge/{jid}/export")
    assert r.status_code == 200, r.text
    with Session(engine()) as session:
        lauf = session.get(ExportLauf, r.json()["id"])
        assert lauf.planungsstand_id == jung


def test_druck_lehnt_fremden_planungsstand_ab(client, jahrgang_id, berechnet):
    """Ein Stand aus einem anderen Jahrgang ist nicht druckbar — sonst ließe
    sich über die stand_id ein fremder Plan ausgeben."""
    fremd = client.post("/api/jahrgaenge", json={"bezeichnung": "Fremd"}).json()["id"]
    fremder_stand = _stand_anlegen(fremd, 1)
    r = client.get(f"/api/jahrgaenge/{jahrgang_id}/druck/raumschilder",
                   params={"stand_id": fremder_stand})
    assert r.status_code == 404


def test_umbuchung_kollidiert_nicht_mit_der_versionsvergabe(client, jahrgang_id, berechnet):
    """Auch die Umbuchung vergibt über dieselbe Stelle — der neue Stand liegt
    über allen bestehenden Versionen des Jahrgangs."""
    staende = client.get(f"/api/jahrgaenge/{jahrgang_id}/planungsstaende").json()
    hoechste = max(s["version"] for s in staende)
    plan = client.get(f"/api/jahrgaenge/{jahrgang_id}/plan").json()
    z = plan["zuweisungen"][0]
    r = client.post(f"/api/jahrgaenge/{jahrgang_id}/umbuchen", json={
        "zuweisung_id": z["id"], "raum_id": z["raum_id"], "bestaetigt": True,
    })
    assert r.status_code == 200, r.text
    assert r.json()["version"] == hoechste + 1


def test_jahrgang_loeschen(client):
    """NF_001: Jahrgangs-Löschfunktion entfernt alle personenbezogenen Daten."""
    r = client.post("/api/jahrgaenge", json={"bezeichnung": "Löschtest"})
    jid = r.json()["id"]
    r = client.delete(f"/api/jahrgaenge/{jid}")
    assert r.status_code == 200
    assert jid not in [j["id"] for j in client.get("/api/jahrgaenge").json()]
