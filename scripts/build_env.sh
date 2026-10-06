#!/bin/zsh
# Make or refresh .venv-build, the environment the desktop app is built from:
# uv's Python 3.13 with PyInstaller, kept apart from the development .venv
# (Xcode's Python 3.9), which the RL environment, the tests and the MCP server
# keep using. Needs uv (https://docs.astral.sh/uv/).
set -e
cd "$(dirname "$0")/.."
UV=$(command -v uv || echo "$HOME/.local/bin/uv")
export UV_LINK_MODE=copy  # the uv cache and this repo sit on different disks
if [ ! -x .venv-build/bin/python ]; then
  "$UV" venv --seed --python 3.13 .venv-build
fi
"$UV" pip install --python .venv-build/bin/python -e ".[dev,desktop,bundle]"
