import re
from dataclasses import dataclass

import pymupdf

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE)


@dataclass
class PdfContent:
    text: str
    title: str | None
    doi: str | None
    year: int | None


def extract_pdf(content: bytes) -> PdfContent:
    with pymupdf.open(stream=content, filetype="pdf") as doc:
        # sort=True orders blocks top-to-bottom, left-to-right, which helps two-column papers.
        text = "\n".join(page.get_text("text", sort=True) for page in doc)
        meta = doc.metadata or {}
    first_page = text[:4000]
    doi_match = DOI_RE.search(first_page)
    title = (meta.get("title") or "").strip() or _guess_title(first_page)
    year_match = re.search(r"\b(19|20)\d{2}\b", meta.get("creationDate", "") or "")
    return PdfContent(
        text=text,
        title=title,
        doi=doi_match.group(1).rstrip(".,;)") if doi_match else None,
        year=int(year_match.group(0)) if year_match else None,
    )


def _guess_title(first_page: str) -> str | None:
    for line in first_page.splitlines():
        line = line.strip()
        if 15 <= len(line) <= 250 and not re.search(r"arxiv|doi|preprint|journal|conference|©|http", line, re.I):
            return line
    return None
