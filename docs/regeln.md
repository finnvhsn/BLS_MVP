# Regel- und Parameterdokumentation (NF_010, Lieferbestandteil)

Alle fachlichen Regeln existieren **genau einmal** im Code:
[`backend/app/core/rules.py`](../backend/app/core/rules.py). Sie werden
genutzt vom Zuweisungsalgorithmus (Constraint-Aufbau), von der Konfliktliste
und von der Live-Validierung bei manueller Nachbearbeitung. Ein automatischer
Test garantiert: Jedes Berechnungsergebnis besteht die vollständige
Regelprüfung ohne Verletzung.

## Wer wird eingeplant?

Eingeplant werden ausschließlich Bewerbende mit **zugelassen = ja** und
**Rückmeldestatus = Zusage**, die nicht kurzfristig abgesagt haben.
Rücksteller und Absagen werden importiert und mitgeführt, aber nicht verplant.

## Harte Regeln (Verletzung ⇒ benannter Konflikt, niemals stillschweigend)

| ID | Titel | Prüfung |
|---|---|---|
| H1 | Keine Doppelbegegnung | Je Paar (Prüfer:in, Bewerber:in) höchstens eine Begegnung — über alle Formate und beide Tage. |
| H2 | Befangenheit | Hinterlegte Paarungen werden niemals zugewiesen (gespeichert ohne Grund — Datensparsamkeit). |
| H3 | Prüfergruppen-Zusammensetzung | Gruppenformate: max. 1 Junior, min. 2 Senior je Prüfergruppe (Grenzen je Format konfigurierbar). |
| H4 | Einzelgespräche nur Senior | Formate mit Kennzeichen „nur Senior“ (Einzelgespräche) ohne Junior-Prüfende. |
| H5 | Keine Doppelbelegung | Personen und Räume je Zeitfenster höchstens einmal verplant; verplante Personen sind am Tag verfügbar und nehmen teil. |
| H6 | Raumeignung & -verfügbarkeit | Kleine Räume für Einzelgespräche, große für Gruppenformate; Verfügbarkeit je Tag und Zeitfenster (inkl. Sperrzeiten). |
| H7 | Vollständigkeit & Tagesbindung | Prüfung ausschließlich am in Access zugeteilten Tag (`tag`-Feld, Pflicht); dort alle konfigurierten Formate genau einmal. |
| H8 | Formatdauern & Zeitmodell | Konfigurierte Dauern eingehalten; alles innerhalb des Tagesfensters (Default 10:00–17:15); Thesenvortrag blockt die gesamte Gruppe für den vollen Block. |
| H9 | Regeln je Konstellation | Prüfergruppen dürfen über den Tag wechseln; H1–H4 werden je Prüfungsereignis (= je Konstellation) geprüft. |

## Weiche Regeln / Optimierungsziele (werden maximiert, Abweichungen ausgewiesen)

| ID | Ziel | Kennzahl im Ergebnis |
|---|---|---|
| W1 | Ideal 8 unterschiedliche Prüfende je Bewerber:in (= Summe der Prüfergruppengrößen aller Formate) | Liste der Abweichler mit Ist-Wert |
| W2 | Ca. 12 Bewerbende je Prüfer:in, gleichmäßig verteilt | Durchschnitt, Min/Max, Streuung |
| W3 | Diverse Bewerbendengruppen (Geschlecht, Studiengang), zufallsbasiert | Diversitäts-Score je Gruppe |
| W4 | Gemischte Prüfergruppen (Geschlecht) | Anteil gemischter Prüfergruppen |
| W5 | Wartezeiten minimieren | Wartezeit je Bewerber:in, Summe, Maximum |
| W6 | Stabilität bei Neuberechnung | erhalten / entfallen / neu |

## Parameter (über die UI je Jahrgang konfigurierbar, F_OM_010)

| Parameter | Default | Bedeutung |
|---|---|---|
| Tagesfenster | 10:00 – 17:15 | Harte Grenze für alle Zuweisungen (H8) |
| Mindestpause zwischen Terminen | 15 min | Wegzeit für den Raumwechsel; gilt zwischen **allen** Terminen einer Person. Muss ein Vielfaches von 15 min sein (Zeitraster) — andere Werte werden beim Speichern abgelehnt. |
| Vorbereitungspuffer Gruppe | 15 min | Zusätzliche Kaffeepause/Vorbereitungszeit **vor Gruppenformaten**. Wirksam wird der jeweils größere der beiden Werte. Achtung: rasterfremde Werte (z. B. 10) bleiben hier aus historischen Gründen erlaubt, sind aber **wirkungslos** — die Belegungsprüfung läuft auf dem 15-Minuten-Raster. |
| Formate | Einzel 1 (30 min), Einzel 2 (30 min), Gruppenarbeit (45 min), Thesenvortrag (150 min) | Dauer, Prüfergruppengröße, Senior-/Junior-Grenzen, Raumgröße je Format; Zusammenlegung der Einzelgespräche = Konfigurationsänderung |
| Gruppengröße | 4 | Bewerbende je Gruppe (W3) |
| Zeitbudget je Optimierungsschritt | 60 s | **Kein Gesamtlimit.** Eine Berechnung besteht aus drei Schritten je Prüfungstag (Zeitplanung, Raumvergabe, Prüfendenzuordnung); bei Relaxierung wird ein Schritt einmal wiederholt. Daraus folgt die Gesamtdauer — im schlechtesten Fall rund 9 min, typisch 3 min beim realen Mengengerüst (NF_003: ≤ 15 min). Werte über 60 s bringen kein besseres Ergebnis; die Raumvergabe nutzt höchstens 30 s, weil sie ein einfaches Matching ist. |
| Zufalls-Seed | 42 | Reproduzierbarkeit der Läufe (NF_010) |

## Gewichtung der weichen Ziele (nicht in der UI, bewusst)

Die Gewichte der Zielfunktion sind Solver-Tuning, kein Verfahrensparameter: ein
Fehleintrag erzeugt keinen Fehler, sondern still einen schlechteren Plan. Sie
sind daher in
[`backend/app/core/konfiguration.py`](../backend/app/core/konfiguration.py)
festgelegt (über die Konfigurations-API weiterhin überschreibbar):

| Ziel | Gewicht | misst | Rohgröße je Lauf |
|---|---|---|---|
| W2 gleichmäßige Auslastung | 30 | Auslastungsabweichung je Prüfer:in | kleine Ganzzahlen |
| W4 gemischte Prüfergruppen | 10 | gemischt ja/nein je Ereignis | 0/1 |
| W5 Wartezeiten | 5 | Minuten je Bewerber:in, aufsummiert | ~10.000–25.000 |
| W6 Bestandserhalt | 1000 | Anzahl erhaltener Zuweisungen | einige hundert |

Die Staffelung ist notwendig, weil die vier Terme in **einer** Zielfunktion
stehen, aber verschiedene Einheiten messen: bei gleicher Gewichtung würde W5
allein durch seine Größenordnung alles andere überstimmen. `w6 = 1000` liegt
bewusst unterhalb der Relaxierungsstrafe `STRAFE = 1_000_000` — erst dadurch ist
eine Neuberechnung minimalinvasiv, ohne die Relaxierung auszuhebeln.

W1 braucht keinen eigenen Term (strukturell durch H1 + vollständig besetzte
Panels impliziert), W3 wirkt in Stufe 1 über `grouping.py`.

## Nicht aktive Ausbaustufen

**Etappen/Wellen je Tag (F_OM_005).** Gemeint ist, die Kohorte in zeitversetzten
Etappen über den Tag zu verteilen, damit nicht alle Bewerbenden gleichzeitig
Räume und Prüfende binden. Ein Parameter „Wellen je Tag“ existierte, war aber
wirkungslos: er verschob lediglich den *frühestmöglichen* Start der
Gruppenformate, und beim Default (1 Welle) war dieser Versatz konstant 0. Der
Parameter wurde deshalb entfernt.

Eine wirksame Umsetzung müsste den Tagesrahmen je Kohorte **partitionieren** —
also harte Fenstergrenzen je Welle setzen (Welle *k* von *n* darf nur zwischen
`start + k·(fenster/n)` und `start + (k+1)·(fenster/n)` liegen) — statt nur den
frühesten Start zu verschieben. Ansatzpunkt ist `starts_fuer()` in
[`backend/app/core/solver.py`](../backend/app/core/solver.py).

Praktisch verteilt bereits W5 (Wartezeit-Minimierung) die Prüfungen über den
Tag; ein Bedarf für echte Wellen ist im Referenzverfahren nicht aufgetreten.
