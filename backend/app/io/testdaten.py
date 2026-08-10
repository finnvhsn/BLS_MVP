"""Testdaten-Generator für das reale Mengengerüst (Kap. 3 der Spec).

Erzeugt CSV-Dateien im dokumentierten Austauschformat (docs/formats.md), damit
der komplette Importpfad mitgetestet wird. Deterministisch über ``--seed``.

Referenzwerte 2026/2027:
- 262 eingeladene Bewerbende (131 Fr / 131 Sa), davon ~130 Zusagen,
  ~30 Rücksteller, Rest Absagen → geplant werden nur Zusagen (~65 je Tag)
- 87 Prüfende: 58 Senior, 29 Junior
- Räume: Annahme ~24 klein (Einzel) + ~10 groß (Gruppenformate)

Aufruf:  python -m app.io.testdaten --ziel ../testdaten [--seed 42] [...]
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

VORNAMEN_W = [
    "Anna", "Charlotte", "Clara", "Emilia", "Frieda", "Greta", "Hannah", "Ida",
    "Johanna", "Katharina", "Lea", "Lena", "Luise", "Marie", "Mia", "Nele",
    "Paula", "Sophie", "Theresa", "Viktoria",
]
VORNAMEN_M = [
    "Anton", "Ben", "Carl", "David", "Emil", "Felix", "Friedrich", "Henri",
    "Jakob", "Jonas", "Julius", "Konstantin", "Leon", "Lukas", "Maximilian",
    "Moritz", "Noah", "Paul", "Theo", "Vincent",
]
NACHNAMEN = [
    "Ahrens", "Bachmann", "Becker", "Berger", "Brandt", "Busch", "Dietrich",
    "Engel", "Fischer", "Franke", "Fuchs", "Graf", "Hartmann", "Hoffmann",
    "Huber", "Jansen", "Kaiser", "Keller", "Klein", "Koch", "Krause", "Krüger",
    "Lange", "Lehmann", "Lorenz", "Ludwig", "Maier", "Martens", "Meyer",
    "Möller", "Neumann", "Otte", "Peters", "Richter", "Sauer", "Schmidt",
    "Schneider", "Schröder", "Schulz", "Seidel", "Simon", "Sommer", "Stein",
    "Thiele", "Vogel", "Voigt", "Wagner", "Weber", "Winkler", "Wolf",
]
STUDIENGAENGE = ["Rechtswissenschaft", "Recht und Wirtschaft"]  # 2. Studiengang ab 2027


def _person(rnd: random.Random) -> tuple[str, str, str]:
    """(vorname, nachname, geschlecht) — geschlecht w/m/d, divers selten."""
    wurf = rnd.random()
    if wurf < 0.02:
        geschlecht = "d"
        vorname = rnd.choice(VORNAMEN_W + VORNAMEN_M)
    elif wurf < 0.51:
        geschlecht = "w"
        vorname = rnd.choice(VORNAMEN_W)
    else:
        geschlecht = "m"
        vorname = rnd.choice(VORNAMEN_M)
    return vorname, rnd.choice(NACHNAMEN), geschlecht


def _schreiben(pfad: Path, kopf: list[str], zeilen: list[list]) -> None:
    with pfad.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(kopf)
        writer.writerows(zeilen)


def generieren(
    ziel: Path,
    seed: int = 42,
    anzahl_bewerber: int = 262,
    anzahl_senior: int = 58,
    anzahl_junior: int = 29,
    raeume_klein: int = 24,
    raeume_gross: int = 10,
    zusage_quote: float = 0.50,
    ruecksteller_quote: float = 0.115,
    befangenheit_anzahl: int = 15,
) -> dict[str, Path]:
    """Erzeugt die vier CSV-Dateien und gibt ihre Pfade zurück."""
    rnd = random.Random(seed)
    ziel.mkdir(parents=True, exist_ok=True)

    # --- Bewerbende: Tageszuteilung 50/50 (kommt fachlich aus Access, H7) ---
    bewerber_zeilen = []
    for i in range(1, anzahl_bewerber + 1):
        vorname, nachname, geschlecht = _person(rnd)
        tag = "Fr" if i % 2 == 1 else "Sa"
        wurf = rnd.random()
        if wurf < zusage_quote:
            status, ruecksteller = "Zusage", "nein"
        elif wurf < zusage_quote + ruecksteller_quote:
            status, ruecksteller = "Offen", "ja"   # Rücksteller
        else:
            status, ruecksteller = "Absage", "nein"
        studiengang = STUDIENGAENGE[0] if rnd.random() < 0.75 else STUDIENGAENGE[1]
        bewerber_zeilen.append([
            f"BW-{i:04d}", nachname, vorname, tag, geschlecht, studiengang,
            ruecksteller, i, status, "ja",
        ])
    bewerber_pfad = ziel / "bewerbende.csv"
    _schreiben(
        bewerber_pfad,
        ["bewerber_id", "nachname", "vorname", "tag", "geschlecht", "studiengang",
         "ruecksteller", "rangfolge", "rueckmeldestatus", "zugelassen"],
        bewerber_zeilen,
    )

    # --- Prüfende: 58 Senior + 29 Junior, i. d. R. beide Tage verfügbar ---
    pruefer_zeilen = []
    for i in range(1, anzahl_senior + anzahl_junior + 1):
        vorname, nachname, geschlecht = _person(rnd)
        status = "Senior" if i <= anzahl_senior else "Junior"
        # ~5 % stehen nur an einem Tag zur Verfügung
        verfuegbar_fr, verfuegbar_sa = "ja", "ja"
        if rnd.random() < 0.05:
            if rnd.random() < 0.5:
                verfuegbar_fr = "nein"
            else:
                verfuegbar_sa = "nein"
        pruefer_zeilen.append([
            f"PR-{i:03d}", nachname, vorname, geschlecht, status, verfuegbar_fr, verfuegbar_sa,
        ])
    pruefer_pfad = ziel / "pruefende.csv"
    _schreiben(
        pruefer_pfad,
        ["pruefer_id", "nachname", "vorname", "geschlecht", "status",
         "verfuegbar_fr", "verfuegbar_sa"],
        pruefer_zeilen,
    )

    # --- Räume ---
    raum_zeilen = []
    for i in range(1, raeume_klein + 1):
        raum_zeilen.append([f"1.{i:02d}", "klein", "ja", "ja", ""])
    for i in range(1, raeume_gross + 1):
        raum_zeilen.append([f"2.{i:02d}", "gross", "ja", "ja", ""])
    raum_pfad = ziel / "raeume.csv"
    _schreiben(
        raum_pfad,
        ["raumnummer", "groesse", "verfuegbar_fr", "verfuegbar_sa", "sperrzeiten"],
        raum_zeilen,
    )

    # --- Befangenheiten: wenige Paare, nur unter Zusagen relevant, aber
    #     bewusst auch einzelne irrelevante Paare (realistisch) ---
    befangenheit_zeilen = []
    paare: set[tuple[str, str]] = set()
    while len(befangenheit_zeilen) < befangenheit_anzahl:
        pruefer_key = f"PR-{rnd.randint(1, anzahl_senior + anzahl_junior):03d}"
        bewerber_key = f"BW-{rnd.randint(1, anzahl_bewerber):04d}"
        if (pruefer_key, bewerber_key) in paare:
            continue
        paare.add((pruefer_key, bewerber_key))
        befangenheit_zeilen.append([pruefer_key, bewerber_key])
    befangenheit_pfad = ziel / "befangenheiten.csv"
    _schreiben(befangenheit_pfad, ["pruefer_id", "bewerber_id"], befangenheit_zeilen)

    return {
        "bewerbende": bewerber_pfad,
        "pruefende": pruefer_pfad,
        "raeume": raum_pfad,
        "befangenheiten": befangenheit_pfad,
    }


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="BLS-Testdaten-Generator (reales Mengengerüst)")
    parser.add_argument("--ziel", type=Path, default=Path("../testdaten"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bewerber", type=int, default=262)
    parser.add_argument("--senior", type=int, default=58)
    parser.add_argument("--junior", type=int, default=29)
    parser.add_argument("--raeume-klein", type=int, default=24)
    parser.add_argument("--raeume-gross", type=int, default=10)
    parser.add_argument("--befangenheiten", type=int, default=15)
    args = parser.parse_args()
    pfade = generieren(
        args.ziel, seed=args.seed, anzahl_bewerber=args.bewerber,
        anzahl_senior=args.senior, anzahl_junior=args.junior,
        raeume_klein=args.raeume_klein, raeume_gross=args.raeume_gross,
        befangenheit_anzahl=args.befangenheiten,
    )
    for name, pfad in pfade.items():
        print(f"{name}: {pfad}")


if __name__ == "__main__":
    main()
