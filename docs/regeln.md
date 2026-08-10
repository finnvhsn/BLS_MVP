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
| Wellen je Tag | 1 | Etappen/Wellen der Kohorte |
| Puffer | 15 min | Pausenpuffer zwischen Prüfungen einer Person (Kaffeepause vor Gruppenvortrag) |
| Formate | Einzel 1 (30 min), Einzel 2 (30 min), Gruppenarbeit (45 min), Thesenvortrag (150 min) | Dauer, Prüfergruppengröße, Senior-/Junior-Grenzen, Raumgröße je Format; Zusammenlegung der Einzelgespräche = Konfigurationsänderung |
| Gruppengröße | 4 | Bewerbende je Gruppe (W3) |
| Gewichte W1–W6 | 100 / 30 / 10 / 10 / 5 / 1000 | Gewichtung der weichen Ziele in der Zielfunktion |
| Solver-Timeout | 600 s | Abbruchzeit; bestes gefundenes Ergebnis wird ausgegeben (NF_003: ≤ 15 min) |
| Zufalls-Seed | 42 | Reproduzierbarkeit der Läufe (NF_010) |
