#!/usr/bin/env bash
set -euo pipefail

# Endpoints (override in CI if needed)
APP="${APP:-http://localhost:8001}"     # lc_mcp_app
MCP="${MCP:-http://localhost:8000}"     # mcp-server

JQ="${JQ:-jq}"                           # pretty-print helper

jsonpp() {
  if command -v "$JQ" >/dev/null 2>&1; then "$JQ" .; else python -m json.tool; fi
}

wait_ready() {
  local url="$1" name="$2" tries=60
  echo "⏳ waiting for $name at $url ..."
  for i in $(seq 1 "$tries"); do
    if curl -fsS "$url" >/dev/null; then
      echo "✅ $name is ready"
      return 0
    fi
    sleep 2
  done
  echo "❌ $name did not become healthy at $url" >&2
  return 1
}

require_contains() {
  local needle="$1" || true
  if ! grep -q "$needle"; then
    echo "❌ expected output to contain: $needle" >&2
    exit 1
  fi
}

echo "=== SMOKE: health checks ==="
wait_ready "${MCP}/health" "MCP server"
wait_ready "${APP}/health" "LC MCP app"

echo
echo "=== SMOKE: /v1/models ==="
MODELS_JSON="$(curl -fsS "${APP}/v1/models")"
echo "$MODELS_JSON" | jsonpp
echo "$MODELS_JSON" | grep -q '"object":"list"'
echo "$MODELS_JSON" | grep -q '"object": "list"' || true  # tolerate spaced variant
echo "$MODELS_JSON" | grep -q '"data"' || (echo "no data array in /v1/models" && exit 1)

echo
echo "=== SMOKE: non-streaming chat completion ==="
NONSTREAM_JSON="$(
  curl -fsS "${APP}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d '{"model":"mcp-proxy","messages":[{"role":"user","content":"hello"}]}'
)"
echo "$NONSTREAM_JSON" | jsonpp
echo "$NONSTREAM_JSON" | grep -q '"object":"chat.completion"'

echo
echo "=== SMOKE: streaming chat completion ==="
# Capture a few lines; require at least one chunk object
STREAM_OK=0
# shellcheck disable=SC2034
while IFS= read -r line; do
  echo "$line"
  if echo "$line" | grep -q '"object":"chat.completion.chunk"'; then
    STREAM_OK=1
    break
  fi
done < <(curl -fsS -N "${APP}/v1/chat/completions" \
          -H 'Content-Type: application/json' \
          -d '{"model":"mcp-proxy","stream":true,"messages":[{"role":"user","content":"stream please"}]}')
if [[ "$STREAM_OK" -ne 1 ]]; then
  echo "❌ did not observe a streaming chunk" >&2
  exit 1
fi
echo "✅ streaming emitted a chunk"

echo
echo "=== SMOKE: real MCP tool call (read_file) ==="
TOOL_JSON="$(
  curl -fsS "${MCP}/tools/read_file" \
    -H 'Content-Type: application/json' \
    -d '{"path":"README.md"}'
)"
echo "$TOOL_JSON" | jsonpp
echo "$TOOL_JSON" | grep -qi 'readme' || echo "ℹ️ tool output may not include the word 'readme'—proceeding"

echo
echo "🎉 SMOKE PASS"
