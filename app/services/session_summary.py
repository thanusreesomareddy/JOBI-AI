import json

import anthropic

from app.config import settings
from app.models.session import SessionSummary, SessionTurn
from app.services.llm_json import extract_tool_input, parse_json_text, repair_json_with_claude

SYSTEM_PROMPT = """Summarize a completed interview practice session for the candidate.
Use the submit_session_summary tool. Be encouraging but honest."""

SUMMARY_TOOL = {
    "name": "submit_session_summary",
    "description": "Return end-of-session summary for the candidate.",
    "input_schema": {
        "type": "object",
        "properties": {
            "average_score": {"type": "number", "minimum": 0, "maximum": 10},
            "headline": {"type": "string"},
            "strengths": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "areas_to_improve": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "recommendation": {"type": "string"},
        },
        "required": ["average_score", "headline", "strengths", "areas_to_improve", "recommendation"],
    },
}


def build_session_summary(
    *,
    target_role: str,
    day_title: str,
    turns: list[SessionTurn],
) -> SessionSummary:
    if not turns:
        return SessionSummary(
            average_score=0,
            headline="Session complete",
            strengths=[],
            areas_to_improve=[],
            recommendation="Practice again tomorrow.",
        )

    scores = [t.evaluation.score for t in turns]
    avg = round(sum(scores) / len(scores), 1)

    if not settings.anthropic_configured:
        return SessionSummary(
            average_score=avg,
            headline=f"Day complete — average score {avg}/10",
            strengths=[],
            areas_to_improve=[],
            recommendation="Review your feedback and try the next day.",
        )

    payload = {
        "target_role": target_role,
        "day_title": day_title,
        "scores": scores,
        "turns": [
            {
                "question": t.prompt,
                "score": t.evaluation.score,
                "feedback": t.evaluation.feedback,
            }
            for t in turns
        ],
    }

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[SUMMARY_TOOL],
        tool_choice={"type": "tool", "name": "submit_session_summary"},
        messages=[{"role": "user", "content": json.dumps(payload, indent=2)}],
    )

    try:
        data = extract_tool_input(message, "submit_session_summary")
    except ValueError:
        block = message.content[0]
        if block.type != "text":
            raise ValueError("Unexpected summary response") from None
        try:
            data = parse_json_text(block.text)
        except json.JSONDecodeError as e:
            data = repair_json_with_claude(client, block.text, str(e))

    summary = SessionSummary.model_validate(data)
    return summary.model_copy(update={"average_score": avg})
