/** Zentraler API-Zugriff mit deutschen Fehlermeldungen. */

export class ApiFehler extends Error {
  status: number;
  constructor(status: number, meldung: string) {
    super(meldung);
    this.status = status;
  }
}

export async function api<T>(pfad: string, optionen: RequestInit = {}): Promise<T> {
  const antwort = await fetch(pfad, {
    credentials: "same-origin",
    headers:
      optionen.body && !(optionen.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : undefined,
    ...optionen,
  });
  if (!antwort.ok) {
    let meldung = `Fehler ${antwort.status}`;
    try {
      const daten = await antwort.json();
      if (typeof daten?.detail === "string") meldung = daten.detail;
    } catch {
      /* keine JSON-Antwort */
    }
    throw new ApiFehler(antwort.status, meldung);
  }
  return antwort.json() as Promise<T>;
}

export const get = <T,>(pfad: string) => api<T>(pfad);
export const post = <T,>(pfad: string, daten?: unknown) =>
  api<T>(pfad, { method: "POST", body: daten === undefined ? undefined : JSON.stringify(daten) });
export const put = <T,>(pfad: string, daten: unknown) =>
  api<T>(pfad, { method: "PUT", body: JSON.stringify(daten) });
export const patch = <T,>(pfad: string, daten: unknown) =>
  api<T>(pfad, { method: "PATCH", body: JSON.stringify(daten) });
export const del = <T,>(pfad: string) => api<T>(pfad, { method: "DELETE" });

export async function hochladen<T>(pfad: string, datei: File): Promise<T> {
  const formular = new FormData();
  formular.append("datei", datei);
  return api<T>(pfad, { method: "POST", body: formular });
}
