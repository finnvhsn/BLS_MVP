import { useEffect, useState } from "react";
import { get } from "../api";
import type { ProtokollEintrag } from "../types";

/** Lauf- und Änderungsprotokoll (NF_010). */
export function ProtokollPanel({
  jahrgangId,
  onSchliessen,
}: {
  jahrgangId: number;
  onSchliessen: () => void;
}) {
  const [eintraege, setEintraege] = useState<ProtokollEintrag[]>([]);

  useEffect(() => {
    get<ProtokollEintrag[]>(`/api/jahrgaenge/${jahrgangId}/protokoll`).then(setEintraege);
  }, [jahrgangId]);

  return (
    <div className="dialog-hintergrund" onClick={onSchliessen}>
      <div className="dialog" style={{ minWidth: 640 }} onClick={(e) => e.stopPropagation()}>
        <h2>Protokoll (Berechnungsläufe &amp; manuelle Eingriffe)</h2>
        <div className="tabellen-rahmen" style={{ maxHeight: 480 }}>
          <table>
            <thead>
              <tr><th>Zeitpunkt</th><th>Benutzer</th><th>Aktion</th><th>Details</th></tr>
            </thead>
            <tbody>
              {eintraege.map((p, i) => (
                <tr key={i}>
                  <td>{new Date(p.zeitpunkt).toLocaleString("de-DE")}</td>
                  <td>{p.benutzer}</td>
                  <td>{p.aktion}</td>
                  <td className="hinweis">
                    {Object.entries(p.details)
                      .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
                      .join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ marginTop: "0.8rem", textAlign: "right" }}>
          <button onClick={onSchliessen}>Schließen</button>
        </div>
      </div>
    </div>
  );
}
