#!/bin/zsh
# Double-clickable launcher for the RoadDraft GUI (macOS).
# Starts the local web app and opens it in your browser.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/roaddraft-web ]; then
  echo "First run: creating environment..."
  python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"
fi
exec .venv/bin/roaddraft-web "$@"
