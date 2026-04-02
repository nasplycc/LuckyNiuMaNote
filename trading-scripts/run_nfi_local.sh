#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ ! -d .venv ]; then
  echo "[error] missing virtualenv: .venv"
  echo "run: cd trading-scripts && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

source .venv/bin/activate

if [ ! -f config/.hl_config ]; then
  echo "[error] missing config/.hl_config"
  echo "run: cp config/.hl_config.sample config/.hl_config"
  exit 1
fi

if [ ! -f config/.runtime_config.json ]; then
  echo "[warn] missing config/.runtime_config.json, creating from sample"
  cp config/.runtime_config.sample.json config/.runtime_config.json
fi

echo "[info] starting NFI trader in current shell"
python scripts/auto_trader_nostalgia_for_infinity.py
