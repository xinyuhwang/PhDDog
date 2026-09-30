from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://phddog:phddog@localhost:5432/phddog"
    data_dir: Path = Path("../data")

    # "fake" runs fully offline with rule-based stand-ins; "claude" uses the Claude API.
    llm_provider: str = "fake"
    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-5-5"
    # LLM_PROVIDER=ollama: a local model for profile extraction; other tasks use the offline rules.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Sent in the User-Agent and to Unpaywall (which requires an email).
    contact_email: str = "phddog@example.com"

    target_cycle: str = "Fall 2027"
    # Papers older than (current year - window + 1) get a warning, not a filter.
    paper_year_window: int = 2

    fetch_cache_days: int = 7
    # A professor's site check older than this is flagged in the UI as needing a re-check.
    recheck_after_days: int = 60
    max_subpages: int = 8
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
