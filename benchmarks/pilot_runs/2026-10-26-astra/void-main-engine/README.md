# Void: served by main's engine

These twelve episodes ran in the 2:48 AM window of 2026-10-27. The resume
script set `PYTHONPATH=src` (relative); the Codex CLI starts `roaddraft-mcp`
in each episode's `project/` folder, where that names nothing, so the server
imported the editable install -- the main checkout's engine (0e464b6f at the
time), not the pilot-astra branch the run pins. Their traces, saves and
reports are kept here for the record and count for nothing; each probe is
rerun with `--force` on the right engine. The runner now refuses to start
when the served engine is not its own (`runners.core.check_engine`).
