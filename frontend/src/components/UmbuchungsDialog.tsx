import { useState } from "react";
import { ApiFehler, post } from "../api";
import type { Konflikt, PlanAnsicht, PrueferZeile, UmbuchungsAntwort, ZuweisungAnsicht } from "../types";

/** Umbuchungsdialog mit sofortiger Regelvalidierung (F_OM_012).
 * Nicht regelkonforme Änderungen werden nur nach bewusster Bestätigung
 * übernommen (F_OM_016) und protokolliert. */
export function UmbuchungsDialog({
  jahrgangId,
  zuweisung,
  plan,
  pruefende,
  onSchliessen,
  onUebernommen,
}: {
  jahrgangId: number;
  zuweisung: ZuweisungAnsicht;
  plan: PlanAnsicht;
  pruefende: PrueferZeile[];
  onSchliessen: () => void;
  onUebernommen: () => void;
}) {
  const [raumId, setRaumId] = useState(zuweisung.raum_id);
  const [start, setStart] = useState(zuweisung.start);
  const [prueferIds, setPrueferIds] = useState<number[]>(zuweisung.pruefer.map((p) => p.id));
  const [konflikte, setKonflikte] = useState<Konflikt[] | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [laedt, setLaedt] = useState(false);

  const absenden = async (bestaetigt: boolean) => {
    setLaedt(true);
    setFehler(null);
    try {
      const antwort = await post<UmbuchungsAntwort>(
        `/api/jahrgaenge/${jahrgangId}/umbuchen`,
        {
          zuweisung_id: zuweisung.id,
          raum_id: raumId !== zuweisung.raum_id ? raumId : null,
          start: start !== zuweisung.start ? start : null,
          pruefer_ids: prueferIds,
          bestaetigt,
        }
      );
      if (antwort.uebernommen) {
        onUebernommen();
      } else {
        setKonflikte(antwort.konflikte);
      }
    } catch (e) {
      setFehler(e instanceof ApiFehler ? e.message : "Umbuchung fehlgeschlagen.");
    } finally {
      setLaedt(false);
    }
  };

  const prueferUmschalten = (id: number) => {
    setKonflikte(null);
    setPrueferIds((alt) =>
      alt.includes(id) ? alt.filter((p) => p !== id) : [...alt, id]
    );
  };

  return (
    <div className="dialog-hintergrund" onClick={onSchliessen}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h2>Umbuchung: {zuweisung.format_name}</h2>
        <p className="hinweis">
          {zuweisung.tag}, {zuweisung.start}–{zuweisung.ende} · Raum {zuweisung.raumnummer}
          {zuweisung.gruppe ? ` · ${zuweisung.gruppe}` : ""}
          <br />
          Bewerbende: {zuweisung.bewerber.map((b) => b.name).join(", ")}
        </p>

        <div className="zeile">
          <label className="feld">
            <span>Beginn (Uhrzeit)</span>
            <input type="time" value={start} onChange={(e) => { setStart(e.target.value); setKonflikte(null); }} />
          </label>
          <label className="feld">
            <span>Raum</span>
            <select value={raumId} onChange={(e) => { setRaumId(Number(e.target.value)); setKonflikte(null); }}>
              {plan.raeume.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.raumnummer} ({r.groesse}{r.aktiv ? "" : ", ausgefallen"})
                </option>
              ))}
            </select>
          </label>
        </div>

        <h3>Prüfende ({prueferIds.length} zugewiesen)</h3>
        <div className="tabellen-rahmen" style={{ maxHeight: 220 }}>
          <table>
            <tbody>
              {pruefende
                .filter((p) => p.aktiv)
                .sort((a, b) => {
                  // Ursprünglich zugewiesene Prüfende zuerst
                  const aZu = zuweisung.pruefer.some((z) => z.id === a.id) ? 0 : 1;
                  const bZu = zuweisung.pruefer.some((z) => z.id === b.id) ? 0 : 1;
                  return aZu - bZu || a.name.localeCompare(b.name, "de");
                })
                .map((p) => (
                  <tr key={p.id}>
                    <td style={{ width: 30 }}>
                      <input
                        type="checkbox"
                        checked={prueferIds.includes(p.id)}
                        onChange={() => prueferUmschalten(p.id)}
                      />
                    </td>
                    <td>{p.vorname} {p.name}</td>
                    <td>
                      <span className={`abzeichen ${p.status === "Senior" ? "gruen" : "gelb"}`}>
                        {p.status}
                      </span>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        {fehler && <div className="fehler">{fehler}</div>}

        {konflikte && konflikte.length > 0 && (
          <div className="fehler">
            <b>Diese Änderung verletzt Regeln:</b>
            <ul style={{ margin: "0.4rem 0", paddingLeft: "1.1rem" }}>
              {konflikte.map((k, i) => (
                <li key={i}>
                  <b>{k.regel}:</b> {k.meldung}
                </li>
              ))}
            </ul>
            Sie können die Änderung dennoch bewusst übernehmen — sie bleibt als
            Konflikt markiert und wird protokolliert.
          </div>
        )}

        <div className="zeile" style={{ marginTop: "0.8rem", justifyContent: "flex-end" }}>
          <button className="sekundaer" onClick={onSchliessen} disabled={laedt}>
            Abbrechen
          </button>
          {konflikte && konflikte.length > 0 ? (
            <button className="gefahr" onClick={() => absenden(true)} disabled={laedt}>
              Trotz Regelverstoß übernehmen
            </button>
          ) : (
            <button onClick={() => absenden(false)} disabled={laedt}>
              {laedt ? "Prüfe Regeln…" : "Prüfen und übernehmen"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
