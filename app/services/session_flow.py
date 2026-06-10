import json
from uuid import UUID

import anthropic

from app.config import settings
from app.models.session import AnswerResponse, EvaluationResult, PlanAdaptationInfo
from app.services import evaluator, session_store


def evaluate_and_submit(session_id: UUID, answer: str) -> AnswerResponse:
    if not settings.anthropic_configured:
        raise RuntimeError("Anthropic is not configured. Set ANTHROPIC_API_KEY in .env")

    try:
        ctx = session_store.get_turn_context(session_id)
    except session_store.SessionNotFoundError as e:
        raise LookupError(str(e)) from e
    except session_store.DayNotFoundError as e:
        raise LookupError(str(e)) from e
    except ValueError as e:
        raise ValueError(str(e)) from e

    day_plan = ctx["day_plan"]

    try:
        evaluation: EvaluationResult = evaluator.evaluate_answer(
            target_role=ctx["target_role"],
            day_title=day_plan.title,
            prompt=ctx["current_prompt"],
            rubric=ctx["rubric"],
            answer=answer,
        )
    except anthropic.NotFoundError as e:
        raise RuntimeError(
            f"Invalid ANTHROPIC_MODEL ({settings.anthropic_model}). "
            "Set ANTHROPIC_MODEL=claude-sonnet-4-6 in .env and restart."
        ) from e
    except anthropic.APIError as e:
        raise RuntimeError(f"Anthropic API error: {e.message}") from e
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"Could not parse Claude response: {e}") from e

    try:
        result = session_store.submit_answer(session_id, answer, evaluation)
    except RuntimeError as e:
        raise RuntimeError(str(e)) from e

    return AnswerResponse(
        session_id=result["session_id"],
        session_status=result["session_status"],
        prompt_index=result["prompt_index"],
        evaluation=result["evaluation"],
        next_prompt=result["next_prompt"],
        next_focus=result.get("next_focus"),
        total_prompts=result["total_prompts"],
        session_summary=result.get("session_summary"),
        plan_adaptation=(
            PlanAdaptationInfo.model_validate(result["plan_adaptation"])
            if result.get("plan_adaptation")
            else None
        ),
    )
