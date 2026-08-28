import { useCallback, useEffect, useState } from "react";
import { ApiFehler, get, post } from "../api";
import type { ExportLauf, Planungsstand } from "../types";

/** Schritt 5 – versionierter CSV-Export an Access (F_OM_013), Druckdaten
 * (F_DM_001/002) und Datensicherung (NF_004). */
export function ExportSchritt({ jahrgangId }: { jahrgangId: number }) {
  const [laeufe, setLaeufe] = useState<ExportLauf[]>([]);
  const [staende, setStaende] = useState<Planungsstand[]>([]);
  const [backups, setBackups] = useState<string[]>([]);
  const [meldung, setMeldung] = useState<{ text: string; fehler: boolean } | null>(null);

  const laden = useCallback(async () => {
    const [l, s, b] = await Promise.all([
      get<ExportLauf[]>(`/api/jahrgaenge/${jahrgangId}/export/laeufe`),
      get<Planungsstand[]>(`/api/jahrgaenge/${jahrgangId}/planungsstaende`),
      get<string[]>("/api/backup/liste"),
    ]);
    setLaeufe(l);
    setStaende(s);
    setBackups(b);
  }, [jahrgangId]);

  useEffect(() => {
    laden().catch(() => undefined);
  }, [laden]);

  const exportieren = async () => {
    setMeldung(null);
    try {
      const e = await post<{ version: number; dateiname: string; id: number }>(
        `/api/jahrgaenge/${jahrgangId}/export`
      );
      setMeldung({ text: `Export v${e.version} erstellt: ${e.dateiname}`, fehler: false });
      await laden();
      window.open(`/api/export/${e.id}/datei`, "_blank");
    } catch (err) {
      setMeldung({
        text: err instanceof ApiFehler ? err.message : "Export fehlgeschlagen.",
        fehler: true,
      });
    }
  };

  const sichern = async () => {
    setMeldung(null);
    const b = await post<{ datei: string }>("/api/backup");
    setMeldung({ text: `Sicherung erstellt: ${b.datei}`, fehler: false });
    await laden();
  };

  return (
    <>
      <h2>Schritt 5 – Export</h2>
      {meldung && <div className={meldung.fehler ? "fehler" : "erfolg"}>{meldung.text}</div>}

      <div className="zeile">
        <div className="karte">
          <h3 style={{ marginTop: 0 }}>Zuteilung an Access (CSV)</h3>
          <p className="hinweis">
            Vollständige finale Zuteilung: je Zuweisung Person, Tag, Zeitfenster,
            Raum, Format, Gruppe sowie die Zuordnung Prüfende↔Bewerbende
            (Grundlage der Abschlusskonferenz). Exporte sind versioniert und nach
            jeder Neuberechnung wiederholbar. Format: docs/formats.md&nbsp;§5.
          </p>
          <button onClick={exportieren} disabled={staende.length === 0}>
            Export erstellen und herunterladen
          </button>
          {staende.length === 0 && (
            <p className="hinweis">Noch kein Planungsstand — zuerst berechnen (Schritt 3).</p>
          )}
          <h3>Bisherige Exporte</h3>
          <table>
            <thead>
              <tr><th>Version</th><th>Datei</th><th>Planungsstand</th><th>Erstellt</th><th></th></tr>
            </thead>
            <tbody>
              {laeufe.map((l) => (
                <tr key={l.id}>
                  <td>v{l.version}</td>
                  <td>{l.dateiname}</td>
                  <td>{l.planungsstand_version != null ? `v${l.planungsstand_version}` : "–"}</td>
                  <td>{new Date(l.erstellt_am).toLocaleString("de-DE")}</td>
                  <td>
                    <a href={`/api/export/${l.id}/datei`} target="_blank" rel="noreferrer">
                      Herunterladen
                    </a>
                  </td>
                </tr>
              ))}
              {laeufe.length === 0 && (
                <tr><td colSpan={5} className="hinweis">Noch keine Exporte.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="karte">
          <h3 style={{ marginTop: 0 }}>Druckdaten (PDF)</h3>
          <p className="hinweis">
            Laufzettel je Bewerber:in und Prüfer:in sowie Raumschilder — jeweils
            aus dem aktuellen Planungsstand, nach Neuberechnung einfach neu erzeugen.
            „Ansehen" öffnet die Vorschau im Browser, „Speichern" legt die
            PDF-Datei direkt ab.
          </p>
          <div className="feldgruppe">
            {([
              ["laufzettel-bewerbende", "Laufzettel Bewerbende"],
              ["laufzettel-pruefende", "Laufzettel Prüfende"],
              ["raumschilder", "Raumschilder"],
            ] as const).map(([art, beschriftung]) => (
              <div className="feld" key={art}>
                <span>{beschriftung}</span>
                <div className="zeile">
                  <a
                    href={`/api/jahrgaenge/${jahrgangId}/druck/${art}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <button className="klein sekundaer" disabled={staende.length === 0}>
                      Ansehen
                    </button>
                  </a>
                  <a href={`/api/jahrgaenge/${jahrgangId}/druck/${art}?download=1`}>
                    <button className="klein sekundaer" disabled={staende.length === 0}>
                      Speichern
                    </button>
                  </a>
                </div>
              </div>
            ))}
          </div>

          <h3>Datensicherung</h3>
          <p className="hinweis">
            Sichert die komplette Datenbank (alle Jahrgänge und Planungsstände).
            Der letzte gültige Stand bleibt so jederzeit wiederherstellbar (NF_004).
          </p>
          <button className="sekundaer" onClick={sichern}>Sicherung jetzt erstellen</button>
          <ul className="hinweis">
            {backups.slice(0, 5).map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>

          <h3>Planungsstände</h3>
          <table>
            <thead>
              <tr><th>Version</th><th>Typ</th><th>Erstellt</th><th>Seed</th></tr>
            </thead>
            <tbody>
              {staende.map((s) => (
                <tr key={s.id}>
                  <td>v{s.version}</td>
                  <td>{s.typ}</td>
                  <td>{new Date(s.erstellt_am).toLocaleString("de-DE")}</td>
                  <td>{s.seed ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
