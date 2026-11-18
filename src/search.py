"""Query layer on top of the Elasticsearch index (used by the web app and the evaluation).

Ranking profiles (compared in the evaluation):
  * baseline : standard analyzer, title + body, plain BM25
  * italian  : Italian analyzer (elision, stopwords, folding, light stemming),
               fields title^3, lead^1.5, body, categories^2, location
  * full     : italian + boosts for exact phrases and adjacent word pairs (shingles)

CLI:
    python src/search.py "papa francesco" [--profile full] [-k 10]
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass, field

from elasticsearch import Elasticsearch

ES_URL = os.environ.get("ES_URL", "http://localhost:9200")
INDEX = os.environ.get("ES_INDEX", "wikinews")
PROFILES = ("baseline", "italian", "full")

ADVANCED_SYNTAX = re.compile(r'["+|*~()]|(^|\s)-\w')


@dataclass
class Filters:
    categories: list[str] = field(default_factory=list)
    publishers: list[str] = field(default_factory=list)
    year_from: int | None = None
    year_to: int | None = None
    location: str | None = None


def text_query(q: str, profile: str = "full") -> dict:
    q = q.strip()
    if not q:
        return {"match_all": {}}

    if profile == "baseline":
        return {"multi_match": {"query": q, "fields": ["title.std", "body.std"]}}

    it_fields = ["title^3", "lead^1.5", "body", "categories.text^2", "location.text"]

    # Power-user syntax: "exact phrase", +must, -exclude, a | b, prefix*
    if ADVANCED_SYNTAX.search(q):
        return {"simple_query_string": {
            "query": q, "fields": it_fields, "default_operator": "and",
            "quote_field_suffix": ".exact" if profile == "full" else "",
        }}

    main = {"multi_match": {
        "query": q, "fields": it_fields, "type": "best_fields",
        "tie_breaker": 0.3, "minimum_should_match": "2<75%",
    }}
    if profile == "italian":
        return main

    return {"bool": {
        "must": [main],
        "should": [
            {"match_phrase": {"title.exact": {"query": q, "slop": 1, "boost": 4}}},
            {"match_phrase": {"body.exact": {"query": q, "slop": 2, "boost": 1.5}}},
            {"match": {"title.shingles": {"query": q, "boost": 2}}},
            {"match": {"body.shingles": {"query": q, "boost": 0.5}}},
        ],
    }}


def filter_clauses(f: Filters | None) -> list[dict]:
    if not f:
        return []
    out: list[dict] = [{"term": {"categories": c}} for c in f.categories]
    if f.publishers:
        out.append({"terms": {"publishers": f.publishers}})
    if f.year_from or f.year_to:
        rng = {}
        if f.year_from:
            rng["gte"] = f.year_from
        if f.year_to:
            rng["lte"] = f.year_to
        out.append({"range": {"year": rng}})
    if f.location:
        out.append({"term": {"location": f.location}})
    return out


def build_body(q: str, profile: str = "full", filters: Filters | None = None,
               sort: str = "relevance", page: int = 1, size: int = 10,
               facets: bool = True, highlight: bool = True) -> dict:
    body: dict = {
        "query": {"bool": {"must": [text_query(q, profile)], "filter": filter_clauses(filters)}},
        "from": (page - 1) * size,
        "size": size,
        "_source": ["id", "title", "url", "date", "categories", "lead", "location",
                    "image", "publishers", "sources", "n_chars"],
        "track_total_hits": True,
    }
    if sort == "date_desc":
        body["sort"] = [{"date": {"order": "desc", "missing": "_last"}}, "_score"]
    elif sort == "date_asc":
        body["sort"] = [{"date": {"order": "asc", "missing": "_last"}}, "_score"]
    if highlight and q.strip():
        body["highlight"] = {
            "pre_tags": ["<mark>"], "post_tags": ["</mark>"], "encoder": "html",
            "fields": {
                "title": {"number_of_fragments": 0},
                "body": {"type": "fvh", "fragment_size": 180, "number_of_fragments": 2,
                         "no_match_size": 200},
            },
        }
    if facets:
        body["aggs"] = {
            "categories": {"terms": {"field": "categories", "size": 15}},
            "publishers": {"terms": {"field": "publishers", "size": 10}},
            "years": {"histogram": {"field": "year", "interval": 1, "min_doc_count": 1}},
        }
    return body


class Searcher:
    def __init__(self, url: str = ES_URL, index: str = INDEX):
        self.es = Elasticsearch(url, request_timeout=30)
        self.index = index

    def search(self, q: str, **kw) -> dict:
        return self.es.search(index=self.index, **build_body(q, **kw)).body

    def ids(self, q: str, profile: str, k: int = 10) -> list[int]:
        res = self.search(q, profile=profile, size=k, facets=False, highlight=False)
        return [h["_source"]["id"] for h in res["hits"]["hits"]]

    def suggest(self, prefix: str, k: int = 8) -> list[str]:
        if not prefix.strip():
            return []
        res = self.es.search(index=self.index, size=k, _source=["title"], query={
            "multi_match": {"query": prefix, "type": "bool_prefix", "operator": "and",
                            "fields": ["title.suggest", "title.suggest._2gram", "title.suggest._3gram"]}})
        return [h["_source"]["title"] for h in res["hits"]["hits"]]

    def get(self, doc_id: int) -> dict | None:
        res = self.es.options(ignore_status=404).get(index=self.index, id=doc_id)
        return res.body.get("_source") if res.body.get("found") else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--profile", choices=PROFILES, default="full")
    ap.add_argument("-k", type=int, default=10)
    args = ap.parse_args()
    res = Searcher().search(args.query, profile=args.profile, size=args.k, facets=False, highlight=False)
    print(f"{res['hits']['total']['value']} hits in {res['took']} ms")
    for i, h in enumerate(res["hits"]["hits"], 1):
        s = h["_source"]
        print(f"{i:2d}. {h['_score']:7.2f}  {s.get('date') or '----------'}  {s['title']}")


if __name__ == "__main__":
    main()
