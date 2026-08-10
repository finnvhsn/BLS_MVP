"""Gemeinsame Fixtures: komplettes Verfahren aus Generator-Daten in In-Memory-DB."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.core.konfiguration import JahrgangsKonfiguration, standard_konfiguration
from app.core.plan import PlanKontext, kontext_aus_db
from app.db.models import Jahrgang
from app.io import importer, testdaten


@dataclass
class Verfahren:
    session: Session
    jahrgang_id: int
    kontext: PlanKontext

    def kontext_neu_laden(self, konfiguration: JahrgangsKonfiguration | None = None) -> PlanKontext:
        self.kontext = kontext_aus_db(
            self.session, self.jahrgang_id, konfiguration or self.kontext.konfiguration
        )
        return self.kontext


def verfahren_erzeugen(
    ziel_pfad, konfiguration: JahrgangsKonfiguration | None = None, **generator_kwargs
) -> Verfahren:
    """Erzeugt Generator-CSVs, importiert sie in eine In-Memory-DB und liefert
    den Plan-Kontext. Auch außerhalb von Fixtures nutzbar (Modul-Scope)."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    jahrgang = Jahrgang(bezeichnung="Test 2026/2027")
    session.add(jahrgang)
    session.commit()
    session.refresh(jahrgang)

    pfade = testdaten.generieren(ziel_pfad, **generator_kwargs)
    for fn, key in [
        (importer.bewerbende_importieren, "bewerbende"),
        (importer.pruefende_importieren, "pruefende"),
        (importer.raeume_importieren, "raeume"),
        (importer.befangenheiten_importieren, "befangenheiten"),
    ]:
        ergebnis = fn(session, jahrgang.id, pfade[key].read_bytes())
        assert ergebnis.ok, ergebnis.fehler

    kontext = kontext_aus_db(session, jahrgang.id, konfiguration or standard_konfiguration())
    return Verfahren(session=session, jahrgang_id=jahrgang.id, kontext=kontext)


@pytest.fixture()
def verfahren_bauen(tmp_path):
    """Factory-Fixture um :func:`verfahren_erzeugen` (Function-Scope)."""
    offene: list[Verfahren] = []

    def _bauen(konfiguration: JahrgangsKonfiguration | None = None, **generator_kwargs) -> Verfahren:
        verfahren = verfahren_erzeugen(
            tmp_path / f"td{len(offene)}", konfiguration, **generator_kwargs
        )
        offene.append(verfahren)
        return verfahren

    yield _bauen
    for v in offene:
        v.session.close()
