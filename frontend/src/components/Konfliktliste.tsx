import type { Konflikt } from "../types";

/** Übersichtsliste aller Regelverletzungen mit Sprung zur Stelle (F_OM_015). */
export function Konfliktliste({
  konflikte,
  onSpringen,
}: {
  konflikte: Konflikt[];
  onSpringen: (k: Konflikt) => void;
}) {
  if (konflikte.length === 0) {
    return <div className="erfolg">Keine Regelverletzungen — der Plan ist konfliktfrei.</div>;
  }
  return (
    <>
      <div className="fehler">
        <b>{konflikte.length} Konflikt(e)</b> — harte Regeln werden niemals
        stillschweigend gebrochen; jede Verletzung ist hier benannt.
      </div>
      <ul className="konfliktliste">
        {konflikte.map((k, i) => (
          <li key={i} onClick={() => onSpringen(k)} title="Zur Stelle springen">
            <span className="regel">{k.regel}</span>
            {k.meldung}
          </li>
        ))}
      </ul>
    </>
  );
}
