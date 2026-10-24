#!/bin/bash
# Double-click to set up (first run) and start Hire an Agent at http://localhost:8000
cd "$(dirname "$0")" || exit 1
if [ ! -d .venv ]; then
  echo "First run: creating .venv and installing dependencies..."
  python3 -m venv .venv || { echo "python3 not found. Install Python 3.10+ and try again."; read -r; exit 1; }
  .venv/bin/python -m pip install -q -r requirements-dev.txt || { echo "Dependency install failed."; read -r; exit 1; }
fi
echo "Starting server at http://localhost:8000 (close this window to stop)"
exec .venv/bin/python server.py
