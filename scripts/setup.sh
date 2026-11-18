#!/usr/bin/env bash
# One-shot setup: virtualenv, dump download, parsing, Elasticsearch, indexing.
# Usage: ./scripts/setup.sh   (from the project root)
set -euo pipefail
cd "$(dirname "$0")/.."

DUMP_URL="https://dumps.wikimedia.org/other/enterprise_html/runs/20250320/itwikinews-NS0-20250320-ENTERPRISE-HTML.json.tar.gz"
DUMP="data/raw/itwikinews.json.tar.gz"

echo "==> Python virtualenv"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

echo "==> Dump (~73 MB)"
mkdir -p data/raw data/processed
[ -f "$DUMP" ] || curl -fL --progress-bar -o "$DUMP" "$DUMP_URL"

echo "==> Parsing"
.venv/bin/python src/parse_dump.py "$DUMP" data/processed/articles.jsonl > /dev/null

echo "==> Elasticsearch"
docker compose up -d
until curl -s localhost:9200/_cluster/health | grep -qE '"status":"(green|yellow)"'; do sleep 2; done

echo "==> Indexing"
.venv/bin/python src/index_articles.py data/processed/articles.jsonl --recreate

echo
echo "Done. Start the web app with:"
echo "  .venv/bin/uvicorn src.web.app:app --port 8000"
