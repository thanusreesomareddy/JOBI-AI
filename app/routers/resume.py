import json
import uuid
from pathlib import Path
from uuid import UUID

import anthropic
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.models.resume import ParsedResume
from app.services import parser, plan_store, role_detector

router = APIRouter(prefix="/resume", tags=["resume"])


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    candidate_id: UUID | None = None,
) -> dict:
    """Upload PDF, extract text, optionally attach to an existing candidate."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF resumes are supported for now")

    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    cid = candidate_id or plan_store.create_candidate()
    suffix = Path(file.filename).suffix or ".pdf"
    stored_name = f"{uuid.uuid4()}{suffix}"
    dest = settings.upload_dir / stored_name

    content = await file.read()
    dest.write_bytes(content)

    try:
        raw_text = parser.extract_text_from_pdf(dest)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    resume_id = plan_store.save_resume(cid, raw_text=raw_text, file_path=str(dest))

    return {
        "candidate_id": str(cid),
        "resume_id": str(resume_id),
        "raw_text_preview": raw_text[:500],
        "char_count": len(raw_text),
    }


@router.post("/{resume_id}/analyze")
def analyze_resume(resume_id: UUID) -> dict:
    """Run LLM role/skills detection and persist parsed_json."""
    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured")
    if not settings.anthropic_configured:
        raise HTTPException(status_code=503, detail="Anthropic is not configured")

    row = plan_store.get_resume(resume_id)
    raw_text = row.get("raw_text")
    if not raw_text:
        raise HTTPException(status_code=404, detail="Resume not found or has no text")

    try:
        parsed: ParsedResume = role_detector.analyze_resume(raw_text)
    except anthropic.NotFoundError as e:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Invalid ANTHROPIC_MODEL ({settings.anthropic_model}). "
                "Set ANTHROPIC_MODEL=claude-sonnet-4-6 in .env and restart the server."
            ),
        ) from e
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {e.message}") from e
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=502, detail=f"Could not parse Claude response: {e}") from e

    plan_store.update_resume_parsed(resume_id, parsed)

    return {
        "resume_id": str(resume_id),
        "candidate_id": row["candidate_id"],
        "parsed": parsed.model_dump(mode="json"),
    }
