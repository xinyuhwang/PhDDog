"""Resolve a paper link to metadata + text (docs/DESIGN.md §4.3).

Handlers are tried in order: arXiv, PubMed, DOI (incl. bioRxiv/medRxiv), generic page.
Each fills what it can; a missing full text is reported as `abstract_only`, not an error.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx
from selectolax.parser import HTMLParser

from app.config import get_settings
from app.ingest.fetch import fetch, get_json
from app.ingest.html import html_to_text
from app.ingest.pdf import DOI_RE, extract_pdf

FULL_TEXT_MIN_CHARS = 3000


@dataclass
class PaperMeta:
    source: str
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    abstract: str | None = None
    full_text: str | None = None
    pdf_bytes: bytes | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def text_status(self) -> str:
        if self.full_text and len(self.full_text) >= FULL_TEXT_MIN_CHARS:
            return "full"
        if self.abstract or self.full_text:
            return "abstract_only"
        return "failed"


def resolve_url(url: str) -> PaperMeta:
    url = url.strip()
    if m := re.search(r"arxiv\.org/(?:abs|pdf)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?$", url):
        return _arxiv(m.group(1))
    if m := re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", url):
        return _pubmed(m.group(1))
    if m := DOI_RE.search(url):
        doi = re.sub(r"(v\d+)?(\.full(\.pdf)?)?$", "", m.group(1).rstrip("/"))
        meta = _doi(doi)
        if meta.text_status != "full":
            _merge_generic(meta, url)
        return meta
    meta = PaperMeta(source="generic")
    _merge_generic(meta, url)
    if meta.doi and meta.text_status != "full":
        _fill_from_doi(meta, meta.doi)
    return meta


# --- handlers ----------------------------------------------------------------------

ATOM = {"a": "http://www.w3.org/2005/Atom"}


def _arxiv(arxiv_id: str) -> PaperMeta:
    meta = PaperMeta(source="arxiv")
    xml = fetch(f"http://export.arxiv.org/api/query?id_list={arxiv_id}", check_robots=False).text
    entry = ET.fromstring(xml).find("a:entry", ATOM)
    if entry is not None:
        meta.title = _clean(entry.findtext("a:title", default="", namespaces=ATOM))
        meta.abstract = _clean(entry.findtext("a:summary", default="", namespaces=ATOM))
        meta.authors = [_clean(a.findtext("a:name", default="", namespaces=ATOM)) for a in entry.findall("a:author", ATOM)]
        published = entry.findtext("a:published", default="", namespaces=ATOM)
        meta.year = int(published[:4]) if published[:4].isdigit() else None
        meta.venue = "arXiv"
    _attach_pdf(meta, f"https://arxiv.org/pdf/{arxiv_id}")
    return meta


def _pubmed(pmid: str) -> PaperMeta:
    meta = PaperMeta(source="pubmed")
    xml = fetch(
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&retmode=xml", check_robots=False
    ).text
    art = ET.fromstring(xml).find(".//Article")
    if art is not None:
        meta.title = _clean("".join(art.find("ArticleTitle").itertext())) if art.find("ArticleTitle") is not None else None
        meta.abstract = _clean(" ".join("".join(t.itertext()) for t in art.findall(".//AbstractText"))) or None
        meta.venue = art.findtext(".//Journal/Title")
        year = art.findtext(".//JournalIssue/PubDate/Year") or art.findtext(".//ArticleDate/Year")
        meta.year = int(year) if year and year.isdigit() else None
        meta.authors = [
            f"{a.findtext('ForeName', '')} {a.findtext('LastName', '')}".strip() for a in art.findall(".//Author")
        ]
    root = ET.fromstring(xml)
    doi = root.findtext(".//ArticleId[@IdType='doi']")
    if doi:
        meta.doi = doi
        _unpaywall(meta, doi)
    return meta


def _doi(doi: str) -> PaperMeta:
    meta = PaperMeta(source="doi", doi=doi)
    _fill_from_doi(meta, doi)
    return meta


def _fill_from_doi(meta: PaperMeta, doi: str) -> None:
    try:
        work = get_json(f"https://api.crossref.org/works/{quote(doi)}")["message"]
        meta.title = meta.title or _clean(" ".join(work.get("title") or [])) or None
        meta.authors = meta.authors or [
            f"{a.get('given', '')} {a.get('family', '')}".strip() for a in work.get("author", [])
        ]
        parts = (work.get("issued") or work.get("published") or {}).get("date-parts") or [[None]]
        meta.year = meta.year or parts[0][0]
        meta.venue = meta.venue or " ".join(work.get("container-title") or []) or work.get("publisher")
        if work.get("abstract") and not meta.abstract:
            meta.abstract = _clean(re.sub(r"<[^>]+>", " ", work["abstract"]))
    except (httpx.HTTPError, KeyError, ValueError) as e:
        meta.notes.append(f"Crossref lookup failed: {e}")
    _unpaywall(meta, doi)


def _unpaywall(meta: PaperMeta, doi: str) -> None:
    if meta.pdf_bytes:
        return
    try:
        data = get_json(f"https://api.unpaywall.org/v2/{quote(doi)}", params={"email": get_settings().contact_email})
        pdf_url = ((data.get("best_oa_location") or {}).get("url_for_pdf"))
        if pdf_url:
            _attach_pdf(meta, pdf_url)
        else:
            meta.notes.append("No open-access PDF found (Unpaywall)")
    except (httpx.HTTPError, ValueError) as e:
        meta.notes.append(f"Unpaywall lookup failed: {e}")


def _merge_generic(meta: PaperMeta, url: str) -> None:
    try:
        r = fetch(url)
    except Exception as e:  # noqa: BLE001 - any failure here means "no page text", not a crash
        meta.notes.append(f"Could not fetch page: {e}")
        return
    if "pdf" in r.content_type or r.content[:4] == b"%PDF":
        _use_pdf(meta, r.content)
        return
    html = r.text
    tree = HTMLParser(html)

    def meta_tag(name: str) -> str | None:
        node = tree.css_first(f'meta[name="{name}"]') or tree.css_first(f'meta[property="{name}"]')
        return (node.attributes.get("content") or "").strip() if node else None

    meta.title = meta.title or meta_tag("citation_title") or meta_tag("og:title") or (
        tree.css_first("title").text(strip=True) if tree.css_first("title") else None
    )
    meta.doi = meta.doi or meta_tag("citation_doi")
    date = meta_tag("citation_publication_date") or meta_tag("citation_date") or ""
    if not meta.year and (m := re.search(r"(19|20)\d{2}", date)):
        meta.year = int(m.group(0))
    meta.venue = meta.venue or meta_tag("citation_journal_title") or meta_tag("citation_conference_title")
    meta.abstract = meta.abstract or meta_tag("citation_abstract") or meta_tag("description")
    if not meta.pdf_bytes and (pdf_url := meta_tag("citation_pdf_url")):
        _attach_pdf(meta, pdf_url)
    if not meta.full_text:
        text = html_to_text(html, main_only=True)
        if len(text) >= FULL_TEXT_MIN_CHARS:
            meta.full_text = text


def _attach_pdf(meta: PaperMeta, pdf_url: str) -> None:
    try:
        r = fetch(pdf_url)
        if r.content[:4] == b"%PDF":
            _use_pdf(meta, r.content)
        else:
            meta.notes.append(f"Link did not return a PDF: {pdf_url}")
    except Exception as e:  # noqa: BLE001
        meta.notes.append(f"PDF download failed: {e}")


def _use_pdf(meta: PaperMeta, content: bytes) -> None:
    pdf = extract_pdf(content)
    meta.pdf_bytes = content
    meta.full_text = pdf.text
    meta.title = meta.title or pdf.title
    meta.doi = meta.doi or pdf.doi
    meta.year = meta.year or pdf.year


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()
