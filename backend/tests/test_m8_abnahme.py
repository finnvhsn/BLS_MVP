"""M8: Ende-zu-Ende-Abnahme gegen die Akzeptanzkriterien (Kap. 11 der Spec).

Realer Ablauf über die API mit realem Mengengerüst (262 Bewerbende,
87 Prüfende, beide Tage):

    Import → Parametrierung → Zuweisung → manuelle Anpassung → Export

Läuft über ``pytest -m langsam`` (AK1, AK3 — Minuten-Laufzeit).
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.io import testdaten

pytestmark = pytest.mark.langsam


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os

    os.environ["BLS_DATEN_VERZEICHNIS"] = str(tmp_path_factory.mktemp("m8daten"))
    from app.db import database

    database.engine_zuruecksetzen()
    from app.main import app

    with TestClient(app) as c:
        c.post("/api/auth/login", json={"benutzername": "verfahren", "passwort": "bls-auswahl"})
        yield c
    database.engine_zuruecksetzen()
    os.environ.pop("BLS_DATEN_VERZEICHNIS", None)


def test_ende_zu_ende_reales_mengengeruest(client, tmp_path_factory):
    # --- Schritt 1: Import (reales Mengengerüst, Kap. 3) -------------------
    jid = client.post("/api/jahrgaenge", json={"bezeichnung": "Abnahme 2026/2027"}).json()["id"]
    pfade = testdaten.generieren(tmp_path_factory.mktemp("m8td"), seed=42)
    for typ in ("bewerbende", "pruefende", "raeume", "befangenheiten"):
        r = client.post(f"/api/jahrgaenge/{jid}/import/{typ}",
                        files={"datei": (f"{typ}.csv", pfade[typ].read_bytes(), "text/csv")})
        assert r.json()["fehler"] == [], f"Importfehler bei {typ}"
    bewerbende = client.get(f"/api/jahrgaenge/{jid}/bewerbende").json()
    assert len(bewerbende) == 262

    # --- Schritt 2: Parametrierung (Default-Konfiguration, AK9) ------------
    konf = client.get(f"/api/jahrgaenge/{jid}/konfiguration").json()
    assert konf["zeitmodell"]["tag_start"] == "10:00"
    assert konf["zeitmodell"]["tag_ende"] == "17:15"
    client.put(f"/api/jahrgaenge/{jid}/konfiguration", json=konf)

    # --- Schritt 3: Zuweisung (AK1, AK3: Vollberechnung ≤ 15 min) ----------
    client.post(f"/api/jahrgaenge/{jid}/gruppen/einteilen", json={})
    t0 = time.monotonic()
    r = client.post(f"/api/jahrgaenge/{jid}/berechnen",
                    json={"neuberechnung": False, "synchron": True})
    voll_dauer = time.monotonic() - t0
    status = r.json()
    assert status["status"] == "fertig", status
    assert voll_dauer <= 15 * 60, f"Vollberechnung dauerte {voll_dauer:.0f}s"
    assert status["konflikte"] == 0                       # AK1: regelkonform

    plan = client.get(f"/api/jahrgaenge/{jid}/plan").json()
    kz = plan["planungsstand"]["kennzahlen"]
    # AK8: W1/W2-Abweichungen und Wartezeiten ausgewiesen
    assert kz["w1_erfuellt"] == kz["anzahl_geplante_bewerber"]
    assert "w5_wartezeit_summe_min" in kz and "w2_streuung" in kz
    # AK5: Raster-Daten je Tag mit beiden Sichten möglich
    assert {z["tag"] for z in plan["zuweisungen"]} == {"Fr", "Sa"}

    # --- Schritt 4: Kontrolle & manuelle Anpassung (AK1, AK6) --------------
    einzel = [z for z in plan["zuweisungen"] if z["format_typ"] == "einzel"]
    z1 = einzel[0]
    anderes = next(z for z in einzel
                   if z["bewerber"][0]["id"] == z1["bewerber"][0]["id"] and z["id"] != z1["id"])
    # Regelwidrige Umbuchung wird benannt abgelehnt (AK6)
    r = client.post(f"/api/jahrgaenge/{jid}/umbuchen", json={
        "zuweisung_id": z1["id"], "pruefer_ids": [anderes["pruefer"][0]["id"]],
    })
    assert r.json()["uebernommen"] is False
    assert r.json()["konflikte"][0]["regel"] == "H1"
    # Regelkonforme Umbuchung: unbeteiligte:n Senior wählen (H1-frei)
    beteiligte = {p["id"] for z in plan["zuweisungen"]
                  if z1["bewerber"][0]["id"] in [b["id"] for b in z["bewerber"]]
                  for p in z["pruefer"]}
    ueberschneidung = {
        p["id"] for z in plan["zuweisungen"]
        if z["tag"] == z1["tag"] and z["start_min"] < z1["ende_min"] and z1["start_min"] < z["ende_min"]
        for p in z["pruefer"]
    }
    pruefende = client.get(f"/api/jahrgaenge/{jid}/pruefende").json()
    frei = next(p for p in pruefende
                if p["status"] == "Senior" and p["aktiv"]
                and (p["id"] not in beteiligte) and (p["id"] not in ueberschneidung)
                and (p["verfuegbar_fr"] if z1["tag"] == "Fr" else p["verfuegbar_sa"]))
    r = client.post(f"/api/jahrgaenge/{jid}/umbuchen", json={
        "zuweisung_id": z1["id"], "pruefer_ids": [frei["id"]],
    })
    antwort = r.json()
    assert antwort["uebernommen"] is True and antwort["konflikte"] == []

    plan2 = client.get(f"/api/jahrgaenge/{jid}/plan").json()
    assert plan2["konflikte"] == []                       # AK1: keine offenen Konflikte

    # --- Schritt 5: Export (AK7) -------------------------------------------
    e = client.post(f"/api/jahrgaenge/{jid}/export").json()
    assert e["version"] == 1
    inhalt = client.get(f"/api/export/{e['id']}/datei").content.decode("utf-8-sig")
    kopf = inhalt.splitlines()[0]
    for spalte in ("tag", "zeit_von", "raum", "format", "gruppe", "person_id", "partner_ids"):
        assert spalte in kopf
    # Wiederholter Export ⇒ neue Version (AK7)
    assert client.post(f"/api/jahrgaenge/{jid}/export").json()["version"] == 2

    # --- AK3: Neuberechnung nach 1 Prüferabsage deutlich schneller ---------
    pid = plan2["zuweisungen"][0]["pruefer"][0]["id"]
    client.patch(f"/api/jahrgaenge/{jid}/pruefende/{pid}", json={"aktiv": False})
    t0 = time.monotonic()
    r = client.post(f"/api/jahrgaenge/{jid}/berechnen",
                    json={"neuberechnung": True, "synchron": True})
    neu_dauer = time.monotonic() - t0
    status = r.json()
    assert status["status"] == "fertig", status
    assert status["konflikte"] == 0
    assert neu_dauer < voll_dauer, f"Neuberechnung ({neu_dauer:.0f}s) nicht schneller als Vollberechnung ({voll_dauer:.0f}s)"

    plan3 = client.get(f"/api/jahrgaenge/{jid}/plan").json()
    kz3 = plan3["planungsstand"]["kennzahlen"]
    stab = kz3["w6_stabilitaet"]
    assert stab["erhalten"] > stab["neu"]                 # AK3: maximaler Bestandserhalt
    assert all(pid not in [p["id"] for p in z["pruefer"]] for z in plan3["zuweisungen"])

    # --- AK10: Protokollierung ---------------------------------------------
    protokoll = client.get(f"/api/jahrgaenge/{jid}/protokoll").json()
    aktionen = {p["aktion"] for p in protokoll}
    assert {"Berechnung abgeschlossen", "Umbuchung", "Export erstellt",
            "Prüfer:in geändert"} <= aktionen
