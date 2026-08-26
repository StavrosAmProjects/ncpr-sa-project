"""
cylaw_scraper.py

Read-only scraper for cylaw.org / cylii.org (Cyprus Bar Association's
free legal database: Supreme Court judgments, administrative court
decisions, tribunal decisions, legislation).

IMPORTANT / HONESTY NOTES (read before relying on this):
- Neither site publishes a documented public API. This module works by
  parsing the same HTML pages a browser would load. It is NOT calling
  any private/internal API.
- cylaw.org's full-text search box is powered by a Perl/Sino CGI engine.
  I could not confirm the exact GET/POST parameter names for the live
  search form from outside a browser, so this module does NOT attempt
  free-text search on cylaw.org. What it *can* do reliably is walk the
  static, always-present year/category index pages, which are plain
  HTML links -- and fetch a given document by its known path.
- cylii.org is a newer Next.js site with clean, guessable listing URLs
  (per-court, per-year) and a document viewer at /document?id=<path>.
  Its on-page search box likely calls an internal API that isn't meant
  for outside use, so this module does not call it either. Instead it
  offers keyword filtering over the listing pages it can already read,
  which covers "find me the case about X between these years" style
  requests reasonably well.
- Be a polite scraper: this module caches responses, sends a real
  User-Agent + contact string, and rate-limits itself. If you scale
  this up, drop the site an email (info@cylaw.org) and ask about
  bulk/API access -- that's the correct way to get more than this
  script can responsibly provide.

Usage:
    from scraper import CyLawClient
    client = CyLawClient()
    hits = client.search_cylii("diait/aap", year=2026, keyword="POLYECO")
    doc = client.get_document(hits[0]["url"])
"""

from __future__ import annotations

import re
import time
import functools
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Set CYLAW_CONTACT_EMAIL in the deployment environment.  A real contact
# address is important when making automated requests to a small public site.
USER_AGENT = "cylaw-research-bot/0.2 (legal research; contact: {email})"

CYLAW_BASE = "https://cylaw.org"
CYLII_BASE = "https://cylii.org"

MIN_REQUEST_INTERVAL_SECONDS = 1.5  # be polite; don't hammer a small public site


@dataclass
class CaseHit:
    number: str
    title: str
    url: str
    source: str  # "cylaw" or "cylii"


@dataclass
class DocumentResult:
    url: str
    title: str
    text: str
    raw_html: str = field(repr=False, default="")


class _RateLimiter:
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self):
        elapsed = time.monotonic() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


class CyLawClient:
    """Read-only client for cylaw.org and cylii.org."""

    # Known cylii court/section paths worth knowing about. Not exhaustive --
    # extend as you discover more via browse_cylii_root().
    KNOWN_CYLII_SECTIONS = {
        "supreme_court": "cy/cases/anot",
        "administrative_court": "cy/cases/dd",
        "tender_review_authority": "cy/cases/diait/aap",
        "competition_commission": "cy/cases/diait/epa",
    }

    def __init__(self, session: Optional[requests.Session] = None, cache_size: int = 256):
        self.session = session or requests.Session()
        import os
        email = os.getenv("CYLAW_CONTACT_EMAIL", "operator@example.invalid")
        self.session.headers.update({"User-Agent": USER_AGENT.format(email=email)})
        self._limiter = _RateLimiter(MIN_REQUEST_INTERVAL_SECONDS)
        self._get_cached = functools.lru_cache(maxsize=cache_size)(self._get_raw)

    # ---------- low-level fetch ----------

    def _get_raw(self, url: str) -> str:
        self._limiter.wait()
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding  # cylaw.org's legacy pages mis-declare charset
        return resp.text

    def _get(self, url: str, use_cache: bool = True) -> str:
        return self._get_cached(url) if use_cache else self._get_raw(url)

    # ---------- cylii.org (modern site) ----------

    def browse_cylii(
        self,
        section_path: str,
        year: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> list[CaseHit]:
        """
        List cases under a cylii.org section, e.g. section_path="cy/cases/diait/aap".

        year: filters via the site's own ?year= query param when the listing
              page supports it (best-effort; falls back to no filter).
        keyword: client-side substring filter (case-insensitive) applied to
                 the case title text after fetching the page, since there's
                 no confirmed public search endpoint to call instead.
        """
        url = f"{CYLII_BASE}/{section_path.strip('/')}"
        if year:
            url += f"?year={year}"

        html = self._get(url)
        soup = BeautifulSoup(html, "html.parser")

        hits: list[CaseHit] = []
        for link in soup.select("a[href*='/document?id=']"):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or not href:
                continue
            if keyword and keyword.lower() not in title.lower():
                continue
            # Listings put the file/application number in the preceding cell;
            # using the first word of the party name was incorrect.
            number_cell = link.find_parent("tr")
            number_text = ""
            if number_cell:
                cells = number_cell.find_all("td")
                if cells:
                    number_text = cells[0].get_text(" ", strip=True)
            number_match = re.match(r"^([^\s(]+(?:/[^\s(]+)?)", number_text)
            hits.append(
                CaseHit(
                    number=number_match.group(1) if number_match else "",
                    title=title,
                    url=urljoin(CYLII_BASE, href),
                    source="cylii",
                )
            )
        return hits

    # ---------- cylaw.org (legacy site) ----------

    def browse_cylaw_index(self, index_path: str, keyword: Optional[str] = None) -> list[CaseHit]:
        """
        Walk a static cylaw.org listing page, e.g.
        index_path="supreme/index_2024.html" or "areiospagos/index.html".
        """
        url = f"{CYLAW_BASE}/{index_path.lstrip('/')}"
        html = self._get(url)
        soup = BeautifulSoup(html, "html.parser")

        hits: list[CaseHit] = []
        for link in soup.find_all("a", href=True):
            title = link.get_text(strip=True)
            href = link["href"]
            if not title or href.startswith("mailto:") or href.startswith("#"):
                continue
            if keyword and keyword.lower() not in title.lower():
                continue
            hits.append(
                CaseHit(number="", title=title, url=urljoin(url, href), source="cylaw")
            )
        return hits

    # ---------- document retrieval (works for either site) ----------

    def get_document(self, url: str) -> DocumentResult:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"cylaw.org", "www.cylaw.org", "cylii.org", "www.cylii.org"}:
            raise ValueError("url must be an https URL on cylaw.org or cylii.org")
        html = self._get(url)
        soup = BeautifulSoup(html, "html.parser")

        # CyLII uses the generic browser title "Cylaw".  The decision title
        # is the first visible heading-like span in main instead.
        title_tag = soup.select_one("main .pt-4 span") or soup.find("title")
        title = title_tag.get_text(" ", strip=True) if title_tag else url

        # Strip nav/script/style noise, keep body text
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        text = soup.get_text("\n", strip=True)
        return DocumentResult(url=url, title=title, text=text, raw_html=html)


if __name__ == "__main__":
    client = CyLawClient()
    results = client.browse_cylii("cy/cases/diait/aap", year=2026, keyword="POLYECO")
    for r in results:
        print(r.number, "-", r.title)
        print(" ", r.url)
