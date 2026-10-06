#!/bin/zsh
# Build dist/RoadDraft.app: RoadDraft with its own Python, opened like any Mac
# app. Makes or refreshes the build environment (.venv-build) and the icons
# first, so this one script is the whole build.
set -e
cd "$(dirname "$0")/.."
./scripts/build_env.sh
.venv-build/bin/python packaging/make_icons.py
.venv-build/bin/pyinstaller --noconfirm --clean --log-level WARN \
  --distpath dist --workpath build/pyinstaller packaging/RoadDraft.spec
echo "Built $(pwd)/dist/RoadDraft.app ($(du -sh dist/RoadDraft.app | cut -f1))"
