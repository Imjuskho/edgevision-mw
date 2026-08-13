#!/usr/bin/env bash
# End-to-end smoke test for EdgeVision Studio API + route availability.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="${API_BASE:-http://localhost:8000}"
FRONTEND="${FRONTEND_BASE:-http://localhost:3000}"
EMAIL="${E2E_EMAIL:-admin@edgevision.mw}"
PASSWORD="${E2E_PASSWORD:-admin123}"

pass=0
fail=0

check() {
  local name="$1"
  local cmd="$2"
  if eval "$cmd" >/dev/null 2>&1; then
    echo "  OK  $name"
    pass=$((pass + 1))
  else
    echo "  FAIL $name"
    fail=$((fail + 1))
  fi
}

echo "=== EdgeVision E2E Smoke ==="
echo "API: $API  Frontend: $FRONTEND"

TOKEN=""
login_resp="$(curl -sf -X POST "$API/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" 2>/dev/null || true)"
if [[ -n "$login_resp" ]]; then
  TOKEN="$(python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))" <<<"$login_resp")"
fi

if [[ -z "$TOKEN" ]]; then
  echo "WARN: Could not log in as $EMAIL — API checks will be skipped."
else
  echo ""
  echo "Auth"
  check "GET /api/v1/auth/me" "curl -sf -H 'Authorization: Bearer $TOKEN' '$API/api/v1/auth/me'"

  echo ""
  echo "Studio API"
  check "GET /api/v1/datasets/" "curl -sf -H 'Authorization: Bearer $TOKEN' '$API/api/v1/datasets/?page=1&page_size=5'"
  DATASET_ID="$(curl -sf -H "Authorization: Bearer $TOKEN" "$API/api/v1/datasets/?page=1&page_size=1" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); items=d.get('items') or d.get('data',{}).get('items') or []; print(items[0]['dataset_id'] if items else '')" 2>/dev/null || true)"
  if [[ -n "$DATASET_ID" ]]; then
    check "GET dataset health" "curl -sf -H 'Authorization: Bearer $TOKEN' '$API/api/v1/studio/datasets/$DATASET_ID/health'"
    check "POST annotation session" "curl -sf -X POST -H 'Authorization: Bearer $TOKEN' -H 'Content-Type: application/json' -d '{\"dataset_id\":\"'$DATASET_ID'\"}' '$API/api/v1/studio/sessions'"
  else
    echo "  SKIP dataset-scoped API (no datasets)"
  fi

  echo ""
  echo "Global routes"
  for path in queue assign review nodes road-taxonomy agri-taxonomy; do
    check "GET /$path" "curl -sf -o /dev/null -w '%{http_code}' '$FRONTEND/$path' | grep -q '^200$'"
  done

  echo ""
  echo "Dataset-scoped frontend routes"
  if [[ -n "$DATASET_ID" ]]; then
    for suffix in "" "/annotate" "/upload" "/health" "/dedup" "/export" "/road-analysis" "/agri-analysis" "/training" "/live-annotate" "/segment" "/review/fast"; do
      check "GET /datasets/$DATASET_ID$suffix" "curl -sf -o /dev/null -w '%{http_code}' '$FRONTEND/datasets/$DATASET_ID$suffix' | grep -q '^200$'"
    done
  fi
fi

echo ""
echo "Backend pytest (live annotation)"
cd "$ROOT"
if POSTGRES_HOST=localhost "$ROOT/.venv/bin/python" -m pytest tests/test_live_annotation_ws.py tests/test_live_annotation.py -q --tb=no 2>/dev/null; then
  echo "  OK  live annotation tests"
  pass=$((pass + 1))
else
  echo "  FAIL live annotation tests"
  fail=$((fail + 1))
fi

echo ""
echo "=== Results: $pass passed, $fail failed ==="
[[ "$fail" -eq 0 ]]
