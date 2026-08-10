"""Datenmodell des MVP „Zuweisungsalgorithmus mündliches Auswahlverfahren".

Alle fachlichen Entitäten tragen eine ``jahrgang_id`` (NF_008: Jahrgangsfähigkeit).
Befangenheiten werden datensparsam ohne Grundangabe gespeichert (H2, NF_001).
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def jetzt() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums (Werte deutsch, da sie in UI und CSV-Export sichtbar werden)
# ---------------------------------------------------------------------------

class Tag(str, enum.Enum):
    FR = "Fr"
    SA = "Sa"


class Geschlecht(str, enum.Enum):
    WEIBLICH = "w"
    MAENNLICH = "m"
    DIVERS = "d"


class PrueferStatus(str, enum.Enum):
    SENIOR = "Senior"
    JUNIOR = "Junior"


class Raumgroesse(str, enum.Enum):
    KLEIN = "klein"    # Einzelgespräche
    GROSS = "gross"    # Gruppenarbeit, Thesenvortrag


class Rueckmeldestatus(str, enum.Enum):
    ZUSAGE = "Zusage"
    ABSAGE = "Absage"
    ALTERNATIVTERMIN = "Alternativtermin"
    OFFEN = "Offen"


class Rolle(str, enum.Enum):
    """Rollenmodell (NF_002). Im MVP ist nur VERFAHRENSORGANISATION aktiv;
    PRUEFENDE ist angelegt, wird aber 2027 nicht direkt genutzt."""

    VERFAHRENSORGANISATION = "Verfahrensorganisation"
    PRUEFENDE = "Pruefende"


class PlanungsstandTyp(str, enum.Enum):
    VOLLBERECHNUNG = "Vollberechnung"
    NEUBERECHNUNG = "Neuberechnung"
    MANUELL = "Manuell"


# ---------------------------------------------------------------------------
# Jahrgang & Konfiguration (NF_008, F_OM_010)
# ---------------------------------------------------------------------------

class Jahrgang(SQLModel, table=True):
    __tablename__ = "jahrgang"

    id: Optional[int] = Field(default=None, primary_key=True)
    bezeichnung: str = Field(index=True, unique=True)  # z. B. "2026/2027"
    aktiv: bool = Field(default=True)
    erstellt_am: datetime = Field(default_factory=jetzt)


class Konfiguration(SQLModel, table=True):
    """Jahrgangs-Konfiguration (Zeitmodell, Formate, Gewichte, Solver).

    ``daten`` folgt dem Pydantic-Schema in ``core/konfiguration.py``.
    Konfigurationen sind je Jahrgang speicher-, kopier- und wiederverwendbar.
    """

    __tablename__ = "konfiguration"

    id: Optional[int] = Field(default=None, primary_key=True)
    jahrgang_id: int = Field(foreign_key="jahrgang.id", index=True)
    name: str = Field(default="Standard")
    daten: dict = Field(sa_column=Column(JSON), default_factory=dict)
    erstellt_am: datetime = Field(default_factory=jetzt)


# ---------------------------------------------------------------------------
# Stammdaten (F_OM_001–003, F_OM_009)
# ---------------------------------------------------------------------------

class Bewerber(SQLModel, table=True):
    __tablename__ = "bewerber"

    id: Optional[int] = Field(default=None, primary_key=True)
    jahrgang_id: int = Field(foreign_key="jahrgang.id", index=True)
    import_key: Optional[str] = Field(default=None, index=True)  # ID aus Access (Re-Import/Delta)
    name: str
    vorname: str = Field(default="")
    tag: Tag = Field(index=True)  # Tageszuteilung aus Access — Pflichtfeld (H7)
    geschlecht: Geschlecht
    studiengang: str
    ruecksteller_kennzeichen: bool = Field(default=False)
    # Für spätere Access-Ablösung mitgeführt, vom Solver nicht benötigt (Kap. 10):
    rangfolge: Optional[int] = Field(default=None)
    rueckmeldestatus: Rueckmeldestatus = Field(default=Rueckmeldestatus.OFFEN)
    zugelassen: bool = Field(default=True)  # nimmt am mündlichen Verfahren teil
    aktiv: bool = Field(default=True)       # False = kurzfristige Absage (Szenario 2)
    gruppe_id: Optional[int] = Field(default=None, foreign_key="gruppe.id", index=True)


class Pruefer(SQLModel, table=True):
    __tablename__ = "pruefer"

    id: Optional[int] = Field(default=None, primary_key=True)
    jahrgang_id: int = Field(foreign_key="jahrgang.id", index=True)
    import_key: Optional[str] = Field(default=None, index=True)  # ID aus Salesforce
    name: str
    vorname: str = Field(default="")
    geschlecht: Geschlecht
    status: PrueferStatus
    verfuegbar_fr: bool = Field(default=True)
    verfuegbar_sa: bool = Field(default=True)
    aktiv: bool = Field(default=True)  # False = kurzfristige Absage (Szenario 1)


class Raum(SQLModel, table=True):
    __tablename__ = "raum"

    id: Optional[int] = Field(default=None, primary_key=True)
    jahrgang_id: int = Field(foreign_key="jahrgang.id", index=True)
    raumnummer: str
    groesse: Raumgroesse
    verfuegbar_fr: bool = Field(default=True)
    verfuegbar_sa: bool = Field(default=True)
    # Sperrzeiten je Tag: Liste von {"tag": "Fr", "von_min": 600, "bis_min": 720}
    # (Minuten seit Mitternacht) — H6: Verfügbarkeit je Tag UND Zeitfenster
    sperrzeiten: list = Field(sa_column=Column(JSON), default_factory=list)
    aktiv: bool = Field(default=True)  # False = Raumausfall (Szenario 5)


class Befangenheit(SQLModel, table=True):
    """Ausschlussbeziehung Prüfer:in ↔ Bewerber:in — ohne Grund (H2, NF_001)."""

    __tablename__ = "befangenheit"

    id: Optional[int] = Field(default=None, primary_key=True)
    jahrgang_id: int = Field(foreign_key="jahrgang.id", index=True)
    pruefer_id: int = Field(foreign_key="pruefer.id", index=True)
    bewerber_id: int = Field(foreign_key="bewerber.id", index=True)


class Gruppe(SQLModel, table=True):
    """Bewerbendengruppe (F_OM_006). Mitgliedschaft über Bewerber.gruppe_id."""

    __tablename__ = "gruppe"

    id: Optional[int] = Field(default=None, primary_key=True)
    jahrgang_id: int = Field(foreign_key="jahrgang.id", index=True)
    tag: Tag = Field(index=True)
    nummer: int  # fortlaufend je Tag, z. B. Gruppe Fr-01


# ---------------------------------------------------------------------------
# Planungsstände & Zuweisungen (F_OM_007, NF_010: Versionierung)
# ---------------------------------------------------------------------------

class Planungsstand(SQLModel, table=True):
    __tablename__ = "planungsstand"

    id: Optional[int] = Field(default=None, primary_key=True)
    jahrgang_id: int = Field(foreign_key="jahrgang.id", index=True)
    version: int = Field(index=True)  # fortlaufend je Jahrgang
    typ: PlanungsstandTyp
    basis_planungsstand_id: Optional[int] = Field(default=None, foreign_key="planungsstand.id")
    seed: Optional[int] = Field(default=None)          # Determinismus (Kap. 9)
    parameter: dict = Field(sa_column=Column(JSON), default_factory=dict)
    kennzahlen: dict = Field(sa_column=Column(JSON), default_factory=dict)  # W1/W2/W5, Stabilität
    konflikte: list = Field(sa_column=Column(JSON), default_factory=list)   # benannte Regelverletzungen
    erstellt_am: datetime = Field(default_factory=jetzt)


class Zuweisung(SQLModel, table=True):
    """Ein Prüfungsereignis: Format × Zeitfenster × Raum mit Teilnehmenden."""

    __tablename__ = "zuweisung"

    id: Optional[int] = Field(default=None, primary_key=True)
    planungsstand_id: int = Field(foreign_key="planungsstand.id", index=True)
    tag: Tag
    format_key: str                     # Schlüssel aus der Format-Konfiguration
    start_min: int                      # Minuten seit Mitternacht (600 = 10:00)
    ende_min: int
    raum_id: int = Field(foreign_key="raum.id")
    gruppe_id: Optional[int] = Field(default=None, foreign_key="gruppe.id")
    manuell_geaendert: bool = Field(default=False)  # F_OM_012: manuelle Eingriffe erkennbar


class ZuweisungBewerber(SQLModel, table=True):
    __tablename__ = "zuweisung_bewerber"

    id: Optional[int] = Field(default=None, primary_key=True)
    zuweisung_id: int = Field(foreign_key="zuweisung.id", index=True)
    bewerber_id: int = Field(foreign_key="bewerber.id", index=True)


class ZuweisungPruefer(SQLModel, table=True):
    __tablename__ = "zuweisung_pruefer"

    id: Optional[int] = Field(default=None, primary_key=True)
    zuweisung_id: int = Field(foreign_key="zuweisung.id", index=True)
    pruefer_id: int = Field(foreign_key="pruefer.id", index=True)


# ---------------------------------------------------------------------------
# Export-Versionierung (F_OM_013)
# ---------------------------------------------------------------------------

class ExportLauf(SQLModel, table=True):
    __tablename__ = "export_lauf"

    id: Optional[int] = Field(default=None, primary_key=True)
    jahrgang_id: int = Field(foreign_key="jahrgang.id", index=True)
    planungsstand_id: int = Field(foreign_key="planungsstand.id")
    version: int  # fortlaufend je Jahrgang
    dateiname: str
    erstellt_am: datetime = Field(default_factory=jetzt)


# ---------------------------------------------------------------------------
# Benutzer, Sitzungen, Protokoll (NF_002, NF_010)
# ---------------------------------------------------------------------------

class Benutzer(SQLModel, table=True):
    __tablename__ = "benutzer"

    id: Optional[int] = Field(default=None, primary_key=True)
    benutzername: str = Field(index=True, unique=True)
    passwort_hash: str
    rolle: Rolle = Field(default=Rolle.VERFAHRENSORGANISATION)
    aktiv: bool = Field(default=True)
    erstellt_am: datetime = Field(default_factory=jetzt)


class Sitzung(SQLModel, table=True):
    __tablename__ = "sitzung"

    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(index=True, unique=True)
    benutzer_id: int = Field(foreign_key="benutzer.id")
    erstellt_am: datetime = Field(default_factory=jetzt)
    gueltig_bis: datetime


class Protokoll(SQLModel, table=True):
    """Lauf- und Änderungsprotokoll (NF_010): Berechnungsläufe, Importe,
    manuelle Eingriffe, Exporte, An-/Abmeldungen."""

    __tablename__ = "protokoll"

    id: Optional[int] = Field(default=None, primary_key=True)
    jahrgang_id: Optional[int] = Field(default=None, foreign_key="jahrgang.id", index=True)
    zeitpunkt: datetime = Field(default_factory=jetzt)
    benutzer: str = Field(default="System")
    aktion: str = Field(index=True)  # z. B. "Import Bewerbende", "Vollberechnung", "Umbuchung"
    details: dict = Field(sa_column=Column(JSON), default_factory=dict)
