"""OllamaLLM plumbing with the model call stubbed (no Ollama needed)."""

import httpx

from app.config import Settings
from app.llm.ollama import OllamaLLM
from app.llm.schemas import PageText

PAGES = [
    PageText(url="https://x.edu/~jd/", text="Jane Doe. Contact: jd@x.edu. I study clinical NLP."),
    PageText(url="https://x.edu/~jd/join", text="I am recruiting PhD students for Fall 2027.", kind="subpage"),
]


def make(monkeypatch, response):
    llm = OllamaLLM(Settings(llm_provider="ollama"))
    if isinstance(response, Exception):
        def chat(prompt, schema):
            raise response
    else:
        def chat(prompt, schema):
            return response
    monkeypatch.setattr(llm, "_chat", chat)
    return llm


def test_maps_page_numbers_and_keeps_rule_based_email(monkeypatch):
    llm = make(monkeypatch, {
        "title": "Assistant Professor", "departments": [], "stated_interests": "Clinical NLP.",
        "claims": [
            {"kind": "recruiting", "claim": "explicitly_recruiting", "cycle": "Fall 2027",
             "quote": "I am recruiting PhD students for Fall 2027.", "page": 2},
            {"kind": "recruiting", "claim": "do_not_email", "cycle": None, "quote": "x", "page": 1},  # kind mismatch
            {"kind": "contact_policy", "claim": "welcomes_email", "cycle": None, "quote": "y", "page": 9},  # no such page
        ],
    })
    x = llm.extract_profile(PAGES, "Jane Doe", "x.edu")
    assert x.stated_interests == "Clinical NLP." and x.email == "jd@x.edu"
    assert [(c.claim, c.source_url) for c in x.claims] == [("explicitly_recruiting", "https://x.edu/~jd/join")]


def test_falls_back_to_rules_when_ollama_is_down(monkeypatch):
    llm = make(monkeypatch, httpx.ConnectError("refused"))
    x = llm.extract_profile(PAGES, "Jane Doe", "x.edu")
    assert x.claims and x.claims[0].claim == "explicitly_recruiting"  # found by the rules


def test_empty_or_invented_quotes_are_rejected():
    from app.llm.schemas import Claim, ExtractedProfile
    from app.services.professors import verified_claims

    x = ExtractedProfile(claims=[
        Claim(kind="recruiting", claim="not_recruiting", quote="", source_url=PAGES[0].url),
        Claim(kind="recruiting", claim="not_recruiting", quote="I am not taking students.", source_url=PAGES[0].url),
        Claim(kind="recruiting", claim="explicitly_recruiting", quote="I am recruiting PhD students for Fall 2027.",
              source_url=PAGES[1].url),
    ])
    assert [c.claim for c in verified_claims(x, PAGES)] == ["explicitly_recruiting"]
