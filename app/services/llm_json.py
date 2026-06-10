import json
from typing import Any

import anthropic

from app.config import settings


def strip_markdown_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


def parse_json_text(text: str) -> Any:
    return json.loads(strip_markdown_fence(text))


def extract_tool_input(message: anthropic.types.Message, tool_name: str) -> dict[str, Any]:
    for block in message.content:
        if block.type == "tool_use" and block.name == tool_name:
            if isinstance(block.input, dict):
                return block.input
            raise ValueError(f"Tool {tool_name} returned non-object input")
    raise ValueError(f"No tool_use block named {tool_name} in Claude response")


def repair_json_with_claude(client: anthropic.Anthropic, broken: str, error: str) -> Any:
    repair = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=16384,
        system="Fix the JSON so it is valid. Return ONLY the corrected JSON, no markdown or commentary.",
        messages=[
            {
                "role": "user",
                "content": f"JSON parse error: {error}\n\nBroken JSON:\n{broken[:100_000]}",
            }
        ],
    )
    block = repair.content[0]
    if block.type != "text":
        raise ValueError("Unexpected repair response type from Claude")
    return parse_json_text(block.text)
