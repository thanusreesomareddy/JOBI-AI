import json

import anthropic

from app.config import settings
from app.models.resume import ParsedResume

SYSTEM_PROMPT = """You analyze resumes for a career coaching app.
Return ONLY valid JSON matching this schema (no markdown):
{
  "target_role": "string — best job role to prepare for",
  "seniority": "intern|junior|mid|senior|lead|executive|unknown",
  "skills": ["string", ...],
  "gaps": ["string — skills or areas to improve for that role"],
  "summary": "string — one short paragraph"
}
Infer target_role from experience and skills. Be specific (e.g. "Backend Engineer" not "Engineer")."""


def analyze_resume(raw_text: str) -> ParsedResume:
    if not settings.anthropic_configured:
        raise RuntimeError("Anthropic is not configured. Set ANTHROPIC_API_KEY in .env")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Resume text:\n\n{raw_text[:120_000]}",
            }
        ],
    )

    block = message.content[0]
    if block.type != "text":
        raise ValueError("Unexpected response type from Claude")

    text = block.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

    data = json.loads(text)
    return ParsedResume.model_validate(data)
