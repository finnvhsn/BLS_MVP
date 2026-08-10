"""M1-Tests: CSV-Import (Validierung, deutsche Fehlermeldungen, Re-Import)
und Testdaten-Generator (reales Mengengerüst)."""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import Befangenheit, Bewerber, Jahrgang, Pruefer, Raum, Rueckmeldestatus, Tag
from app.io import importer, testdaten


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        jahrgang = Jahrgang(bezeichnung="2026/2027")
        s.add(jahrgang)
        s.commit()
        s.refresh(jahrgang)
        s.jahrgang_id = jahrgang.id  # bequemer Zugriff in Tests
        yield s


def test_bewerber_import_gueltig(session):
    csv_text = (
        "bewerber_id;nachname;vorname;tag;geschlecht;studiengang;ruecksteller;rangfolge;rueckmeldestatus;zugelassen\n"
        "BW-1;Muster;Anna;Fr;w;Rechtswissenschaft;nein;1;Zusage;ja\n"
        "BW-2;Beispiel;Ben;Sa;m;Rechtswissenschaft;ja;2;Offen;ja\n"
    )
    ergebnis = importer.bewerbende_importieren(session, session.jahrgang_id, csv_text)
    assert ergebnis.ok, ergebnis.fehler
    assert ergebnis.anzahl_neu == 2
    b = session.exec(select(Bewerber).where(Bewerber.import_key == "BW-1")).one()
    assert b.tag == Tag.FR
    assert b.rueckmeldestatus == Rueckmeldestatus.ZUSAGE


def test_bewerber_import_fehlender_tag_wird_gemeldet(session):
    """H7: Import ohne gültigen tag-Wert ist ein Validierungsfehler (kein Raten)."""
    csv_text = (
        "bewerber_id;nachname;vorname;tag;geschlecht;studiengang;ruecksteller\n"
        "BW-1;Muster;Anna;;w;Rechtswissenschaft;nein\n"
        "BW-2;Beispiel;Ben;Montag;m;Rechtswissenschaft;nein\n"
        "BW-3;Gueltig;Clara;Sa;w;Rechtswissenschaft;nein\n"
    )
    ergebnis = importer.bewerbende_importieren(session, session.jahrgang_id, csv_text)
    assert len(ergebnis.fehler) == 2
    assert all(f.spalte == "tag" for f in ergebnis.fehler)
    assert "Tageszuteilung" in ergebnis.fehler[0].meldung
    assert ergebnis.fehler[0].zeile == 2 and ergebnis.fehler[1].zeile == 3
    # Die gültige Zeile wurde importiert
    assert ergebnis.anzahl_neu == 1


def test_bewerber_import_fehlende_pflichtspalte(session):
    ergebnis = importer.bewerbende_importieren(
        session, session.jahrgang_id, "bewerber_id;nachname\nBW-1;Muster\n"
    )
    assert not ergebnis.ok
    assert any("Pflichtspalte" in f.meldung and f.spalte == "tag" for f in ergebnis.fehler)


def test_bewerber_reimport_aktualisiert(session):
    kopf = "bewerber_id;nachname;vorname;tag;geschlecht;studiengang;ruecksteller;rueckmeldestatus\n"
    importer.bewerbende_importieren(
        session, session.jahrgang_id, kopf + "BW-1;Muster;Anna;Fr;w;Rechtswissenschaft;nein;Offen\n"
    )
    ergebnis = importer.bewerbende_importieren(
        session, session.jahrgang_id, kopf + "BW-1;Muster;Anna;Fr;w;Rechtswissenschaft;nein;Zusage\n"
    )
    assert ergebnis.anzahl_neu == 0 and ergebnis.anzahl_aktualisiert == 1
    b = session.exec(select(Bewerber).where(Bewerber.import_key == "BW-1")).one()
    assert b.rueckmeldestatus == Rueckmeldestatus.ZUSAGE


def test_pruefer_import_mit_defaults(session):
    csv_text = (
        "pruefer_id;nachname;vorname;geschlecht;status;verfuegbar_fr;verfuegbar_sa\n"
        "PR-1;Senior;Sabine;w;Senior;;\n"
        "PR-2;Junior;Jan;m;Junior;nein;ja\n"
        "PR-3;Kaputt;Kai;m;Chef;;\n"
    )
    ergebnis = importer.pruefende_importieren(session, session.jahrgang_id, csv_text)
    assert ergebnis.anzahl_neu == 2
    assert len(ergebnis.fehler) == 1 and "Senior oder Junior" in ergebnis.fehler[0].meldung
    p1 = session.exec(select(Pruefer).where(Pruefer.import_key == "PR-1")).one()
    assert p1.verfuegbar_fr and p1.verfuegbar_sa  # Default: beide Tage


def test_raum_import_mit_sperrzeiten(session):
    csv_text = (
        "raumnummer;groesse;verfuegbar_fr;verfuegbar_sa;sperrzeiten\n"
        "1.01;klein;ja;ja;Fr 12:00-13:00|Sa 10:00-11:30\n"
        "2.01;gross;ja;nein;\n"
        "3.01;riesig;ja;ja;\n"
    )
    ergebnis = importer.raeume_importieren(session, session.jahrgang_id, csv_text)
    assert ergebnis.anzahl_neu == 2
    assert len(ergebnis.fehler) == 1 and ergebnis.fehler[0].spalte == "groesse"
    r = session.exec(select(Raum).where(Raum.raumnummer == "1.01")).one()
    assert r.sperrzeiten == [
        {"tag": "Fr", "von_min": 720, "bis_min": 780},
        {"tag": "Sa", "von_min": 600, "bis_min": 690},
    ]


def test_befangenheiten_import(session):
    importer.bewerbende_importieren(
        session, session.jahrgang_id,
        "bewerber_id;nachname;tag;geschlecht;studiengang;ruecksteller\n"
        "BW-1;Muster;Fr;w;Rechtswissenschaft;nein\n",
    )
    importer.pruefende_importieren(
        session, session.jahrgang_id,
        "pruefer_id;nachname;geschlecht;status\nPR-1;Senior;w;Senior\n",
    )
    csv_text = "pruefer_id;bewerber_id\nPR-1;BW-1\nPR-1;BW-99\n"
    ergebnis = importer.befangenheiten_importieren(session, session.jahrgang_id, csv_text)
    assert ergebnis.anzahl_neu == 1
    assert len(ergebnis.fehler) == 1 and "Unbekannte bewerber_id" in ergebnis.fehler[0].meldung
    assert session.exec(select(Befangenheit)).one() is not None
    # Doppelter Import derselben Paarung legt nichts Neues an
    ergebnis2 = importer.befangenheiten_importieren(
        session, session.jahrgang_id, "pruefer_id;bewerber_id\nPR-1;BW-1\n"
    )
    assert ergebnis2.anzahl_neu == 0


def test_windows_1252_dekodierung(session):
    csv_bytes = (
        "bewerber_id;nachname;tag;geschlecht;studiengang;ruecksteller\n"
        "BW-1;Müller-Lüdenscheid;Fr;w;Rechtswissenschaft;nein\n"
    ).encode("cp1252")
    ergebnis = importer.bewerbende_importieren(session, session.jahrgang_id, csv_bytes)
    assert ergebnis.ok
    b = session.exec(select(Bewerber)).one()
    assert b.name == "Müller-Lüdenscheid"


def test_generator_reales_mengengeruest(session, tmp_path):
    """Generator erzeugt das reale Mengengerüst und alles ist importierbar."""
    pfade = testdaten.generieren(tmp_path / "td", seed=42)

    e1 = importer.bewerbende_importieren(session, session.jahrgang_id, pfade["bewerbende"].read_bytes())
    e2 = importer.pruefende_importieren(session, session.jahrgang_id, pfade["pruefende"].read_bytes())
    e3 = importer.raeume_importieren(session, session.jahrgang_id, pfade["raeume"].read_bytes())
    e4 = importer.befangenheiten_importieren(session, session.jahrgang_id, pfade["befangenheiten"].read_bytes())
    for e in (e1, e2, e3, e4):
        assert e.ok, e.fehler

    assert e1.anzahl_neu == 262
    assert e2.anzahl_neu == 87
    assert e3.anzahl_neu == 34
    assert e4.anzahl_neu == 15

    bewerber = list(session.exec(select(Bewerber)))
    # Tageszuteilung 131/131 (H7: kommt aus Access)
    assert sum(1 for b in bewerber if b.tag == Tag.FR) == 131
    # Plausible Zusagenzahl (~130): geplant wird nur, wer zugesagt hat
    zusagen = [b for b in bewerber if b.rueckmeldestatus == Rueckmeldestatus.ZUSAGE]
    assert 110 <= len(zusagen) <= 150
    # Senior/Junior-Verhältnis
    pruefer = list(session.exec(select(Pruefer)))
    assert sum(1 for p in pruefer if p.status.value == "Senior") == 58

    # Determinismus: gleicher Seed ⇒ identische Dateien
    pfade2 = testdaten.generieren(tmp_path / "td2", seed=42)
    assert pfade["bewerbende"].read_bytes() == pfade2["bewerbende"].read_bytes()
