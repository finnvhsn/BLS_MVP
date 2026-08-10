# Single-Container-Deployment (NF_005): Cloud-EU oder On-Premises identisch.
# Stage 1: Frontend-Build
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN if [ -f package.json ]; then npm ci; fi
COPY frontend/ ./
RUN if [ -f package.json ]; then npm run build; fi && mkdir -p dist

# Stage 2: Backend + statisches Frontend
FROM python:3.12-slim
# WeasyPrint-Systemabhängigkeiten (PDF: Laufzettel/Raumschilder)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
    fonts-dejavu-core shared-mime-info \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt weasyprint
COPY backend/ backend/
COPY docs/ docs/
COPY --from=frontend /build/dist frontend/dist
ENV BLS_DATEN_VERZEICHNIS=/data
VOLUME ["/data"]
EXPOSE 8000
WORKDIR /srv/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
