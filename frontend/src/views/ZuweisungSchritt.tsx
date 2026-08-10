import { useCallback, useEffect, useRef, useState } from "react";
import { ApiFehler, get, post } from "../api";
import type { BerechnungsStatus, Gruppe, Konflikt } from "../types";

/** Schritt 3 – Gruppeneinteilung (F_OM_006) und Zuweisung (F_OM_007/011). */
export function ZuweisungSchritt({
  jahrgangId,
  zurKontrolle,
}: {
  jahrgangId: number;
  zurKontrolle: () => void;
}) {
  const [gruppen, setGruppen] = useState<Gruppe[]>([]);
  const [seed, setSeed] = useState<string>("");
  const [status, setStatus] = useState<BerechnungsStatus>({ status: "keine" });
  const [fehler, setFehler] = useState<string | null>(null);
  const abfrage = useRef<number | null>(null);

  const gruppenLaden = useCallback(
    () => get<Gruppe[]>(`/api/jahrgaenge/${jahrgangId}/gruppen`).then(setGruppen),
    [jahrgangId]
  );

  const statusLaden = useCallback(async () => {
    const s = await get<BerechnungsStatus>(`/api/jahrgaenge/${jahrgangId}/berechnen/status`);
    setStatus(s);
    return s;
  }, [jahrgangId]);

  useEffect(() => {
    gruppenLaden().catch(() => undefined);
    statusLaden().catch(() => undefined);
    return () => {
      if (abfrage.current) window.clearInterval(abfrage.current);
    };
  }, [gruppenLaden, statusLaden]);

  const einteilen = async () => {
    setFehler(null);
    try {
      await post(`/api/jahrgaenge/${jahrgangId}/gruppen/einteilen`,
        seed.trim() === "" ? {} : { seed: Number(seed) });
      await gruppenLaden();
    } catch (e) {
      setFehler(e instanceof ApiFehler ? e.message : "Einteilung fehlgeschlagen.");
    }
  };

  const berechnen = async (neuberechnung: boolean) => {
    setFehler(null);
    try {
      await post(`/api/jahrgaenge/${jahrgangId}/berechnen`, { neuberechnung });
      setStatus({ status: "laeuft" });
      abfrage.current = window.setInterval(async () => {
        const s = await statusLaden();
        if (s.status !== "laeuft" && abfrage.current) {
          window.clearInterval(abfrage.current);
          abfrage.current = null;
        }
      }, 2000);
    } catch (e) {
      setFehler(e instanceof ApiFehler ? e.message : "Berechnung konnte nicht gestartet werden.");
    }
  };

  const verschieben = async (bewerberId: number, gruppeId: number) => {
    setFehler(null);
    try {
      await post(`/api/jahrgaenge/${jahrgangId}/gruppen/verschieben`, {
        bewerber_id: bewerberId,
        gruppe_id: gruppeId,
      });
      await gruppenLaden();
    } catch (e) {
      setFehler(e instanceof ApiFehler ? e.message : "Verschieben fehlgeschlagen.");
    }
  };

  const fr = gruppen.filter((g) => g.tag === "Fr");
  const sa = gruppen.filter((g) => g.tag === "Sa");

  return (
    <>
      <h2>Schritt 3 – Zuweisung berechnen</h2>
      {fehler && <div className="fehler">{fehler}</div>}

      <div className="karte">
        <h3 style={{ marginTop: 0 }}>Stufe 1: Gruppeneinteilung</h3>
        <p className="hinweis">
          Zufallsbasiert und möglichst gemischt nach Geschlecht und Studiengang (W3).
          Neue Einteilung verwirft die bisherige; einzelne Personen können unten
          manuell verschoben werden.
        </p>
        <div className="zeile" style={{ alignItems: "flex-end" }}>
          <label className="feld">
            <span>Seed (leer = aus Konfiguration)</span>
            <input value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="z. B. 42" />
          </label>
          <button onClick={einteilen}>Gruppen (neu) einteilen</button>
          <span className="hinweis">
            {fr.length} Gruppen Fr, {sa.length} Gruppen Sa
          </span>
        </div>

        {gruppen.length > 0 && (
          <div className="zeile" style={{ marginTop: "0.75rem" }}>
            {[{ titel: "Freitag", liste: fr }, { titel: "Samstag", liste: sa }].map(({ titel, liste }) => (
              <div key={titel} style={{ flex: 1, minWidth: 380 }}>
                <h3>{titel}</h3>
                <div className="tabellen-rahmen" style={{ maxHeight: 300 }}>
                  <table>
                    <thead>
                      <tr><th>Gruppe</th><th>Mitglieder (verschiebbar)</th></tr>
                    </thead>
                    <tbody>
                      {liste.map((g) => (
                        <tr key={g.id}>
                          <td>{g.bezeichnung}</td>
                          <td>
                            {g.mitglieder.map((m) => (
                              <span key={m.id} style={{ display: "inline-flex", gap: 2, marginRight: 8 }}>
                                {m.vorname} {m.name}
                                <select
                                  className="klein"
                                  value={g.id}
                                  title="In andere Gruppe verschieben"
                                  onChange={(e) => verschieben(m.id, Number(e.target.value))}
                                >
                                  {liste.map((ziel) => (
                                    <option key={ziel.id} value={ziel.id}>
                                      {ziel.bezeichnung}
                                    </option>
                                  ))}
                                </select>
                              </span>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="karte">
        <h3 style={{ marginTop: 0 }}>Stufe 2: Zuweisung Prüfende – Bewerbende – Räume</h3>
        <div className="zeile">
          <button
            onClick={() => berechnen(false)}
            disabled={status.status === "laeuft" || gruppen.length === 0}
          >
            Vollberechnung starten
          </button>
          <button
            className="sekundaer"
            onClick={() => berechnen(true)}
            disabled={status.status === "laeuft" || gruppen.length === 0}
            title="Bestehende Zuweisungen möglichst beibehalten (minimalinvasiv, W6)"
          >
            Neuberechnung (Bestand erhalten)
          </button>
          {gruppen.length === 0 && (
            <span className="hinweis">Zuerst Gruppen einteilen.</span>
          )}
        </div>

        {status.status === "laeuft" && (
          <div className="erfolg" style={{ background: "var(--gelb-hell)", borderColor: "#c9a200", color: "#8a6d00" }}>
            Berechnung läuft … (Regeln H1–H9 als Constraints, Ziele W1–W6 in der
            Optimierung; Zeitlimit gemäß Konfiguration)
          </div>
        )}

        {status.status === "fertig" && (
          <>
            <div className="erfolg">
              Berechnung abgeschlossen: Planungsstand&nbsp;v{status.version} in{" "}
              {status.laufzeit_sekunden}s —{" "}
              {typeof status.konflikte === "number" && status.konflikte === 0
                ? "keine Konflikte."
                : `${status.konflikte} Konflikt(e), Details in der Kontrolle.`}
              {(status.hinweise ?? []).map((h, i) => (
                <div key={i} className="hinweis">{h}</div>
              ))}
            </div>
            <button onClick={zurKontrolle}>Weiter zur Kontrolle →</button>
          </>
        )}

        {status.status === "unloesbar" && (
          <div className="fehler">
            <b>Keine gültige Zuteilung möglich.</b> Verletzte Regeln:
            <ul style={{ margin: "0.4rem 0 0", paddingLeft: "1.1rem" }}>
              {(status.konflikte as Konflikt[] | undefined)?.map((k, i) => (
                <li key={i}>
                  <b>{k.regel}:</b> {k.meldung}
                </li>
              ))}
            </ul>
          </div>
        )}

        {status.status === "fehler" && (
          <div className="fehler">Interner Fehler: {status.meldung}</div>
        )}
      </div>
    </>
  );
}
