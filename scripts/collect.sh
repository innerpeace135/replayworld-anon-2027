#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

QUERIES="${QUERIES:?set QUERIES to a JSONL file of task queries, one JSON object with a query field per line}"
: "${SHOPPINGBENCH_URL:?set SHOPPINGBENCH_URL to the address of the ShoppingBench API}"
: "${TOOLBENCH_ANSWER_DIR:?set TOOLBENCH_ANSWER_DIR to the answer files of the ToolBench release}"
TRACES=data/webshop/collected
mkdir -p "$TRACES"

python -m collect.shoppingbench --queries "$QUERIES" --server "$SHOPPINGBENCH_URL" --output "$TRACES/shoppingbench.jsonl"
python -m collect.browsergym --queries "$QUERIES" --output "$TRACES/browsergym.jsonl"
python -m collect.toolbench --answers "$TOOLBENCH_ANSWER_DIR" --sample 215 --output "$TRACES/toolbench.jsonl"
python -m collect.mind2web --sample 169 --output "$TRACES/mind2web.jsonl"

python -m collect.split "$@" --traces \
  "$TRACES/shoppingbench.jsonl" "$TRACES/browsergym.jsonl" "$TRACES/toolbench.jsonl" "$TRACES/mind2web.jsonl"
