import { useEffect, useState } from "react";
import { ApiFehler, get, put } from "../api";
import type { Konfiguration } from "../types";

/** Schritt 2 – Parametrierung ohne Programmierkenntnisse (F_OM_010).
 * Alle Variablen des Verfahrens; je Jahrgang gespeichert und beim Anlegen
 * eines neuen Jahrgangs als Vorlage übernehmbar (NF_008). */
export function ParameterSchritt({ jahrgangId }: { jahrgangId: number }) {
  const [konf, setKonf] = useState<Konfiguration | null>(null);
  const [meldung, setMeldung] = useState<{ text: string; fehler: boolean } | null>(null);

  useEffect(() => {
    setMeldung(null);
    get<Konfiguration>(`/api/jahrgaenge/${jahrgangId}/konfiguration`).then(setKonf);
  }, [jahrgangId]);

  if (!konf) return null;

  const speichern = async () => {
    setMeldung(null);
    try {
      await put(`/api/jahrgaenge/${jahrgangId}/konfiguration`, konf);
      setMeldung({ text: "Konfiguration gespeichert.", fehler: false });
    } catch (e) {
      setMeldung({
        text: e instanceof ApiFehler ? e.message : "Speichern fehlgeschlagen.",
        fehler: true,
      });
    }
  };

  const zm = konf.zeitmodell;

  return (
    <>
      <h2>Schritt 2 – Parametrierung</h2>
      {meldung && (
        <div className={meldung.fehler ? "fehler" : "erfolg"}>{meldung.text}</div>
      )}

      <div className="zeile">
        <div className="karte">
          <h3 style={{ marginTop: 0 }}>Tages-Zeitmodell</h3>
          <div className="zeile">
            <label className="feld">
              <span>Beginn</span>
              <input
                type="time"
                value={zm.tag_start}
                onChange={(e) =>
                  setKonf({ ...konf, zeitmodell: { ...zm, tag_start: e.target.value } })
                }
              />
            </label>
            <label className="feld">
              <span>Ende (harte Grenze)</span>
              <input
                type="time"
                value={zm.tag_ende}
                onChange={(e) =>
                  setKonf({ ...konf, zeitmodell: { ...zm, tag_ende: e.target.value } })
                }
              />
            </label>
            <label className="feld">
              <span>Vorbereitungspuffer Gruppe (Min.)</span>
              <input
                type="number"
                min={0}
                step={15}
                value={zm.puffer_min}
                onChange={(e) =>
                  setKonf({ ...konf, zeitmodell: { ...zm, puffer_min: Number(e.target.value) } })
                }
              />
            </label>
            <label className="feld">
              <span>Mindestpause zwischen Terminen (Min.)</span>
              <input
                type="number"
                min={0}
                step={15}
                value={zm.mindestpause_min}
                onChange={(e) =>
                  setKonf({
                    ...konf,
                    zeitmodell: { ...zm, mindestpause_min: Number(e.target.value) },
                  })
                }
              />
            </label>
          </div>
          <p className="hinweis">
            Alle Zuweisungen liegen vollständig innerhalb dieses Fensters. Die
            <b> Mindestpause</b> ist die Wegzeit für den Raumwechsel und gilt zwischen
            allen Terminen einer Person; der <b>Vorbereitungspuffer</b> gilt zusätzlich
            nur vor dem Gruppenvortrag (Kaffeepause). Beide Werte wirken nur in
            Schritten von 15&nbsp;Minuten — das ist das Zeitraster der Planung.
          </p>
        </div>

        <div className="karte">
          <h3 style={{ marginTop: 0 }}>Gruppen &amp; Berechnung</h3>
          <div className="zeile">
            <label className="feld">
              <span>Gruppengröße Bewerbende</span>
              <input
                type="number"
                min={2}
                max={8}
                value={konf.gruppengroesse}
                onChange={(e) => setKonf({ ...konf, gruppengroesse: Number(e.target.value) })}
              />
            </label>
            <label className="feld">
              <span>Zeitbudget je Optimierungsschritt (Sek.)</span>
              <input
                type="number"
                min={5}
                max={60}
                value={konf.solver.schritt_budget_sekunden}
                onChange={(e) =>
                  setKonf({
                    ...konf,
                    solver: {
                      ...konf.solver,
                      schritt_budget_sekunden: Number(e.target.value),
                    },
                  })
                }
              />
            </label>
            <label className="feld">
              <span>Zufalls-Seed (Reproduzierbarkeit)</span>
              <input
                type="number"
                value={konf.solver.seed}
                onChange={(e) =>
                  setKonf({ ...konf, solver: { ...konf.solver, seed: Number(e.target.value) } })
                }
              />
            </label>
          </div>
          <p className="hinweis">
            Das Budget gilt je Optimierungsschritt, nicht für den Gesamtlauf: eine
            Berechnung besteht aus drei Schritten je Prüfungstag (Zeitplanung,
            Raumvergabe, Prüfendenzuordnung). Mehr als 60&nbsp;Sekunden bringt kein
            besseres Ergebnis — die Lösungsqualität erreicht ihr Plateau nach
            wenigen Sekunden; ein kleinerer Wert verkürzt die Wartezeit.
          </p>
        </div>
      </div>

      <div className="karte">
        <h3 style={{ marginTop: 0 }}>Prüfungsformate</h3>
        <p className="hinweis">
          Referenz 2026/2027: 2 Einzelgespräche à 30&nbsp;min (nur Senior), Gruppenarbeit
          45&nbsp;min, Thesenvortrag als 2,5-h-Block. Eine Zusammenlegung der
          Einzelgespräche ist reine Konfigurationsänderung (Dauer anpassen, Format entfernen).
        </p>
        <table>
          <thead>
            <tr>
              <th>Format</th><th>Typ</th><th>Dauer (min)</th><th>Prüfende</th>
              <th>min. Senior</th><th>max. Junior</th><th>Raumgröße</th><th>nur Senior</th>
            </tr>
          </thead>
          <tbody>
            {konf.formate.map((f, i) => (
              <tr key={f.key}>
                <td>
                  <input
                    value={f.name}
                    style={{ width: "14rem" }}
                    onChange={(e) => {
                      const formate = [...konf.formate];
                      formate[i] = { ...f, name: e.target.value };
                      setKonf({ ...konf, formate });
                    }}
                  />
                </td>
                <td>{f.typ}</td>
                <td>
                  <input
                    type="number"
                    min={5}
                    step={5}
                    value={f.dauer_min}
                    onChange={(e) => {
                      const formate = [...konf.formate];
                      formate[i] = { ...f, dauer_min: Number(e.target.value) };
                      setKonf({ ...konf, formate });
                    }}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min={1}
                    value={f.anzahl_pruefer}
                    onChange={(e) => {
                      const formate = [...konf.formate];
                      formate[i] = { ...f, anzahl_pruefer: Number(e.target.value) };
                      setKonf({ ...konf, formate });
                    }}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min={0}
                    value={f.min_senior}
                    disabled={f.typ === "einzel"}
                    onChange={(e) => {
                      const formate = [...konf.formate];
                      formate[i] = { ...f, min_senior: Number(e.target.value) };
                      setKonf({ ...konf, formate });
                    }}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min={0}
                    value={f.max_junior}
                    disabled={f.typ === "einzel"}
                    onChange={(e) => {
                      const formate = [...konf.formate];
                      formate[i] = { ...f, max_junior: Number(e.target.value) };
                      setKonf({ ...konf, formate });
                    }}
                  />
                </td>
                <td>{f.raumgroesse}</td>
                <td>{f.nur_senior ? "ja" : "nein"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="hinweis">
          Summe der Prüfergruppengrößen ={" "}
          <b>{konf.formate.reduce((s, f) => s + f.anzahl_pruefer, 0)} Kontakte</b> je
          Bewerber:in (Ziel: 8 unterschiedliche Prüfende).
        </p>
      </div>

      <button onClick={speichern}>Konfiguration speichern</button>
    </>
  );
}
