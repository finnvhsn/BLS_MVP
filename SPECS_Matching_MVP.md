# SPECS – MVP „Zuweisungsalgorithmus mündliches Auswahlverfahren" (Bucerius Law School)

> **Zweck dieses Dokuments:** Referenzspezifikation für die Entwicklung eines MVP via Claude Code / Claude Agents.
> Grundlage: Fachspezifikation (Word) + Anforderungsspezifikation Anlage 1 (Excel), Stand 08/2026.
> **Scope-Regel:** Es werden ausschließlich Anforderungen mit Umsetzungskennzeichnung **27** implementiert.
> Anforderungen mit Kennzeichnung **28** werden NICHT gebaut – sie dienen nur als Orientierung für Erweiterbarkeit (siehe Kap. 10).

---

## 1. Ziel des MVP

Die BLS vergibt jährlich Studienplätze über ein mehrstufiges Auswahlverfahren. Kern ist ein mündliches Auswahlverfahren an zwei Prüfungstagen (Freitag/Samstag) am Campus. Die heutige Access-basierte Zuteilung von Prüfenden, Bewerbenden und Räumen skaliert nicht mehr (ab 2027 zusätzlicher Studiengang → ~260 statt 230 Bewerbende).

**Der MVP muss können:**
Anhand importierter Prüfenden-, Bewerbenden- und Raumdaten unter Einhaltung aller fachlichen Regeln (Kap. 4) eine **korrekte, vollständige, konfliktfreie Raum-/Gruppen-/Prüfendenzuteilung** je Prüfungstag berechnen und **tabellarisch darstellen und exportieren**.

**Prozessfluss (End-to-End, verpflichtend):**

```
Import → Parametrierung → Zuweisung → Kontrolle (inkl. manuelle Nachbearbeitung) → Export
```

Der MVP endet mit dem Export der finalen Zuteilung. Die Lösung wird **in der Vorbereitung** der Prüfungstage genutzt, nicht während der Prüfungstage selbst.

---

## 2. Scope

### 2.1 In Scope (Umsetzung 27)

| Bereich | Inhalt |
|---|---|
| Datenimport | Bewerbende (CSV aus Access), Prüfende (CSV aus Salesforce + manuelle Nachpflege), Räume (CSV/Excel oder manuelle Pflege), Prüfungsformate als Konfiguration |
| Zuweisungskern | Algorithmus mit allen harten und weichen Regeln, Gruppeneinteilung, Neuberechnung bei Änderungen (minimalinvasiv) |
| UI | Planungsansicht (Raster Raum × Zeitfenster je Tag), Sichtenwechsel (Bewerbende/Prüfende/Räume), Konfliktliste mit Navigation, manuelle Nachbearbeitung mit Live-Regelvalidierung, Parametrierung ohne Programmierkenntnisse, deutschsprachig |
| Export | CSV-Export der finalen Zuteilung (Access-kompatibel), versioniert, wiederholbar |
| Druckdaten | Laufzettel je Bewerber:in/Prüfer:in (PDF, konfigurierbar) und Raumschilder (PDF) — Soll-Anforderungen (B) |
| Nicht-funktional | DSGVO/Datensparsamkeit, Rollen/Auth, Performance ≤ 15 min, Jahrgangsfähigkeit, Formatvalidierung, Protokollierung/Nachvollziehbarkeit |

### 2.2 Nicht in Scope (verbleibt in Bestandssystemen)

- Ranglistenberechnung und Tageszuteilung (Fr/Sa) → bleibt in **Access** (Tageszuteilung kommt als Importfeld mit!)
- Kommunikation mit Bewerbenden/Prüfenden → Access/E-Mail
- TYPO3-Bewerber- und Prüferplattform, Ergebniseintragung
- Schriftliches Auswahlverfahren (externer Dienstleister ITB)
- Alle Anforderungen mit Kennzeichnung **28** (F_BW_001–003, F_SV_001–003, F_OM_004, F_DM_003–005, F_AK_001–006, NF_007)
- Campus-Infrastruktur (Laptops, WLAN)

---

## 3. Mengengerüst (Referenz Verfahren 2026/2027)

| Größe | Wert |
|---|---|
| Bewerbende (eingeladen) | ~262 (131 Fr / 131 Sa) → ca. 130 Zusagen, ~30 Rücksteller, Rest Absagen |
| Studienplätze | ~130 (vorher 116) |
| Auswahlkommission | ~87 Prüfende: 58 Senior (Vollmitglieder), 29 Junior |
| Touchpoints je Bewerber:in | ideal 8 unterschiedliche Prüfende (2 Einzelgespräche, 1 Gruppenarbeit, 1 Thesenvortrag) |
| Bewerbende je Prüfer:in | ca. 12, möglichst gleichmäßig verteilt |
| Prüfungstage | 2 (Freitag + Samstag); Prüfende stehen i. d. R. an beiden Tagen zur Verfügung |
| Tagesdauer | **10:00 – 17:15 Uhr** an beiden Prüfungstagen (Default-Zeitmodell; als Konfiguration hinterlegt und je Jahrgang änderbar) |

**Wichtig:** Die Lösung ist **mengenunabhängig** auszulegen – steigende Teilnehmerzahlen dürfen keine Anpassung von Algorithmus oder Schnittstellen erfordern (NF_003, Abschn. 3.2 Fachspez.).

### Prüfungsformate (Referenzwerte, konfigurierbar!)

| Format | Dauer | Besonderheit |
|---|---|---|
| Einzelgespräch | derzeit 2 × ca. 30 min (Zusammenlegung zu 1 × 30–45 min wird geprüft, nicht entschieden → **konfigurierbar halten**) | nur Senior-Prüfende |
| Gruppenvortrag/Gruppenarbeit | 45 min | informelle Vorbereitung in vorangehender Kaffeepause |
| Thesenvortrag | fix 2,5 h Block | alle 4 Bewerbenden der Gruppe für den gesamten Block geblockt |

### Tages-Zeitmodell (Default-Konfiguration)

- **Prüfungszeitraum je Tag: 10:00 – 17:15 Uhr** (7 h 15 min = 435 min nutzbare Planungszeit)
- Das Slot-Raster wird aus den konfigurierten Formatdauern innerhalb dieses Zeitfensters erzeugt; alle Zuweisungen müssen vollständig innerhalb von 10:00–17:15 liegen (harte Grenze, siehe H8)
- Etappen/Wellen, Pausen- und Pufferzeiten sind innerhalb dieses Rahmens konfigurierbar (F_OM_005/F_OM_010); für Testdaten plausible Annahme: Kaffeepause vor dem Gruppenvortrag als Vorbereitungszeit
- Start/Ende sind als Jahrgangs-Konfiguration hinterlegt, nicht hartkodiert

---

## 4. Fachliche Regeln des Zuweisungsalgorithmus

### 4.1 Harte Regeln (MÜSSEN eingehalten werden; Verletzung = Konflikt)

| ID | Regel |
|---|---|
| H1 | **Keine Doppelbegegnung:** Eine prüfende Person prüft dieselbe bewerbende Person höchstens einmal (über alle Formate und beide Tage). |
| H2 | **Befangenheit:** Als befangen hinterlegte Paarungen (Prüfer:in ↔ Bewerber:in) werden niemals zugewiesen. Datensparsam abbilden: reine Ausschlussbeziehung ohne Grundangabe. |
| H3 | **Prüfergruppen-Zusammensetzung:** Bei Gruppenprüfungen max. 1 Junior und min. 2 Senior je Prüfergruppe. |
| H4 | **Einzelgespräche nur Senior:** Junior-Prüfende werden keinen Einzelgesprächen zugewiesen. |
| H5 | **Keine Doppelbelegung:** Jede Person (Prüfende + Bewerbende) und jeder Raum ist je Zeitfenster nur genau einmal verplant (überschneidungsfreier Tagesplan). |
| H6 | **Raumeignung & -verfügbarkeit:** Zuweisung nur in verfügbare Räume (je Tag + Zeitfenster); kleine Räume für Einzelgespräche, größere Räume für Gruppenarbeiten und Thesenvorträge. Je Raum + Zeitslot genau eine Prüfung. |
| H7 | **Vollständigkeit & Tagesbindung:** Jede:r zugelassene Bewerbende wird ausschließlich an dem im Datensatz zugeteilten Tag (Feld `tag` = Fr/Sa, Pflichtfeld aus dem Access-Import) geprüft und durchläuft dort alle konfigurierten Prüfungsformate. Der Algorithmus verteilt Bewerbende niemals selbst auf Tage — die Tageszuteilung erfolgt vorgelagert in Access und ist Eingabedatum. |
| H8 | **Formatdauern & Zeitmodell:** Zuweisung hält die konfigurierten Formatdauern und Zeitfenster/Etappen ein; alle Slots liegen vollständig innerhalb der Tagesdauer (Default **10:00–17:15**); Thesenvortrag blockt alle Gruppenmitglieder für den gesamten 2,5-h-Block. |
| H9 | Prüfergruppen können sich im Laufe des Tages ändern; die Regeln H1–H4 gelten für **jede** Konstellation. |

### 4.2 Weiche Regeln / Optimierungsziele (SOLLEN maximiert werden; Abweichungen ausweisen)

| ID | Ziel |
|---|---|
| W1 | Jede:r Bewerbende wird idealerweise von **8 unterschiedlichen** Prüfenden gesehen; Abweichungen ausweisen. |
| W2 | Jede prüfende Person sieht **ca. 12** Bewerbende; Auslastung möglichst gleichmäßig verteilen. |
| W3 | **Diversität Bewerbendengruppen:** zufallsbasierte Einteilung, möglichst gemischt nach Geschlecht und Studiengang; Gruppengrößen konfigurierbar; manuelle Nachjustierung möglich. |
| W4 | **Diversität Prüfendengruppen:** möglichst gemischte Zusammensetzung (Geschlecht). |
| W5 | **Wartezeiten** der Bewerbenden zwischen Prüfungsphasen minimieren und im Ergebnis ausweisen. |
| W6 | **Stabilität bei Neuberechnung:** bestehende, weiterhin gültige Zuweisungen möglichst beibehalten (minimalinvasive Umplanung). |

### 4.3 Konfliktverhalten

- Kann eine harte Regel nicht erfüllt werden → **kein stillschweigender Regelbruch**, sondern Konflikt mit Begründung (verletzte Regel benennen) ausgeben (F_OM_008 AK3, NF_010).
- Konflikte erscheinen in einer Übersichtsliste und sind je Zuweisung markiert; Sprung zur betroffenen Stelle in der Planungsansicht (F_OM_015).

---

## 5. Änderungsszenarien (Neuberechnung, F_OM_011)

Für alle Szenarien gilt: Auswirkung anzeigen → Neuberechnung mit maximalem Erhalt bestehender Zuweisungen → vollständige Revalidierung gegen alle Regeln.

| # | Szenario | Anforderung |
|---|---|---|
| 1 | Kurzfristige Absage Prüfer:in | Betroffene Kontakte auf andere Prüfende umverteilen; H1–H4 einhalten |
| 2 | Kurzfristige Absage Bewerber:in | Slots entfallen; Gruppenarbeiten mit reduzierter Größe durchführbar halten oder Gruppen neu mischen |
| 3 | Nachrücken von Reserveliste | Person vollständig einplanen (alle Formate, 8 Kontakte), gleiche Regeln |
| 4 | Nachträgliche Befangenheit | Betroffene Zuweisung auflösen und systemgestützt ersetzen |
| 5 | Raumausfall / Ersatzraum | Betroffene Slots auf verfügbare, formatgeeignete Räume umverteilen |

Neuberechnung muss **jederzeit** möglich sein und den aktuellen Datenstand berücksichtigen; wiederholter Datenimport bis kurz vor dem Verfahren (F_OM_001 AK3). Neuberechnungen mit minimalen Änderungen deutlich schneller als Vollberechnung (NF_003).

---

## 6. Datenmodell & Schnittstellen

### 6.1 Datenobjekte

**Bewerbende** (Quelle: Access, CSV-Import)
- Pflichtfelder: `name`, `tag` (Fr/Sa — **Tageskennzeichnung**: jede:r Bewerbende wird nur an genau diesem einen Tag geprüft, vgl. H7), `geschlecht`, `studiengang`, `ruecksteller_kennzeichen`
- Import ohne gültigen `tag`-Wert wird als Validierungsfehler gemeldet (kein stilles Raten des Tages)
- Weitere: Rangfolge, Rückmeldestatus (Zusage/Absage/Alternativtermin)
- Validierung der Pflichtfelder beim Import; fehlerhafte Datensätze werden gemeldet (F_OM_001)
- Aus dem Import muss eindeutig hervorgehen, wer zum mündlichen Verfahren **zugelassen** ist

**Prüfende** (Quelle: Salesforce, CSV-Import + manuelle Erfassung)
- Felder: `name`, `geschlecht`, `status` (Senior/Junior), Verfügbarkeit je Prüfungstag
- Manuelle Nachpflege von Zu-/Absagen (finale Liste erst 2–3 Tage vor dem Verfahren)
- Prüfende stehen i. d. R. an beiden Tagen zur Verfügung; Einplanung nur eines Tages nicht vorgesehen

**Räume** (Quelle: Excel/CSV oder manuelle Pflege im System)
- Felder: `raumnummer`, `kapazitaet/groesse` (klein = Einzelgespräch, groß = Gruppenformate), Verfügbarkeit je Tag (Fr/Sa) und Zeitfenster

**Prüfungsformate & Zeitmodell** (Konfiguration in der Lösung)
- Formate mit Dauer konfigurierbar; Kohorte in Etappen/Wellen über den Tag verteilbar

**Befangenheiten**
- Paarung `pruefer_id ↔ bewerber_id`, keine Gründe speichern (Datensparsamkeit)

### 6.2 Import (eingehend)

| Fluss | Format | Hinweise |
|---|---|---|
| Access → Lösung | CSV | Bewerbendenliste mit Rangfolge, Tageszuteilung, Rückmeldestatus; wiederholter Import (Delta oder Vollabzug) |
| Salesforce/manuell → Lösung | CSV | Prüfendendaten inkl. kurzfristiger Nachpflege |
| Excel/manuell → Lösung | CSV/Excel | Raumdaten und Verfügbarkeiten |

Alle Importe: **Formatvalidierung mit verständlichen deutschen Fehlermeldungen**, mengenunabhängig, dokumentierte und versionierte Austauschformate (NF_006).

### 6.3 Export (ausgehend)

| Fluss | Inhalt |
|---|---|
| Lösung → Access | Finale Zuteilung als CSV: je Zuweisung Person, Tag, Zeitfenster, Raum, Format, Gruppe + Zuordnung Prüfende↔Bewerbende (Grundlage Abschlusskonferenz). Wiederholte Exporte nach Neuberechnung möglich und **versioniert** (F_OM_013) |
| Lösung → Druckaufbereitung | Laufzettel je Bewerber:in/Prüfer:in (PDF, Inhalte konfigurierbar, nach Neuberechnung aktualisierbar) und Raumschilder (PDF) (F_DM_001/002, B) |

*Hinweis: Der in der Fachspez. genannte TYPO3-Export (Zuteilungsdaten je Prüfer:in, zeitgesteuert 2 Tage vor Prüfungstag) kann im MVP über den versionierten CSV-Export abgedeckt werden — kein eigener API-Push nötig.*

---

## 7. Funktionale Anforderungen (Umsetzung 27) — Checkliste

| Nr. | Anforderung | Scope |
|---|---|---|
| F_OM_001 | Import Bewerbendenliste mit Tageszuteilung (CSV, Pflichtfeldvalidierung, Re-Import) | **A** |
| F_OM_002 | Import Prüfendendaten (CSV Salesforce + manuell, Senior/Junior, Geschlecht, Nachpflege) | **A** |
| F_OM_003 | Raumdatenverwaltung (Import/manuelle Pflege, Größe, Verfügbarkeit je Tag/Zeitfenster) | **A** |
| F_OM_005 | Prüfungsformate mit Dauer konfigurierbar; Etappen/Wellen; überschneidungsfreier Plan; 1 Prüfung je Raum/Slot; Wartezeiten minimieren + ausweisen | **A** |
| F_OM_006 | Gruppeneinteilung Bewerbende (zufallsbasiert, divers nach Studiengang/Geschlecht, Größe konfigurierbar, manuell nachjustierbar) | **A** |
| F_OM_007 | Automatische Zuweisung Prüfende–Bewerbende–Räume (H1, W1, W2, Raumvergabe) | **A** |
| F_OM_008 | Regeln Prüfendengruppen (H3, H4; Regelkonflikte auflösen oder melden) | **A** |
| F_OM_009 | Befangenheitsregeln (Hinterlegung + Ausschluss, datensparsam) | **A** |
| F_OM_010 | Parametrierung aller Variablen über UI ohne Programmierkenntnisse; Konfigurationen je Jahrgang speicher- und wiederverwendbar | **A** |
| F_OM_011 | Neuberechnung bei kurzfristigen Änderungen, minimalinvasiv | **A** |
| F_OM_012 | Manuelle Nachbearbeitung mit sofortiger Regelvalidierung; Änderungen protokolliert | **A** |
| F_OM_013 | Export der Zuteilung an Access (CSV, vollständig, versioniert) | **A** |
| F_OM_014 | Visualisierung: Planungsansicht je Tag (Raster Raum × Zeitfenster), Sichtenwechsel Bewerbende/Prüfende/Räume | **A** |
| F_OM_015 | Konfliktanzeige: Markierung je Zuweisung, Übersichtsliste, Navigation zur Stelle, verletzte Regel benannt | **A** |
| F_OM_016 | Interaktive Anpassung (z. B. Drag & Drop) mit Live-Validierung; nicht regelkonforme Änderung nur nach bewusster Bestätigung | B |
| F_DM_001 | Laufzettel Bewerbende + Prüfende (PDF, konfigurierbar, nach Neuberechnung aktualisierbar) | B |
| F_DM_002 | Raumschilder (PDF) | B |

**MVP-Priorisierung:** A-Anforderungen zuerst und vollständig; B-Anforderungen (F_OM_016, F_DM_001/002) danach. Für F_OM_016 genügt im MVP ein einfacher Umbuchungsdialog (Auswahl statt Drag & Drop), sofern Live-Validierung + Bestätigungslogik erfüllt sind.

---

## 8. Nicht-funktionale Anforderungen (Umsetzung 27)

| Nr. | Anforderung | MVP-Umsetzung |
|---|---|---|
| NF_001 | DSGVO: Datensparsamkeit, Lösch-/Aufbewahrungskonzept je Jahrgang, VVT/AVV-Fähigkeit | Nur verfahrensnotwendige Felder speichern; Jahrgangs-Löschfunktion; Befangenheit ohne Gründe |
| NF_002 | Rollen & Berechtigungen (mind. Verfahrensorganisation, Prüfende); Auth mind. individuelles Passwort; Zugriffe auf personenbezogene Daten protokolliert | MVP: eine aktive Rolle „Verfahrensorganisation" mit Login; Rollenmodell im Code angelegt (Prüfende nutzen die Lösung 2027 nicht direkt) |
| NF_003 | Performance: Vollberechnung ≤ 15 min beim realen Mengengerüst; Neuberechnung deutlich schneller; skaliert bei moderatem Wachstum | Solver-Timeout konfigurierbar, Zielwert ≤ 15 min, Warmstart für Neuberechnung |
| NF_004 | Verfügbarkeit in Vorbereitungswoche; Backup/Wiederanlauf inkl. Export der letzten gültigen Zuteilung | Automatische Sicherung der DB-Datei + jederzeit möglicher Export des letzten gültigen Stands |
| NF_005 | Betriebsmodell darlegbar (Cloud EU / On-Prem) | Single-Container-Deployment → beides möglich |
| NF_006 | Dokumentierte, versionierte CSV-Formate; Formatvalidierung mit verständlichen Fehlermeldungen | Formatdoku als Teil des Repos (`/docs/formats.md`), Schema-Validierung beim Import |
| NF_008 | Jahrgangsfähigkeit: logisch getrennte Jahrgänge, archivier-/löschbar, Konfiguration als Vorlage übernehmbar | `jahrgang`-Dimension im Datenmodell, Konfig-Kopierfunktion |
| NF_009 | Bedienbarkeit ohne IT-Spezialwissen, deutschsprachige UI, geführter Prozess Import → Parametrierung → Zuweisung → Kontrolle → Export | UI als geführter 5-Schritte-Workflow, alle Texte Deutsch |
| NF_010 | Nachvollziehbarkeit: Regelverletzungen mit Begründung; Berechnungsläufe + manuelle Eingriffe protokolliert; Versionierung der Planungsstände; Regel-/Parameterdoku als Lieferbestandteil | Lauf-Historie mit Snapshots, Änderungsprotokoll, `/docs/regeln.md` |

---

## 9. IT-Architektur (Vorschlag: simpel, effizient, wartungsarm)

**Leitidee: Ein Monolith, eine Datei-Datenbank, ein Container. Keine Microservices, keine Message Queues, kein Kubernetes.**

```
┌─────────────────────────────────────────────────┐
│  Docker-Container (einzeln deploybar,           │
│  Cloud-EU oder On-Premises)                     │
│                                                 │
│  ┌───────────────────────────────────────────┐  │
│  │ FastAPI (Python 3.12)                     │  │
│  │  ├─ REST-API (JSON)                       │  │
│  │  ├─ Auth (Session/Passwort, bcrypt)       │  │
│  │  ├─ Import-/Export-Modul (CSV, pandas)    │  │
│  │  ├─ Solver-Modul (Google OR-Tools CP-SAT) │  │
│  │  ├─ Regel-Validator (pure functions,      │  │
│  │  │   gleiche Regeln wie Solver!)          │  │
│  │  └─ PDF-Generator (WeasyPrint)            │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │ SQLite (eine Datei, WAL-Modus)            │  │
│  │  + tägliches Datei-Backup                 │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │ Frontend: React + Vite + TypeScript       │  │
│  │  (statischer Build, von FastAPI serviert) │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### Begründung der Entscheidungen

| Entscheidung | Warum |
|---|---|
| **Python + FastAPI** | Bestes Ökosystem für Optimierung + Datenverarbeitung; minimaler Boilerplate; automatische API-Doku (OpenAPI) → erfüllt NF_007-Orientierung „API-Fähigkeit angelegt" ohne Mehraufwand |
| **Google OR-Tools CP-SAT** (Open Source, Apache 2.0) | Constraint-Programming ist die natürliche Abbildung der fachlichen Regeln: harte Regeln = Constraints, weiche Regeln = gewichtete Zielfunktion. Bewährter, aktiv gepflegter Solver; Mengengerüst (~130 Bewerbende/Tag, ~87 Prüfende, ~30 Räume) ist für CP-SAT klein → Lösungen weit unter 15 min realistisch |
| **SQLite** | Ein-Nutzergruppen-Werkzeug mit saisonaler Nutzung braucht keinen DB-Server. Eine Datei = triviales Backup (NF_004), triviale Jahrgangsarchivierung (NF_008), null Administrationsaufwand |
| **Ein Container** | On-Prem wie Cloud-EU identisch deploybar (NF_005); ein `docker compose up` ist der gesamte Betrieb |
| **React + Vite + TS** | Interaktive Planungsansicht (Raster, Konfliktnavigation, spätere D&D-Erweiterung F_OM_016) sauber umsetzbar; statischer Build → kein eigener Frontend-Server |
| **WeasyPrint** (Open Source) | HTML/CSS → PDF für Laufzettel/Raumschilder; Templates = einfache HTML-Dateien → „Inhalte konfigurierbar" trivial erfüllbar |
| **Gemeinsamer Regel-Validator** | Die Regeln H1–H9 existieren **genau einmal** als pure functions und werden sowohl vom Solver (Constraint-Aufbau) als auch von der manuellen Nachbearbeitung (Live-Validierung F_OM_012/015/016) genutzt → keine Regel-Drift |

### Solver-Design (Kern-Hinweise für die Implementierung)

1. **Zwei Stufen:**
   Stufe 1 – Gruppeneinteilung der Bewerbenden (zufallsbasiert mit Diversitäts-Score, F_OM_006; eigenständig wiederholbar/nachjustierbar).
   Stufe 2 – CP-SAT-Modell: Zuweisung (Bewerbendengruppe/Person × Format × Zeitslot × Raum × Prüfendengruppe).
2. **Harte Regeln als Constraints** (H1–H9), **weiche Regeln als gewichtete Terme der Zielfunktion** (W1–W5). Gewichte als benannte Konstanten konfigurierbar.
3. **Neuberechnung (W6):** bestehende Zuweisungen als Soft-Constraint mit hohem Gewicht („Abweichung vom Bestand bestrafen") → minimalinvasive Umplanung; kein separater Algorithmus nötig.
4. **Infeasibility-Handling:** Wenn keine gültige Lösung existiert, Constraints schrittweise relaxieren und die verletzten Regeln als benannte Konflikte ausgeben (NF_010) — niemals stillschweigend liefern.
5. **Determinismus:** `random_seed` als Parameter speichern, damit Läufe reproduzierbar/vergleichbar sind (Protokollierung NF_010).
6. **Solver-Timeout** konfigurierbar (Default z. B. 10 min), bestes gefundenes Ergebnis + Qualitätskennzahlen (erfüllte/verfehlte weiche Ziele, Wartezeiten) ausgeben.

### Projektstruktur (Vorschlag)

```
/backend
  /app
    main.py               # FastAPI-Entry
    /api                  # Router: import, config, solve, plan, export, print
    /core
      rules.py            # H1–H9 + W1–W6 als pure functions (Single Source of Truth)
      solver.py           # CP-SAT-Modellaufbau, Warmstart, Relaxierung
      grouping.py         # Stufe 1: Gruppeneinteilung
      validator.py        # Validierung von Plänen & manuellen Änderungen
    /io
      importer.py         # CSV-Import + Schema-Validierung (deutsche Fehlermeldungen)
      exporter.py         # versionierter CSV-Export
      pdf.py              # Laufzettel/Raumschilder (WeasyPrint, HTML-Templates)
    /db
      models.py           # SQLModel/SQLAlchemy: Jahrgang, Bewerber, Pruefer, Raum,
                          # Format, Befangenheit, Konfiguration, Planungsstand, Protokoll
  /tests                  # pytest: Regel-Tests, Solver-Tests mit realem Mengengerüst
/frontend
  /src
    /views                # 5-Schritte-Workflow: Import | Parameter | Zuweisung | Kontrolle | Export
    /components           # Planungsraster, Konfliktliste, Umbuchungsdialog
/docs
  formats.md              # dokumentierte, versionierte CSV-Austauschformate (NF_006)
  regeln.md               # Regel- und Parameterdokumentation (NF_010, Lieferbestandteil)
docker-compose.yml
```

---

## 10. Langfristige Ziele (28) — NICHT bauen, nur berücksichtigen

Die folgenden Punkte werden **nicht implementiert**, dürfen aber durch Architekturentscheidungen nicht verbaut werden („ohne grundlegendes Re-Design", NF_007):

- Ablösung der CSV-Übergaben durch **API-Integrationen** und CRM-Anbindung → deshalb: klare REST-API, Import-/Export-Logik von Transportweg entkoppelt (Datei heute, API morgen)
- Ablösung weiterer Access-Bestandteile (Rangliste, Zulassung, Reserveliste, Kommunikation) → deshalb: Datenmodell nicht künstlich auf Zuweisung verengen (z. B. Rangfolge/Rückmeldestatus mitführen)
- Raumbuchungs-/CMS-Schnittstelle (F_OM_004), Ergebniserfassung, Abschlusskonferenz-Artefakte, DocuSign-/E-CAMS-Exporte → keine Vorarbeit nötig, nur keine Sackgassen einbauen
- SSO-/IDM-Fähigkeit (NF_002) → Auth als austauschbares Modul kapseln

---

## 11. Akzeptanzkriterien MVP (Definition of Done)

1. **Ende-zu-Ende-Testlauf mit realem Mengengerüst** (262 Bewerbende, 87 Prüfende, beide Tage): Import → Parametrierung → Zuweisung → manuelle Anpassung → Export läuft vollständig durch, Ergebnis regelkonform, keine offenen Konflikte.
2. Alle harten Regeln H1–H9 durch automatisierte Tests abgedeckt; kein Testlauf produziert eine unmarkierte Regelverletzung.
3. Vollberechnung ≤ 15 min; Neuberechnung nach Einzeländerung (z. B. 1 Prüferabsage) deutlich schneller, mit maximalem Bestandserhalt.
4. Alle 5 Änderungsszenarien (Kap. 5) sind durchspielbar.
5. Ergebnis tabellarisch je Tag einsehbar (Raum × Zeitfenster), Sichtenwechsel Bewerbende/Prüfende/Räume funktioniert.
6. Konflikte werden benannt (verletzte Regel), gelistet und sind ansteuerbar.
7. CSV-Export enthält je Zuweisung: Person, Tag, Zeitfenster, Raum, Format, Gruppe + Prüfende↔Bewerbende-Zuordnung; Exporte sind versioniert und wiederholbar.
8. Wartezeiten und Abweichungen von W1/W2 werden ausgewiesen.
9. Konfigurationen sind je Jahrgang speicher- und wiederverwendbar; UI vollständig deutsch, ohne IT-Spezialwissen bedienbar.
10. Berechnungsläufe und manuelle Eingriffe sind protokolliert; Planungsstände versioniert.
11. `/docs/formats.md` und `/docs/regeln.md` liegen vor.

---

## 12. Hinweise für Claude Code (Vibecoding-Reihenfolge)

1. **Datenmodell + CSV-Import** (F_OM_001–003, 005) mit Validierung und Testdaten-Generator für das reale Mengengerüst.
2. **`rules.py`**: alle Regeln als pure functions + pytest-Suite. *Erst danach* den Solver bauen — die Tests sind das Sicherheitsnetz.
3. **Solver** (Stufe 1 Gruppierung, Stufe 2 CP-SAT) gegen die Testdaten; Qualitätskennzahlen ausgeben.
4. **Warmstart/Neuberechnung** + die 5 Änderungsszenarien als Integrationstests.
5. **API + Frontend** entlang des 5-Schritte-Workflows; Planungsraster + Konfliktliste vor Umbuchungsdialog.
6. **Export + Versionierung**, dann PDF-Erzeugnisse (B-Anforderungen).
7. Durchgehend: deutsche UI-Texte und Fehlermeldungen, Protokollierung, Jahrgangs-Dimension von Anfang an im Schema.
