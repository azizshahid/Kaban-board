#!/usr/bin/env bash
# Starts the Productivity Board on 127.0.0.1:5000 (local only, debug off).
set -euo pipefail
cd "$(dirname "$0")"

# Separate from any Windows "venv" folder (those have Scripts/, not bin/)
VENV=".venv-linux"
[ -f "$VENV/bin/activate" ] || python3 -m venv "$VENV"
source "$VENV/bin/activate"
python -c "import flask" 2>/dev/null || pip install --quiet flask

echo "Productivity Board: http://127.0.0.1:5000/  (Ctrl+C to stop)"
exec python backend/app.py
