"""Druckdaten (F_DM_001/002, Soll-Anforderungen B): Laufzettel je
Bewerber:in/Prüfer:in und Raumschilder als PDF via WeasyPrint.

Die HTML-Erzeugung ist von der PDF-Wandlung getrennt: HTML entsteht immer
(testbar ohne Systembibliotheken), die Wandlung nutzt WeasyPrint. Das Layout
liegt als editierbares Stylesheet in ``vorlagen/druck.css`` — Inhalte und
Gestaltung sind damit ohne Programmierkenntnisse anpassbar.
"""

from __future__ import annotations

import html
from pathlib import Path

from ..core.konfiguration import hhmm
from ..core.plan import Plan, PlanKontext

VORLAGEN = Path(__file__).parent / "vorlagen"


class PdfNichtVerfuegbar(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "PDF-Erzeugung nicht verfügbar: WeasyPrint bzw. seine Systembibliotheken "
            "(Pango/GObject) fehlen. Im Docker-Betrieb sind sie enthalten; lokal: "
            "'pip install weasyprint' und unter macOS 'brew install pango'."
        )


def _dokument(titel: str, seiten: list[str]) -> str:
    css = (VORLAGEN / "druck.css").read_text(encoding="utf-8")
    inhalt = "\n".join(f'<div class="seite">{s}</div>' for s in seiten)
    return (
        "<!DOCTYPE html><html lang=\"de\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(titel)}</title><style>{css}</style></head>"
        f"<body>{inhalt}</body></html>"
    )


def _e(text: object) -> str:
    return html.escape(str(text))


# ---------------------------------------------------------------------------
# Laufzettel Bewerbende (F_DM_001)
# ---------------------------------------------------------------------------

def laufzettel_bewerbende_html(plan: Plan, kontext: PlanKontext, jahrgang: str) -> str:
    seiten = []
    for info in sorted(kontext.planbare_bewerber(), key=lambda b: (b.name, b.vorname)):
        ereignisse = sorted(plan.fuer_bewerber(info.id), key=lambda z: z.start_min)
        if not ereignisse:
            continue
        zeilen = []
        for z in ereignisse:
            fmt = kontext.konfiguration.format(z.format_key)
            raum = kontext.raeume.get(z.raum_id)
            pruefer = ", ".join(
                kontext.pruefer[p].anzeigename for p in sorted(z.pruefer_ids)
                if p in kontext.pruefer
            )
            zeilen.append(
                f"<tr><td>{hhmm(z.start_min)} – {hhmm(z.ende_min)}</td>"
                f"<td>{_e(fmt.name)}</td>"
                f"<td>{_e(raum.raumnummer if raum else z.raum_id)}</td>"
                f"<td>{_e(pruefer)}</td></tr>"
            )
        gruppe = kontext.gruppen.get(info.gruppe_id)
        seiten.append(
            f"<h1>Laufzettel – {_e(info.anzeigename)}</h1>"
            f"<div class='untertitel'>Mündliches Auswahlverfahren {_e(jahrgang)} · "
            f"Prüfungstag: {'Freitag' if info.tag.value == 'Fr' else 'Samstag'}"
            f"{' · ' + _e(gruppe.bezeichnung) if gruppe else ''}</div>"
            "<table><thead><tr><th>Zeit</th><th>Prüfungsteil</th><th>Raum</th>"
            "<th>Prüfende</th></tr></thead><tbody>" + "".join(zeilen) + "</tbody></table>"
            "<div class='hinweisbox'>Bitte finden Sie sich jeweils fünf Minuten vor "
            "Beginn vor dem angegebenen Raum ein. Die Kaffeepause vor dem "
            "Gruppenvortrag dient der informellen Vorbereitung.</div>"
        )
    return _dokument(f"Laufzettel Bewerbende {jahrgang}", seiten)


# ---------------------------------------------------------------------------
# Laufzettel Prüfende (F_DM_001)
# ---------------------------------------------------------------------------

def laufzettel_pruefende_html(plan: Plan, kontext: PlanKontext, jahrgang: str) -> str:
    seiten = []
    for info in sorted(kontext.pruefer.values(), key=lambda p: (p.name, p.vorname)):
        ereignisse = sorted(plan.fuer_pruefer(info.id), key=lambda z: (z.tag.value, z.start_min))
        if not ereignisse:
            continue
        abschnitte = []
        for tag_wert, tag_name in (("Fr", "Freitag"), ("Sa", "Samstag")):
            tages = [z for z in ereignisse if z.tag.value == tag_wert]
            if not tages:
                continue
            zeilen = []
            for z in tages:
                fmt = kontext.konfiguration.format(z.format_key)
                raum = kontext.raeume.get(z.raum_id)
                bewerber = ", ".join(
                    kontext.bewerber[b].anzeigename for b in sorted(z.bewerber_ids)
                    if b in kontext.bewerber
                )
                zeilen.append(
                    f"<tr><td>{hhmm(z.start_min)} – {hhmm(z.ende_min)}</td>"
                    f"<td>{_e(fmt.name)}</td>"
                    f"<td>{_e(raum.raumnummer if raum else z.raum_id)}</td>"
                    f"<td>{_e(bewerber)}</td></tr>"
                )
            abschnitte.append(
                f"<h2>{tag_name}</h2><table><thead><tr><th>Zeit</th><th>Prüfungsteil</th>"
                "<th>Raum</th><th>Bewerbende</th></tr></thead><tbody>"
                + "".join(zeilen) + "</tbody></table>"
            )
        seiten.append(
            f"<h1>Einsatzplan – {_e(info.anzeigename)} ({_e(info.status.value)})</h1>"
            f"<div class='untertitel'>Mündliches Auswahlverfahren {_e(jahrgang)}</div>"
            + "".join(abschnitte)
        )
    return _dokument(f"Laufzettel Prüfende {jahrgang}", seiten)


# ---------------------------------------------------------------------------
# Raumschilder (F_DM_002)
# ---------------------------------------------------------------------------

def raumschilder_html(plan: Plan, kontext: PlanKontext, jahrgang: str) -> str:
    seiten = []
    for raum in sorted(kontext.raeume.values(), key=lambda r: r.raumnummer):
        for tag_wert, tag_name in (("Fr", "Freitag"), ("Sa", "Samstag")):
            tages = sorted(
                (z for z in plan.zuweisungen if z.raum_id == raum.id and z.tag.value == tag_wert),
                key=lambda z: z.start_min,
            )
            if not tages:
                continue
            zeilen = []
            for z in tages:
                fmt = kontext.konfiguration.format(z.format_key)
                gruppe = kontext.gruppen.get(z.gruppe_id) if z.gruppe_id else None
                wer = gruppe.bezeichnung if gruppe else ", ".join(
                    kontext.bewerber[b].anzeigename for b in sorted(z.bewerber_ids)
                    if b in kontext.bewerber
                )
                zeilen.append(
                    f"<tr><td>{hhmm(z.start_min)} – {hhmm(z.ende_min)}</td>"
                    f"<td>{_e(fmt.name)}</td><td>{_e(wer)}</td></tr>"
                )
            seiten.append(
                "<div class='raumschild'>"
                f"<div class='raumnummer'>Raum {_e(raum.raumnummer)}</div>"
                f"<div class='tagestitel'>Mündliches Auswahlverfahren {_e(jahrgang)} – {tag_name}</div>"
                "<table><thead><tr><th>Zeit</th><th>Prüfungsteil</th><th>Teilnehmende</th>"
                "</tr></thead><tbody>" + "".join(zeilen) + "</tbody></table></div>"
            )
    return _dokument(f"Raumschilder {jahrgang}", seiten)


# ---------------------------------------------------------------------------
# PDF-Wandlung
# ---------------------------------------------------------------------------

def html_zu_pdf(html_text: str) -> bytes:
    try:
        from weasyprint import HTML
    except Exception as e:  # ImportError oder fehlende Systembibliotheken (OSError)
        raise PdfNichtVerfuegbar() from e
    return HTML(string=html_text).write_pdf()
