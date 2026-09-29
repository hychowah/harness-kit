# 2026-09-29 — Repository record

Version: 0.2.0

The kit is a git repository, so it keeps a project document and a work log. The changelog stays the list of what a consumer gets.

Asked for documentation and logging in this repo, beside `CHANGELOG.md`.

Landed:

- `REPO.md` — standing document for this repository: what the records are, how a piece of kit work closes, and why `plans/`, `sessions/`, and `project/` stay in the consumer.
- `STATUS.md` — live pointer. Last closed names this file.
- `log/` — one file per closed piece of work. This is the first entry. `0.1.0` and `0.1.1` remain in the changelog.
- Session start reads `REPO.md` and `STATUS.md`. A log-only edit does not move `VERSION`.

Gate: `python3 scripts/test_harness.py` checks that Last closed names a real log file, and that `plans/`, `sessions/`, and `project/` are absent at the repo root.
