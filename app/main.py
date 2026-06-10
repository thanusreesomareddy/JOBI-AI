from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import plans, progress, resume, session

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Jobi AI API",
    description="Resume ingestion, plan generation, and daily practice sessions",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resume.router)
app.include_router(plans.router)
app.include_router(session.router)
app.include_router(progress.router)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "supabase": settings.supabase_configured,
        "anthropic": settings.anthropic_configured,
        "stt": settings.stt_configured,
        "stt_provider": settings.stt_provider_label,
        "browser_stt": settings.stt_provider == "browser" or not settings.stt_configured,
        "browser_tts": True,
    }
