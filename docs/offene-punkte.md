# Offene Punkte

Stand **2026-08-26**. Alle Änderungen dieser Sitzung sind im Code, die
Verifikation ist aber **unvollständig**. Diese Liste zuerst abarbeiten.

## 1. Verifikation nachholen (blockiert die Abnahme)

### 1.1 Backend-Suite erneut laufen lassen

```bash
cd backend && ../.venv/bin/python -m pytest      # erwartet: 73 passed
```

Der letzte grüne Lauf (73 passed, 187 s) war **vor** dem Fix der
Planungsstand-Versionierung in [`backend/app/api/planung.py`](../backend/app/api/planung.py)
(`_naechste_version`, Tiebreak `id.desc()` in `_letzter_planungsstand`).
Dieser Fix ist noch durch keinen Test gelaufen.

### 1.2 Gegenprobe der Mindestpause

Der Lauf mit `mindestpause_min = 15` ist **bestanden**: 393 Übergänge,
**0 Null-Lücken** (vorher 467 von 786), `solver_status = gueltig`, 0 Konflikte,
244 s gegenüber ~190 s zuvor.

Offen ist die Gegenprobe mit `mindestpause_min = 0`, die das alte Verhalten
reproduzieren muss. Sie schlug zweimal scheinbar fehl — beide Male wegen
Messfehlern, nicht wegen des Features. Wer sie wiederholt, muss zwei Fallen
kennen:

- **`POST /berechnen` hat `neuberechnung: true` als Default.** Ohne
  `{"neuberechnung": false}` erbt der Lauf den vorigen Planungsstand, und W6
  (Gewicht 1000) hält dessen Zeiten fest — die Gegenprobe wiederholt dann nur
  die alte Lösung.
- **Danach prüfen, welchen Stand `GET /plan` liefert** (Feld
  `planungsstand.id`), sonst wertet man womöglich den Vorgänger aus.

Prüfkriterien: kein Übergang unter `mindestpause_min`, `solver_status` bleibt
`gueltig` (nicht `relaxiert`), Laufzeit im Rahmen von ~250 s.

## 2. Entscheidungen, die noch zu treffen sind

- **`puffer_min = 10` ist wirkungslos.** In allen gespeicherten Konfigurationen
  steht 10; die Belegungsprüfung läuft auf dem 15-Minuten-Raster (`RASTER_MIN`),
  ein Vorlauf von 10 fällt zwischen zwei Rasterpunkte und blockiert nichts.
  Entweder auf 15 setzen (wird wirksam, **verändert bestehende Pläne**) oder auf
  0 (ehrlich abgeschaltet). Nicht ungefragt geändert.
  Ein Raster-Validator auf `puffer_min` ist **keine** Option: er würde das Laden
  aller Bestandsjahrgänge mit HTTP 500 quittieren.
- **Mindestpause bei manueller Umbuchung.** Der Solver hält sie ein, ein
  Handeingriff in Schritt 4 kann sie unterlaufen, ohne dass ein Konflikt
  erscheint. Sauber wäre sie als Regel in
  [`backend/app/core/rules.py`](../backend/app/core/rules.py) — dann zeigen
  allerdings alle Bestandspläne schlagartig hunderte Konflikte. Bewusst
  ausgeklammert, weil das eine fachliche Entscheidung ist.
- **`ruecksteller` bleibt Pflichtspalte** beim Import, obwohl das Kennzeichen von
  keiner Regel ausgewertet wird (siehe [formats.md](formats.md)). Optional machen
  (fehlend ⇒ `nein`) würde handgebaute Test-CSVs erleichtern.
- **Jahrgang 2028** enthält Testdaten (262/87/34/15) und Planungsstände aus den
  Messläufen. Bei Bedarf über „Import zurücksetzen" leeren.

## 3. Behobener Bestandsfehler — Hintergrund

`version = (bestand_stand.version + 1) if bestand_stand else 1` vergab bei jeder
**Vollberechnung** erneut die Version 1, weil dort kein Bestand geerbt wird. Ein
Jahrgang konnte so mehrere Stände mit derselben Nummer haben, und
`_letzter_planungsstand` sortierte nur nach `version.desc()` ohne Zweitschlüssel
— welcher Stand „der aktuelle Plan" ist, hing damit von der Sortierreihenfolge
der Datenbank ab. Kontrolle, Export und Druck konnten einen veralteten Plan
zeigen. Behoben, siehe 1.1 zur ausstehenden Absicherung.
