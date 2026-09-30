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
HEADING_START = re.compile(r"(<h[1-6]\b[^>]*>)", re.IGNORECASE)
LIST_ITEM_START = re.compile(r"(<li\b[^>]*>)", re.IGNORECASE)
# Inline elements styled as list items or tags (e.g. <span class="detail_item">), one per line.
ITEM_START = re.compile(
    r'(<(?:span|a|div|p)\b[^>]*\bclass="[^"]*(?<![a-z])(?:item|tag|chip|keyword|badge|pill|label)s?(?![a-z])[^"]*"[^>]*>)',
    re.IGNORECASE,
)
CHROME = "nav, script, style, noscript, template, [role=navigation], [role=contentinfo], [aria-hidden=true]"
CHROME_CLASS = re.compile(r"\b(nav|navbar|menu|breadcrumbs?|skip-link|site-footer|cookie)\b", re.IGNORECASE)


def visible_text(html: str) -> str:
    """Readable page text without site navigation.

    Headings become '## ...' lines and list items '- ...' lines so sections survive.
    Line breaks go only after block elements so inline tags (<b>, <a>) don't split sentences.
    """
    html = re.sub(r"\s+", " ", html)  # line breaks in HTML source are just spaces
    html = BLOCK_END.sub(r"\1\n", html)
    html = HEADING_START.sub(r"\1\n## ", html)
    html = LIST_ITEM_START.sub(r"\1\n- ", html)
    html = ITEM_START.sub(r"\1\n- ", html)
    tree = HTMLParser(html)
    for node in tree.css(CHROME):
        node.decompose()
    # Site-wide footers only: some templates put real content in a <footer> inside a page section.
    for node in tree.css("footer"):
        if not _has_ancestor(node, ("article", "section", "main")):
            node.decompose()
    total = len(tree.body.text()) if tree.body else 0
    for node in tree.css("[class], [id]"):
        attrs = f"{node.attributes.get('class') or ''} {node.attributes.get('id') or ''}"
        # Size check: a wrapper like <div class="menu-open"> can hold the whole page.
        if CHROME_CLASS.search(attrs) and node.tag not in ("body", "main", "html") and len(node.text()) < 0.3 * total:
            node.decompose()
    for a in tree.css("a"):
        if a.text(strip=True).lower().startswith("skip to"):
            a.decompose()

    body = tree.body
    main = tree.css_first("main") or tree.css_first("[role=main]")
    parts = [body] if body else []
    # Prefer <main> when it holds most of the content; keep sidebars, where recruiting notes often sit.
    if body and main and len(main.text()) >= 0.3 * len(body.text()):
        parts = [main, *(a for a in tree.css("aside") if not _inside(a, main))]
    text = "\n".join(p.text(separator=" ") for p in parts)
    lines = (re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.splitlines())
    text = "\n".join(line for line in lines if line not in ("##", "-"))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _has_ancestor(node, tags: tuple[str, ...]) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.tag in tags:
            return True
        parent = parent.parent
    return False


def _inside(node, ancestor) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.mem_id == ancestor.mem_id:
            return True
        parent = parent.parent
    return False


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


OWN_SITE_TEXT = re.compile(
    r"^(personal\s+|research\s+|lab\s+|group\s+|my\s+|faculty\s+)?(web\s?site|home\s?page|lab(oratory)?|research group|group|site)"
    r"(\s+(website|page|site))?$",
    re.IGNORECASE,
)


def scope_prefix(url: str) -> str:
    """Path prefix a crawl may stay within.

    '/~name/...' -> '/~name/'; a directory-style profile like '/faculty/jane-doe/' or
    '/cse/profiles/doe.html' -> just that profile; a personal site at '/' -> everything.
    """
    segments = [s for s in urlsplit(url).path.split("/") if s]
    if not segments:
        return "/"
    if segments[0].startswith("~"):
        return f"/{segments[0]}/"
    if "." in segments[-1]:
        if len(segments) == 1:
            return "/"
        return "/" + "/".join(segments[:-1]) + "/" + segments[-1].rsplit(".", 1)[0]
    return "/" + "/".join(segments)


def _links(html: str, base_url: str):
    for a in HTMLParser(html).css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "javascript:", "tel:", "#")):
            continue
        url = urljoin(base_url, href).split("#")[0]
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or re.search(r"\.(pdf|jpg|jpeg|png|gif|zip|pptx?|docx?)$", parts.path, re.I):
            continue
        yield a.text(strip=True), url, parts


def subpage_links(html: str, base_url: str, limit: int) -> list[str]:
    """Links within the professor's own part of the site whose text or path looks like Research/People/Join/etc.

    Staying under the profile's path prefix keeps a department directory profile from
    wandering into department-wide pages (hiring, admissions), which say nothing about
    this professor.
    """
    base = urlsplit(base_url)
    prefix = scope_prefix(base_url)
    seen: set[str] = set()
    out: list[str] = []
    for text, url, parts in _links(html, base_url):
        if parts.netloc != base.netloc or not parts.path.startswith(prefix.rstrip("/") or "/"):
            continue
        if url.rstrip("/") == base_url.rstrip("/") or url in seen or not SUBPAGE_PATTERN.search(f"{text} {parts.path}"):
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= limit:
            break
    return out


def own_site_links(html: str, base_url: str, limit: int = 2) -> list[str]:
    """Links labeled 'Website', 'Homepage', 'Lab', etc. that leave the profile: usually the professor's own site."""
    prefix = scope_prefix(base_url)
    base = urlsplit(base_url)
    out: list[str] = []
    for text, url, parts in _links(html, base_url):
        inside = parts.netloc == base.netloc and parts.path.startswith(prefix.rstrip("/") or "/")
        if not inside and OWN_SITE_TEXT.match(text.strip(" :")) and url not in out:
            out.append(url)
            if len(out) >= limit:
                break
    return out
