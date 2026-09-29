"""Claude provider (docs/DESIGN.md §7). Not implemented yet.

The fake provider covers every task offline; the Claude implementation will
fill in the same methods using `anthropic` with `messages.parse()` and the
schemas in app.llm.schemas.
"""

from app.config import Settings


class ClaudeLLM:
    name = "claude"

    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise RuntimeError("LLM_PROVIDER=claude requires ANTHROPIC_API_KEY. Use LLM_PROVIDER=fake to run offline.")
        self.model = settings.claude_model

    def __getattr__(self, task: str):
        raise NotImplementedError(
            f"Claude provider task '{task}' is not implemented yet. Set LLM_PROVIDER=fake to run offline."
        )
