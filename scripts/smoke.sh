#!/usr/bin/env bash
set -euo pipefail
BASE="${BASE:-http://127.0.0.1:18080}"
echo "GET $BASE/v1/models"
curl -sS -o /tmp/proxy_models.json -w "http %{http_code}\n" "$BASE/v1/models" || true
head -c 500 /tmp/proxy_models.json 2>/dev/null || true
echo
