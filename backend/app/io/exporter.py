"""CSV-Export der Zuteilung (F_OM_013, Format siehe docs/formats.md §5).

Die Erzeugung ist vom Transportweg entkoppelt (String heute, API morgen —
Kap. 10). Versionierung und Datei-Ablage kommen in der API-Schicht (M6).
"""

from __future__ import annotations

import csv
import io

from ..core.konfiguration import hhmm
from ..core.plan import Plan, PlanKontext

EXPORT_SPALTEN = [
    "export_version", "jahrgang", "tag", "zeit_von", "zeit_bis", "format",
    "raum", "gruppe", "rolle", "person_id", "nachname", "vorname", "partner_ids",
]


def plan_als_csv(
    plan: Plan,
    kontext: PlanKontext,
    jahrgang_bezeichnung: str,
    export_version: int,
) -> str:
    """Eine Zeile je Person × Prüfungsereignis, inkl. Zuordnung
    Prüfende↔Bewerbende (AK7)."""
    puffer = io.StringIO()
    writer = csv.writer(puffer, delimiter=";", lineterminator="\n")
    writer.writerow(EXPORT_SPALTEN)

    def sortierschluessel(z):
        return (z.tag.value, z.start_min, kontext.raeume[z.raum_id].raumnummer
                if z.raum_id in kontext.raeume else str(z.raum_id))

    for z in sorted(plan.zuweisungen, key=sortierschluessel):
        fmt = kontext.konfiguration.format(z.format_key)
        raum = kontext.raeume.get(z.raum_id)
        gruppe = kontext.gruppen.get(z.gruppe_id) if z.gruppe_id else None
        bewerber_keys = ",".join(sorted(
            kontext.bewerber[b].import_key or str(b) for b in z.bewerber_ids
        ))
        pruefer_keys = ",".join(sorted(
            kontext.pruefer[p].import_key or str(p) for p in z.pruefer_ids
        ))
        basis = [
            export_version, jahrgang_bezeichnung, z.tag.value,
            hhmm(z.start_min), hhmm(z.ende_min), fmt.name,
            raum.raumnummer if raum else z.raum_id,
            gruppe.bezeichnung if gruppe else "",
        ]
        for bid in sorted(z.bewerber_ids):
            b = kontext.bewerber[bid]
            writer.writerow(basis + ["Bewerber", b.import_key or bid, b.name, b.vorname, pruefer_keys])
        for pid in sorted(z.pruefer_ids):
            p = kontext.pruefer[pid]
            writer.writerow(basis + ["Pruefer", p.import_key or pid, p.name, p.vorname, bewerber_keys])
    return puffer.getvalue()
