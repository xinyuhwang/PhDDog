from functools import lru_cache

from app.config import get_settings
from app.llm.base import LLM


@lru_cache
def get_llm() -> LLM:
    settings = get_settings()
    if settings.llm_provider == "claude":
        from app.llm.claude import ClaudeLLM

        return ClaudeLLM(settings)
    from app.llm.fake import FakeLLM

    return FakeLLM()
