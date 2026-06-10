import json

import anthropic

from app.config import settings
from app.models.plan import TrainingPlan
from app.models.resume import ParsedResume
from app.services.llm_json import extract_tool_input, parse_json_text, repair_json_with_claude

SYSTEM_PROMPT = """You create structured interview/career training plans.
Use the emit_training_plan tool to return the plan.

Rules:
- schedule length MUST equal days
- day numbers 1..days inclusive, one entry each
- reading.content: concise actionable bullets, max ~400 words per day, no unescaped control characters
- voice_session: 2-4 prompts per day, rubric specific to that day
- Progress difficulty across days"""

PLAN_TOOL = {
    "name": "emit_training_plan",
    "description": "Return a complete N-day career training plan.",
    "input_schema": {
        "type": "object",
        "properties": {
            "target_role": {"type": "string"},
            "days": {"type": "integer", "minimum": 1, "maximum": 30},
            "schedule": {
                "type": "array",
                "items": {
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
                },
            },
        },
        "required": ["target_role", "days", "schedule"],
    },
}


def _call_claude(client: anthropic.Anthropic, user_payload: dict, days: int) -> anthropic.types.Message:
    return client.messages.create(
        model=settings.anthropic_model,
        max_tokens=16384,
        system=SYSTEM_PROMPT,
        tools=[PLAN_TOOL],
        tool_choice={"type": "tool", "name": "emit_training_plan"},
        messages=[
            {
                "role": "user",
                "content": f"Create a {days}-day training plan:\n\n{json.dumps(user_payload, indent=2)}",
            }
        ],
    )


def _message_to_plan_data(message: anthropic.types.Message, client: anthropic.Anthropic) -> dict:
    try:
        return extract_tool_input(message, "emit_training_plan")
    except ValueError:
        pass

    block = message.content[0]
    if block.type != "text":
        raise ValueError("Unexpected response type from Claude")

    text = block.text
    try:
        data = parse_json_text(text)
    except json.JSONDecodeError as e:
        data = repair_json_with_claude(client, text, str(e))

    if not isinstance(data, dict):
        raise ValueError("Claude plan response was not a JSON object")
    return data


def generate_plan(parsed: ParsedResume, days: int) -> TrainingPlan:
    if not settings.anthropic_configured:
        raise RuntimeError("Anthropic is not configured. Set ANTHROPIC_API_KEY in .env")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_payload = {
        "target_role": parsed.target_role,
        "seniority": parsed.seniority.value,
        "skills": parsed.skills,
        "gaps": parsed.gaps,
        "summary": parsed.summary,
        "days": days,
    }

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            message = _call_claude(client, user_payload, days)
            data = _message_to_plan_data(message, client)
            plan = TrainingPlan.model_validate(data)
            if plan.days != days:
                plan = plan.model_copy(update={"days": days})
            return plan
        except (ValueError, json.JSONDecodeError, anthropic.APIError) as e:
            last_error = e
            if attempt == 0 and not isinstance(e, anthropic.APIError):
                continue
            raise

    raise last_error or RuntimeError("Plan generation failed")
