import json

import anthropic

from app.config import settings
from app.models.plan import DayPlan
from app.models.session import EvaluationResult, GeneratedQuestion, NextQuestionResult, SessionTurn
from app.services.llm_json import extract_tool_input, parse_json_text, repair_json_with_claude

OPENING_SYSTEM = """You are an interview coach starting a practice session.
Use propose_opening_question to create the FIRST question.

Rules:
- Base the question on today's reading, role, rubric, and planned themes
- Create an ORIGINAL question — do not copy planned_prompts verbatim; use them as topic hints only
- One clear, realistic interview question appropriate for the target role
- Match difficulty to the day title and reading content
- focus: 2-4 words only (e.g. "SQL depth", "leadership story") — never a sentence"""

FOLLOWUP_SYSTEM = """You are an interview coach mid-session.
Use propose_next_question after each candidate answer.

Rules:
- Combine TWO sources: (1) today's plan context — reading, rubric, role, planned themes
      (2) what the candidate actually said — gaps, strengths, last score and feedback
- next_question must be original, not copied from planned_prompts
- Dig deeper into weak areas from the last answer; probe strong claims with specifics
- should_continue=false when depth is sufficient or max turns reached
- Do not repeat questions already asked
- focus: 2-4 words only — short topic label, NOT an explanation or summary"""

OPENING_TOOL = {
    "name": "propose_opening_question",
    "description": "Create the opening interview question for this practice day.",
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "focus": {"type": "string"},
        },
        "required": ["question", "focus"],
    },
}

NEXT_QUESTION_TOOL = {
    "name": "propose_next_question",
    "description": "Propose the next interview question or end the session.",
    "input_schema": {
        "type": "object",
        "properties": {
            "should_continue": {"type": "boolean"},
            "next_question": {"type": "string"},
            "focus": {"type": "string"},
        },
        "required": ["should_continue", "next_question", "focus"],
    },
}


def _clamp_focus(focus: str) -> str:
    words = " ".join((focus or "").split()).split()
    short = " ".join(words[:4])
    return short[:48]


def _day_context(target_role: str, day_plan: DayPlan) -> dict:
    return {
        "target_role": target_role,
        "day_title": day_plan.title,
        "reading_content": day_plan.reading.content[:4000],
        "reading_duration_min": day_plan.reading.duration_min,
        "rubric": day_plan.voice_session.rubric,
        "planned_prompt_themes": day_plan.voice_session.prompts,
    }


def _call_tool(client: anthropic.Anthropic, *, system: str, tool: dict, tool_name: str, user_content: str) -> dict:
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user_content}],
    )
    try:
        return extract_tool_input(message, tool_name)
    except ValueError:
        block = message.content[0]
        if block.type != "text":
            raise ValueError("Unexpected response type from Claude") from None
        try:
            return parse_json_text(block.text)
        except json.JSONDecodeError as e:
            return repair_json_with_claude(client, block.text, str(e))


def generate_opening_question(*, target_role: str, day_plan: DayPlan) -> GeneratedQuestion:
    if not settings.anthropic_configured:
        raise RuntimeError("Anthropic is not configured. Set ANTHROPIC_API_KEY in .env")

    payload = {
        **_day_context(target_role, day_plan),
        "instruction": (
            "Create an opening question from the day context. "
            "Use planned_prompt_themes as inspiration only — write a fresh question."
        ),
    }

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    data = _call_tool(
        client,
        system=OPENING_SYSTEM,
        tool=OPENING_TOOL,
        tool_name="propose_opening_question",
        user_content=json.dumps(payload, indent=2),
    )

    question = (data.get("question") or "").strip()
    if not question:
        raise ValueError("Could not generate opening question")
    return GeneratedQuestion(
        question=question,
        focus=_clamp_focus(data.get("focus", "opening")),
        source="context",
    )


def generate_next_question(
    *,
    target_role: str,
    day_plan: DayPlan,
    turns: list[SessionTurn],
    last_evaluation: EvaluationResult,
    turns_completed: int,
    max_turns: int,
) -> NextQuestionResult:
    if not settings.anthropic_configured:
        raise RuntimeError("Anthropic is not configured. Set ANTHROPIC_API_KEY in .env")

    if turns_completed >= max_turns:
        return NextQuestionResult(should_continue=False, next_question="", focus="session complete")

    history = [
        {
            "question": t.prompt,
            "question_source": t.prompt_source,
            "answer": t.answer[:2000],
            "score": t.evaluation.score,
            "feedback": t.evaluation.feedback,
            "improvements": t.evaluation.improvements,
        }
        for t in turns
    ]

    payload = {
        **_day_context(target_role, day_plan),
        "turns_completed": turns_completed,
        "max_turns": max_turns,
        "last_score": last_evaluation.score,
        "last_feedback": last_evaluation.feedback,
        "last_improvements": last_evaluation.improvements,
        "last_answer": turns[-1].answer[:2000] if turns else "",
        "conversation": history,
        "instruction": (
            "Generate the next question using BOTH the day context and the candidate's last answer. "
            "Address specific gaps from last_improvements. Do not reuse planned_prompt_themes verbatim."
        ),
    }

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    data = _call_tool(
        client,
        system=FOLLOWUP_SYSTEM,
        tool=NEXT_QUESTION_TOOL,
        tool_name="propose_next_question",
        user_content=json.dumps(payload, indent=2),
    )

    data["focus"] = _clamp_focus(data.get("focus", ""))
    result = NextQuestionResult.model_validate(data)
    if result.should_continue and not result.next_question.strip():
        result = NextQuestionResult(should_continue=False, next_question="", focus=result.focus)
    return result
