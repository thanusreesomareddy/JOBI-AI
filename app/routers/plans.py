from uuid import UUID

import json

import anthropic
from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.models.plan import TrainingPlan
from app.models.resume import ParsedResume
from app.services import plan_generator, plan_store

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("/generate")
def generate_plan(
    resume_id: UUID = Query(..., description="Resume UUID from upload + analyze"),
    days: int | None = Query(default=None, ge=1, le=30),
) -> dict:
    """Build N-day plan from analyzed resume and store in Supabase."""
    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured")
    if not settings.anthropic_configured:
        raise HTTPException(status_code=503, detail="Anthropic is not configured")

    n_days = days or settings.plan_days_default
    row = plan_store.get_resume(resume_id)
    parsed_data = row.get("parsed_json")
    if not parsed_data:
        raise HTTPException(
            status_code=400,
            detail="Resume not analyzed yet. Call POST /resume/{resume_id}/analyze first.",
        )

    parsed = ParsedResume.model_validate(parsed_data)
    try:
        plan: TrainingPlan = plan_generator.generate_plan(parsed, n_days)
    except anthropic.NotFoundError as e:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Invalid ANTHROPIC_MODEL ({settings.anthropic_model}). "
                "Set ANTHROPIC_MODEL=claude-sonnet-4-6 in .env and restart."
            ),
        ) from e
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {e.message}") from e
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=502, detail=f"Could not parse Claude response: {e}") from e
    candidate_id = UUID(row["candidate_id"])
    plan_id = plan_store.save_plan(candidate_id, plan)

    return {
        "plan_id": str(plan_id),
        "candidate_id": str(candidate_id),
        "resume_id": str(resume_id),
        "plan": plan.model_dump(mode="json"),
    }


@router.get("/candidate/{candidate_id}")
def get_candidate_plan(candidate_id: UUID) -> dict:
    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    row = plan_store.get_plan_for_candidate(candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="No plan found for this candidate")

    return {
        "plan_id": row["id"],
        "candidate_id": row["candidate_id"],
        "target_role": row["target_role"],
        "days": row["days"],
        "plan": row["plan_json"],
        "created_at": row["created_at"],
        "updated_at": row.get("updated_at"),
        "adaptation_log": row.get("adaptation_log") or [],
    }
