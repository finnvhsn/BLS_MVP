# BLS – Zuweisungsalgorithmus mündliches Auswahlverfahren (MVP)

Berechnet für das mündliche Auswahlverfahren der Bucerius Law School eine
korrekte, vollständige und konfliktfreie Raum-/Gruppen-/Prüfendenzuteilung je
Prüfungstag und stellt sie tabellarisch dar (UI + versionierter CSV-Export).

Verbindliche Referenz: [`SPECS_Matching_MVP.md`](SPECS_Matching_MVP.md).
Geführter Prozess: **Import → Parametrierung → Zuweisung → Kontrolle → Export**.

## Betrieb

Der gesamte Betrieb ist ein Befehl (Single-Container, Cloud-EU oder On-Premises):

```bash
docker compose up --build
```

Danach: <http://localhost:8000> — Anmeldung mit `verfahren` /
`bls-auswahl` (Passwort für den Einsatz per `.env` ändern:
`BLS_ADMIN_PASSWORT=…`). Die SQLite-Datenbank liegt im Docker-Volume
`bls-daten`; Sicherungen und Exporte werden dort abgelegt.

## Entwicklung

```bash
# Backend (Python ≥ 3.12)
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cd backend && ../.venv/bin/python -m uvicorn app.main:app --reload   # http://localhost:8000

# Frontend (Entwicklung mit Hot-Reload, Proxy auf :8000)
cd frontend && npm install && npm run dev                            # http://localhost:5173

# Frontend-Build (wird danach von FastAPI unter / serviert)
cd frontend && npm run build
```

PDF-Erzeugung lokal (macOS): `brew install pango` und
`.venv/bin/pip install weasyprint` — im Docker-Image ist alles enthalten.

## Tests

```bash
cd backend
../.venv/bin/python -m pytest                # schnelle Suite (Regeln, Import, API, …)
../.venv/bin/python -m pytest -m langsam     # Volllast: reales Mengengerüst (AK1/AK3), Minuten-Laufzeit
```

Zentrale Absicherung: Alle harten Regeln H1–H9 sind einzeln getestet
(`tests/test_m2_regeln.py`), und der Property-Test „jeder Solver-Output
besteht den Validator“ verhindert Regel-Drift zwischen Solver und
manueller Validierung.

## Testdaten

```bash
cd backend && ../.venv/bin/python -m app.io.testdaten --ziel ../testdaten --seed 42
```

Erzeugt das reale Mengengerüst (262 Bewerbende mit Tageszuteilung 131 Fr /
131 Sa, 58 Senior- + 29 Junior-Prüfende, 34 Räume, Befangenheiten) als
importierbare CSVs im dokumentierten Austauschformat.

## Aufbau

```
backend/app/core/rules.py      # H1–H9 + W1–W6: die EINZIGE Quelle der Wahrheit
backend/app/core/validator.py  # Ganzplan- und Was-wäre-wenn-Validierung
backend/app/core/grouping.py   # Stufe 1: zufallsbasierte, diverse Gruppeneinteilung
backend/app/core/solver.py     # Stufe 2: CP-SAT (Zeiten/Räume → Prüfende), Warmstart
backend/app/io/                # CSV-Import/-Export, Testdaten, PDF (WeasyPrint)
backend/app/api/               # REST-Router entlang des 5-Schritte-Workflows
frontend/                      # React + Vite + TS, deutschsprachige UI
docs/formats.md                # versionierte CSV-Austauschformate (NF_006)
docs/regeln.md                 # Regel- und Parameterdokumentation (NF_010)
```

Scope-Hinweis: Umgesetzt sind ausschließlich Anforderungen der Kennzeichnung
**27**; „28“-Themen (API-Integrationen, SSO, weitere Access-Ablösung) sind
bewusst nicht gebaut, aber architektonisch nicht verbaut (Import/Export vom
Transportweg entkoppelt, Auth als Modul, breites Datenmodell).
