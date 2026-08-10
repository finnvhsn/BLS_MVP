/** Typen entlang der API (siehe backend/app/api). */

export interface Benutzer {
  benutzername: string;
  rolle: string;
}

export interface Jahrgang {
  id: number;
  bezeichnung: string;
  aktiv: boolean;
}

export interface ImportFehler {
  zeile: number;
  spalte: string;
  meldung: string;
}

export interface ImportErgebnis {
  typ: string;
  anzahl_neu: number;
  anzahl_aktualisiert: number;
  fehler: ImportFehler[];
}

export interface BewerberZeile {
  id: number;
  import_key: string | null;
  name: string;
  vorname: string;
  tag: "Fr" | "Sa";
  geschlecht: string;
  studiengang: string;
  ruecksteller: boolean;
  rangfolge: number | null;
  rueckmeldestatus: string;
  zugelassen: boolean;
  aktiv: boolean;
  gruppe_id: number | null;
  planbar: boolean;
}

export interface PrueferZeile {
  id: number;
  import_key: string | null;
  name: string;
  vorname: string;
  geschlecht: string;
  status: "Senior" | "Junior";
  verfuegbar_fr: boolean;
  verfuegbar_sa: boolean;
  aktiv: boolean;
}

export interface RaumZeile {
  id: number;
  raumnummer: string;
  groesse: "klein" | "gross";
  verfuegbar_fr: boolean;
  verfuegbar_sa: boolean;
  sperrzeiten: { tag: string; von_min: number; bis_min: number }[];
  aktiv: boolean;
}

export interface Befangenheit {
  id: number;
  pruefer_id: number;
  bewerber_id: number;
}

export interface FormatKonfiguration {
  key: string;
  name: string;
  typ: "einzel" | "gruppe" | "thesen";
  dauer_min: number;
  anzahl_pruefer: number;
  nur_senior: boolean;
  max_junior: number;
  min_senior: number;
  raumgroesse: "klein" | "gross";
}

export interface Konfiguration {
  zeitmodell: {
    tag_start: string;
    tag_ende: string;
    wellen: number;
    puffer_min: number;
  };
  formate: FormatKonfiguration[];
  gruppengroesse: number;
  gewichte: Record<string, number>;
  solver: { timeout_sekunden: number; seed: number };
}

export interface Gruppe {
  id: number;
  tag: "Fr" | "Sa";
  nummer: number;
  bezeichnung: string;
  mitglieder: { id: number; name: string; vorname: string; geschlecht: string; studiengang: string }[];
}

export interface BerechnungsStatus {
  status: "keine" | "laeuft" | "fertig" | "unloesbar" | "fehler";
  planungsstand_id?: number;
  version?: number;
  solver_status?: string;
  laufzeit_sekunden?: number;
  konflikte?: number | Konflikt[];
  hinweise?: string[];
  meldung?: string;
}

export interface Konflikt {
  regel: string;
  meldung: string;
  zuweisungen: number[];
  bewerber_ids: number[];
  pruefer_ids: number[];
  raum_id: number | null;
}

export interface PersonRef {
  id: number;
  name: string;
  status?: string;
}

export interface ZuweisungAnsicht {
  id: number;
  tag: "Fr" | "Sa";
  format_key: string;
  format_name: string;
  format_typ: "einzel" | "gruppe" | "thesen";
  start: string;
  ende: string;
  start_min: number;
  ende_min: number;
  raum_id: number;
  raumnummer: string;
  gruppe: string | null;
  gruppe_id: number | null;
  manuell_geaendert: boolean;
  konflikt: boolean;
  bewerber: PersonRef[];
  pruefer: PersonRef[];
}

export interface PlanAnsicht {
  planungsstand: {
    id: number;
    version: number;
    typ: string;
    erstellt_am: string;
    kennzahlen: Record<string, unknown>;
  };
  zeitmodell: { start_min: number; ende_min: number };
  zuweisungen: ZuweisungAnsicht[];
  konflikte: Konflikt[];
  raeume: { id: number; raumnummer: string; groesse: string; aktiv: boolean }[];
}

export interface Planungsstand {
  id: number;
  version: number;
  typ: string;
  erstellt_am: string;
  seed: number | null;
  kennzahlen: Record<string, unknown>;
}

export interface ExportLauf {
  id: number;
  version: number;
  dateiname: string;
  erstellt_am: string;
  planungsstand_version: number | null;
}

export interface ProtokollEintrag {
  zeitpunkt: string;
  benutzer: string;
  aktion: string;
  details: Record<string, unknown>;
}

export interface UmbuchungsAntwort {
  uebernommen: boolean;
  konflikte: Konflikt[];
  planungsstand_id?: number;
  version?: number;
}
