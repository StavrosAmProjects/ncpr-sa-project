"""
api.py -- a tiny local API in front of scraper.py, so an AI assistant
(or any tool) can hit plain HTTP/JSON endpoints instead of importing
Python directly.

Run it with:
    pip install fastapi uvicorn requests beautifulsoup4 --break-system-packages
    uvicorn api:app --reload --port 8008

Then, e.g.:
    GET  /browse/cylii?section=cy/cases/diait/aap&year=2026&keyword=POLYECO
    GET  /browse/cylaw?index_path=supreme/index_2024.html&keyword=Andronikou
    GET  /document?url=https://cylii.org/document?id=/cy/cases/diait/aap/2026/ip/4-2026.htm

Point your assistant at this base URL (e.g. via a custom tool/connector)
and it can locate and read cases for you on demand.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from scraper import CyLawClient, CaseHit, DocumentResult

app = FastAPI(
    title="CyLaw/CyLII lookup API (unofficial)",
    description=(
        "Read-only helper API over cylaw.org and cylii.org public pages. "
        "Not affiliated with the Cyprus Bar Association. Be a polite "
        "consumer of a small public-interest legal database."
    ),
    version="0.1.0",
)

client = CyLawClient()


class CaseHitOut(BaseModel):
    number: str
    title: str
    url: str
    source: str


class DocumentOut(BaseModel):
    url: str
    title: str
    text: str


def _to_out(hit: CaseHit) -> CaseHitOut:
    return CaseHitOut(number=hit.number, title=hit.title, url=hit.url, source=hit.source)


@app.get("/browse/cylii", response_model=list[CaseHitOut])
def browse_cylii(
    section: str = Query(..., description="e.g. cy/cases/diait/aap"),
    year: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None, description="case-insensitive substring filter on title"),
):
    try:
        hits = client.browse_cylii(section, year=year, keyword=keyword)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream fetch failed: {e}")
    return [_to_out(h) for h in hits]


@app.get("/browse/cylaw", response_model=list[CaseHitOut])
def browse_cylaw(
    index_path: str = Query(..., description="e.g. supreme/index_2024.html"),
    keyword: Optional[str] = Query(None),
):
    try:
        hits = client.browse_cylaw_index(index_path, keyword=keyword)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream fetch failed: {e}")
    return [_to_out(h) for h in hits]


@app.get("/document", response_model=DocumentOut)
def get_document(url: str = Query(..., description="a cylaw.org or cylii.org document URL")):
    if "cylaw.org" not in url and "cylii.org" not in url:
        raise HTTPException(status_code=400, detail="url must be on cylaw.org or cylii.org")
    try:
        doc: DocumentResult = client.get_document(url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream fetch failed: {e}")
    return DocumentOut(url=doc.url, title=doc.title, text=doc.text)


@app.get("/sections")
def known_sections():
    """A short, hand-curated list of cylii.org section paths to start from."""
    return client.KNOWN_CYLII_SECTIONS
