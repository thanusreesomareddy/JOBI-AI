from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.models.session import (
    AnswerRequest,
    AnswerResponse,
    InterviewBeginResponse,
    InterviewExchange,
    InterviewTurnRequest,
    InterviewTurnResponse,
    PlanAdaptationInfo,
    SessionStatus,
    SessionTurn,
    StartSessionRequest,
    StartSessionResponse,
)
from app.services import session_flow, session_store, stt

router = APIRouter(prefix="/session", tags=["session"])


@router.post("/start", response_model=StartSessionResponse)
def start_session(body: StartSessionRequest) -> StartSessionResponse:
    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    try:
        candidate_id = UUID(body.candidate_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid candidate_id UUID") from e

    try:
        session = session_store.start_session(candidate_id, body.day, adapt_plan=body.adapt_plan)
    except session_store.PlanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except session_store.DayNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    day_plan = session["day_plan"]
    return StartSessionResponse(
        session_id=session["id"],
        candidate_id=session["candidate_id"],
        plan_id=session["plan_id"],
        day=session["day"],
        title=day_plan["title"],
        reading=day_plan["reading"],
        current_prompt=session["current_prompt"],
        prompt_index=session["prompt_index"],
        total_prompts=session["total_prompts"],
        status=SessionStatus.in_progress,
        session_mode="interview",
        interview_phase=session.get("interview_phase") or "lobby",
        interview_log=[],
    )


class InterviewBeginRequest(BaseModel):
    interviewer_name: str = "Alex"


@router.post("/{session_id}/interview-begin", response_model=InterviewBeginResponse)
def join_interview(session_id: UUID, body: InterviewBeginRequest | None = None) -> InterviewBeginResponse:
    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    name = (body.interviewer_name if body else "Alex") or "Alex"
    try:
        result = session_store.begin_interview(session_id, interviewer_name=name)
    except session_store.SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return InterviewBeginResponse(
        session_id=result["session_id"],
        session_status=result["session_status"],
        interview_phase=result["interview_phase"],
        coach_messages=result["coach_messages"],
        conversation=[InterviewExchange(**c) for c in result["conversation"]],
        topic_preview=result.get("topic_preview", ""),
        total_rounds=result.get("total_rounds", 1),
    )


@router.get("/{session_id}")
def get_session(session_id: UUID) -> dict:
    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    try:
        return session_store.get_session_detail(session_id)
    except session_store.SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except session_store.DayNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{session_id}/answer", response_model=AnswerResponse)
def submit_answer(session_id: UUID, body: AnswerRequest) -> AnswerResponse:
    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    try:
        return session_flow.evaluate_and_submit(session_id, body.answer)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/{session_id}/answer-audio", response_model=AnswerResponse)
async def submit_audio_answer(
    session_id: UUID,
    audio: UploadFile = File(..., description="Recorded answer (webm, wav, mp3, m4a)"),
) -> AnswerResponse:
    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured")
    if not settings.stt_configured:
        key_hint = (
            "DEEPGRAM_API_KEY"
            if settings.stt_provider == "deepgram"
            else "OPENAI_API_KEY"
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Speech-to-text is not configured. Set {key_hint} in .env "
                "(or use Speak mode in Chrome — it can use free browser transcription)."
            ),
        )

    content = await audio.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio file")

    audio_path = stt.save_uploaded_audio(content, audio.filename)
    try:
        transcript = stt.transcribe_audio(audio_path)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    finally:
        audio_path.unlink(missing_ok=True)

    try:
        result = session_flow.evaluate_and_submit(session_id, transcript)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return result.model_copy(update={"transcript": transcript})


@router.post("/{session_id}/interview-audio", response_model=InterviewTurnResponse)
async def submit_interview_audio(
    session_id: UUID,
    audio: UploadFile = File(..., description="Recorded speech (webm, wav, mp3, m4a)"),
) -> InterviewTurnResponse:
    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured")
    if not settings.stt_configured:
        raise HTTPException(status_code=503, detail="Speech-to-text is not configured")
    if not settings.anthropic_configured:
        raise HTTPException(status_code=503, detail="Anthropic is not configured")

    content = await audio.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio file")

    audio_path = stt.save_uploaded_audio(content, audio.filename)
    try:
        transcript = stt.transcribe_audio(audio_path)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    finally:
        audio_path.unlink(missing_ok=True)

    try:
        result = session_store.submit_interview_turn(session_id, transcript)
    except session_store.SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except session_store.DayNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return _interview_turn_response(result)


def _interview_turn_response(result: dict) -> InterviewTurnResponse:
    return InterviewTurnResponse(
        session_id=result["session_id"],
        session_status=result["session_status"],
        interview_phase=result.get("interview_phase", "interview"),
        coach_messages=result["coach_messages"],
        action=result["action"],
        conversation=[InterviewExchange(**c) for c in result["conversation"]],
        round_index=result["round_index"],
        total_rounds=result["total_rounds"],
        evaluation=result.get("evaluation"),
        answer_feedback=result.get("answer_feedback"),
        feedback_label=result.get("feedback_label") or "",
        feedback_skipped=bool(result.get("feedback_skipped")),
        session_summary=result.get("session_summary"),
        plan_adaptation=(
            PlanAdaptationInfo.model_validate(result["plan_adaptation"])
            if result.get("plan_adaptation")
            else None
        ),
        turns=(
            [SessionTurn.model_validate(t) for t in result["turns"]]
            if result.get("turns")
            else None
        ),
    )


@router.post("/{session_id}/interview-end", response_model=InterviewTurnResponse)
def end_interview(session_id: UUID) -> InterviewTurnResponse:
    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured")
    if not settings.anthropic_configured:
        raise HTTPException(status_code=503, detail="Anthropic is not configured")

    try:
        result = session_store.end_interview_session(session_id)
    except session_store.SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return _interview_turn_response(result)


@router.post("/{session_id}/interview-turn", response_model=InterviewTurnResponse)
def submit_interview_turn(session_id: UUID, body: InterviewTurnRequest) -> InterviewTurnResponse:
    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured")
    if not settings.anthropic_configured:
        raise HTTPException(status_code=503, detail="Anthropic is not configured")

    try:
        result = session_store.submit_interview_turn(
            session_id, body.message, interviewer_name=body.interviewer_name
        )
    except session_store.SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except session_store.DayNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return _interview_turn_response(result)
