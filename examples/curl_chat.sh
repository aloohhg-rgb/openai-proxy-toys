#!/usr/bin/env bash
# Hit the local proxy as if it were OpenAI.
set -euo pipefail
BASE="${BASE:-http://127.0.0.1:18080}"
curl -s "$BASE/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "local-whatever",
    "messages": [{"role":"user","content":"ping"}],
    "max_tokens": 16
  }' | head -c 2000
echo
