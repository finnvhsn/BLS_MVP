"""FastAPI-Entry des MVP „Zuweisung mündliches Auswahlverfahren" (BLS)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from .api import auth, druck, export, jahrgaenge, planung, stammdaten
from .core.security import admin_anlegen
from .db.database import engine, schema_anlegen


@asynccontextmanager
async def lifespan(app: FastAPI):
    schema_anlegen()
    with Session(engine()) as session:
        admin_anlegen(session)
    yield


app = FastAPI(
    title="BLS Zuweisung mündliches Auswahlverfahren",
    description="MVP: Import → Parametrierung → Zuweisung → Kontrolle → Export",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(jahrgaenge.router)
app.include_router(stammdaten.router)
app.include_router(planung.router)
app.include_router(export.router)
app.include_router(druck.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Statisches Frontend (Vite-Build), falls vorhanden — von FastAPI serviert.
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():  # pragma: no cover
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
