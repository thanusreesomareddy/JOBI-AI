import json

import anthropic

from app.config import settings
from app.models.session import EvaluationResult
from app.services.llm_json import extract_tool_input, parse_json_text, repair_json_with_claude

SYSTEM_PROMPT = """You are an interview coach evaluating a candidate's spoken-style answer.
Use the submit_evaluation tool to return your assessment.

Rules:
- Set addresses_question=true only if the answer substantively responds to the interview question
- Set addresses_question=false for greetings, filler, small talk, off-topic replies, meta requests (e.g. "repeat the question"), or answers unrelated to the question
- When addresses_question=false, score 0-2 and keep feedback to one sentence explaining they need to answer the question
- When addresses_question=true, score 0-10 against the rubric only
- feedback: plain text only, no emojis; 2-4 sentences when relevant, direct and actionable
- strengths: 1-3 specific things done well (empty if not relevant)
- improvements: 1-3 concrete things to fix next time
- Be fair; do not invent facts about the candidate"""

EVALUATION_TOOL = {
    "name": "submit_evaluation",
    "description": "Submit structured interview answer evaluation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 10},
            "feedback": {"type": "string"},
            "strengths": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "improvements": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "addresses_question": {
                "type": "boolean",
                "description": "True only if the answer substantively addresses the interview question.",
            },
        },
        "required": ["score", "feedback", "strengths", "improvements", "addresses_question"],
    },
}


def evaluate_answer(
    *,
    target_role: str,
    day_title: str,
    prompt: str,
    rubric: str,
    answer: str,
) -> EvaluationResult:
    if not settings.anthropic_configured:
        raise RuntimeError("Anthropic is not configured. Set ANTHROPIC_API_KEY in .env")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_payload = {
        "target_role": target_role,
        "day_title": day_title,
        "question": prompt,
        "rubric": rubric,
        "answer": answer,
    }

    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        tools=[EVALUATION_TOOL],
        tool_choice={"type": "tool", "name": "submit_evaluation"},
        messages=[
            {
                "role": "user",
                "content": f"Evaluate this answer:\n\n{json.dumps(user_payload, indent=2)}",
            }
        ],
    )

    try:
        data = extract_tool_input(message, "submit_evaluation")
    except ValueError:
        block = message.content[0]
        if block.type != "text":
            raise ValueError("Unexpected response type from Claude") from None
        try:
            data = parse_json_text(block.text)
        except json.JSONDecodeError as e:
            data = repair_json_with_claude(client, block.text, str(e))

    return EvaluationResult.model_validate(data)


QUICK_SYSTEM_PROMPT = """You are an interview coach giving brief feedback on one spoken reply during a live mock interview.
Use the submit_evaluation tool.

Rules:
- Set addresses_question=true only if this reply substantively addresses the current interview question
- Set addresses_question=false for greetings, filler ("um", "okay"), small talk, off-topic content, or replies that do not engage with the question
- When addresses_question=false, score 0-2; feedback one sentence max; strengths and improvements empty
- When addresses_question=true, score 0-10 against the rubric for this single reply only
- feedback: plain text only, no emojis; 1-2 sentences when relevant
- strengths: 0-2 specific things done well in this reply
- improvements: 0-2 concrete fixes for this reply
- Be fair; do not invent facts about the candidate"""


def evaluate_answer_quick(
    *,
    target_role: str,
    day_title: str,
    prompt: str,
    rubric: str,
    answer: str,
) -> EvaluationResult:
    if not settings.anthropic_configured:
        raise RuntimeError("Anthropic is not configured. Set ANTHROPIC_API_KEY in .env")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_payload = {
        "target_role": target_role,
        "day_title": day_title,
        "question": prompt,
        "rubric": rubric,
        "candidate_reply": answer,
        "note": "Evaluate only this single reply, not prior messages in the conversation.",
    }

    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=768,
        system=QUICK_SYSTEM_PROMPT,
        tools=[EVALUATION_TOOL],
        tool_choice={"type": "tool", "name": "submit_evaluation"},
        messages=[
            {
                "role": "user",
                "content": f"Quick feedback on this reply:\n\n{json.dumps(user_payload, indent=2)}",
            }
        ],
    )

    try:
        data = extract_tool_input(message, "submit_evaluation")
    except ValueError:
        block = message.content[0]
        if block.type != "text":
            raise ValueError("Unexpected response type from Claude") from None
        try:
            data = parse_json_text(block.text)
        except json.JSONDecodeError as e:
            data = repair_json_with_claude(client, block.text, str(e))

    return EvaluationResult.model_validate(data)


def answer_feedback_for_client(
    evaluation: EvaluationResult | None, *, label: str
) -> tuple[EvaluationResult | None, str, bool]:
    """Return sidebar feedback only when the answer addresses the question."""
    if evaluation is None:
        return None, "", False
    if evaluation.addresses_question:
        return evaluation, label, False
    return None, "", True
