# Projektstand & offene Punkte

Stand **2026-08-27**, Ende der zweiten Arbeitsrunde. Alle Änderungen sind im
Code, die Suite ist grün (`88 passed, 2 deselected`, 186 s), das Frontend
gebaut. Der Dev-Server ist heruntergefahren.

Offen ist genau ein fachlicher Punkt — die Mindestpause für **Prüfende** —, er
ist auf Wunsch zurückgestellt, damit das System vorführbar bleibt.

## 1. Was steht

### 1.1 Verifikation nachgeholt (war der Rückstand vom 26.08.)

- Backend-Suite auf dem unveränderten Stand: `73 passed` — der Fix der
  Planungsstand-Versionierung übersteht die Bestandssuite.
- **Gegenprobe der Mindestpause** aus den gespeicherten Ständen des Jahrgangs
  2028 ausgewertet statt neu gemessen; beide Läufe lagen bereits vor, beide mit
  `neuberechnung: false` (erben also keinen Bestand, W6 hält nichts fest):

  | Stand | `mindestpause_min` | Übergänge | kleinste Lücke | Null-Lücken | Status | Laufzeit |
  |---|---|---|---|---|---|---|
  | v1 | 15 | 393 | 15 min | 0 | gueltig, 0 Konflikte | 187 s |
  | v2 | 0 | 393 | 0 min | 297 | gueltig, 0 Konflikte | 196 s |

  Der Nachweis steht seither als Test im Code
  (`test_mindestpause_zwischen_allen_terminen` in
  [`backend/tests/test_m3_solver.py`](../backend/tests/test_m3_solver.py)) —
  deterministisch, in Sekunden, und über H10 im Regelkatalog gegen künftige
  Drift abgesichert. Er hängt damit nicht mehr an den Messdaten, die beim Leeren
  des Jahrgangs 2028 entfallen sind.

### 1.2 Versionierung der Planungsstände

Der Fix vom 26.08. saß nur in `planung.py`.
[`druck.py`](../backend/app/api/druck.py) und
[`export.py`](../backend/app/api/export.py) ermittelten „den letzten Stand"
jeweils selbst — ohne den `id.desc()`-Zweitschlüssel — und liefen weiter in
genau den Fehler, der Kontrolle, Export und Druck auseinanderlaufen ließ. Alle
drei Wege nutzen jetzt `letzter_planungsstand` / `stand_laden` aus
[`jahrgaenge.py`](../backend/app/api/jahrgaenge.py); Versionen vergibt allein
`naechste_version`, auch bei der Umbuchung. Nebenbefund mit behoben: `druck.py`
prüfte als einziger Endpunkt nicht, ob ein übergebener `stand_id` zum Jahrgang
gehört — ein fremder Plan war druckbar.

### 1.3 Mindestpause als harte Regel (H10)

Zwischen zwei Terminen derselben bewerbenden Person liegt mindestens die
konfigurierte Wegzeit, vor jedem Format derselbe Wert. Solver und Validator
lesen **dieselbe** Zahl (`zeitmodell.mindestpause_min`), sodass Constraint und
Prüfung nicht auseinanderlaufen können. Eine manuelle Umbuchung, die die Pause
unterschreitet, wird nur nach ausdrücklicher Bestätigung übernommen (F_OM_016).

Der Wert muss ein Vielfaches von 15 sein und wird sonst mit einer deutschen
Meldung abgelehnt — siehe die 10-Minuten-Frage unter Punkt 2.

### 1.4 Kleinere Korrekturen aus der Testphase

- **`puffer_min` ersatzlos entfallen.** Der Vorbereitungspuffer vor
  Gruppenformaten war nur oberhalb der Mindestpause überhaupt sichtbar. In
  gespeicherten Konfigurationen steht der Schlüssel weiter und wird beim Laden
  ignoriert — geprüft an Bestandsdaten.
- **W5 zieht jetzt die Mindestpause ab** statt des Puffers. Sie fällt zwischen
  jedem Terminpaar unvermeidbar an; als Kennzahl bleibt die Zeit übrig, die sich
  durch bessere Planung noch einsparen ließe. Die ausgewiesenen Wartezeiten
  fallen dadurch niedriger aus als in älteren Ständen.
- **`ruecksteller` ist optionale Importspalte** (fehlend ⇒ `nein`). Ein Wert
  außerhalb von `ja`/`nein` bleibt ein Fehler.
- **Jahrgänge lassen sich im Frontend löschen** (Kopfzeile, mit Rückfrage, die
  aufzählt was verschwindet). Der Endpunkt gab es schon, es fehlte der Weg.
- **Eingabefelder in Schritt 2 stehen bündig.** Ursache war `align-items: center`
  aus der `label`-Regel, das `.feld` nicht überschrieb — in einer
  Spalten-Flexbox ist das die waagerechte Achse, jedes Feld saß also mittig
  unter seinem unterschiedlich breiten Label.
- **Druckerzeugnisse haben einen Speichern-Link** (`?download=1` ⇒
  `Content-Disposition: attachment`) neben der Vorschau. Es waren immer schon
  echte PDFs; es fehlte nur der Direkt-Download.
- **Der Umbuchungsdialog** trägt nur noch den Formatnamen statt
  „Umbuchung: <Format>".

### 1.5 Testdaten

[`testdaten/demo-klein/`](../testdaten/demo-klein/) (48 Bewerbende, 29 Zusagen,
19 Prüfende, 10 Räume — für Vorführungen, mit Schrittbudget 15 s in unter einer
Minute gerechnet) und [`testdaten/realistisch/`](../testdaten/realistisch/)
(262/87/34/15, das reale Mengengerüst, ~3 min). Je vier CSV in der
Importreihenfolge.

## 2. Offen

### 2.1 Prüfende haben keine Mindestpause (zurückgestellt)

Der Solver erzwingt die Wegzeit nur für Bewerbende; Prüfende wechseln aber
genauso den Raum. Der Weg ist untersucht und steht fest:

- **Phase B** (`solver.py`) belegt je Zeitscheibe über
  `e.start <= tick < e.start + e.dauer`. Das Fenster muss um die Pause nach vorn
  wachsen — dieselbe Vorlauf-Semantik wie in Phase A, **ohne eine einzige neue
  Variable**, nur zusätzliche `AddAtMostOne` auf den bestehenden ~10.000
  Booleans.
- **Prüferkapazität in Phase A** zählt `occ(i, tick)` ohne Vorlauf. Bliebe sie
  so, gäbe Phase A Zeitpläne frei, die Phase B nicht mehr besetzen kann.
- **Vorab-Diagnose** rechnet den Senior-Bedarf mit `e.dauer` und müsste auf
  `e.dauer + pause` gehen, sonst meldet sie Machbarkeit, die es nicht gibt.
- **Neue Relaxierungsstufe:** Ist ein Tag mit Pause nicht besetzbar, fällt
  zuerst die Pause — vor der bestehenden Lockerung von H1/H3. Eine
  unterschrittene Wegzeit ist ein organisatorisches Ärgernis, eine
  Doppelbegegnung ein Verfahrensfehler.
- **Regel H10** gruppiert bisher nur nach `(bewerber_id, tag)` und bekäme
  `(pruefer_id, tag)` dazu.

Vor der Umsetzung gehört eine Vorher-/Nachher-Messung auf dem realen
Mengengerüst dazu. Referenzwert vorher: 414 s für beide Volllasttests.

### 2.2 Mindestpause von 10 Minuten

Mit dem 15-Minuten-Raster nicht darstellbar: Startzeiten und Formatdauern
(30/45/150) sind Vielfache von 15, erreichbare Lücken damit 0, 15, 30 … Eine 10
verböte exakt dasselbe wie eine 15 und erlaubte exakt dasselbe — der Plan wäre
identisch, die Oberfläche zeigte eine Zahl, die er nicht abbildet. Deshalb wird
sie abgelehnt statt still gerundet.

Echte 10 Minuten bräuchten ein **5-Minuten-Raster**; ein 10er scheidet aus, weil
die Gruppenarbeit 45 Minuten dauert. Erste Messung (kompakte Instanz, 120
Bewerbende, 20 s Schrittbudget, ohne Prüfenden-Pause):

| Konfiguration | Ergebnis | Laufzeit | Relaxierung |
|---|---|---|---|
| Raster 15 / Pause 15 (heute) | gültig, 0 Konflikte | 42,9 s | — |
| Raster 5 / Pause 10 | gültig, 0 Konflikte | 45,3 s | — |
| Raster 5 / Pause 15 | gültig, 0 Konflikte | 66,1 s | ja |

Das feinere Raster kostet **nicht** die erwartete Rechenzeit — das Schrittbudget
deckelt jede Phase ohnehin. Der Preis zeigt sich als Lockerung. Die Entscheidung
braucht noch eine Messung am realen Mengengerüst, sinnvollerweise zusammen mit
2.1.

### 2.3 Kleineres

- **Kein Unique-Constraint auf `(jahrgang_id, version)`.** Wäre die saubere
  Absicherung gegen Versionskollisionen, verlangt aber eine Datenmigration.
  Abgedeckt durch den `id.desc()`-Zweitschlüssel und eine einzige Vergabestelle.
- **Toter Zweig in `solver.berechnen`:** `elif relaxiert: status = "gueltig"`
  liefert dasselbe wie der Normalfall. „relaxiert" entsteht ausschließlich über
  Validator-Konflikte. Kosmetik, aber irreführend zu lesen.

## 3. Stand der Dev-Datenbank

`backend/data/bls.db` enthält nach der Testphase zwei Jahrgänge: **Testjahrgang**
(id 3, 262 Bewerbende / 87 Prüfende / 42 Räume, ein Planungsstand v1) und einen
leeren **2027** (id 4). Die früheren Jahrgänge 2027 und 2028 sind über den neuen
Löschen-Knopf entfernt worden. Eine Sicherung des Standes von vor dem Aufräumen
liegt im Sitzungs-Scratchpad (`$TMPDIR/bls_backup/`) und überlebt den nächsten
Neustart nicht.
