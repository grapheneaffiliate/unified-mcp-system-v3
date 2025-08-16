#!/usr/bin/env bash
# Smoke tests for the Unified MCP System
# Tests all critical endpoints to ensure they work

set -euo pipefail

APP=${APP:-http://localhost:8001}
MCP=${MCP:-http://localhost:8000}

echo "🧪 Running smoke tests for Unified MCP System"
echo "================================================"

echo "📋 Testing /v1/models endpoint..."
curl -sS ${APP}/v1/models | jq . || echo "❌ /v1/models failed"

echo ""
echo "💬 Testing non-streaming chat completion..."
curl -sS ${APP}/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer dev-key-123' \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello, respond with just: Hello from MCP!"}],
    "max_tokens": 50
  }' | jq . || echo "❌ Non-streaming chat failed"

echo ""
echo "🌊 Testing streaming chat completion..."
curl -sS -N ${APP}/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer dev-key-123' \
  -d '{
    "model": "gpt-4",
    "stream": true,
    "messages": [{"role": "user", "content": "Count from 1 to 3"}],
    "max_tokens": 30
  }' || echo "❌ Streaming chat failed"

echo ""
echo "🔧 Testing function calling..."
curl -sS ${APP}/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer dev-key-123' \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "List files in current directory"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "list_files",
        "description": "List files in a directory",
        "parameters": {
          "type": "object",
          "properties": {
            "path": {"type": "string", "description": "Directory path"}
          },
          "required": ["path"]
        }
      }
    }]
  }' | jq . || echo "❌ Function calling failed"

echo ""
echo "🏥 Testing health endpoints..."
curl -sS ${APP}/health | jq . || echo "❌ LC MCP App health failed"
curl -sS ${MCP}/health | jq . || echo "❌ MCP Server health failed"

echo ""
echo "📊 Testing metrics endpoints..."
curl -sS ${APP}/metrics || echo "❌ LC MCP App metrics failed"
curl -sS ${MCP}/metrics || echo "❌ MCP Server metrics failed"

echo ""
echo "🛠️ Testing direct tool execution..."
curl -sS ${MCP}/tools \
  -H 'Content-Type: application/json' | jq . || echo "❌ Tool listing failed"

echo ""
echo "✅ Smoke tests completed!"
echo "If you see any ❌ errors above, check that both services are running:"
echo "  - MCP Server: ${MCP}"
echo "  - LC MCP App: ${APP}"
