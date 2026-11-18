"""Web interface for the Wikinews search engine.

Run (from the project root):
    .venv/bin/uvicorn src.web.app:app --reload --port 8000
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from search import PROFILES, Filters, Searcher  # noqa: E402

HERE = Path(__file__).resolve().parent
PAGE_SIZE = 10
MONTHS_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
             "agosto", "settembre", "ottobre", "novembre", "dicembre"]

app = FastAPI(title="Wikinews IT Search")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
searcher = Searcher()


def fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS_IT[int(m) - 1]} {y}"


def thumb(url: str | None, width: int = 330) -> str:
    """Wikimedia Commons thumbnail URL (originals can be several MB)."""
    prefix = "https://upload.wikimedia.org/wikipedia/commons/"
    if not url or not url.startswith(prefix):
        return url or ""
    path = url[len(prefix):]                      # e/e9/File.jpg
    name = path.rsplit("/", 1)[-1]
    suffix = ".png" if name.lower().endswith((".svg", ".tif", ".tiff")) else ""
    return f"{prefix}thumb/{path}/{width}px-{name}{suffix}"


templates.env.filters["itdate"] = fmt_date
templates.env.filters["thumb"] = thumb


def url_with(params: dict, **changes) -> str:
    """Rebuild the current query string with some parameters changed (None removes)."""
    p = {k: v for k, v in params.items() if k != "page"}
    for k, v in changes.items():
        p[k] = v
    flat = []
    for k, v in p.items():
        if v is None or v == "" or v == []:
            continue
        for item in (v if isinstance(v, list) else [v]):
            flat.append((k, item))
    return "/search?" + urlencode(flat)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    stats = searcher.es.count(index=searcher.index)["count"]
    return templates.TemplateResponse(request, "home.html", {"n_docs": stats, "q": ""})


@app.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: str = "",
    cat: list[str] = Query(default=[]),
    pub: list[str] = Query(default=[]),
    year_from: int | None = None,
    year_to: int | None = None,
    sort: str = "relevance",
    profile: str = "full",
    page: int = 1,
):
    if profile not in PROFILES:
        profile = "full"
    page = max(1, min(page, 100))
    filters = Filters(categories=cat, publishers=pub, year_from=year_from, year_to=year_to)

    t0 = time.perf_counter()
    res = searcher.search(q, profile=profile, filters=filters, sort=sort, page=page, size=PAGE_SIZE)
    elapsed = (time.perf_counter() - t0) * 1000

    total = res["hits"]["total"]["value"]
    hits = []
    for h in res["hits"]["hits"]:
        s, hl = h["_source"], h.get("highlight", {})
        hits.append({
            **s,
            "score": h.get("_score"),
            "title_hl": hl.get("title", [None])[0],
            "snippets": hl.get("body", []),
        })

    params = {"q": q, "cat": cat, "pub": pub, "year_from": year_from, "year_to": year_to,
              "sort": sort, "profile": profile}
    aggs = res.get("aggregations", {})
    years = [(int(b["key"]), b["doc_count"]) for b in aggs.get("years", {}).get("buckets", [])]
    max_year_count = max((c for _, c in years), default=1)

    return templates.TemplateResponse(request, "results.html", {
        "q": q, "hits": hits, "total": total, "took": res["took"], "elapsed": elapsed,
        "page": page, "pages": min(100, math.ceil(total / PAGE_SIZE)) if total else 0,
        "params": params, "url_with": url_with, "profiles": PROFILES,
        "cat_facets": aggs.get("categories", {}).get("buckets", []),
        "pub_facets": aggs.get("publishers", {}).get("buckets", []),
        "years": years, "max_year_count": max_year_count,
        "active_filters": bool(cat or pub or year_from or year_to),
    })


@app.get("/article/{doc_id}", response_class=HTMLResponse)
def article(request: Request, doc_id: int, q: str = ""):
    doc = searcher.get(doc_id)
    if not doc:
        raise HTTPException(404, "Articolo non trovato")
    related = searcher.es.search(index=searcher.index, size=5, _source=["id", "title", "date"], query={
        "more_like_this": {"fields": ["title", "body"], "like": [{"_index": searcher.index, "_id": doc_id}],
                           "min_term_freq": 1, "max_query_terms": 25}}).body["hits"]["hits"]
    return templates.TemplateResponse(request, "article.html", {
        "doc": doc, "q": q, "paragraphs": doc["body"].split("\n\n"),
        "similar": [h["_source"] for h in related],
    })


@app.get("/api/suggest")
def suggest(q: str = ""):
    return JSONResponse(searcher.suggest(q))


@app.get("/api/search")
def api_search(q: str = "", profile: str = "full", k: int = 10):
    """JSON endpoint (handy for tests and the evaluation scripts)."""
    res = searcher.search(q, profile=profile if profile in PROFILES else "full", size=min(k, 100),
                          facets=False, highlight=False)
    return {"total": res["hits"]["total"]["value"], "took_ms": res["took"],
            "hits": [{"id": h["_source"]["id"], "title": h["_source"]["title"],
                      "date": h["_source"].get("date"), "score": h["_score"]}
                     for h in res["hits"]["hits"]]}
