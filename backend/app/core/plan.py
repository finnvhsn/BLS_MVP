"""Leichtgewichtige, DB-unabhängige Plan-Repräsentation.

Regelwerk (rules.py), Validator und Solver arbeiten ausschließlich auf diesen
Strukturen — dadurch sind die Regeln pure functions und in Sekundenbruchteilen
auf ganze Pläne anwendbar (Live-Validierung F_OM_012).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

from sqlmodel import Session, select

from ..db.models import (
    Befangenheit,
    Bewerber,
    Gruppe,
    Pruefer,
    PrueferStatus,
    Raum,
    Raumgroesse,
    Rueckmeldestatus,
    Tag,
    Zuweisung,
    ZuweisungBewerber,
    ZuweisungPruefer,
)
from .konfiguration import JahrgangsKonfiguration


# ---------------------------------------------------------------------------
# Kontext: alle Stammdaten, die die Regeln benötigen
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BewerberInfo:
    id: int
    name: str
    vorname: str
    tag: Tag
    geschlecht: str
    studiengang: str
    zugelassen: bool
    aktiv: bool
    rueckmeldestatus: Rueckmeldestatus
    ruecksteller: bool
    gruppe_id: Optional[int]
    import_key: Optional[str]

    @property
    def planbar(self) -> bool:
        """Wird diese Person vom Algorithmus eingeplant? (docs/formats.md §1)"""
        return self.zugelassen and self.aktiv and self.rueckmeldestatus == Rueckmeldestatus.ZUSAGE

    @property
    def anzeigename(self) -> str:
        return f"{self.vorname} {self.name}".strip()


@dataclass(frozen=True)
class PrueferInfo:
    id: int
    name: str
    vorname: str
    geschlecht: str
    status: PrueferStatus
    verfuegbar_fr: bool
    verfuegbar_sa: bool
    aktiv: bool
    import_key: Optional[str]

    def verfuegbar(self, tag: Tag) -> bool:
        if not self.aktiv:
            return False
        return self.verfuegbar_fr if tag == Tag.FR else self.verfuegbar_sa

    @property
    def ist_junior(self) -> bool:
        return self.status == PrueferStatus.JUNIOR

    @property
    def anzeigename(self) -> str:
        return f"{self.vorname} {self.name}".strip()


@dataclass(frozen=True)
class RaumInfo:
    id: int
    raumnummer: str
    groesse: Raumgroesse
    verfuegbar_fr: bool
    verfuegbar_sa: bool
    sperrzeiten: tuple  # ({"tag": "Fr", "von_min": .., "bis_min": ..}, ...)
    aktiv: bool

    def verfuegbar(self, tag: Tag, start_min: int, ende_min: int) -> bool:
        if not self.aktiv:
            return False
        if not (self.verfuegbar_fr if tag == Tag.FR else self.verfuegbar_sa):
            return False
        for sperre in self.sperrzeiten:
            if sperre["tag"] == tag.value and start_min < sperre["bis_min"] and ende_min > sperre["von_min"]:
                return False
        return True


@dataclass(frozen=True)
class GruppeInfo:
    id: int
    tag: Tag
    nummer: int

    @property
    def bezeichnung(self) -> str:
        return f"Gruppe {self.tag.value}-{self.nummer:02d}"


@dataclass
class PlanKontext:
    konfiguration: JahrgangsKonfiguration
    bewerber: dict[int, BewerberInfo]
    pruefer: dict[int, PrueferInfo]
    raeume: dict[int, RaumInfo]
    gruppen: dict[int, GruppeInfo]
    befangenheiten: frozenset  # {(pruefer_id, bewerber_id), ...}

    def planbare_bewerber(self, tag: Tag | None = None) -> list[BewerberInfo]:
        return [
            b for b in self.bewerber.values()
            if b.planbar and (tag is None or b.tag == tag)
        ]

    def verfuegbare_pruefer(self, tag: Tag) -> list[PrueferInfo]:
        return [p for p in self.pruefer.values() if p.verfuegbar(tag)]


# ---------------------------------------------------------------------------
# Plan: eine Menge von Prüfungsereignissen
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanZuweisung:
    """Ein Prüfungsereignis: Format × Zeitfenster × Raum × Teilnehmende."""

    tag: Tag
    format_key: str
    start_min: int
    ende_min: int
    raum_id: int
    bewerber_ids: frozenset
    pruefer_ids: frozenset
    gruppe_id: Optional[int] = None
    db_id: Optional[int] = None
    manuell_geaendert: bool = False

    @property
    def schluessel(self) -> tuple:
        """Stabiler Vergleichsschlüssel für Bestandserhalt (W6)."""
        return (self.tag, self.format_key, self.start_min, self.raum_id,
                self.bewerber_ids, self.pruefer_ids)


@dataclass
class Plan:
    zuweisungen: list[PlanZuweisung] = field(default_factory=list)

    def fuer_bewerber(self, bewerber_id: int) -> list[PlanZuweisung]:
        return [z for z in self.zuweisungen if bewerber_id in z.bewerber_ids]

    def fuer_pruefer(self, pruefer_id: int) -> list[PlanZuweisung]:
        return [z for z in self.zuweisungen if pruefer_id in z.pruefer_ids]

    def ersetzt(self, index: int, neue: PlanZuweisung) -> "Plan":
        """Kopie des Plans mit ersetzter Zuweisung (für Was-wäre-wenn-Validierung)."""
        kopie = list(self.zuweisungen)
        kopie[index] = neue
        return Plan(zuweisungen=kopie)


# ---------------------------------------------------------------------------
# Laden aus der Datenbank
# ---------------------------------------------------------------------------

def kontext_aus_db(session: Session, jahrgang_id: int, konfiguration: JahrgangsKonfiguration) -> PlanKontext:
    bewerber = {
        b.id: BewerberInfo(
            id=b.id, name=b.name, vorname=b.vorname, tag=b.tag,
            geschlecht=b.geschlecht.value, studiengang=b.studiengang,
            zugelassen=b.zugelassen, aktiv=b.aktiv, rueckmeldestatus=b.rueckmeldestatus,
            ruecksteller=b.ruecksteller_kennzeichen, gruppe_id=b.gruppe_id,
            import_key=b.import_key,
        )
        for b in session.exec(select(Bewerber).where(Bewerber.jahrgang_id == jahrgang_id))
    }
    pruefer = {
        p.id: PrueferInfo(
            id=p.id, name=p.name, vorname=p.vorname, geschlecht=p.geschlecht.value,
            status=p.status, verfuegbar_fr=p.verfuegbar_fr, verfuegbar_sa=p.verfuegbar_sa,
            aktiv=p.aktiv, import_key=p.import_key,
        )
        for p in session.exec(select(Pruefer).where(Pruefer.jahrgang_id == jahrgang_id))
    }
    raeume = {
        r.id: RaumInfo(
            id=r.id, raumnummer=r.raumnummer, groesse=r.groesse,
            verfuegbar_fr=r.verfuegbar_fr, verfuegbar_sa=r.verfuegbar_sa,
            sperrzeiten=tuple(r.sperrzeiten or []), aktiv=r.aktiv,
        )
        for r in session.exec(select(Raum).where(Raum.jahrgang_id == jahrgang_id))
    }
    gruppen = {
        g.id: GruppeInfo(id=g.id, tag=g.tag, nummer=g.nummer)
        for g in session.exec(select(Gruppe).where(Gruppe.jahrgang_id == jahrgang_id))
    }
    befangenheiten = frozenset(
        (bef.pruefer_id, bef.bewerber_id)
        for bef in session.exec(select(Befangenheit).where(Befangenheit.jahrgang_id == jahrgang_id))
    )
    return PlanKontext(
        konfiguration=konfiguration, bewerber=bewerber, pruefer=pruefer,
        raeume=raeume, gruppen=gruppen, befangenheiten=befangenheiten,
    )


def plan_aus_db(session: Session, planungsstand_id: int) -> Plan:
    zuweisungen = list(session.exec(
        select(Zuweisung).where(Zuweisung.planungsstand_id == planungsstand_id)
    ))
    bewerber_map: dict[int, set] = {}
    for zb in session.exec(select(ZuweisungBewerber)):
        bewerber_map.setdefault(zb.zuweisung_id, set()).add(zb.bewerber_id)
    pruefer_map: dict[int, set] = {}
    for zp in session.exec(select(ZuweisungPruefer)):
        pruefer_map.setdefault(zp.zuweisung_id, set()).add(zp.pruefer_id)
    return Plan(zuweisungen=[
        PlanZuweisung(
            tag=z.tag, format_key=z.format_key, start_min=z.start_min, ende_min=z.ende_min,
            raum_id=z.raum_id, gruppe_id=z.gruppe_id, db_id=z.id,
            manuell_geaendert=z.manuell_geaendert,
            bewerber_ids=frozenset(bewerber_map.get(z.id, set())),
            pruefer_ids=frozenset(pruefer_map.get(z.id, set())),
        )
        for z in zuweisungen
    ])


def plan_speichern(session: Session, planungsstand_id: int, plan: Plan) -> None:
    for z in plan.zuweisungen:
        zeile = Zuweisung(
            planungsstand_id=planungsstand_id, tag=z.tag, format_key=z.format_key,
            start_min=z.start_min, ende_min=z.ende_min, raum_id=z.raum_id,
            gruppe_id=z.gruppe_id, manuell_geaendert=z.manuell_geaendert,
        )
        session.add(zeile)
        session.flush()  # id vergeben
        for bid in z.bewerber_ids:
            session.add(ZuweisungBewerber(zuweisung_id=zeile.id, bewerber_id=bid))
        for pid in z.pruefer_ids:
            session.add(ZuweisungPruefer(zuweisung_id=zeile.id, pruefer_id=pid))
    session.commit()
