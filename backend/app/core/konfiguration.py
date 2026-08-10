"""Jahrgangs-Konfiguration (F_OM_005, F_OM_010): Zeitmodell, Prüfungsformate,
Gruppengröße, Gewichte der weichen Regeln, Solver-Parameter.

Alle fachlichen Variablen sind hier — und NUR hier — definiert und werden über
die UI parametriert (keine Programmierkenntnisse nötig). Die Defaults bilden
das Referenzverfahren 2026/2027 ab (Kap. 3 der Spec).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from ..db.models import Raumgroesse

# Zeitangaben intern in Minuten seit Mitternacht (600 = 10:00 Uhr).
RASTER_MIN = 15  # Slot-Raster: Startzeiten alle 15 Minuten


def minuten(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def hhmm(minuten_wert: int) -> str:
    return f"{minuten_wert // 60:02d}:{minuten_wert % 60:02d}"


class FormatKonfiguration(BaseModel):
    """Ein Prüfungsformat (konfigurierbar, Kap. 3)."""

    key: str                      # stabiler Schlüssel, z. B. "einzel_1"
    name: str                     # Anzeigename, z. B. "Einzelgespräch 1"
    typ: str                      # "einzel" | "gruppe" | "thesen"
    dauer_min: int                # Dauer eines Prüfungsereignisses
    anzahl_pruefer: int           # Größe der Prüfergruppe
    nur_senior: bool = False      # H4: Einzelgespräche nur Senior
    max_junior: int = 1           # H3: max. 1 Junior je Prüfergruppe (Gruppenformate)
    min_senior: int = 2           # H3: min. 2 Senior je Prüfergruppe (Gruppenformate)
    raumgroesse: Raumgroesse      # H6: Raumeignung

    @field_validator("typ")
    @classmethod
    def _typ_gueltig(cls, v: str) -> str:
        if v not in ("einzel", "gruppe", "thesen"):
            raise ValueError(f"Unbekannter Formattyp: {v!r}")
        return v

    @model_validator(mode="after")
    def _einzel_regeln(self) -> "FormatKonfiguration":
        if self.typ == "einzel" and not self.nur_senior:
            # H4 ist eine harte fachliche Regel — Einzelformate erzwingen Senior.
            raise ValueError("Einzelgespräche müssen 'nur_senior' sein (H4).")
        return self


class Zeitmodell(BaseModel):
    """Tages-Zeitmodell (Default 10:00–17:15, je Jahrgang änderbar; H8)."""

    tag_start: str = "10:00"
    tag_ende: str = "17:15"
    # Etappen/Wellen (F_OM_005): Anzahl der Kohorten-Wellen je Tag.
    # 1 = ganzer Tag ein Fenster; N teilt die Gruppen in N zeitversetzte Kohorten.
    wellen: int = Field(default=1, ge=1, le=4)
    # Pufferzeit zwischen zwei Prüfungen derselben Person (Kaffeepause vor dem
    # Gruppenvortrag dient als informelle Vorbereitung — Default 15 min Puffer).
    puffer_min: int = Field(default=15, ge=0)

    @property
    def start_min(self) -> int:
        return minuten(self.tag_start)

    @property
    def ende_min(self) -> int:
        return minuten(self.tag_ende)

    @model_validator(mode="after")
    def _fenster_gueltig(self) -> "Zeitmodell":
        if self.ende_min <= self.start_min:
            raise ValueError("Tagesende muss nach Tagesbeginn liegen.")
        return self


class Gewichte(BaseModel):
    """Gewichte der weichen Regeln W1–W6 (benannte Konstanten, konfigurierbar)."""

    w1_acht_kontakte: int = 100        # Abweichung von 8 unterschiedlichen Prüfenden
    w2_gleichverteilung: int = 30      # Abweichung von gleichmäßiger Prüfer-Auslastung
    w4_diversitaet_pruefer: int = 10   # gemischte Prüfergruppen (Geschlecht)
    w5_wartezeit: int = 5              # Wartezeit-Minuten der Bewerbenden
    w6_bestandserhalt: int = 1000      # Abweichung vom bestehenden Plan (Neuberechnung)
    # W3 (Diversität Bewerbendengruppen) wirkt in Stufe 1 (grouping.py):
    w3_diversitaet_gruppen: int = 10


class SolverParameter(BaseModel):
    timeout_sekunden: int = Field(default=600, ge=10)  # NF_003: Ziel ≤ 15 min
    seed: int = 42                                      # Determinismus (NF_010)


class JahrgangsKonfiguration(BaseModel):
    """Gesamte Konfiguration eines Jahrgangs — als JSON in der DB gespeichert,
    als Vorlage in den nächsten Jahrgang kopierbar (NF_008)."""

    zeitmodell: Zeitmodell = Field(default_factory=Zeitmodell)
    formate: list[FormatKonfiguration] = Field(default_factory=lambda: standard_formate())
    gruppengroesse: int = Field(default=4, ge=2, le=8)  # W3: konfigurierbar
    gewichte: Gewichte = Field(default_factory=Gewichte)
    solver: SolverParameter = Field(default_factory=SolverParameter)

    @model_validator(mode="after")
    def _formate_pruefen(self) -> "JahrgangsKonfiguration":
        keys = [f.key for f in self.formate]
        if len(keys) != len(set(keys)):
            raise ValueError("Format-Schlüssel müssen eindeutig sein.")
        if not self.formate:
            raise ValueError("Mindestens ein Prüfungsformat muss konfiguriert sein.")
        fenster = self.zeitmodell.ende_min - self.zeitmodell.start_min
        for f in self.formate:
            if f.dauer_min > fenster:
                raise ValueError(
                    f"Format {f.name!r} ({f.dauer_min} min) passt nicht in das "
                    f"Tagesfenster ({fenster} min)."
                )
        return self

    def format(self, key: str) -> FormatKonfiguration:
        for f in self.formate:
            if f.key == key:
                return f
        raise KeyError(f"Unbekanntes Format: {key!r}")


def standard_formate() -> list[FormatKonfiguration]:
    """Referenz-Formate 2026/2027 (Kap. 3). Die geprüfte Zusammenlegung der
    Einzelgespräche (1 × 30–45 min) ist nicht entschieden — daher zwei separate
    Einzelformate als Default; die Zusammenlegung ist reine Konfigurationsänderung.

    Ergibt die 8 Touchpoints: 1 + 1 (Einzel) + 3 (Gruppe) + 3 (Thesen) = 8.
    """
    return [
        FormatKonfiguration(
            key="einzel_1", name="Einzelgespräch 1", typ="einzel", dauer_min=30,
            anzahl_pruefer=1, nur_senior=True, max_junior=0, min_senior=1,
            raumgroesse=Raumgroesse.KLEIN,
        ),
        FormatKonfiguration(
            key="einzel_2", name="Einzelgespräch 2", typ="einzel", dauer_min=30,
            anzahl_pruefer=1, nur_senior=True, max_junior=0, min_senior=1,
            raumgroesse=Raumgroesse.KLEIN,
        ),
        FormatKonfiguration(
            key="gruppenarbeit", name="Gruppenvortrag/Gruppenarbeit", typ="gruppe",
            dauer_min=45, anzahl_pruefer=3, max_junior=1, min_senior=2,
            raumgroesse=Raumgroesse.GROSS,
        ),
        FormatKonfiguration(
            key="thesenvortrag", name="Thesenvortrag", typ="thesen", dauer_min=150,
            anzahl_pruefer=3, max_junior=1, min_senior=2,
            raumgroesse=Raumgroesse.GROSS,
        ),
    ]


def standard_konfiguration() -> JahrgangsKonfiguration:
    return JahrgangsKonfiguration()
