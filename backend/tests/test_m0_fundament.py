"""M0-Smoke-Tests: App startet, Schema wird angelegt, Auth funktioniert."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BLS_DATEN_VERZEICHNIS", str(tmp_path))
    from app.db import database

    database.engine_zuruecksetzen()
    from app.main import app

    with TestClient(app) as c:
        yield c
    database.engine_zuruecksetzen()


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_login_und_geschuetzte_route(client):
    # Ohne Anmeldung: 401
    assert client.get("/api/auth/ich").status_code == 401

    # Falsches Passwort: 401 mit deutscher Fehlermeldung
    r = client.post("/api/auth/login", json={"benutzername": "verfahren", "passwort": "falsch"})
    assert r.status_code == 401
    assert "falsch" in r.json()["detail"]

    # Korrekte Anmeldung (Default-Zugangsdaten der lokalen Entwicklung)
    r = client.post("/api/auth/login", json={"benutzername": "verfahren", "passwort": "bls-auswahl"})
    assert r.status_code == 200
    assert r.json()["rolle"] == "Verfahrensorganisation"

    r = client.get("/api/auth/ich")
    assert r.status_code == 200
    assert r.json()["benutzername"] == "verfahren"

    # Abmeldung invalidiert die Sitzung
    client.post("/api/auth/logout")
    assert client.get("/api/auth/ich").status_code == 401


def test_standard_konfiguration_valide():
    from app.core.konfiguration import standard_konfiguration

    konf = standard_konfiguration()
    assert konf.zeitmodell.start_min == 600      # 10:00
    assert konf.zeitmodell.ende_min == 1035      # 17:15
    assert len(konf.formate) == 4
    # 8 Touchpoints: 1+1+3+3
    assert sum(f.anzahl_pruefer for f in konf.formate) == 8
    assert konf.format("thesenvortrag").dauer_min == 150


def test_mindestpause_liegt_auf_dem_raster():
    """Abstände wirken nur auf dem 15-Minuten-Raster: Startzeiten und
    Formatdauern sind Vielfache von 15, erreichbare Lücken damit 0, 15, 30 …
    Ein Zwischenwert bliebe wirkungslos, ohne dass es auffiele — deshalb wird
    er abgelehnt statt still gerundet."""
    import pytest as _pytest

    from app.core.konfiguration import Zeitmodell

    assert Zeitmodell(mindestpause_min=0).mindestpause_min == 0
    assert Zeitmodell(mindestpause_min=30).mindestpause_min == 30
    with _pytest.raises(ValueError, match="Vielfaches"):
        Zeitmodell(mindestpause_min=10)


def test_zeitmodell_kennt_keinen_gruppenpuffer_mehr():
    """Der frühere ``puffer_min`` ist ersatzlos entfallen — er wäre nur
    oberhalb der Mindestpause sichtbar geworden. Gespeicherte Konfigurationen
    tragen den Schlüssel noch und müssen weiterhin fehlerfrei laden."""
    from app.core.konfiguration import Zeitmodell

    assert not hasattr(Zeitmodell(), "puffer_min")
    alt = Zeitmodell.model_validate(
        {"tag_start": "10:00", "tag_ende": "17:15", "puffer_min": 10, "mindestpause_min": 15}
    )
    assert alt.mindestpause_min == 15
