from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

SttProvider = Literal["deepgram", "openai", "browser"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    stt_provider: SttProvider = "deepgram"
    deepgram_api_key: str = ""
    openai_api_key: str = ""
    supabase_url: str = ""
    supabase_service_key: str = ""
    plan_days_default: int = 7
    session_max_turns: int = 4
    upload_dir: Path = Path("uploads")

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def stt_configured(self) -> bool:
        if self.stt_provider == "browser":
            return False
        if self.stt_provider == "deepgram":
            return bool(self.deepgram_api_key)
        return bool(self.openai_api_key)

    @property
    def stt_provider_label(self) -> str:
        if self.stt_provider == "browser":
            return "browser"
        if self.stt_configured:
            return self.stt_provider
        return "none"


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
