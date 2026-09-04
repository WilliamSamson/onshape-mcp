#!/bin/bash
# One-shot launcher. Two modes:
#   ./scripts/serve.sh             # MCP stdio server (for Claude Code, Cursor, …)
#   ./scripts/serve.sh web         # Gemini-MCP web client on http://127.0.0.1:8765
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -d .venv ]; then
  echo "[serve.sh] no venv found, running bootstrap"
  python3 scripts/bootstrap.py
fi

# shellcheck disable=SC1091
source .venv/bin/activate
unset PYTHONPATH

if [ "${1:-}" = "web" ]; then
  exec python3 scripts/web_client.py
fi

exec python3 -m onshape_mcp.server

