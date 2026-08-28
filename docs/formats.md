# CSV-Austauschformate (Version 1.0)

Dokumentierte, versionierte Austauschformate gemäß NF_006. Änderungen an
diesen Formaten erhöhen die Versionsnummer; ältere Versionen bleiben hier
dokumentiert.

**Allgemein:**

- Trennzeichen: Semikolon `;` (Komma wird beim Import automatisch erkannt)
- Zeichensatz: UTF-8 (mit oder ohne BOM); Windows-1252 wird beim Import
  automatisch erkannt (übliche Access-/Excel-Exporte)
- Erste Zeile: Kopfzeile mit den dokumentierten Spaltennamen
- Boolesche Felder: `ja` / `nein` (toleriert: `1`/`0`, `true`/`false`)
- Fehlerhafte Zeilen werden beim Import **gemeldet** (Zeilennummer, Spalte,
  deutsche Fehlermeldung) und nicht importiert; gültige Zeilen werden
  übernommen (F_OM_001)
- **Re-Import:** Datensätze werden über ihre ID-Spalte wiedererkannt und
  aktualisiert (Upsert). Beim Re-Import fehlende Datensätze werden niemals
  stillschweigend gelöscht.

---

## 1. `bewerbende.csv` (Access → Lösung, F_OM_001)

| Spalte | Pflicht | Werte | Bedeutung |
|---|---|---|---|
| `bewerber_id` | ja | Text, eindeutig | Schlüssel aus Access (Re-Import/Delta) |
| `nachname` | ja | Text | |
| `vorname` | nein | Text | |
| `tag` | **ja** | `Fr` / `Sa` | **Tageszuteilung aus Access (H7).** Fehlender oder ungültiger Wert ⇒ Validierungsfehler — der Tag wird niemals geraten. |
| `geschlecht` | ja | `w` / `m` / `d` | |
| `studiengang` | ja | Text | z. B. „Rechtswissenschaft“ |
| `ruecksteller` | nein | `ja` / `nein` | Rücksteller-Kennzeichen; leer oder fehlende Spalte ⇒ `nein`. Wird importiert und mitgeführt, aber von **keiner** Regel ausgewertet — die Planbarkeit hängt allein an `zugelassen`, `rueckmeldestatus` und dem Aktiv-Status. Der Access-Export liefert die Spalte weiterhin mit; optional ist sie, damit sich Testdateien von Hand bauen lassen. Ein Wert außerhalb von `ja`/`nein` bleibt ein Fehler. |
| `rangfolge` | nein | Ganzzahl | Rangliste (verbleibt fachlich in Access) |
| `rueckmeldestatus` | nein | `Zusage` / `Absage` / `Alternativtermin` / `Offen` | leer ⇒ `Offen` |
| `zugelassen` | nein | `ja` / `nein` | leer ⇒ `ja`; muss eindeutig hervorgehen, wer zum mündlichen Verfahren zugelassen ist |

**Geplant** (d. h. vom Algorithmus eingeplant) werden ausschließlich
Bewerbende mit `zugelassen = ja` **und** `rueckmeldestatus = Zusage`, die
nicht abgesagt haben (aktiv).

## 2. `pruefende.csv` (Salesforce/manuell → Lösung, F_OM_002)

| Spalte | Pflicht | Werte | Bedeutung |
|---|---|---|---|
| `pruefer_id` | ja | Text, eindeutig | Schlüssel aus Salesforce |
| `nachname` | ja | Text | |
| `vorname` | nein | Text | |
| `geschlecht` | ja | `w` / `m` / `d` | |
| `status` | ja | `Senior` / `Junior` | Senior = Vollmitglied |
| `verfuegbar_fr` | nein | `ja` / `nein` | leer ⇒ `ja` (Prüfende stehen i. d. R. an beiden Tagen zur Verfügung) |
| `verfuegbar_sa` | nein | `ja` / `nein` | leer ⇒ `ja` |

Ein **Aktiv-Kennzeichen gibt es bewusst nicht im Importformat**: kurzfristige
Absagen prüfender Personen werden in der Oberfläche gepflegt (Schritt 1,
Datenbestand → Prüfende), nicht über einen erneuten Import. So bleibt der Import
die Abbildung des Quellsystems, während tagesaktuelle Änderungen daneben stehen.

## 3. `raeume.csv` (Excel/manuell → Lösung, F_OM_003)

| Spalte | Pflicht | Werte | Bedeutung |
|---|---|---|---|
| `raumnummer` | ja | Text, eindeutig | |
| `groesse` | ja | `klein` / `gross` | klein = Einzelgespräche, gross = Gruppenarbeit/Thesenvortrag (H6) |
| `verfuegbar_fr` | nein | `ja` / `nein` | leer ⇒ `ja` |
| `verfuegbar_sa` | nein | `ja` / `nein` | leer ⇒ `ja` |
| `sperrzeiten` | nein | z. B. `Fr 12:00-13:00\|Sa 10:00-11:30` | Zeitfenster, in denen der Raum nicht verfügbar ist; mehrere mit `\|` getrennt |

## 4. `befangenheiten.csv` (manuell → Lösung, F_OM_009)

| Spalte | Pflicht | Werte | Bedeutung |
|---|---|---|---|
| `pruefer_id` | ja | Schlüssel aus `pruefende.csv` | |
| `bewerber_id` | ja | Schlüssel aus `bewerbende.csv` | |

Datensparsamkeit (NF_001): Es wird **kein Grund** gespeichert — reine
Ausschlussbeziehung (H2). Voraussetzung: Prüfende und Bewerbende sind zuvor
importiert (sonst Validierungsfehler „unbekannte ID“).

## 5. `zuteilung_export.csv` (Lösung → Access, F_OM_013)

Wird mit Meilenstein M6 finalisiert (eine Zeile je Person × Prüfungsereignis):

| Spalte | Bedeutung |
|---|---|
| `export_version` | fortlaufende Versionsnummer des Exports |
| `jahrgang` | Bezeichnung des Jahrgangs |
| `tag` | `Fr` / `Sa` |
| `zeit_von` / `zeit_bis` | Uhrzeit `HH:MM` |
| `format` | Anzeigename des Prüfungsformats |
| `raum` | Raumnummer |
| `gruppe` | Gruppenbezeichnung (leer bei Einzelgesprächen) |
| `rolle` | `Bewerber` / `Pruefer` |
| `person_id` | `bewerber_id` bzw. `pruefer_id` (Import-Schlüssel) |
| `nachname`, `vorname` | |
| `partner_ids` | Import-Schlüssel der Gegenseite (Prüfende↔Bewerbende-Zuordnung) |
