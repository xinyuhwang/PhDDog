import re
from urllib.parse import urljoin, urlsplit

import trafilatura
from selectolax.parser import HTMLParser

SUBPAGE_PATTERN = re.compile(
    r"research|publication|papers|people|members|team|join|prospective|opening|position|students|cv|bio|about|contact|lab",
    re.IGNORECASE,
)


BLOCK_END = re.compile(
    r"(<br\s*/?>|</(?:p|div|li|h[1-6]|tr|td|th|section|article|ul|ol|table|blockquote|header|footer|dd|dt|nav)>)",
    re.IGNORECASE,
)


def visible_text(html: str) -> str:
    """All visible text, with line breaks only after block elements so inline tags don't split sentences."""
    tree = HTMLParser(BLOCK_END.sub(r"\1\n", html))
    for tag in tree.css("script, style, noscript"):
        tag.decompose()
    body = tree.body.text(separator=" ") if tree.body else ""
    body = "\n".join(re.sub(r"[ \t\xa0]+", " ", line).strip() for line in body.splitlines())
    return re.sub(r"\n\s*\n+", "\n\n", body).strip()


def html_to_text(html: str, main_only: bool = False) -> str:
    """Page text for extraction.

    Professor pages keep everything visible: recruiting notes often sit in sidebars or
    collapsible sections that article extractors drop. `main_only` is for paper pages,
    where trafilatura removes navigation and boilerplate.
    """
    body = visible_text(html)
    if not main_only:
        return body
    extracted = trafilatura.extract(html, include_links=False, include_tables=True, favor_recall=True) or ""
    return extracted if len(extracted) >= 0.3 * len(body) else body


def subpage_links(html: str, base_url: str, limit: int) -> list[str]:
    """Same-site links whose text or path looks like Research/People/Join/etc."""
    base = urlsplit(base_url)
    seen: set[str] = set()
    out: list[str] = []
    for a in HTMLParser(html).css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "javascript:", "#")):
            continue
        url = urljoin(base_url, href).split("#")[0]
        parts = urlsplit(url)
        if parts.netloc != base.netloc or parts.scheme not in ("http", "https"):
            continue
        if re.search(r"\.(pdf|jpg|jpeg|png|gif|zip|pptx?|docx?)$", parts.path, re.I):
            continue
        label = f"{a.text(strip=True)} {parts.path}"
        if url.rstrip("/") == base_url.rstrip("/") or url in seen or not SUBPAGE_PATTERN.search(label):
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= limit:
            break
    return out
