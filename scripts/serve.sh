#!/bin/bash
# One-shot server launcher. Replaces:
#   cd ~/Codes/onshape-mcp
#   source .venv/bin/activate
#   python3 -m onshape_mcp.server
#
# Usage:
#   ./scripts/serve.sh           # foreground (Ctrl+C to stop)
#
# Why no --background: MCP servers speak stdio JSON-RPC, so they need
# a live stdin/stdout pair attached to an MCP client. Backgrounding with
# stdin closed makes the server exit immediately. To leave the server
# running while you do other things, run this in a separate terminal
# (tmux, screen, or just another tab). To call it from a script, pipe
# JSON-RPC messages in via stdin.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -d .venv ]; then
  echo "[serve.sh] no venv found, running bootstrap"
  python3 scripts/bootstrap.py
fi

# shellcheck disable=SC1091
source .venv/bin/activate

exec python3 -m onshape_mcp.server
