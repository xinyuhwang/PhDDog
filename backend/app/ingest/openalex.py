"""School lookup via OpenAlex institutions (free, no key): names, acronyms and web domains."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app.ingest.fetch import get_json

# Accept the top acronym match automatically only if it is this many times larger
# (by publication count) than the next match; otherwise ask the user to pick.
DOMINANCE_RATIO = 5


@dataclass
class Institution:
    name: str
    acronyms: list[str]
    domain: str | None
    country: str | None
    works_count: int

    def as_suggestion(self) -> dict:
        return {"name": self.name, "aliases": self.acronyms, "primary_domain": self.domain, "country": self.country}


def domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    host = urlsplit(url if "://" in url else f"https://{url}").netloc.lower()
    host = re.sub(r"^www\d?\.", "", host.split(":")[0])
    return host or None


def search_institutions(query: str, limit: int = 8) -> list[Institution]:
    try:
        data = get_json(
            "https://api.openalex.org/institutions",
            params={
                "search": query, "per_page": limit,
                "select": "display_name,homepage_url,display_name_acronyms,works_count,country_code,type",
            },
        )
    except (httpx.HTTPError, ValueError):
        return []
    return [
        Institution(
            name=r["display_name"], acronyms=[a.strip() for a in r.get("display_name_acronyms") or [] if a.strip()],
            domain=domain_from_url(r.get("homepage_url")), country=r.get("country_code"),
            works_count=r.get("works_count") or 0,
        )
        for r in data.get("results", [])
        if r.get("type") in (None, "education")
    ]


def resolve_school(query: str) -> tuple[Institution | None, list[Institution]]:
    """Returns (confident match or None, suggestions to show the user)."""
    results = search_institutions(query)
    q = query.strip().lower()
    matches = [i for i in results if i.name.lower() == q or q in (a.lower() for a in i.acronyms)]
    matches.sort(key=lambda i: i.works_count, reverse=True)
    exact_name = [i for i in matches if i.name.lower() == q]
    if len(exact_name) == 1:
        return exact_name[0], matches[:5]
    if len(matches) == 1 or (len(matches) > 1 and matches[0].works_count >= DOMINANCE_RATIO * matches[1].works_count):
        return matches[0], matches[:5]
    return None, (matches or results)[:5]
