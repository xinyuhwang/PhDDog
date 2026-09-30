from typing import Protocol

from app.llm.schemas import (
    CandidateOut,
    ConnectionOut,
    EmailOut,
    ExtractedProfile,
    HomepageVerification,
    PageText,
    PaperSummary,
    ParsedEntry,
    SchoolInfo,
    ScreenOutput,
    StructuredProfile,
)


class LLM(Protocol):
    """Every task the app asks of a language model. See docs/DESIGN.md §7."""

    name: str

    def parse_professor_input(self, text: str, known_aliases: dict[str, str]) -> list[ParsedEntry]:
        """known_aliases maps lowercase alias -> canonical school name."""
        ...

    def normalize_school(self, raw: str) -> SchoolInfo: ...

    def find_homepage(
        self, name: str, school: str, domain: str | None, department: str | None
    ) -> list[CandidateOut]: ...

    def verify_homepage(
        self, page: PageText, name: str, school: str, aliases: list[str], domain: str | None
    ) -> HomepageVerification: ...

    def extract_profile(self, pages: list[PageText], name: str, school_domain: str | None) -> ExtractedProfile: ...

    def structure_resume(self, resume_text: str, research_statement: str | None) -> StructuredProfile: ...

    def screen_professor(
        self, profile: StructuredProfile, keywords: list[str], research_statement: str | None,
        professor_interests: str,
    ) -> ScreenOutput: ...

    def summarize_paper(self, title: str | None, text: str) -> PaperSummary: ...

    def find_connections(
        self, papers: list[tuple[str, str, PaperSummary]], profile: StructuredProfile, resume_text: str
    ) -> list[tuple[int, ConnectionOut]]:
        """papers: (title, full_text, summary). Returns (paper_index, connection)."""
        ...

    def draft_email(
        self, professor_name: str, professor_title: str | None, school: str,
        connections: list[tuple[str, ConnectionOut]], profile: StructuredProfile,
        user_name: str, tone: str, ask: str,
    ) -> EmailOut:
        """connections: (paper_title, connection)."""
        ...
