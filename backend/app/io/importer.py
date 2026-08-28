"""CSV-Import mit Schema-Validierung und deutschen Fehlermeldungen
(F_OM_001–003, F_OM_009, NF_006).

Formate sind in ``/docs/formats.md`` dokumentiert und versioniert.
Die Import-Logik ist vom Transportweg entkoppelt (heute Datei-Upload,
morgen API — Kap. 10): alle Funktionen arbeiten auf Text/Bytes.

Re-Import-Semantik (F_OM_001 AK3): Upsert über ``import_key`` —
bestehende Datensätze werden aktualisiert, neue angelegt. Datensätze
werden beim Re-Import niemals stillschweigend gelöscht.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from sqlmodel import Session, select

from ..core.konfiguration import minuten
from ..db.models import (
    Befangenheit,
    Bewerber,
    Geschlecht,
    Pruefer,
    PrueferStatus,
    Raum,
    Raumgroesse,
    Rueckmeldestatus,
    Tag,
)

FORMATVERSION = "1.0"  # versioniertes Austauschformat (NF_006)


# ---------------------------------------------------------------------------
# Ergebnis-Strukturen
# ---------------------------------------------------------------------------

@dataclass
class ImportFehler:
    zeile: int          # 1-basiert inkl. Kopfzeile (Zeile 1 = Kopf)
    spalte: str
    meldung: str

    def __str__(self) -> str:  # pragma: no cover - Anzeige
        return f"Zeile {self.zeile}, Spalte „{self.spalte}“: {self.meldung}"


@dataclass
class ImportErgebnis:
    typ: str
    anzahl_neu: int = 0
    anzahl_aktualisiert: int = 0
    fehler: list[ImportFehler] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fehler

    def als_dict(self) -> dict:
        return {
            "typ": self.typ,
            "anzahl_neu": self.anzahl_neu,
            "anzahl_aktualisiert": self.anzahl_aktualisiert,
            "fehler": [
                {"zeile": f.zeile, "spalte": f.spalte, "meldung": f.meldung}
                for f in self.fehler
            ],
        }


# ---------------------------------------------------------------------------
# Parsen & Dekodieren
# ---------------------------------------------------------------------------

def daten_dekodieren(daten: bytes | str) -> str:
    """Dekodiert Upload-Bytes: UTF-8 (mit BOM) bevorzugt, sonst Windows-1252
    (übliche Access-/Excel-Exporte)."""
    if isinstance(daten, str):
        return daten
    try:
        return daten.decode("utf-8-sig")
    except UnicodeDecodeError:
        return daten.decode("cp1252")


def _zeilen_lesen(text: str) -> tuple[list[str], list[dict[str, str]]]:
    """Liest CSV (Trennzeichen ; oder , — automatisch erkannt) in Dictionaries."""
    kopfzeile = text.lstrip().splitlines()[0] if text.strip() else ""
    trenner = ";" if kopfzeile.count(";") >= kopfzeile.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=trenner)
    spalten = [s.strip() for s in (reader.fieldnames or [])]
    zeilen = []
    for row in reader:
        zeilen.append({(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None})
    return spalten, zeilen


def _pflichtspalten_pruefen(
    vorhanden: list[str], erwartet: list[str], ergebnis: ImportErgebnis
) -> bool:
    fehlend = [s for s in erwartet if s not in vorhanden]
    for spalte in fehlend:
        ergebnis.fehler.append(
            ImportFehler(1, spalte, f"Pflichtspalte „{spalte}“ fehlt in der Kopfzeile.")
        )
    return not fehlend


def _ja_nein(wert: str, spalte: str, zeile: int, fehler: list[ImportFehler],
             default: bool | None = None) -> bool | None:
    w = wert.strip().lower()
    if w in ("ja", "1", "x", "true", "wahr"):
        return True
    if w in ("nein", "0", "false", "falsch"):
        return False
    if w == "" and default is not None:
        return default
    fehler.append(ImportFehler(zeile, spalte, f"Ungültiger Wert {wert!r} — erwartet: ja/nein."))
    return None


# ---------------------------------------------------------------------------
# Bewerbende (F_OM_001)
# ---------------------------------------------------------------------------

BEWERBER_PFLICHTSPALTEN = ["bewerber_id", "nachname", "tag", "geschlecht", "studiengang"]
# ruecksteller ist optional (fehlend ⇒ nein): das Kennzeichen wird importiert und
# mitgeführt, aber von keiner Regel ausgewertet — als Pflichtspalte hätte es nur
# handgebaute CSVs erschwert. Siehe docs/formats.md.
BEWERBER_OPTIONALE_SPALTEN = ["vorname", "ruecksteller", "rangfolge", "rueckmeldestatus", "zugelassen"]


def bewerbende_importieren(session: Session, jahrgang_id: int, daten: bytes | str) -> ImportErgebnis:
    ergebnis = ImportErgebnis(typ="Bewerbende")
    spalten, zeilen = _zeilen_lesen(daten_dekodieren(daten))
    if not _pflichtspalten_pruefen(spalten, BEWERBER_PFLICHTSPALTEN, ergebnis):
        return ergebnis

    bestehende = {
        b.import_key: b
        for b in session.exec(select(Bewerber).where(Bewerber.jahrgang_id == jahrgang_id))
        if b.import_key
    }
    gesehene_keys: set[str] = set()

    for i, zeile in enumerate(zeilen, start=2):
        fehler: list[ImportFehler] = []
        key = zeile.get("bewerber_id", "")
        if not key:
            fehler.append(ImportFehler(i, "bewerber_id", "Pflichtfeld ist leer."))
        elif key in gesehene_keys:
            fehler.append(ImportFehler(i, "bewerber_id", f"Doppelte bewerber_id {key!r} in der Datei."))

        nachname = zeile.get("nachname", "")
        if not nachname:
            fehler.append(ImportFehler(i, "nachname", "Pflichtfeld ist leer."))

        # H7: Tageszuteilung ist Pflicht — kein stilles Raten des Tages.
        tag_wert = zeile.get("tag", "")
        tag: Tag | None = None
        if tag_wert.capitalize() in (Tag.FR.value, Tag.SA.value):
            tag = Tag(tag_wert.capitalize())
        else:
            fehler.append(ImportFehler(
                i, "tag",
                f"Ungültige oder fehlende Tageszuteilung {tag_wert!r} — erwartet: Fr oder Sa. "
                "Die Tageszuteilung erfolgt in Access und ist Pflichtfeld.",
            ))

        geschlecht_wert = zeile.get("geschlecht", "").lower()
        geschlecht: Geschlecht | None = None
        if geschlecht_wert in [g.value for g in Geschlecht]:
            geschlecht = Geschlecht(geschlecht_wert)
        else:
            fehler.append(ImportFehler(
                i, "geschlecht", f"Ungültiger Wert {zeile.get('geschlecht', '')!r} — erwartet: w, m oder d."
            ))

        studiengang = zeile.get("studiengang", "")
        if not studiengang:
            fehler.append(ImportFehler(i, "studiengang", "Pflichtfeld ist leer."))

        ruecksteller = _ja_nein(zeile.get("ruecksteller", ""), "ruecksteller", i, fehler,
                                default=False)
        zugelassen = _ja_nein(zeile.get("zugelassen", "ja"), "zugelassen", i, fehler, default=True)

        rangfolge: int | None = None
        rangfolge_wert = zeile.get("rangfolge", "")
        if rangfolge_wert:
            try:
                rangfolge = int(rangfolge_wert)
            except ValueError:
                fehler.append(ImportFehler(i, "rangfolge", f"Ungültige Zahl {rangfolge_wert!r}."))

        status_wert = zeile.get("rueckmeldestatus", "").capitalize() or Rueckmeldestatus.OFFEN.value
        status: Rueckmeldestatus | None = None
        if status_wert in [s.value for s in Rueckmeldestatus]:
            status = Rueckmeldestatus(status_wert)
        else:
            fehler.append(ImportFehler(
                i, "rueckmeldestatus",
                f"Ungültiger Wert {zeile.get('rueckmeldestatus', '')!r} — erwartet: "
                "Zusage, Absage, Alternativtermin oder Offen.",
            ))

        if fehler:
            ergebnis.fehler.extend(fehler)
            continue

        gesehene_keys.add(key)
        vorhanden = bestehende.get(key)
        if vorhanden is None:
            session.add(Bewerber(
                jahrgang_id=jahrgang_id, import_key=key, name=nachname,
                vorname=zeile.get("vorname", ""), tag=tag, geschlecht=geschlecht,
                studiengang=studiengang, ruecksteller_kennzeichen=ruecksteller,
                rangfolge=rangfolge, rueckmeldestatus=status, zugelassen=zugelassen,
            ))
            ergebnis.anzahl_neu += 1
        else:
            vorhanden.name = nachname
            vorhanden.vorname = zeile.get("vorname", "")
            vorhanden.tag = tag
            vorhanden.geschlecht = geschlecht
            vorhanden.studiengang = studiengang
            vorhanden.ruecksteller_kennzeichen = ruecksteller
            vorhanden.rangfolge = rangfolge
            vorhanden.rueckmeldestatus = status
            vorhanden.zugelassen = zugelassen
            session.add(vorhanden)
            ergebnis.anzahl_aktualisiert += 1

    session.commit()
    return ergebnis


# ---------------------------------------------------------------------------
# Prüfende (F_OM_002)
# ---------------------------------------------------------------------------

PRUEFER_PFLICHTSPALTEN = ["pruefer_id", "nachname", "geschlecht", "status"]


def pruefende_importieren(session: Session, jahrgang_id: int, daten: bytes | str) -> ImportErgebnis:
    ergebnis = ImportErgebnis(typ="Prüfende")
    spalten, zeilen = _zeilen_lesen(daten_dekodieren(daten))
    if not _pflichtspalten_pruefen(spalten, PRUEFER_PFLICHTSPALTEN, ergebnis):
        return ergebnis

    bestehende = {
        p.import_key: p
        for p in session.exec(select(Pruefer).where(Pruefer.jahrgang_id == jahrgang_id))
        if p.import_key
    }
    gesehene_keys: set[str] = set()

    for i, zeile in enumerate(zeilen, start=2):
        fehler: list[ImportFehler] = []
        key = zeile.get("pruefer_id", "")
        if not key:
            fehler.append(ImportFehler(i, "pruefer_id", "Pflichtfeld ist leer."))
        elif key in gesehene_keys:
            fehler.append(ImportFehler(i, "pruefer_id", f"Doppelte pruefer_id {key!r} in der Datei."))

        nachname = zeile.get("nachname", "")
        if not nachname:
            fehler.append(ImportFehler(i, "nachname", "Pflichtfeld ist leer."))

        geschlecht_wert = zeile.get("geschlecht", "").lower()
        geschlecht: Geschlecht | None = None
        if geschlecht_wert in [g.value for g in Geschlecht]:
            geschlecht = Geschlecht(geschlecht_wert)
        else:
            fehler.append(ImportFehler(
                i, "geschlecht", f"Ungültiger Wert {zeile.get('geschlecht', '')!r} — erwartet: w, m oder d."
            ))

        status_wert = zeile.get("status", "").capitalize()
        status: PrueferStatus | None = None
        if status_wert in [s.value for s in PrueferStatus]:
            status = PrueferStatus(status_wert)
        else:
            fehler.append(ImportFehler(
                i, "status",
                f"Ungültiger Wert {zeile.get('status', '')!r} — erwartet: Senior oder Junior.",
            ))

        # Prüfende stehen i. d. R. an beiden Tagen zur Verfügung (Default: ja)
        verfuegbar_fr = _ja_nein(zeile.get("verfuegbar_fr", ""), "verfuegbar_fr", i, fehler, default=True)
        verfuegbar_sa = _ja_nein(zeile.get("verfuegbar_sa", ""), "verfuegbar_sa", i, fehler, default=True)

        if fehler:
            ergebnis.fehler.extend(fehler)
            continue

        gesehene_keys.add(key)
        vorhanden = bestehende.get(key)
        if vorhanden is None:
            session.add(Pruefer(
                jahrgang_id=jahrgang_id, import_key=key, name=nachname,
                vorname=zeile.get("vorname", ""), geschlecht=geschlecht, status=status,
                verfuegbar_fr=verfuegbar_fr, verfuegbar_sa=verfuegbar_sa,
            ))
            ergebnis.anzahl_neu += 1
        else:
            vorhanden.name = nachname
            vorhanden.vorname = zeile.get("vorname", "")
            vorhanden.geschlecht = geschlecht
            vorhanden.status = status
            vorhanden.verfuegbar_fr = verfuegbar_fr
            vorhanden.verfuegbar_sa = verfuegbar_sa
            session.add(vorhanden)
            ergebnis.anzahl_aktualisiert += 1

    session.commit()
    return ergebnis


# ---------------------------------------------------------------------------
# Räume (F_OM_003)
# ---------------------------------------------------------------------------

RAUM_PFLICHTSPALTEN = ["raumnummer", "groesse"]


def _sperrzeiten_parsen(wert: str, zeile: int, fehler: list[ImportFehler]) -> list[dict]:
    """Format: ``Fr 12:00-13:00|Sa 10:00-11:30`` (mehrere mit | getrennt)."""
    ergebnis = []
    if not wert:
        return ergebnis
    for teil in wert.split("|"):
        teil = teil.strip()
        try:
            tag_teil, zeit_teil = teil.split(" ", 1)
            von, bis = zeit_teil.split("-")
            if tag_teil.capitalize() not in (Tag.FR.value, Tag.SA.value):
                raise ValueError
            ergebnis.append({
                "tag": tag_teil.capitalize(),
                "von_min": minuten(von.strip()),
                "bis_min": minuten(bis.strip()),
            })
        except (ValueError, IndexError):
            fehler.append(ImportFehler(
                zeile, "sperrzeiten",
                f"Ungültige Sperrzeit {teil!r} — erwartet z. B. „Fr 12:00-13:00“ "
                "(mehrere mit | getrennt).",
            ))
    return ergebnis


def raeume_importieren(session: Session, jahrgang_id: int, daten: bytes | str) -> ImportErgebnis:
    ergebnis = ImportErgebnis(typ="Räume")
    spalten, zeilen = _zeilen_lesen(daten_dekodieren(daten))
    if not _pflichtspalten_pruefen(spalten, RAUM_PFLICHTSPALTEN, ergebnis):
        return ergebnis

    bestehende = {
        r.raumnummer: r
        for r in session.exec(select(Raum).where(Raum.jahrgang_id == jahrgang_id))
    }
    gesehene: set[str] = set()

    for i, zeile in enumerate(zeilen, start=2):
        fehler: list[ImportFehler] = []
        raumnummer = zeile.get("raumnummer", "")
        if not raumnummer:
            fehler.append(ImportFehler(i, "raumnummer", "Pflichtfeld ist leer."))
        elif raumnummer in gesehene:
            fehler.append(ImportFehler(i, "raumnummer", f"Doppelte Raumnummer {raumnummer!r} in der Datei."))

        groesse_wert = zeile.get("groesse", "").lower().replace("ß", "ss")
        groesse: Raumgroesse | None = None
        if groesse_wert in [g.value for g in Raumgroesse]:
            groesse = Raumgroesse(groesse_wert)
        else:
            fehler.append(ImportFehler(
                i, "groesse",
                f"Ungültiger Wert {zeile.get('groesse', '')!r} — erwartet: klein "
                "(Einzelgespräch) oder gross (Gruppenformate).",
            ))

        verfuegbar_fr = _ja_nein(zeile.get("verfuegbar_fr", ""), "verfuegbar_fr", i, fehler, default=True)
        verfuegbar_sa = _ja_nein(zeile.get("verfuegbar_sa", ""), "verfuegbar_sa", i, fehler, default=True)
        sperrzeiten = _sperrzeiten_parsen(zeile.get("sperrzeiten", ""), i, fehler)

        if fehler:
            ergebnis.fehler.extend(fehler)
            continue

        gesehene.add(raumnummer)
        vorhanden = bestehende.get(raumnummer)
        if vorhanden is None:
            session.add(Raum(
                jahrgang_id=jahrgang_id, raumnummer=raumnummer, groesse=groesse,
                verfuegbar_fr=verfuegbar_fr, verfuegbar_sa=verfuegbar_sa,
                sperrzeiten=sperrzeiten,
            ))
            ergebnis.anzahl_neu += 1
        else:
            vorhanden.groesse = groesse
            vorhanden.verfuegbar_fr = verfuegbar_fr
            vorhanden.verfuegbar_sa = verfuegbar_sa
            vorhanden.sperrzeiten = sperrzeiten
            session.add(vorhanden)
            ergebnis.anzahl_aktualisiert += 1

    session.commit()
    return ergebnis


# ---------------------------------------------------------------------------
# Befangenheiten (F_OM_009) — datensparsam, ohne Grund (H2, NF_001)
# ---------------------------------------------------------------------------

BEFANGENHEIT_PFLICHTSPALTEN = ["pruefer_id", "bewerber_id"]


def befangenheiten_importieren(session: Session, jahrgang_id: int, daten: bytes | str) -> ImportErgebnis:
    ergebnis = ImportErgebnis(typ="Befangenheiten")
    spalten, zeilen = _zeilen_lesen(daten_dekodieren(daten))
    if not _pflichtspalten_pruefen(spalten, BEFANGENHEIT_PFLICHTSPALTEN, ergebnis):
        return ergebnis

    pruefer_map = {
        p.import_key: p.id
        for p in session.exec(select(Pruefer).where(Pruefer.jahrgang_id == jahrgang_id))
        if p.import_key
    }
    bewerber_map = {
        b.import_key: b.id
        for b in session.exec(select(Bewerber).where(Bewerber.jahrgang_id == jahrgang_id))
        if b.import_key
    }
    vorhandene = {
        (bef.pruefer_id, bef.bewerber_id)
        for bef in session.exec(select(Befangenheit).where(Befangenheit.jahrgang_id == jahrgang_id))
    }

    for i, zeile in enumerate(zeilen, start=2):
        fehler: list[ImportFehler] = []
        pruefer_key = zeile.get("pruefer_id", "")
        bewerber_key = zeile.get("bewerber_id", "")
        pruefer_id = pruefer_map.get(pruefer_key)
        bewerber_id = bewerber_map.get(bewerber_key)
        if pruefer_id is None:
            fehler.append(ImportFehler(
                i, "pruefer_id",
                f"Unbekannte pruefer_id {pruefer_key!r} — Prüfende zuerst importieren.",
            ))
        if bewerber_id is None:
            fehler.append(ImportFehler(
                i, "bewerber_id",
                f"Unbekannte bewerber_id {bewerber_key!r} — Bewerbende zuerst importieren.",
            ))
        if fehler:
            ergebnis.fehler.extend(fehler)
            continue
        if (pruefer_id, bewerber_id) in vorhandene:
            ergebnis.anzahl_aktualisiert += 1
            continue
        vorhandene.add((pruefer_id, bewerber_id))
        session.add(Befangenheit(
            jahrgang_id=jahrgang_id, pruefer_id=pruefer_id, bewerber_id=bewerber_id
        ))
        ergebnis.anzahl_neu += 1

    session.commit()
    return ergebnis
