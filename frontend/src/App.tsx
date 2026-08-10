import { useCallback, useEffect, useState } from "react";
import { ApiFehler, get, post } from "./api";
import { Anmeldung } from "./views/Anmeldung";
import { ExportSchritt } from "./views/ExportSchritt";
import { ImportSchritt } from "./views/ImportSchritt";
import { KontrolleSchritt } from "./views/KontrolleSchritt";
import { ParameterSchritt } from "./views/ParameterSchritt";
import { ZuweisungSchritt } from "./views/ZuweisungSchritt";
import { ProtokollPanel } from "./components/ProtokollPanel";
import type { Benutzer, Jahrgang } from "./types";

const SCHRITTE = ["Import", "Parameter", "Zuweisung", "Kontrolle", "Export"] as const;

export function App() {
  const [benutzer, setBenutzer] = useState<Benutzer | null>(null);
  const [geprueft, setGeprueft] = useState(false);
  const [jahrgaenge, setJahrgaenge] = useState<Jahrgang[]>([]);
  const [jahrgangId, setJahrgangId] = useState<number | null>(null);
  const [schritt, setSchritt] = useState(0);
  const [protokollOffen, setProtokollOffen] = useState(false);
  const [neuerName, setNeuerName] = useState("");

  const jahrgaengeLaden = useCallback(async () => {
    const liste = await get<Jahrgang[]>("/api/jahrgaenge");
    setJahrgaenge(liste);
    setJahrgangId((aktuell) =>
      aktuell !== null && liste.some((j) => j.id === aktuell)
        ? aktuell
        : liste[0]?.id ?? null
    );
  }, []);

  useEffect(() => {
    get<Benutzer>("/api/auth/ich")
      .then(setBenutzer)
      .catch(() => setBenutzer(null))
      .finally(() => setGeprueft(true));
  }, []);

  useEffect(() => {
    if (benutzer) jahrgaengeLaden().catch(() => undefined);
  }, [benutzer, jahrgaengeLaden]);

  if (!geprueft) return null;
  if (!benutzer) return <Anmeldung onAngemeldet={setBenutzer} />;

  const jahrgangAnlegen = async () => {
    if (!neuerName.trim()) return;
    try {
      const neu = await post<{ id: number }>("/api/jahrgaenge", {
        bezeichnung: neuerName.trim(),
        vorlage_jahrgang_id: jahrgangId, // Konfiguration als Vorlage (NF_008)
      });
      setNeuerName("");
      await jahrgaengeLaden();
      setJahrgangId(neu.id);
      setSchritt(0);
    } catch (e) {
      alert(e instanceof ApiFehler ? e.message : "Jahrgang konnte nicht angelegt werden.");
    }
  };

  const abmelden = async () => {
    await post("/api/auth/logout");
    setBenutzer(null);
  };

  return (
    <>
      <header className="kopfzeile">
        <h1>Bucerius Law School – Zuweisung mündliches Auswahlverfahren</h1>
        <label style={{ color: "#fff", gap: "0.5rem" }}>
          Jahrgang
          <select
            value={jahrgangId ?? ""}
            onChange={(e) => {
              setJahrgangId(Number(e.target.value));
              setSchritt(0);
            }}
          >
            {jahrgaenge.map((j) => (
              <option key={j.id} value={j.id}>
                {j.bezeichnung}
              </option>
            ))}
          </select>
        </label>
        <input
          placeholder="Neuer Jahrgang…"
          value={neuerName}
          onChange={(e) => setNeuerName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && jahrgangAnlegen()}
          style={{ width: "10rem" }}
        />
        <button className="klein sekundaer" onClick={jahrgangAnlegen}>
          Anlegen
        </button>
        <button className="klein sekundaer" onClick={() => setProtokollOffen(true)}>
          Protokoll
        </button>
        <span>{benutzer.benutzername}</span>
        <button className="klein sekundaer" onClick={abmelden}>
          Abmelden
        </button>
      </header>

      {jahrgangId === null ? (
        <div className="inhalt">
          <div className="karte">
            <h2>Willkommen</h2>
            <p>Legen Sie zunächst oben rechts einen Jahrgang an (z.&nbsp;B. „2026/2027“).</p>
          </div>
        </div>
      ) : (
        <>
          <nav className="schritte">
            {SCHRITTE.map((name, i) => (
              <button
                key={name}
                className={`schritt ${i === schritt ? "aktiv" : ""}`}
                onClick={() => setSchritt(i)}
              >
                {i + 1}. {name}
              </button>
            ))}
          </nav>
          <main className="inhalt">
            {schritt === 0 && <ImportSchritt jahrgangId={jahrgangId} />}
            {schritt === 1 && <ParameterSchritt jahrgangId={jahrgangId} />}
            {schritt === 2 && (
              <ZuweisungSchritt
                jahrgangId={jahrgangId}
                zurKontrolle={() => setSchritt(3)}
              />
            )}
            {schritt === 3 && <KontrolleSchritt jahrgangId={jahrgangId} />}
            {schritt === 4 && <ExportSchritt jahrgangId={jahrgangId} />}
          </main>
        </>
      )}

      {protokollOffen && jahrgangId !== null && (
        <ProtokollPanel jahrgangId={jahrgangId} onSchliessen={() => setProtokollOffen(false)} />
      )}
    </>
  );
}
