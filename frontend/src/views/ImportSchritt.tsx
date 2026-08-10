import { useCallback, useEffect, useState } from "react";
import { ApiFehler, del, get, hochladen, patch, post } from "../api";
import type {
  Befangenheit,
  BewerberZeile,
  ImportErgebnis,
  PrueferZeile,
  RaumZeile,
} from "../types";

const IMPORTE: { typ: string; titel: string; hinweis: string }[] = [
  { typ: "bewerbende", titel: "Bewerbende", hinweis: "CSV aus Access – inkl. Tageszuteilung (Fr/Sa)" },
  { typ: "pruefende", titel: "Prüfende", hinweis: "CSV aus Salesforce – Senior/Junior, Verfügbarkeit" },
  { typ: "raeume", titel: "Räume", hinweis: "CSV – Raumnummer, Größe (klein/gross), Verfügbarkeit" },
  { typ: "befangenheiten", titel: "Befangenheiten", hinweis: "CSV – Paare pruefer_id;bewerber_id (ohne Grund)" },
];

export function ImportSchritt({ jahrgangId }: { jahrgangId: number }) {
  const [ergebnisse, setErgebnisse] = useState<Record<string, ImportErgebnis>>({});
  const [fehler, setFehler] = useState<string | null>(null);
  const [bewerbende, setBewerbende] = useState<BewerberZeile[]>([]);
  const [pruefende, setPruefende] = useState<PrueferZeile[]>([]);
  const [raeume, setRaeume] = useState<RaumZeile[]>([]);
  const [befangenheiten, setBefangenheiten] = useState<Befangenheit[]>([]);
  const [tabelle, setTabelle] = useState<"bewerbende" | "pruefende" | "raeume" | "befangenheiten">("bewerbende");
  const [neuerRaum, setNeuerRaum] = useState({ raumnummer: "", groesse: "klein" });
  const [neueBefangenheit, setNeueBefangenheit] = useState({ pruefer_id: 0, bewerber_id: 0 });

  const laden = useCallback(async () => {
    const basis = `/api/jahrgaenge/${jahrgangId}`;
    const [b, p, r, bef] = await Promise.all([
      get<BewerberZeile[]>(`${basis}/bewerbende`),
      get<PrueferZeile[]>(`${basis}/pruefende`),
      get<RaumZeile[]>(`${basis}/raeume`),
      get<Befangenheit[]>(`${basis}/befangenheiten`),
    ]);
    setBewerbende(b);
    setPruefende(p);
    setRaeume(r);
    setBefangenheiten(bef);
  }, [jahrgangId]);

  useEffect(() => {
    laden().catch((e) => setFehler(e.message));
  }, [laden]);

  const importieren = async (typ: string, datei: File) => {
    setFehler(null);
    try {
      const ergebnis = await hochladen<ImportErgebnis>(
        `/api/jahrgaenge/${jahrgangId}/import/${typ}`,
        datei
      );
      setErgebnisse((alt) => ({ ...alt, [typ]: ergebnis }));
      await laden();
    } catch (e) {
      setFehler(e instanceof ApiFehler ? e.message : "Import fehlgeschlagen.");
    }
  };

  const planbar = bewerbende.filter((b) => b.planbar).length;

  return (
    <>
      <h2>Schritt 1 – Datenimport</h2>
      {fehler && <div className="fehler">{fehler}</div>}
      <div className="zeile">
        {IMPORTE.map(({ typ, titel, hinweis }) => {
          const e = ergebnisse[typ];
          return (
            <div className="karte" key={typ}>
              <h3 style={{ marginTop: 0 }}>{titel}</h3>
              <p className="hinweis">{hinweis}</p>
              <input
                type="file"
                accept=".csv"
                onChange={(ev) => {
                  const datei = ev.target.files?.[0];
                  if (datei) importieren(typ, datei);
                  ev.target.value = "";
                }}
              />
              {e && (
                <div className={e.fehler.length ? "fehler" : "erfolg"}>
                  {e.anzahl_neu} neu, {e.anzahl_aktualisiert} aktualisiert
                  {e.fehler.length > 0 && (
                    <ul style={{ margin: "0.4rem 0 0", paddingLeft: "1.1rem" }}>
                      {e.fehler.slice(0, 8).map((f, i) => (
                        <li key={i}>
                          Zeile {f.zeile}, Spalte „{f.spalte}“: {f.meldung}
                        </li>
                      ))}
                      {e.fehler.length > 8 && <li>… und {e.fehler.length - 8} weitere</li>}
                    </ul>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="karte">
        <div className="zeile" style={{ alignItems: "center" }}>
          <h2 style={{ margin: 0 }}>Datenbestand</h2>
          <span className="abzeichen gruen">{planbar} werden eingeplant</span>
          <span className="abzeichen">{bewerbende.length} Bewerbende</span>
          <span className="abzeichen">{pruefende.length} Prüfende</span>
          <span className="abzeichen">{raeume.length} Räume</span>
          <span className="abzeichen">{befangenheiten.length} Befangenheiten</span>
        </div>
        <p className="hinweis">
          Eingeplant wird, wer <b>zugelassen</b> ist und <b>zugesagt</b> hat.
          Kurzfristige Änderungen (Absagen, Verfügbarkeiten) können hier direkt
          gepflegt werden — danach in Schritt&nbsp;3 neu berechnen.
        </p>
        <div style={{ margin: "0.5rem 0" }}>
          {(["bewerbende", "pruefende", "raeume", "befangenheiten"] as const).map((t) => (
            <button
              key={t}
              className={`klein ${tabelle === t ? "" : "sekundaer"}`}
              style={{ marginRight: "0.4rem" }}
              onClick={() => setTabelle(t)}
            >
              {t === "bewerbende" ? "Bewerbende" : t === "pruefende" ? "Prüfende" : t === "raeume" ? "Räume" : "Befangenheiten"}
            </button>
          ))}
        </div>

        {tabelle === "bewerbende" && (
          <div className="tabellen-rahmen">
            <table>
              <thead>
                <tr>
                  <th>ID</th><th>Name</th><th>Tag</th><th>Studiengang</th>
                  <th>Rückmeldung</th><th>Rücksteller</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {bewerbende.map((b) => (
                  <tr key={b.id}>
                    <td>{b.import_key}</td>
                    <td>{b.vorname} {b.name}</td>
                    <td>{b.tag}</td>
                    <td>{b.studiengang}</td>
                    <td>
                      <select
                        value={b.rueckmeldestatus}
                        onChange={async (e) => {
                          await patch(`/api/jahrgaenge/${jahrgangId}/bewerbende/${b.id}`, {
                            rueckmeldestatus: e.target.value,
                          });
                          await laden();
                        }}
                      >
                        {["Zusage", "Absage", "Alternativtermin", "Offen"].map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </select>
                    </td>
                    <td>{b.ruecksteller ? "ja" : "nein"}</td>
                    <td>
                      {b.planbar ? (
                        <span className="abzeichen gruen">wird eingeplant</span>
                      ) : (
                        <span className="abzeichen">nicht eingeplant</span>
                      )}
                      {!b.aktiv && <span className="abzeichen rot">abgesagt</span>}
                      <button
                        className="klein sekundaer"
                        style={{ marginLeft: "0.3rem" }}
                        onClick={async () => {
                          await patch(`/api/jahrgaenge/${jahrgangId}/bewerbende/${b.id}`, {
                            aktiv: !b.aktiv,
                          });
                          await laden();
                        }}
                      >
                        {b.aktiv ? "Absage erfassen" : "Absage zurücknehmen"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tabelle === "pruefende" && (
          <div className="tabellen-rahmen">
            <table>
              <thead>
                <tr><th>ID</th><th>Name</th><th>Status</th><th>Fr</th><th>Sa</th><th>Aktiv</th></tr>
              </thead>
              <tbody>
                {pruefende.map((p) => (
                  <tr key={p.id}>
                    <td>{p.import_key}</td>
                    <td>{p.vorname} {p.name}</td>
                    <td><span className={`abzeichen ${p.status === "Senior" ? "gruen" : "gelb"}`}>{p.status}</span></td>
                    {(["verfuegbar_fr", "verfuegbar_sa"] as const).map((feld) => (
                      <td key={feld}>
                        <input
                          type="checkbox"
                          checked={p[feld]}
                          onChange={async (e) => {
                            await patch(`/api/jahrgaenge/${jahrgangId}/pruefende/${p.id}`, {
                              [feld]: e.target.checked,
                            });
                            await laden();
                          }}
                        />
                      </td>
                    ))}
                    <td>
                      <input
                        type="checkbox"
                        checked={p.aktiv}
                        title="Abwählen = kurzfristige Absage"
                        onChange={async (e) => {
                          await patch(`/api/jahrgaenge/${jahrgangId}/pruefende/${p.id}`, {
                            aktiv: e.target.checked,
                          });
                          await laden();
                        }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tabelle === "raeume" && (
          <>
            <div className="zeile" style={{ alignItems: "flex-end", marginBottom: "0.5rem" }}>
              <label className="feld">
                <span>Raumnummer</span>
                <input
                  value={neuerRaum.raumnummer}
                  onChange={(e) => setNeuerRaum({ ...neuerRaum, raumnummer: e.target.value })}
                />
              </label>
              <label className="feld">
                <span>Größe</span>
                <select
                  value={neuerRaum.groesse}
                  onChange={(e) => setNeuerRaum({ ...neuerRaum, groesse: e.target.value })}
                >
                  <option value="klein">klein (Einzelgespräch)</option>
                  <option value="gross">gross (Gruppenformate)</option>
                </select>
              </label>
              <button
                onClick={async () => {
                  if (!neuerRaum.raumnummer.trim()) return;
                  await post(`/api/jahrgaenge/${jahrgangId}/raeume`, neuerRaum);
                  setNeuerRaum({ raumnummer: "", groesse: "klein" });
                  await laden();
                }}
              >
                Raum anlegen
              </button>
            </div>
            <div className="tabellen-rahmen">
              <table>
                <thead>
                  <tr><th>Raum</th><th>Größe</th><th>Fr</th><th>Sa</th><th>Sperrzeiten</th><th>Verfügbar</th></tr>
                </thead>
                <tbody>
                  {raeume.map((r) => (
                    <tr key={r.id}>
                      <td>{r.raumnummer}</td>
                      <td>{r.groesse}</td>
                      {(["verfuegbar_fr", "verfuegbar_sa"] as const).map((feld) => (
                        <td key={feld}>
                          <input
                            type="checkbox"
                            checked={r[feld]}
                            onChange={async (e) => {
                              await patch(`/api/jahrgaenge/${jahrgangId}/raeume/${r.id}`, {
                                [feld]: e.target.checked,
                              });
                              await laden();
                            }}
                          />
                        </td>
                      ))}
                      <td>
                        {r.sperrzeiten.map((s, i) => (
                          <span key={i} className="abzeichen gelb" style={{ marginRight: 4 }}>
                            {s.tag} {fmt(s.von_min)}–{fmt(s.bis_min)}
                          </span>
                        ))}
                      </td>
                      <td>
                        <input
                          type="checkbox"
                          checked={r.aktiv}
                          title="Abwählen = Raumausfall"
                          onChange={async (e) => {
                            await patch(`/api/jahrgaenge/${jahrgangId}/raeume/${r.id}`, {
                              aktiv: e.target.checked,
                            });
                            await laden();
                          }}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {tabelle === "befangenheiten" && (
          <>
            <p className="hinweis">
              Befangenheiten werden datensparsam ohne Grund gespeichert (H2). Auch
              nachträglich erfasste Befangenheiten werden bei der nächsten
              Neuberechnung berücksichtigt.
            </p>
            <div className="zeile" style={{ alignItems: "flex-end", marginBottom: "0.5rem" }}>
              <label className="feld">
                <span>Prüfer:in</span>
                <select
                  value={neueBefangenheit.pruefer_id}
                  onChange={(e) =>
                    setNeueBefangenheit({ ...neueBefangenheit, pruefer_id: Number(e.target.value) })
                  }
                >
                  <option value={0}>– wählen –</option>
                  {pruefende.map((p) => (
                    <option key={p.id} value={p.id}>{p.vorname} {p.name}</option>
                  ))}
                </select>
              </label>
              <label className="feld">
                <span>Bewerber:in</span>
                <select
                  value={neueBefangenheit.bewerber_id}
                  onChange={(e) =>
                    setNeueBefangenheit({ ...neueBefangenheit, bewerber_id: Number(e.target.value) })
                  }
                >
                  <option value={0}>– wählen –</option>
                  {bewerbende.map((b) => (
                    <option key={b.id} value={b.id}>{b.vorname} {b.name}</option>
                  ))}
                </select>
              </label>
              <button
                disabled={!neueBefangenheit.pruefer_id || !neueBefangenheit.bewerber_id}
                onClick={async () => {
                  await post(`/api/jahrgaenge/${jahrgangId}/befangenheiten`, neueBefangenheit);
                  setNeueBefangenheit({ pruefer_id: 0, bewerber_id: 0 });
                  await laden();
                }}
              >
                Befangenheit hinterlegen
              </button>
            </div>
            <div className="tabellen-rahmen">
              <table>
                <thead>
                  <tr><th>Prüfer:in</th><th>Bewerber:in</th><th></th></tr>
                </thead>
                <tbody>
                  {befangenheiten.map((bef) => {
                    const p = pruefende.find((x) => x.id === bef.pruefer_id);
                    const b = bewerbende.find((x) => x.id === bef.bewerber_id);
                    return (
                      <tr key={bef.id}>
                        <td>{p ? `${p.vorname} ${p.name}` : bef.pruefer_id}</td>
                        <td>{b ? `${b.vorname} ${b.name}` : bef.bewerber_id}</td>
                        <td>
                          <button
                            className="klein gefahr"
                            onClick={async () => {
                              await del(`/api/jahrgaenge/${jahrgangId}/befangenheiten/${bef.id}`);
                              await laden();
                            }}
                          >
                            Entfernen
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </>
  );
}

function fmt(min: number): string {
  return `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;
}
