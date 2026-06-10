from pydantic import BaseModel, Field, model_validator


class ReadingModule(BaseModel):
    content: str
    duration_min: int = Field(ge=1, le=120, default=10)


class VoiceSession(BaseModel):
    prompts: list[str] = Field(min_length=1, max_length=10)
    rubric: str = Field(..., description="How answers will be evaluated")


class DayPlan(BaseModel):
    day: int = Field(ge=1)
    title: str
    reading: ReadingModule
    voice_session: VoiceSession
    personalized: bool = False
    adapted_from_day: int | None = Field(default=None, ge=1)


class TrainingPlan(BaseModel):
    target_role: str
    days: int = Field(ge=1, le=30)
    schedule: list[DayPlan]

    @model_validator(mode="after")
    def schedule_matches_days(self) -> "TrainingPlan":
        if len(self.schedule) != self.days:
            raise ValueError(f"schedule must have {self.days} days, got {len(self.schedule)}")
        return self
