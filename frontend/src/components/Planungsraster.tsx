import type { PlanAnsicht, ZuweisungAnsicht } from "../types";

/** Raster Raum × Zeitfenster (F_OM_014) mit Sichtenwechsel auf
 * Bewerbende/Prüfende. Konflikt-Zuweisungen sind rot markiert (F_OM_015). */
export function Planungsraster({
  plan,
  tag,
  sicht,
  markiert,
  onAuswahl,
}: {
  plan: PlanAnsicht;
  tag: "Fr" | "Sa";
  sicht: "raeume" | "bewerbende" | "pruefende";
  markiert: Set<number>;
  onAuswahl: (z: ZuweisungAnsicht) => void;
}) {
  const von = plan.zeitmodell.start_min;
  const bis = plan.zeitmodell.ende_min;
  const spanne = bis - von;
  const zuweisungen = plan.zuweisungen.filter((z) => z.tag === tag);

  let zeilen: { schluessel: string; label: string; bloecke: ZuweisungAnsicht[] }[] = [];
  if (sicht === "raeume") {
    zeilen = plan.raeume
      .filter((r) => r.aktiv || zuweisungen.some((z) => z.raum_id === r.id))
      .map((r) => ({
        schluessel: `r${r.id}`,
        label: `${r.raumnummer} (${r.groesse}${r.aktiv ? "" : ", ausgefallen"})`,
        bloecke: zuweisungen.filter((z) => z.raum_id === r.id),
      }));
  } else {
    const personen = new Map<number, { name: string; bloecke: ZuweisungAnsicht[] }>();
    for (const z of zuweisungen) {
      for (const p of sicht === "bewerbende" ? z.bewerber : z.pruefer) {
        if (!personen.has(p.id)) personen.set(p.id, { name: p.name, bloecke: [] });
        personen.get(p.id)!.bloecke.push(z);
      }
    }
    zeilen = [...personen.entries()]
      .sort((a, b) => a[1].name.localeCompare(b[1].name, "de"))
      .map(([id, e]) => ({ schluessel: `p${id}`, label: e.name, bloecke: e.bloecke }));
  }

  const stunden: number[] = [];
  for (let m = von; m <= bis; m += 60) stunden.push(m);

  return (
    <div className="raster-wrap">
      <div className="raster-zeitachse">
        {stunden.map((m) => (
          <span key={m} style={{ flex: 1 }}>
            {String(Math.floor(m / 60)).padStart(2, "0")}:{String(m % 60).padStart(2, "0")}
          </span>
        ))}
      </div>
      <div className="raster">
        {zeilen.map((zeile) => (
          <div className="raster-zeile" key={zeile.schluessel}>
            <div className="raster-label" title={zeile.label}>{zeile.label}</div>
            <div className="raster-spur">
              {zeile.bloecke.map((z) => (
                <div
                  key={`${zeile.schluessel}-${z.id}`}
                  id={`zuweisung-${z.id}`}
                  className={[
                    "raster-block",
                    z.format_typ === "gruppe" ? "gruppe" : "",
                    z.format_typ === "thesen" ? "thesen" : "",
                    z.konflikt ? "konflikt" : "",
                    markiert.has(z.id) ? "markiert" : "",
                  ].join(" ")}
                  style={{
                    left: `${((z.start_min - von) / spanne) * 100}%`,
                    width: `${((z.ende_min - z.start_min) / spanne) * 100}%`,
                  }}
                  title={`${z.format_name} · ${z.start}–${z.ende} · Raum ${z.raumnummer}\nBewerbende: ${z.bewerber
                    .map((b) => b.name)
                    .join(", ")}\nPrüfende: ${z.pruefer.map((p) => p.name).join(", ")}`}
                  onClick={() => onAuswahl(z)}
                >
                  {z.manuell_geaendert ? "✎ " : ""}
                  {sicht === "raeume"
                    ? `${z.start} ${z.gruppe ?? z.bewerber.map((b) => b.name).join(", ")}`
                    : `${z.start} ${z.format_name} · ${z.raumnummer}`}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
