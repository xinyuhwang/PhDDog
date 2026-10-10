"""Offline, rule-based stand-in for Claude.

Deterministic, free and needs no API key. Output quality is intentionally
basic (keyword matching and templates); anything generated rather than quoted
is marked [FAKE] so it is never mistaken for real analysis.
"""

import json
import re
from pathlib import Path

from app.llm.schemas import (
    CandidateOut,
    ConnectionOut,
    EmailOut,
    Claim,
    ExtractedProfile,
    HomepageVerification,
    PageText,
    PaperSummary,
    ParsedEntry,
    PubRef,
    ResumeItem,
    SchoolInfo,
    ScreenOutput,
    StructuredProfile,
)
from app.schools_catalog import KNOWN_SCHOOLS

# --- vocabulary --------------------------------------------------------------

METHOD_TERMS = [
    "machine learning", "deep learning", "reinforcement learning", "transformer", "large language model",
    "language model", "llm", "natural language processing", "nlp", "computer vision", "generative model",
    "generative ai", "diffusion model", "graph neural network", "bayesian optimization", "causal inference",
    "federated learning", "self-supervised learning", "contrastive learning", "foundation model",
    "interpretability", "explainable ai", "explainability", "uncertainty quantification", "time series",
    "survival analysis", "segmentation", "multimodal", "retrieval-augmented generation", "active learning",
    "transfer learning", "representation learning", "probabilistic", "gaussian process",
    "variational autoencoder", "protein language model", "knowledge graph", "agentic ai", "ai agents",
    "robustness", "fairness", "differential privacy", "privacy", "signal processing", "wireless sensing",
    "optimization", "statistical learning", "neural network",
]
DOMAIN_TERMS = [
    "healthcare", "health", "medicine", "medical", "clinical", "medical imaging", "radiology", "pathology",
    "genomics", "single-cell", "proteomics", "drug discovery", "protein design", "electronic health records",
    "ehr", "mental health", "public health", "neuroscience", "cardiology", "oncology", "cancer", "wearable",
    "digital health", "mobile health", "biomedical", "bioinformatics", "computational biology",
    "precision medicine", "alzheimer", "diabetes", "ophthalmology", "surgery", "molecule", "molecular",
    "therapeutics", "epidemiology", "biology", "chemistry", "brain", "patient", "hospital", "biotech",
]
MODALITY_TERMS = [
    "mri", "ct", "x-ray", "ecg", "eeg", "clinical notes", "genomic data", "rna-seq", "sensor", "images",
    "imaging", "video", "speech", "social media", "text", "protein sequences", "molecular graphs",
]

# Terms so common in CS/health research that sharing them says little about fit.
GENERIC_TERMS = {
    "machine learning", "deep learning", "neural network", "optimization", "probabilistic", "statistical learning",
    "ai agents", "health", "medical", "biology", "chemistry", "text", "images", "imaging", "sensor", "patient",
}
# Different words for the same field: a match within a family counts as a related (partial) match.
TERM_FAMILIES = {
    "health & medicine": {
        "healthcare", "health", "medicine", "medical", "clinical", "patient", "hospital", "biomedical",
        "electronic health records", "ehr", "surgery", "digital health", "mobile health", "public health",
        "mental health", "precision medicine", "epidemiology", "cardiology", "oncology", "cancer", "ophthalmology",
    },
    "biology & drug discovery": {
        "genomics", "single-cell", "proteomics", "computational biology", "bioinformatics", "molecule", "molecular",
        "protein design", "drug discovery", "therapeutics", "biology", "biotech", "protein language model",
    },
    "medical imaging": {"medical imaging", "radiology", "pathology", "mri", "ct", "x-ray", "segmentation", "imaging"},
    "language & LLMs": {
        "nlp", "natural language processing", "llm", "large language model", "language model", "transformer",
        "clinical notes", "retrieval-augmented generation",
    },
}

SYNONYMS = {
    "electronic health records": "ehr", "natural language processing": "nlp", "large language model": "llm",
    "language model": "llm", "explainability": "explainable ai", "medicine": "medical",
}


def _canonical(terms: set[str]) -> set[str]:
    return {SYNONYMS.get(t, t) for t in terms}


_TERM_RE = {t: re.compile(rf"\b{re.escape(t)}s?\b", re.IGNORECASE) for t in {*METHOD_TERMS, *DOMAIN_TERMS, *MODALITY_TERMS}}


def find_terms(text: str, vocab: list[str]) -> list[str]:
    return [t for t in vocab if _TERM_RE[t].search(text or "")]


# --- text helpers --------------------------------------------------------------

URL_RE = re.compile(r"https?://[^\s,;)]+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
OBFUSCATED_EMAIL_RE = re.compile(
    r"([\w.+-]+)\s*(?:\[at\]|\(at\)|\sat\s)\s*([\w-]+(?:\s*(?:\[dot\]|\(dot\)|\sdot\s|\.)\s*[\w-]+)+)", re.IGNORECASE
)
CYCLE_RE = re.compile(r"\b(Fall|Spring|Autumn|Winter|Summer)\s+(20\d{2})\b", re.IGNORECASE)


def _blocks(text: str) -> list[str]:
    """Headings, list items and short labels stay separate; wrapped lines of one paragraph are joined."""
    blocks: list[str] = []
    current = ""
    for raw in (text or "").splitlines():
        line = raw.strip()
        standalone = line.startswith(("## ", "- ")) or (
            len(line) < 60 and not current and not re.search(r"[.!?,;:]$", line)
        )
        if not line or standalone:
            if current:
                blocks.append(current)
            current = ""
            if line:
                blocks.append(re.sub(r"^(##|-)\s+", "", line))
            continue
        current = f"{current} {line}" if current else line
    if current:
        blocks.append(current)
    return blocks


def sentences(text: str) -> list[str]:
    out = []
    for block in _blocks(text):
        out += [p.strip() for p in re.split(r"(?<=[.!?])\s+", block) if len(p.strip()) > 3]
    return out


def first_sentence_with(text: str, pattern: re.Pattern, min_len: int = 0) -> str | None:
    for s in sentences(text):
        if len(s) >= min_len and pattern.search(s):
            return s
    return None


class FakeLLM:
    name = "fake"

    def __init__(self) -> None:
        path = Path(__file__).with_name("fake_homepages.json")
        self._homepages = {k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("_")}

    # --- Stage 1: parse ---------------------------------------------------------

    def parse_professor_input(self, text: str, known_aliases: dict[str, str]) -> list[ParsedEntry]:
        aliases = sorted(known_aliases, key=len, reverse=True)  # longest match first
        current_school: str | None = None
        entries: list[ParsedEntry] = []

        for line in text.splitlines():
            for chunk in line.split(";"):
                chunk = chunk.strip()
                if not chunk:
                    continue
                header = re.fullmatch(r"(.+?):", chunk)
                if header and not URL_RE.search(chunk):
                    current_school = header.group(1).strip()
                    continue
                entries.append(self._parse_chunk(chunk, aliases, current_school))
        return entries

    def _parse_chunk(self, chunk: str, aliases: list[str], current_school: str | None) -> ParsedEntry:
        entry = ParsedEntry(raw=chunk)
        url_match = URL_RE.search(chunk)
        if url_match:
            entry.url = url_match.group(0).rstrip(".")
            chunk = (chunk[: url_match.start()] + chunk[url_match.end():]).strip()

        parts = [p.strip() for p in re.split(r"\s*[,()|/]\s*|\s+[-–—]\s+", chunk) if p and p.strip()]
        name, school, dept_parts = None, None, []

        if len(parts) >= 2:
            name = parts[0]
            for part in parts[1:]:
                if school is None:
                    found, rest = _split_school(part, aliases)
                    if found:
                        school = found
                        if rest:
                            dept_parts.append(rest)
                        continue
                dept_parts.append(part)
            if school is None and dept_parts and _looks_like_school(dept_parts[0]):
                school = dept_parts.pop(0)
        elif parts:
            found, before, after = _find_alias_inline(parts[0], aliases)
            if found:
                name, school = before, found
                if after:
                    dept_parts.append(after)
            else:
                name = parts[0]

        if school is None and current_school:
            school = current_school
        entry.name = name.strip() if name else None
        entry.school_raw = school
        entry.department_raw = ", ".join(dept_parts) or None

        if not entry.name or not re.fullmatch(r"[A-Za-zÀ-ÿ.'\- ]{3,80}", entry.name) or not (
            1 <= len(entry.name.split()) <= 5
        ) or len(entry.name.split()) < 2:
            entry.issues.append("unclear_name")
        if not entry.school_raw:
            entry.issues.append("missing_school")
        return entry

    def normalize_school(self, raw: str) -> SchoolInfo:
        key = raw.strip().lower()
        for name, info in KNOWN_SCHOOLS.items():
            if key == name.lower() or key in (a.lower() for a in info["aliases"]):
                return SchoolInfo(name=name, aliases=info["aliases"], primary_domain=info["domain"], known=True)
        return SchoolInfo(name=raw.strip(), aliases=[], primary_domain=None, known=False)

    # --- Stage 1: homepage --------------------------------------------------------

    def find_homepage(self, name: str, school: str, domain: str | None, department: str | None) -> list[CandidateOut]:
        url = self._homepages.get(f"{_norm(name)}|{domain}")
        if url:
            return [CandidateOut(url=url, reason="[FAKE] offline fixture (fake_homepages.json)")]
        return []

    def verify_homepage(
        self, page: PageText, name: str, school: str, aliases: list[str], domain: str | None
    ) -> HomepageVerification:
        text = page.text.lower()
        last = name.split()[-1].lower()
        has_name = name.lower() in text or last in text
        school_terms = [school.lower(), *(a.lower() for a in aliases)]
        has_school = bool(domain and domain in page.url) or any(
            re.search(rf"\b{re.escape(t)}\b", text) for t in school_terms if len(t) > 2
        )
        if has_name and has_school:
            return HomepageVerification(is_match=True, confidence=0.9, reason="Name and school both appear on the page")
        if has_name:
            return HomepageVerification(is_match=True, confidence=0.55, reason="Name appears, but school not confirmed")
        return HomepageVerification(is_match=False, confidence=0.1, reason="Name not found on the page")

    # --- Stage 1: extract ---------------------------------------------------------

    def extract_profile(self, pages: list[PageText], name: str, school_domain: str | None) -> ExtractedProfile:
        out = ExtractedProfile()
        home = pages[0] if pages else PageText(url="", text="")

        emails: list[tuple[str, str]] = []
        for p in pages:
            emails += [(e, p.url) for e in EMAIL_RE.findall(p.text)]
            for user, host in OBFUSCATED_EMAIL_RE.findall(p.text):
                host = re.sub(r"\s*(?:\[dot\]|\(dot\)|\sdot\s|\.)\s*", ".", host)
                emails.append((f"{user}@{host}", p.url))
        if emails:
            preferred = [e for e in emails if school_domain and e[0].lower().endswith(school_domain)]
            out.email, out.field_sources["email"] = (preferred or emails)[0]

        title_re = re.compile(
            r"\b((?:(?:Research|Adjunct|Practice|Term|Presidential|Distinguished)\s+)*"
            r"(?:Assistant|Associate|Full)?\s*Professor(?:\s+(?:of|in)\s+[A-Z][\w&]*(?:\s+(?:and\s+|&\s+)?[A-Z][\w&]*){0,4})?)"
        )
        for p in pages:
            m = title_re.search(p.text)
            if m:
                out.title, out.field_sources["title"] = m.group(1).strip(), p.url
                break

        dept_re = re.compile(r"Department of ((?:[A-Z][\w&]*)(?:\s+(?:and|of|&)?\s*[A-Z][\w&]*){0,5})")
        depts = []
        for p in pages:
            depts += [d.strip() for d in dept_re.findall(p.text)]
        out.departments = list(dict.fromkeys(depts))[:3]

        interests, source = _pick_interests(pages)
        if interests:
            out.stated_interests, out.field_sources["stated_interests"] = interests, source

        bio = first_sentence_with(home.text, re.compile(rf"{re.escape(name.split()[-1])}\b.*\bis an?\b", re.I), 30)
        if bio:
            out.bio_summary = bio

        self._extract_recruiting(pages, out, name)
        out.recent_publications = _find_publications(pages)
        return out

    def _extract_recruiting(self, pages: list[PageText], out: ExtractedProfile, name: str = "") -> None:
        not_recruiting = re.compile(
            r"\b(?:not|no longer)\s+(?:\w+ly\s+){0,2}(?:recruiting|accepting|taking|looking for|admitting)\b[^.]{0,60}\b(?:students?|ph\.?\s?d)"
            r"|\bno (?:open )?(?:positions|openings)\b|\b(?:openings|positions)\b[^.]{0,40}\b(?:are|have been) filled\b",
            re.I,
        )
        recruiting = re.compile(
            r"\b(looking for|recruiting|recruit|seeking|hiring|hire|accepting|admit|admitting|take on|"
            r"(?:have|has|there are|there is)\s+(?:\w+\s+){0,3}(?:open positions?|openings?))\b"
            r"[^.]{0,120}\b(ph\.?\s?d|students?|postdocs?)\b",
            re.I,
        )
        # Recruiting statements about other roles say nothing about PhD openings.
        other_roles = re.compile(
            r"\b(post-?docs?|postdoctoral|undergrad\w*|master['’]?s|ms students|interns?|staff|engineers?|collaborat\w*|"
            r"visiting\s+(?:\w+\s+)?(?:students?|scholars?|researchers?))\b", re.I
        )
        phd_re = re.compile(r"\b(ph\.?\s?d|doctoral|graduate students?)\b", re.I)
        # "our PhD students" are the lab's current members, not applicants.
        members = re.compile(r"\b(our|current|my|the lab'?s)\s+(ph\.?\s?d\.?\s+students?|doctoral students?|postdocs?)", re.I)

        class _Phd:
            @staticmethod
            def search(text: str):
                return phd_re.search(members.sub("", text))

        phd = _Phd()
        general = re.compile(r"\b(every year|each year|always|frequently|regularly|from time to time)\b", re.I)
        do_not_email = re.compile(
            r"\b(cannot|can't|can not|unable to|won't|will not|do not|don't|not able to|not be able to)\s+(?:\w+\s+){0,3}(respond|reply|answer)\b"
            r"|\b(?:please\s+)?(?:do not|don't)\s+(?:e-?mail|contact)\s+me\b", re.I
        )
        # "me", or the professor's own name ("please list Eric Eaton as a prospective advisor").
        who = "|".join(["me", *(re.escape(n) for n in {name, name.split()[-1]} if n)])
        name_me_as_advisor = re.compile(
            rf"\b(?:mention|list|name|select|indicate|choose|put|call)\s+(?:(?:prof(?:essor)?\.?|dr\.?)\s+)?(?:{who})\b(?:\s+out)?[^.]{{0,80}}\b(application|advisor|adviser|statement)",
            re.I,
        )
        apply_program = re.compile(
            r"\bapply (?:to|through|via|directly to) the\b|\bnot necessary to e-?mail\b", re.I
        )
        welcomes = re.compile(
            r"\b(?:feel free to|please|welcome to|encouraged to)\s+(?:e-?mail|contact|reach out to|write to)\s+(?:me|us|our lab|the lab|dr\.?\s+\w+|prof(?:essor)?\.?\s+\w+)\b"
            r"|\bfeel free to reach out\b|\be-?mail me\b|\breach out to me\b",
            re.I,
        )

        seen: set[tuple[str, str]] = set()
        for p in pages:
            for s in sentences(p.text):
                if len(s) > 600:
                    continue
                cycles = CYCLE_RE.findall(s)
                cycle = None
                if cycles:
                    season, year = max(cycles, key=lambda c: int(c[1]))
                    cycle = f"{season.title()} {year}"

                recruit = None
                # "Openings will be rare" says neither yes nor no.
                hedged = re.search(r"\b(rare|unlikely|few if any)\b|(?<!not )\blimited\b(?!\s+to\b)", s, re.I)
                if hedged or (other_roles.search(s) and not phd.search(s)):
                    pass
                elif not_recruiting.search(s):
                    recruit = "not_recruiting"
                elif recruiting.search(s):
                    recruit = "recruits_generally" if general.search(s) and not cycle else "explicitly_recruiting"
                # "Apply and list me as a potential advisor" invites PhD applications: open to students, undated.
                if recruit is None and name_me_as_advisor.search(s) and not (other_roles.search(s) and not phd.search(s)):
                    recruit = "recruits_generally"
                if recruit and ("recruiting", s) not in seen:
                    seen.add(("recruiting", s))
                    out.claims.append(Claim(kind="recruiting", claim=recruit, cycle=cycle, quote=s, source_url=p.url))

                about_other_roles = bool(other_roles.search(s) and not phd.search(s))
                # "If you plan to apply to the program …, please email me" invites email; applying is the condition.
                conditional_apply = re.search(r"\bif you\b[^.]{0,40}\bapply", s, re.I) and welcomes.search(s)
                for policy, pattern in (
                    ("do_not_email", do_not_email), ("apply_via_program", apply_program),
                    ("apply_via_program", name_me_as_advisor), ("welcomes_email", welcomes),
                ):
                    if conditional_apply and policy == "apply_via_program":
                        continue
                    if not about_other_roles and pattern.search(s):
                        if ("contact_policy", s) not in seen:
                            seen.add(("contact_policy", s))
                            out.claims.append(Claim(kind="contact_policy", claim=policy, quote=s, source_url=p.url))
                        break

    # --- Stage 2 --------------------------------------------------------------------

    def structure_resume(self, resume_text: str, research_statement: str | None) -> StructuredProfile:
        text = f"{resume_text}\n{research_statement or ''}"
        methods = find_terms(text, METHOD_TERMS)
        domains = find_terms(text, DOMAIN_TERMS)
        skills_line = first_sentence_with(resume_text, re.compile(r"^\s*(technical\s+)?skills\b", re.I))
        skills = [s.strip() for s in re.split(r"[,;|•]", skills_line.split(":", 1)[-1])][:20] if skills_line else []
        experiences = []
        for s in sentences(resume_text):
            if 30 <= len(s) <= 400 and find_terms(s, METHOD_TERMS + DOMAIN_TERMS):
                experiences.append(ResumeItem(title=" ".join(s.split()[:8]), description=s))
            if len(experiences) >= 12:
                break
        return StructuredProfile(
            interests=domains[:10] + methods[:10], methods=methods, domains=domains,
            skills=[s for s in skills if s], experiences=experiences,
        )

    def screen_professor(
        self, profile: StructuredProfile, keywords: list[str], research_statement: str | None,
        professor_interests: str,
    ) -> ScreenOutput:
        vocab = METHOD_TERMS + DOMAIN_TERMS + MODALITY_TERMS
        user_text = " ".join(keywords) + " " + (research_statement or "")
        user_terms = _canonical(set(profile.methods) | set(profile.domains) | set(find_terms(user_text, vocab)))
        prof_terms = _canonical(set(find_terms(professor_interests, vocab)))
        # The user's own keywords count even if they aren't in the built-in vocabulary.
        own = {k.lower() for k in keywords if len(k) > 2 and k.lower() in professor_interests.lower()}

        shared = (user_terms & prof_terms) | own
        weight = sum(0.5 if t in GENERIC_TERMS else 2 for t in shared)
        related = [
            name for name, family in TERM_FAMILIES.items()
            if family & prof_terms and family & user_terms and not (family & shared) - GENERIC_TERMS
        ]
        weight += len(related)

        label = "strong" if weight >= 3 else "possible" if weight >= 1.5 else "no"
        parts = []
        if specific := sorted(t for t in shared if t not in GENERIC_TERMS):
            parts.append(f"shared: {', '.join(specific)}")
        if generic := sorted(t for t in shared if t in GENERIC_TERMS):
            parts.append(f"broad overlap: {', '.join(generic)}")
        if related:
            parts.append(f"related fields: {', '.join(related)}")
        reason = "[FAKE] " + ("; ".join(parts).capitalize() if parts else "No shared research terms found")
        return ScreenOutput(label=label, score=round(min(1.0, weight / 6), 2), reason=reason)

    # --- Stage 3 --------------------------------------------------------------------

    def summarize_paper(self, title: str | None, text: str) -> PaperSummary:
        abstract = _abstract(text)
        pick = lambda pat, n=3: [s for s in sentences(text) if 30 <= len(s) <= 500 and re.search(pat, s, re.I)][:n]  # noqa: E731
        return PaperSummary(
            problem=(sentences(abstract)[:1] or [""])[0],
            methods=find_terms(text, METHOD_TERMS),
            data_modalities=find_terms(text, MODALITY_TERMS),
            application_setting=", ".join(find_terms(text, DOMAIN_TERMS)[:5]),
            key_findings=pick(r"\b(we show|results show|outperform|achiev|improv|demonstrat)"),
            limitations=pick(r"\blimitation"),
            future_work=pick(r"\b(future work|future research|in the future|future directions?)\b"),
        )

    def find_connections(
        self, papers: list[tuple[str, str, PaperSummary]], profile: StructuredProfile, resume_text: str
    ) -> list[tuple[int, ConnectionOut]]:
        out: list[tuple[int, ConnectionOut]] = []
        resume_sents = sentences(resume_text)

        def resume_evidence(term: str) -> str | None:
            return next((s for s in resume_sents if _TERM_RE[term].search(s)), None)

        def paper_evidence(text: str, term: str) -> str:
            return next((s for s in sentences(text) if _TERM_RE[term].search(s) and len(s) < 500), term)

        for i, (_title, text, summary) in enumerate(papers):
            for kind, shared in (
                ("method_overlap", sorted(set(summary.methods) & set(profile.methods))),
                ("domain_overlap", sorted(set(find_terms(text, DOMAIN_TERMS)) & set(profile.domains))),
            ):
                for term in shared[:2]:
                    ev = resume_evidence(term)
                    if ev:
                        out.append((i, ConnectionOut(
                            kind=kind, paper_evidence=paper_evidence(text, term), user_evidence=ev,
                            explanation=f"[FAKE] Both the paper and your resume mention '{term}'.",
                        )))
            for fw in summary.future_work:
                terms = [t for t in find_terms(fw, METHOD_TERMS + DOMAIN_TERMS) if resume_evidence(t)]
                if terms:
                    out.append((i, ConnectionOut(
                        kind="future_work_hook", paper_evidence=fw, user_evidence=resume_evidence(terms[0]) or "",
                        explanation=f"[FAKE] Their stated future work mentions '{terms[0]}', which appears in your resume.",
                    )))
                    break
        return out[:8]

    # --- Stage 4 --------------------------------------------------------------------

    def draft_email(
        self, professor_name: str, professor_title: str | None, school: str,
        connections: list[tuple[str, ConnectionOut]], profile: StructuredProfile,
        user_name: str, tone: str, ask: str,
    ) -> EmailOut:
        last = professor_name.split()[-1]
        greeting = f"Dear Professor {last}," if tone == "formal" else f"Hi Professor {last},"
        ask_text = {
            "phd": "whether you expect to take new PhD students for the Fall 2027 cycle",
            "ra": "whether there might be any research assistant opportunities in your group",
        }.get(ask, "whether you expect to take new PhD students for Fall 2027, or have any research assistant opportunities")
        paper_line = ""
        if connections:
            title, c = connections[0]
            paper_line = (
                f'I recently read your paper "{title}". {c.paper_evidence} '
                f"This connects to my own experience: {c.user_evidence}"
            )
        body = "\n\n".join(p for p in [
            greeting,
            f"[FAKE DRAFT — generated offline without Claude]\n\nMy name is {user_name}, and I am applying to PhD programs "
            f"in {', '.join(profile.domains[:3]) or 'health AI'}.",
            paper_line,
            f"I would be grateful to know {ask_text}. I have attached my CV for reference.",
            f"Thank you for your time,\n{user_name}",
        ] if p)
        return EmailOut(subject=f"[FAKE] Prospective PhD student interested in your work at {school}", body=body)


# --- module helpers --------------------------------------------------------------------


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z\s-]", "", name.lower())).strip()


def _split_school(part: str, aliases: list[str]) -> tuple[str | None, str]:
    """'UPenn CIS' -> ('UPenn', 'CIS') if a known alias starts or ends the part."""
    for alias in aliases:
        m = re.match(rf"^({re.escape(alias)})\b\s*(.*)$", part, re.I) or re.match(rf"^(.*?)\s*\b({re.escape(alias)})$", part, re.I)
        if m:
            groups = m.groups()
            if groups[0].lower() == alias:
                return groups[0], groups[1].strip()
            return groups[1], groups[0].strip()
    return None, part


def _find_alias_inline(text: str, aliases: list[str]) -> tuple[str | None, str, str]:
    """'Pranam Chatterjee UPenn Bioengineering' -> ('UPenn', 'Pranam Chatterjee', 'Bioengineering')."""
    for alias in aliases:
        m = re.search(rf"\b{re.escape(alias)}\b", text, re.I)
        if m and m.start() > 0:
            return m.group(0), text[: m.start()].strip(), text[m.end():].strip()
    return None, text, ""


def _looks_like_school(text: str) -> bool:
    return bool(re.search(r"\b(university|institute|college|school of|polytechnic|univ\.?)\b", text, re.I))


INTEREST_HEADING = re.compile(
    r"^(research\s+(interests?|areas?|focus|topics|directions?)|areas?\s+of\s+(interest|expertise|research)|"
    r"interests?|expertise|research\s+expertise|keywords|topics)\s*:?$", re.I,
)
PROSE_HEADING = re.compile(r"^(research|about( me)?|bio(graphy)?|overview|profile|summary|welcome)\s*:?$", re.I)
INTEREST_PHRASE = re.compile(
    r"\b(research interests?|my research|our research|(his|her|their|\w+'s) research|research (focuses|focus|centers|spans|lies|is)|"
    r"interested in|works? on|working on|focus(es)? on|we (study|develop|build)|i (study|develop|build)|lab (studies|develops|focuses))\b",
    re.I,
)
# Stricter than INTEREST_PHRASE: the professor describing their own research.
OWN_RESEARCH = re.compile(
    r"\b(my research|our research|(his|her|their|\w+'s) research|research (focuses|focus|centers|spans|lies|interests)|"
    r"(i|we|he|she|they) (work|study|develop|build|focus)|my (work|group|lab)|our (lab|group))\b",
    re.I,
)
NOT_INTERESTS = re.compile(
    r"\b(award|prize|fellowship|received|joined|graduated|ph\.?\s?d\.? (from|in)|degree|b\.?s\.?|m\.?s\.?|undergrad\w*|"
    r"prospective|course|teaching|office hours|e-?mail|phone|copyright|cookie|previously|postdoc|advised by|news|"
    r"looking for|recruit\w*|join|apply)\b",
    re.I,
)


OTHER_SECTION = re.compile(
    r"^(education|awards?|honors|awards? (&|and) honors|biography|bio|(selected |recent )?publications|teaching|courses|contact|"
    r"news|students|appointments|experience|service|links|videos?|media|in the news|affiliations|projects|people|"
    r"professional experience|positions|office hours|cv)\s*:?$", re.I,
)


def _section(lines: list[str], start: int) -> list[str]:
    """Lines under the heading at `start`, up to the next heading (marked or a known section label)."""
    out = []
    for line in lines[start + 1:]:
        text = re.sub(r"^-\s+", "", line.strip())
        if line.startswith("## ") or OTHER_SECTION.match(text):
            break
        if text:
            out.append(text)
    return out


def _score(sentence: str) -> int:
    score = 4 if INTEREST_PHRASE.search(sentence) else 0
    score += min(5, len(find_terms(sentence, METHOD_TERMS + DOMAIN_TERMS)))
    if NOT_INTERESTS.search(sentence):
        score -= 5
    return score


def _pick_interests(pages: list[PageText]) -> tuple[str | None, str | None]:
    """1) a 'Research interests' section; 2) best research sentences, preferring About/Research sections."""
    for page in pages:
        lines = page.text.splitlines()
        for i, line in enumerate(lines):
            label = re.sub(r"^(##|-)\s+", "", line.strip())
            is_heading = line.startswith("## ") or (len(label) < 40 and not re.search(r"[.!?]$", label))
            if is_heading and INTEREST_HEADING.match(label):
                items = []
                for item in dict.fromkeys(_section(lines, i)):
                    # Prose after a list of short labels (e.g. the bio that follows) ends the section.
                    is_sentence = item.endswith(".") and len(item.split()) > 10
                    if len(item) > 150 or (items and is_sentence):
                        break
                    if item.lower() != label.lower():
                        items.append(item)
                items = items[:12]
                if items:
                    joined = "; ".join(x.rstrip(".;,") for x in items)
                    return f"Research interests: {joined[:500]}.", page.url

    best: list[tuple[int, int, str, str]] = []  # (score, order, sentence, url)
    order = 0
    for rank, page in enumerate(pages):
        lines = page.text.splitlines()
        prose_ranges = [
            (i, i + len(_section(lines, i)) + 1) for i, ln in enumerate(lines)
            if ln.startswith("## ") and PROSE_HEADING.match(ln[3:].strip())
        ]
        for block_line, sentence in _sentences_with_lines(page.text):
            order += 1
            if not 40 <= len(sentence) <= 400:
                continue
            score = _score(sentence)
            if any(a <= block_line <= b for a, b in prose_ranges):
                score += 2
            if rank == 0:
                score += 1
            if score >= 3:
                best.append((score, order, sentence, page.url))
    if not best:
        return None, None
    ranked = sorted(best, key=lambda b: (-b[0], b[1]))
    # A second sentence only if it also reads like a research description (not a paper title or abstract).
    top = ranked[:1] + [b for b in ranked[1:2] if OWN_RESEARCH.search(b[2]) and not NOT_INTERESTS.search(b[2])]
    top.sort(key=lambda b: b[1])  # keep reading order
    return " ".join(b[2] for b in top), top[0][3]


def _sentences_with_lines(text: str) -> list[tuple[int, str]]:
    """Sentences with the index of the line they come from, for section membership."""
    out = []
    for i, line in enumerate(text.splitlines()):
        for s in sentences(line):
            out.append((i, s))
    return out


def _abstract(text: str) -> str:
    m = re.search(r"\babstract\b[:.\s]*(.{100,2500}?)(?:\n\s*\n|\b1\.?\s+introduction\b|\bintroduction\b)", text, re.I | re.S)
    return m.group(1) if m else text[:1500]


def _find_publications(pages: list[PageText]) -> list[PubRef]:
    pubs: list[PubRef] = []
    year_re = re.compile(r"\b(202[4-9])\b")
    for p in pages:
        if p.kind == "homepage" and "publication" not in p.url.lower():
            continue
        for line in (p.text or "").splitlines():
            line = line.strip()
            m = year_re.search(line)
            if m and 30 <= len(line) <= 300:
                pubs.append(PubRef(title=line, year=int(m.group(1))))
            if len(pubs) >= 10:
                return pubs
    return pubs
