#!/bin/bash
# One-shot server launcher. Replaces:
#   cd ~/Codes/onshape-mcp
#   source .venv/bin/activate
#   python3 -m onshape_mcp.server
#
# Usage:
#   ./scripts/serve.sh
#   ./scripts/serve.sh --background   # log to logs/serve.log, return immediately
#
# What it does:
#   1. cd to repo root
#   2. Run bootstrap if .venv is missing
#   3. Activate venv
#   4. exec into python -m onshape_mcp.server
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -d .venv ]; then
  echo "[serve.sh] no venv found, running bootstrap"
  python3 scripts/bootstrap.py
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [ "${1:-}" = "--background" ]; then
  mkdir -p logs
  nohup python3 -m onshape_mcp.server > logs/serve.log 2>&1 &
  echo "[serve.sh] started, pid=$!, log=$REPO_ROOT/logs/serve.log"
  echo "[serve.sh] stop with: kill $!"
  exit 0
fi

exec python3 -m onshape_mcp.server
