import { FormEvent, useState } from "react";
import { ApiFehler, post } from "../api";
import type { Benutzer } from "../types";

export function Anmeldung({ onAngemeldet }: { onAngemeldet: (b: Benutzer) => void }) {
  const [benutzername, setBenutzername] = useState("");
  const [passwort, setPasswort] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [laedt, setLaedt] = useState(false);

  const absenden = async (e: FormEvent) => {
    e.preventDefault();
    setLaedt(true);
    setFehler(null);
    try {
      const b = await post<Benutzer>("/api/auth/login", { benutzername, passwort });
      onAngemeldet(b);
    } catch (err) {
      setFehler(err instanceof ApiFehler ? err.message : "Anmeldung fehlgeschlagen.");
    } finally {
      setLaedt(false);
    }
  };

  return (
    <form className="anmeldung karte" onSubmit={absenden}>
      <h2>Anmeldung Verfahrensorganisation</h2>
      <label className="feld">
        <span>Benutzername</span>
        <input
          value={benutzername}
          onChange={(e) => setBenutzername(e.target.value)}
          autoFocus
          autoComplete="username"
        />
      </label>
      <label className="feld">
        <span>Passwort</span>
        <input
          type="password"
          value={passwort}
          onChange={(e) => setPasswort(e.target.value)}
          autoComplete="current-password"
        />
      </label>
      {fehler && <div className="fehler">{fehler}</div>}
      <button disabled={laedt}>{laedt ? "Anmeldung läuft…" : "Anmelden"}</button>
    </form>
  );
}
