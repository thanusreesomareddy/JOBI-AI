from enum import Enum

from pydantic import BaseModel, Field


class Seniority(str, Enum):
    intern = "intern"
    junior = "junior"
    mid = "mid"
    senior = "senior"
    lead = "lead"
    executive = "executive"
    unknown = "unknown"


class ParsedResume(BaseModel):
    """Structured output from resume analysis (LLM)."""

    target_role: str = Field(..., description="Best-fit job role to train for")
    seniority: Seniority = Seniority.unknown
    skills: list[str] = Field(default_factory=list, max_length=30)
    gaps: list[str] = Field(default_factory=list, max_length=15)
    summary: str = Field("", description="One-paragraph candidate summary")
