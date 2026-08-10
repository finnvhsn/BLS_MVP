"""M6-Tests: versionierter Export (F_OM_013, AK7) und Backup (NF_004)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.io import testdaten

KLEIN = dict(
    anzahl_bewerber=40, anzahl_senior=14, anzahl_junior=5,
    raeume_klein=6, raeume_gross=3, befangenheit_anzahl=2,
)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os

    os.environ["BLS_DATEN_VERZEICHNIS"] = str(tmp_path_factory.mktemp("m6daten"))
    from app.db import database

    database.engine_zuruecksetzen()
    from app.main import app

    with TestClient(app) as c:
        c.post("/api/auth/login", json={"benutzername": "verfahren", "passwort": "bls-auswahl"})
        yield c
    database.engine_zuruecksetzen()
    os.environ.pop("BLS_DATEN_VERZEICHNIS", None)


@pytest.fixture(scope="module")
def jahrgang_id(client, tmp_path_factory):
    jid = client.post("/api/jahrgaenge", json={"bezeichnung": "Export 2026/2027"}).json()["id"]
    pfade = testdaten.generieren(tmp_path_factory.mktemp("m6td"), seed=7, **KLEIN)
    for typ in ("bewerbende", "pruefende", "raeume", "befangenheiten"):
        r = client.post(f"/api/jahrgaenge/{jid}/import/{typ}",
                        files={"datei": (f"{typ}.csv", pfade[typ].read_bytes(), "text/csv")})
        assert r.json()["fehler"] == []
    konf = client.get(f"/api/jahrgaenge/{jid}/konfiguration").json()
    konf["solver"]["timeout_sekunden"] = 40
    client.put(f"/api/jahrgaenge/{jid}/konfiguration", json=konf)
    client.post(f"/api/jahrgaenge/{jid}/gruppen/einteilen", json={})
    r = client.post(f"/api/jahrgaenge/{jid}/berechnen",
                    json={"neuberechnung": False, "synchron": True})
    assert r.json()["status"] == "fertig"
    return jid


def test_export_ohne_planungsstand(client):
    jid = client.post("/api/jahrgaenge", json={"bezeichnung": "Leer"}).json()["id"]
    r = client.post(f"/api/jahrgaenge/{jid}/export")
    assert r.status_code == 404
    assert "zuerst berechnen" in r.json()["detail"]


def test_export_versioniert_und_wiederholbar(client, jahrgang_id):
    e1 = client.post(f"/api/jahrgaenge/{jahrgang_id}/export").json()
    e2 = client.post(f"/api/jahrgaenge/{jahrgang_id}/export").json()
    assert (e1["version"], e2["version"]) == (1, 2)          # versioniert + wiederholbar
    laeufe = client.get(f"/api/jahrgaenge/{jahrgang_id}/export/laeufe").json()
    assert [l["version"] for l in laeufe] == [2, 1]

    r = client.get(f"/api/export/{e1['id']}/datei")
    assert r.status_code == 200
    inhalt = r.content.decode("utf-8-sig")
    kopf = inhalt.splitlines()[0].split(";")
    # AK7: Person, Tag, Zeitfenster, Raum, Format, Gruppe + Zuordnung
    for spalte in ("tag", "zeit_von", "zeit_bis", "format", "raum", "gruppe",
                   "person_id", "partner_ids"):
        assert spalte in kopf
    # Jede Zeile trägt die Exportversion; Bewerber- und Prüferzeilen vorhanden
    zeilen = inhalt.strip().splitlines()[1:]
    assert all(z.startswith("1;") for z in zeilen)
    rollen = {z.split(";")[8] for z in zeilen}
    assert rollen == {"Bewerber", "Pruefer"}


def test_backup_und_liste(client, jahrgang_id):
    r = client.post("/api/backup")
    assert r.status_code == 200
    datei = r.json()["datei"]
    assert datei in client.get("/api/backup/liste").json()
