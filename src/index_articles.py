"""Create the Elasticsearch index and bulk-load the parsed articles.

Usage:
    python src/index_articles.py data/processed/articles.jsonl [--index wikinews] [--recreate]
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Iterator

from elasticsearch import Elasticsearch, helpers

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / "es" / "index_settings.json"
ES_URL = os.environ.get("ES_URL", "http://localhost:9200")


def actions(path: Path, index: str) -> Iterator[dict]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            a["year"] = int(a["date"][:4]) if a.get("date") else None
            a["publishers"] = sorted({s["publisher"] for s in a.get("sources", []) if s.get("publisher")})
            yield {"_index": index, "_id": a["id"], "_source": a}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--index", default="wikinews")
    ap.add_argument("--recreate", action="store_true", help="drop the index if it exists")
    args = ap.parse_args()

    es = Elasticsearch(ES_URL, request_timeout=120)
    if es.indices.exists(index=args.index):
        if not args.recreate:
            raise SystemExit(f"index '{args.index}' exists: use --recreate to rebuild it")
        es.indices.delete(index=args.index)

    body = json.loads(SETTINGS.read_text(encoding="utf-8"))
    for an in body["settings"]["analysis"]["analyzer"].values():
        an.pop("comment", None)
    # faster bulk load: no refresh while indexing
    body["settings"]["refresh_interval"] = "-1"
    es.indices.create(index=args.index, settings=body["settings"], mappings=body["mappings"])

    t0 = time.perf_counter()
    ok, errors = helpers.bulk(es, actions(args.input, args.index), chunk_size=500,
                              raise_on_error=False, stats_only=False)
    es.indices.put_settings(index=args.index, settings={"refresh_interval": "1s"})
    es.indices.refresh(index=args.index)
    es.indices.forcemerge(index=args.index, max_num_segments=1)
    dt = time.perf_counter() - t0

    count = es.count(index=args.index)["count"]
    size = es.indices.stats(index=args.index)["indices"][args.index]["total"]["store"]["size_in_bytes"]
    print(f"indexed {ok} docs ({len(errors)} errors) in {dt:.1f}s -> count={count}, size={size / 1e6:.1f} MB")
    for e in errors[:5]:
        print("ERROR", json.dumps(e)[:500])


if __name__ == "__main__":
    main()
