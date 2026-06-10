from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.services import session_store

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/candidate/{candidate_id}")
def get_candidate_progress(candidate_id: UUID) -> dict:
    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    try:
        return session_store.get_candidate_progress(candidate_id)
    except session_store.PlanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
