"""Local model via Ollama for profile extraction (docs/DESIGN.md §7).

Only `extract_profile` uses the model; every other task falls back to the offline rules until it
has been evaluated. Rules still handle what they do reliably (emails, publication lists), and
every quote the model returns is checked against the page text by the caller.
"""

import json
import logging
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.llm.fake import FakeLLM
from app.llm.schemas import Claim, ExtractedProfile, PageText

log = logging.getLogger(__name__)

PAGE_CHARS = 6000  # per page sent to the model
TOTAL_CHARS = 24000  # ~6K tokens, well within num_ctx below
NUM_CTX = 12288
# Small models can loop inside a JSON list; the answer never needs more than this.
NUM_PREDICT = 1500


class _ModelClaim(BaseModel):
    kind: Literal["recruiting", "contact_policy"]
    claim: Literal[
        "explicitly_recruiting", "recruits_generally", "not_recruiting",
        "welcomes_email", "apply_via_program", "do_not_email",
    ]
    cycle: str | None = Field(None, description='Admission cycle named in the quote, e.g. "Fall 2026", else null')
    quote: str = Field(description="The sentence copied exactly from the page")
    page: int = Field(description="Number of the PAGE the quote is from")


class _ModelProfile(BaseModel):
    title: str | None = Field(None, description='Academic title, e.g. "Assistant Professor"')
    departments: list[str] = []
    stated_interests: str | None = Field(None, description="The professor's research interests, 1-3 sentences or a list")
    claims: list[_ModelClaim] = []


SYSTEM = """You extract facts about one professor from the text of their web pages.
Rules:
- Use only the pages given. Do not guess. Leave a field null or a list empty if the pages don't say.
- stated_interests: what THIS professor researches, from their own description or a "Research interests" list. Not awards, not news, not paper titles.
- claims: every sentence that says whether they are taking students, or how prospective students should contact them.
  - kind "recruiting": explicitly_recruiting (e.g. "I am looking for PhD students for Fall 2026"), recruits_generally ("every year I look for students"), not_recruiting ("I am not taking students").
  - kind "contact_policy": do_not_email ("I cannot respond to emails from prospective students"), apply_via_program ("apply to the PhD program and mention me"), welcomes_email ("feel free to email me").
  - quote must be copied word for word from the page. page is the PAGE number it came from.
  - Sentences about the department, admissions office, jobs, or other people are NOT claims."""


class OllamaLLM(FakeLLM):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.url = settings.ollama_url.rstrip("/")
        self.model = settings.ollama_model
        self.name = f"ollama:{self.model}"

    def _chat(self, prompt: str, schema: dict) -> dict:
        r = httpx.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model, "stream": False, "format": schema,
                "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            },
            timeout=300,
        )
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])

    def extract_profile(self, pages: list[PageText], name: str, school_domain: str | None) -> ExtractedProfile:
        base = super().extract_profile(pages, name, school_domain)  # emails, publications, fallbacks
        blocks, used = [], 0
        for i, p in enumerate(pages, 1):
            text = p.text[: min(PAGE_CHARS, TOTAL_CHARS - used)]
            if not text:
                break
            used += len(text)
            blocks.append(f"=== PAGE {i}: {p.url} ===\n{text}")
        prompt = f"Professor: {name}\n\n" + "\n\n".join(blocks)

        try:
            out = _ModelProfile.model_validate(self._chat(prompt, _ModelProfile.model_json_schema()))
        except (httpx.HTTPError, ValidationError, json.JSONDecodeError, KeyError) as e:
            log.warning("ollama extraction failed for %s, using rules: %s", name, e)
            return base

        base.title = out.title or base.title
        base.departments = out.departments or base.departments
        if out.stated_interests:
            base.stated_interests = out.stated_interests
            base.field_sources["stated_interests"] = pages[0].url if pages else ""
        base.claims = [
            Claim(kind=c.kind, claim=c.claim, cycle=c.cycle, quote=c.quote.strip(), source_url=pages[c.page - 1].url)
            for c in out.claims
            if 1 <= c.page <= len(pages) and _kind_matches(c)
        ]
        return base


def _kind_matches(c: _ModelClaim) -> bool:
    recruiting = c.claim in ("explicitly_recruiting", "recruits_generally", "not_recruiting")
    return recruiting == (c.kind == "recruiting")
