"""Polite HTTP fetching: robots.txt, 1 request/sec per domain, redirects followed."""

import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.config import get_settings

_last_request: dict[str, float] = {}
_robots: dict[str, RobotFileParser | None] = {}
_lock = threading.Lock()
MIN_INTERVAL = 1.0


def user_agent() -> str:
    return f"PhDDog/0.1 (personal PhD advisor research tool; {get_settings().contact_email})"


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    content_type: str
    content: bytes
    last_modified: str | None = None
    tls_unverified: bool = False  # fetched after an incomplete-certificate-chain error (see fetch)

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class FetchBlocked(Exception):
    pass


def _client(verify: bool = True) -> httpx.Client:
    return httpx.Client(
        follow_redirects=True, timeout=20.0, headers={"User-Agent": user_agent()}, max_redirects=5, verify=verify
    )


def _incomplete_chain(e: Exception) -> bool:
    """The server omitted an intermediate certificate (browsers fetch it themselves; Python doesn't).

    Only this case is retried without verification. Expired, self-signed or wrong-host
    certificates still fail.
    """
    return "unable to get local issuer certificate" in str(e)


def _wait_turn(host: str) -> None:
    with _lock:
        wait = _last_request.get(host, 0) + MIN_INTERVAL - time.monotonic()
        _last_request[host] = time.monotonic() + max(wait, 0)
    if wait > 0:
        time.sleep(wait)


def allowed_by_robots(url: str) -> bool:
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots:
        parser = RobotFileParser()
        try:
            with _client() as c:
                r = c.get(f"{base}/robots.txt")
            if r.status_code == 200:
                parser.parse(r.text.splitlines())
                _robots[base] = parser
            else:
                _robots[base] = None  # no robots.txt -> allowed
        except httpx.HTTPError:
            _robots[base] = None
    parser = _robots[base]
    return parser is None or parser.can_fetch(user_agent(), url)


def fetch(url: str, check_robots: bool = True) -> FetchResult:
    if check_robots and not allowed_by_robots(url):
        raise FetchBlocked(f"robots.txt disallows {url}")
    _wait_turn(urlsplit(url).netloc)
    unverified = False
    try:
        with _client() as c:
            r = c.get(url)
    except httpx.ConnectError as e:
        if not _incomplete_chain(e):
            raise
        # Read-only fetch of a public page: acceptable to retry, but the result is flagged.
        unverified = True
        with _client(verify=False) as c:
            r = c.get(url)
    r.raise_for_status()
    return FetchResult(
        url=url, final_url=str(r.url), status_code=r.status_code,
        content_type=r.headers.get("content-type", ""), content=r.content,
        last_modified=r.headers.get("last-modified"), tls_unverified=unverified,
    )


def get_json(url: str, params: dict | None = None) -> dict:
    """For public metadata APIs (Crossref, arXiv, NCBI, Unpaywall)."""
    _wait_turn(urlsplit(url).netloc)
    with _client() as c:
        r = c.get(url, params=params)
    r.raise_for_status()
    return r.json()
