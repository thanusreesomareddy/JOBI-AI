import json
import logging
from datetime import datetime, timezone

import anthropic

from app.config import settings
from app.models.plan import DayPlan, TrainingPlan
from app.models.session import SessionSummary, SessionTurn
from app.services.focus_areas import compute_focus_areas
from app.services.llm_json import extract_tool_input, parse_json_text, repair_json_with_claude

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You adapt an interview training plan based on how the candidate performed.

Use the adapt_upcoming_days tool. Revise ONLY the upcoming days you are given.

Rules:
- Use ALL prior completed days plus the day just finished — recurring weak areas matter most
- Double down on gaps from session summaries, improvement lists, and low-scoring answers
- Keep the same day numbers and total day count
- reading.content: concise actionable bullets, max ~400 words per day
- voice_session: 2-4 prompts per day; rubric must match revised focus
- Do not make days easier — adjust focus, not difficulty downward
- Preserve overall career goal and role trajectory
- If the same weakness appears on multiple days, prioritize it in upcoming days"""

DAY_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "day": {"type": "integer", "minimum": 1},
        "title": {"type": "string"},
        "reading": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "duration_min": {"type": "integer", "minimum": 1, "maximum": 120},
            },
            "required": ["content", "duration_min"],
        },
        "voice_session": {
            "type": "object",
            "properties": {
                "prompts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 10,
                },
                "rubric": {"type": "string"},
            },
            "required": ["prompts", "rubric"],
        },
    },
    "required": ["day", "title", "reading", "voice_session"],
}

ADAPT_TOOL = {
    "name": "adapt_upcoming_days",
    "description": "Return revised upcoming day plans based on candidate performance.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {"type": "string"},
            "days": {
                "type": "array",
                "items": DAY_ITEM_SCHEMA,
                "minItems": 1,
            },
        },
        "required": ["reason", "days"],
    },
}


class PlanAdaptationResult:
    def __init__(
        self,
        *,
        adapted: bool,
        reason: str = "",
        updated_days: list[int] | None = None,
        plan: TrainingPlan | None = None,
    ):
        self.adapted = adapted
        self.reason = reason
        self.updated_days = updated_days or []
        self.plan = plan


def _merge_adapted_days(
    plan: TrainingPlan,
    adapted_entries: list[DayPlan],
    source_day: int,
) -> TrainingPlan:
    by_day = {entry.day: entry for entry in adapted_entries}
    schedule: list[DayPlan] = []
    for entry in plan.schedule:
        if entry.day in by_day:
            schedule.append(
                by_day[entry.day].model_copy(
                    update={"personalized": True, "adapted_from_day": source_day},
                )
            )
        else:
            schedule.append(entry)
    return plan.model_copy(update={"schedule": schedule})


def adapt_upcoming_days(
    *,
    plan: TrainingPlan,
    completed_day: int,
    completed_day_title: str,
    session_summary: SessionSummary,
    turns: list[SessionTurn],
    prior_sessions: list[dict],
) -> PlanAdaptationResult:
    """Revise days after completed_day based on session performance."""
    completed_days = {int(s["day"]) for s in prior_sessions if s.get("day")}
    upcoming = [
        entry
        for entry in plan.schedule
        if entry.day > completed_day and entry.day not in completed_days
    ]
    if not upcoming:
        return PlanAdaptationResult(adapted=False, reason="No upcoming days to adapt")

    if not settings.anthropic_configured:
        return PlanAdaptationResult(adapted=False, reason="Anthropic not configured")

    conversation = [
        {
            "question": t.prompt,
            "answer": t.answer[:1500],
            "score": t.evaluation.score,
            "improvements": t.evaluation.improvements,
        }
        for t in turns
    ]

    prior = []
    for s in prior_sessions:
        if int(s.get("day", 0)) == completed_day:
            continue
        prior_turns = s.get("turns") or []
        prior.append(
            {
                "day": s.get("day"),
                "summary": s.get("session_summary"),
                "turns": [
                    {
                        "question": t.get("prompt", "")[:200],
                        "score": (t.get("evaluation") or {}).get("score"),
                        "improvements": (t.get("evaluation") or {}).get("improvements", []),
                    }
                    for t in prior_turns
                ],
            }
        )

    all_for_focus = list(prior_sessions) + [
        {
            "status": "completed",
            "session_summary": session_summary.model_dump(mode="json"),
            "turns": [t.model_dump(mode="json") for t in turns],
        }
    ]
    focus_areas = compute_focus_areas(all_for_focus)

    payload = {
        "target_role": plan.target_role,
        "completed_day": completed_day,
        "completed_day_title": completed_day_title,
        "session_summary": session_summary.model_dump(mode="json"),
        "conversation": conversation,
        "prior_completed_sessions": prior,
        "recurring_focus_areas": focus_areas,
        "upcoming_days_to_revise": [d.model_dump(mode="json", exclude={"personalized", "adapted_from_day"}) for d in upcoming],
    }

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        message = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=16384,
            system=SYSTEM_PROMPT,
            tools=[ADAPT_TOOL],
            tool_choice={"type": "tool", "name": "adapt_upcoming_days"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Candidate finished Day {completed_day}. "
                        f"Revise these {len(upcoming)} upcoming day(s).\n\n"
                        f"{json.dumps(payload, indent=2)}"
                    ),
                }
            ],
        )
    except anthropic.APIError as e:
        logger.warning("Plan adaptation API error: %s", e.message)
        return PlanAdaptationResult(adapted=False, reason="Adaptation failed")

    try:
        data = extract_tool_input(message, "adapt_upcoming_days")
    except ValueError:
        block = message.content[0]
        if block.type != "text":
            return PlanAdaptationResult(adapted=False, reason="Invalid adaptation response")
        try:
            data = parse_json_text(block.text)
        except json.JSONDecodeError as e:
            try:
                data = repair_json_with_claude(client, block.text, str(e))
            except Exception:
                return PlanAdaptationResult(adapted=False, reason="Could not parse adaptation")

    reason = str(data.get("reason", "")).strip()
    raw_days = data.get("days") or []
    expected_days = {d.day for d in upcoming}
    adapted_entries: list[DayPlan] = []

    for item in raw_days:
        try:
            entry = DayPlan.model_validate(item)
        except Exception:
            continue
        if entry.day in expected_days:
            adapted_entries.append(entry)

    if not adapted_entries:
        return PlanAdaptationResult(adapted=False, reason="No valid adapted days returned")

    updated_plan = _merge_adapted_days(plan, adapted_entries, completed_day)
    return PlanAdaptationResult(
        adapted=True,
        reason=reason or f"Updated days after Day {completed_day} performance",
        updated_days=sorted({e.day for e in adapted_entries}),
        plan=updated_plan,
    )


def adaptation_log_entry(
    *,
    source_day: int,
    reason: str,
    updated_days: list[int],
) -> dict:
    return {
        "source_day": source_day,
        "reason": reason,
        "updated_days": updated_days,
        "adapted_at": datetime.now(timezone.utc).isoformat(),
    }
