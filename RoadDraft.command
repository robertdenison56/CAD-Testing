#!/bin/zsh
# Double-clickable launcher for RoadDraft (macOS): opens the app in a window
# of its own. `RoadDraft.command --browser` opens the GUI in your browser.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/roaddraft-desktop ]; then
  echo "First run: setting up the environment..."
  python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev,desktop]"
fi
if [ "$1" = "--browser" ]; then
  shift
  exec .venv/bin/roaddraft-web "$@"
fi
exec .venv/bin/roaddraft-desktop "$@"
