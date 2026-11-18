"""Offline evaluation of the ranking configurations.

Two test collections:
  * topics      (eval/topics.json)      ad-hoc queries, relevance = editorial categories
  * known-item  (eval/known_items.json) one target article per query

Metrics: P@10, R-Precision, MAP, nDCG@10, Recall@100 (topics); MRR, Success@1/10 (known-item).
Significance: two-sided paired randomisation test against the 'full' configuration.
Latency: end-to-end search time of the production profile.

Usage:
    python eval/evaluate.py data/processed/articles.jsonl [--out eval/results]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from search import PROFILE_CONFIGS, RankConfig, Searcher  # noqa: E402

DEPTH = 100

# Every system is a variation of the production profile `full` (one change at a time).
# The categories field is NOT searched in any of them: the topic judgements are derived
# from categories, so searching them would leak the answer into the ranking.
FULL = PROFILE_CONFIGS["full"]
SYSTEMS: dict[str, tuple[str, RankConfig]] = {
    "baseline":        ("analyzer standard, title+body, OR", PROFILE_CONFIGS["baseline"]),
    "v1":              ("primo design: best_fields, title^3, mm 2<75%, frasi", replace(PROFILE_CONFIGS["v1"], use_categories=False)),
    "full":            ("produzione: italiano, cross_fields, title^1.5, mm 50%", FULL),
    "-stemming":       ("full senza stemming/stopword (campi .exact)", replace(FULL, suffix=".exact")),
    "analyzer std":    ("full con analyzer standard", replace(FULL, suffix=".std")),
    "best_fields":     ("full con best_fields invece di cross_fields", replace(FULL, mm_type="best_fields")),
    "mm 2<75%":        ("full con minimum_should_match 2<75%", replace(FULL, min_match="2<75%")),
    "OR":              ("full senza minimum_should_match", replace(FULL, min_match=None)),
    "title^3":         ("full con boost titolo 3", replace(FULL, title_boost=3)),
    "+frasi":          ("full + bonus frase esatta/shingle", replace(FULL, phrase_boosts=True)),
}
# categories in the score: measurable on known-item only (no leakage there)
KI_EXTRA = {"+categorie": ("full + categories^2, location nel punteggio", replace(FULL, use_categories=True))}


# ------------------------------------------------------------------ metrics ---

def precision_at(ranked, rel, k):
    return sum(d in rel for d in ranked[:k]) / k


def average_precision(ranked, rel):
    hits, s = 0, 0.0
    for i, d in enumerate(ranked, 1):
        if d in rel:
            hits += 1
            s += hits / i
    return s / len(rel) if rel else 0.0


def ndcg_at(ranked, rel, k):
    dcg = sum(1 / math.log2(i + 1) for i, d in enumerate(ranked[:k], 1) if d in rel)
    idcg = sum(1 / math.log2(i + 1) for i in range(1, min(len(rel), k) + 1))
    return dcg / idcg if idcg else 0.0


def topic_metrics(ranked, rel):
    return {
        "P@10": precision_at(ranked, rel, 10),
        "R-Prec": precision_at(ranked, rel, len(rel)) if rel else 0.0,
        "MAP": average_precision(ranked, rel),
        "nDCG@10": ndcg_at(ranked, rel, 10),
        "R@100": sum(d in rel for d in ranked[:DEPTH]) / len(rel),
    }


def ki_metrics(ranked, target):
    rank = ranked.index(target) + 1 if target in ranked else None
    return {"MRR": 1 / rank if rank else 0.0,
            "S@1": float(rank == 1), "S@10": float(bool(rank and rank <= 10)),
            "rank": rank}


def randomization_test(a, b, n=10_000, seed=0):
    """Two-sided paired randomisation (sign-flip) test on the mean difference."""
    rng = random.Random(seed)
    diffs = [x - y for x, y in zip(a, b)]
    observed = abs(sum(diffs))
    count = 0
    for _ in range(n):
        if abs(sum(d if rng.random() < 0.5 else -d for d in diffs)) >= observed - 1e-12:
            count += 1
    return (count + 1) / (n + 1)


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


# --------------------------------------------------------------------- runs ---

def run(searcher, queries, cfg):
    return {qid: searcher.ids(q, cfg, k=DEPTH) for qid, q in queries}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("articles", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "eval" / "results")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    searcher = Searcher()
    topics = json.loads((ROOT / "eval" / "topics.json").read_text(encoding="utf-8"))["topics"]
    kis = json.loads((ROOT / "eval" / "known_items.json").read_text(encoding="utf-8"))["items"]

    # qrels from categories
    qrels = {t["id"]: set() for t in topics}
    with args.articles.open(encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            cats = set(a["categories"])
            for t in topics:
                if cats & set(t["categories"]):
                    qrels[t["id"]].add(a["id"])

    report: dict = {"topics": {}, "known_item": {}, "significance": {}, "latency": {}, "per_topic": {}}

    # ---- topics
    tq = [(t["id"], t["query"]) for t in topics]
    per_query: dict[str, dict[str, dict]] = {}
    for name, (desc, cfg) in SYSTEMS.items():
        runs = run(searcher, tq, cfg)
        per_query[name] = {qid: topic_metrics(runs[qid], qrels[qid]) for qid, _ in tq}
        report["topics"][name] = {"desc": desc, **{m: mean([v[m] for v in per_query[name].values()])
                                                   for m in ("P@10", "R-Prec", "MAP", "nDCG@10", "R@100")}}
        # the production configuration was chosen on the dev half (even positions) only
        report["topics"][name]["MAP_dev"] = mean([per_query[name][q]["MAP"] for i, (q, _) in enumerate(tq) if i % 2 == 0])
        report["topics"][name]["MAP_test"] = mean([per_query[name][q]["MAP"] for i, (q, _) in enumerate(tq) if i % 2 == 1])
    report["per_topic"] = {qid: {"query": q, "n_rel": len(qrels[qid]),
                                 **{s: round(per_query[s][qid]["MAP"], 4) for s in SYSTEMS}}
                           for qid, q in tq}

    # ---- known items
    kq = [(k["id"], k["query"]) for k in kis]
    target = {k["id"]: k["doc_id"] for k in kis}
    ki_per_query: dict[str, dict[str, dict]] = {}
    for name, (desc, cfg) in {**SYSTEMS, **KI_EXTRA}.items():
        runs = run(searcher, kq, cfg)
        ki_per_query[name] = {qid: ki_metrics(runs[qid], target[qid]) for qid, _ in kq}
        vals = ki_per_query[name].values()
        report["known_item"][name] = {"desc": desc, "MRR": mean([v["MRR"] for v in vals]),
                                      "S@1": mean([v["S@1"] for v in vals]),
                                      "S@10": mean([v["S@10"] for v in vals]),
                                      "not_found@100": sum(v["rank"] is None for v in vals)}

    # ---- significance vs full
    for name in SYSTEMS:
        if name == "full":
            continue
        report["significance"][name] = {
            "MAP_p": randomization_test([per_query[name][q]["MAP"] for q, _ in tq],
                                        [per_query["full"][q]["MAP"] for q, _ in tq]),
            "nDCG@10_p": randomization_test([per_query[name][q]["nDCG@10"] for q, _ in tq],
                                            [per_query["full"][q]["nDCG@10"] for q, _ in tq]),
            "KI_MRR_p": randomization_test([ki_per_query[name][q]["MRR"] for q, _ in kq],
                                           [ki_per_query["full"][q]["MRR"] for q, _ in kq]),
        }

    # ---- latency (production profile, with facets + highlight like the web UI)
    for _ in range(3):  # warm-up
        searcher.search("prova", profile="full")
    took, wall = [], []
    for _ in range(5):
        for _, q in tq + kq[:50]:
            t0 = time.perf_counter()
            r = searcher.search(q, profile="full")
            wall.append((time.perf_counter() - t0) * 1000)
            took.append(r["took"])
    qs = statistics.quantiles(wall, n=100)
    report["latency"] = {"n": len(wall), "es_took_mean_ms": mean(took),
                         "wall_mean_ms": mean(wall), "wall_p50_ms": qs[49], "wall_p95_ms": qs[94],
                         "wall_max_ms": max(wall)}

    # ---- output
    (args.out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    md = to_markdown(report, len(topics), len(kis))
    (args.out / "RESULTS.md").write_text(md, encoding="utf-8")
    print(md)


def to_markdown(r, n_topics, n_ki) -> str:
    def star(p):
        return " *" if p < 0.05 else ""
    L = [f"# Risultati sperimentali\n",
         f"## Topic ad-hoc ({n_topics} query, giudizi = categorie editoriali, profondità {DEPTH})\n",
         "| Sistema | Descrizione | P@10 | R-Prec | MAP | nDCG@10 | R@100 | MAP dev | MAP test |",
         "|---|---|---|---|---|---|---|---|---|"]
    for name, v in r["topics"].items():
        s = r["significance"].get(name, {})
        L.append(f"| {name} | {v['desc']} | {v['P@10']:.3f} | {v['R-Prec']:.3f} | "
                 f"{v['MAP']:.3f}{star(s.get('MAP_p', 1))} | {v['nDCG@10']:.3f}{star(s.get('nDCG@10_p', 1))} | "
                 f"{v['R@100']:.3f} | {v['MAP_dev']:.3f} | {v['MAP_test']:.3f} |")
    L += ["", f"## Known-item ({n_ki} query)\n",
          "| Sistema | MRR | Success@1 | Success@10 | non trovati in top-100 |", "|---|---|---|---|---|"]
    for name, v in r["known_item"].items():
        s = r["significance"].get(name, {})
        L.append(f"| {name} | {v['MRR']:.3f}{star(s.get('KI_MRR_p', 1))} | {v['S@1']:.3f} | "
                 f"{v['S@10']:.3f} | {v['not_found@100']} |")
    L += ["", "\\* differenza rispetto a `full` statisticamente significativa (test di randomizzazione "
              "appaiato, 10.000 permutazioni, p < 0.05).", "",
          "`full` è stato scelto con una grid search sui soli topic *dev* (posizioni pari) e sul known-item; "
          "i topic *test* (posizioni dispari) non sono stati usati per nessuna scelta.", ""]
    lat = r["latency"]
    L += ["## Latenza (profilo di produzione, con faccette ed evidenziazione)\n",
          f"{lat['n']} ricerche: media {lat['wall_mean_ms']:.1f} ms, p50 {lat['wall_p50_ms']:.1f} ms, "
          f"p95 {lat['wall_p95_ms']:.1f} ms, max {lat['wall_max_ms']:.1f} ms "
          f"(tempo interno di Elasticsearch: media {lat['es_took_mean_ms']:.1f} ms).", ""]
    L += ["## MAP per topic\n", "| Topic | Query | #rel | " + " | ".join(r["topics"]) + " |",
          "|---|---|---|" + "---|" * len(r["topics"])]
    for qid, v in r["per_topic"].items():
        L.append(f"| {qid} | {v['query']} | {v['n_rel']} | " +
                 " | ".join(f"{v[s]:.3f}" for s in r["topics"]) + " |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
