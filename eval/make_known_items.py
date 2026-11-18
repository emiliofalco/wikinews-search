"""Generate the known-item test set (deterministic).

For N random articles we simulate a user who remembers *what the article was about*
but not its title: the query is made of the K most distinctive words of the body
(tf-idf, document frequency between 2 and 300) that do NOT appear in the title,
listed in order of first appearance.

Usage:
    python eval/make_known_items.py data/processed/articles.jsonl eval/known_items.json
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import random
import re
from pathlib import Path

TOKEN = re.compile(r"[a-zàèéìíòóùú]+", re.IGNORECASE)
STOP = set("""
a ad al alla alle allo agli ai anche ancora avere aveva avevano c che chi ci col come con contro cui da dal
dalla dalle dagli dai degli dei del della delle dello di dopo dove e ed era erano essere fa fino fra gli ha hanno
il in invece io la le lo loro ma mentre molto ne nel nella nelle nello negli nei noi non nostro o ogni oltre per
perché più poi poiché prima proprio quale quali quando quanto quella quelle quello quelli questa queste questo
questi qui se sempre senza si sia sono sta stata stati stato su sua sue sui sul sulla sulle suo suoi tra tutti
tutto tutta tutte un una uno essere stati viene vengono secondo circa dell all dall nell sull altri altre altro
alcuni alcune ieri oggi domani anni anno giorno giorni ore stesso stessa dove così già quindi però tuttavia
inoltre infatti dei della state verso sarà saranno potrebbe essere avrebbe aveva hanno
""".split())


def tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN.findall(text)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("articles", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("-n", type=int, default=300)
    ap.add_argument("-k", type=int, default=4, help="terms per query")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    arts = [json.loads(line) for line in args.articles.open(encoding="utf-8")]
    df: collections.Counter[str] = collections.Counter()
    for a in arts:
        df.update(set(tokens(a["title"] + " " + a["body"])))
    n_docs = len(arts)

    pool = [a for a in arts if a["n_chars"] >= 400]
    rng = random.Random(args.seed)
    rng.shuffle(pool)

    items = []
    for a in pool:
        title_terms = set(tokens(a["title"]))
        body = tokens(a["body"])
        tf = collections.Counter(body)
        cands = {t: tf[t] * math.log(n_docs / df[t]) for t in tf
                 if len(t) >= 4 and t not in STOP and t not in title_terms and 2 <= df[t] <= 300}
        if len(cands) < args.k:
            continue
        best = sorted(cands, key=cands.get, reverse=True)[:args.k]
        best.sort(key=body.index)
        items.append({"id": f"K{len(items) + 1:03d}", "query": " ".join(best),
                      "doc_id": a["id"], "title": a["title"]})
        if len(items) == args.n:
            break

    args.output.write_text(json.dumps({"description": __doc__.strip().split("\n\n")[1],
                                       "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)} known-item queries -> {args.output}")
    for it in items[:5]:
        print(f"  {it['query']!r:55} -> {it['title']}")


if __name__ == "__main__":
    main()
