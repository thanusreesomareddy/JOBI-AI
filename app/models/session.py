from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.models.plan import ReadingModule


class SessionStatus(str, Enum):
    in_progress = "in_progress"
    completed = "completed"


class EvaluationResult(BaseModel):
    score: int = Field(ge=0, le=10)
    feedback: str
    strengths: list[str] = Field(default_factory=list, max_length=5)
    improvements: list[str] = Field(default_factory=list, max_length=5)
    addresses_question: bool = True


class GeneratedQuestion(BaseModel):
    question: str
    focus: str = Field(default="", max_length=48)
    source: Literal["context", "adaptive"] = "context"


class SessionTurn(BaseModel):
    prompt_index: int
    prompt: str
    answer: str
    evaluation: EvaluationResult
    prompt_source: Literal["context", "adaptive", "planned"] = "context"


class NextQuestionResult(BaseModel):
    should_continue: bool
    next_question: str = ""
    focus: str = Field(default="", max_length=48)


class SessionSummary(BaseModel):
    average_score: float = Field(ge=0, le=10)
    headline: str
    strengths: list[str] = Field(default_factory=list, max_length=5)
    areas_to_improve: list[str] = Field(default_factory=list, max_length=5)
    recommendation: str


class PlanAdaptationInfo(BaseModel):
    adapted: bool = True
    reason: str = ""
    updated_days: list[int] = Field(default_factory=list)


class InterviewExchange(BaseModel):
    role: Literal["coach", "candidate"]
    text: str


class StartSessionRequest(BaseModel):
    candidate_id: str
    day: int = Field(ge=1, le=30)
    adapt_plan: bool = True


InterviewPhase = Literal["lobby", "greeting", "interview"]


class StartSessionResponse(BaseModel):
    session_id: str
    candidate_id: str
    plan_id: str
    day: int
    title: str
    reading: ReadingModule
    current_prompt: str
    prompt_index: int
    total_prompts: int
    status: SessionStatus
    session_mode: Literal["standard", "interview"] = "interview"
    interview_phase: InterviewPhase = "lobby"
    interview_log: list[InterviewExchange] = Field(default_factory=list)


class InterviewBeginResponse(BaseModel):
    session_id: str
    session_status: SessionStatus
    interview_phase: InterviewPhase
    coach_messages: list[str] = Field(default_factory=list)
    conversation: list[InterviewExchange] = Field(default_factory=list)
    topic_preview: str = ""
    total_rounds: int = 1


class InterviewTurnRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    interviewer_name: str = Field(default="Alex", max_length=48)


class InterviewTurnResponse(BaseModel):
    session_id: str
    session_status: SessionStatus
    interview_phase: InterviewPhase = "interview"
    coach_messages: list[str] = Field(default_factory=list)
    action: Literal["probe", "advance", "begin_interview"] = "probe"
    conversation: list[InterviewExchange] = Field(default_factory=list)
    round_index: int = 0
    total_rounds: int = 1
    evaluation: EvaluationResult | None = None
    answer_feedback: EvaluationResult | None = None
    feedback_label: str = ""
    feedback_skipped: bool = False
    session_summary: SessionSummary | None = None
    plan_adaptation: PlanAdaptationInfo | None = None
    turns: list[SessionTurn] | None = None


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=20_000)


class AnswerResponse(BaseModel):
    session_id: str
    session_status: SessionStatus
    prompt_index: int
    evaluation: EvaluationResult
    next_prompt: str | None = None
    next_focus: str | None = None
    total_prompts: int
    transcript: str | None = None
    session_summary: SessionSummary | None = None
    plan_adaptation: PlanAdaptationInfo | None = None
