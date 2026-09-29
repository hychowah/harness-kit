# Harness kit

This repository is the plugin consumers clone. It is also a git repo, so it keeps its own document and work log. `REPO.md` says how. Consumer plans and sessions are created in the consumer repo.

## Session start

1. Read `VERSIONING.md`, then `KERNEL.md` and `router.md`.
2. Read `VERSION` and the matching section of `CHANGELOG.md`.
3. Read `REPO.md`, then `STATUS.md` (Last closed and Open only). Open a file under `log/` when that pointer names it.
4. Run `python3 scripts/test_harness.py`. If it fails, stop and fix the kit.

## What a change may do

- Tighten procedure that every project can use: router, packs, protocols, schemas, the CLI, the gate.
- Keep the document pack free of any one domain's objects (no tickers, no patent numbers, no product catalogs).
- Keep the coding pack free of any one project's build system. The project's `verify` command lives in that project's `project/project.json`.
- Record finished kit work in `log/` and move the pointer in `STATUS.md`. Standing notes about this repo go in `REPO.md`.

## What a change must not do

- Add a plan, a session, or a domain fact for a single consumer project.
- Add `plans/`, `sessions/`, or `project/` at the root of this repo. A clone would copy them into every consumer.
- Teach the kit a proper noun that is only true in one repo.
- Make `upgrade` rewrite `project/`, `plans/`, or `sessions/` in a consumer project.
- Edit a consumer's `.harness/kit` clone as a substitute for a commit in this repo.
- Leave an old rule restated in `KERNEL.md` or a pack after the version that replaced it. History of procedure lives in `CHANGELOG.md` and in the old tag. History of the work lives in `log/`.
- Bump `VERSION` for a change that only edits `REPO.md`, `STATUS.md`, or `log/`.

## Done

`python3 scripts/test_harness.py` exits 0. A procedure change updates `VERSION` and `CHANGELOG.md` in the same commit, then tags `v` plus the version. The bump class is in `VERSIONING.md`. Minor and patch releases still accept session files written by the previous release.

Finished kit work writes one `log/YYYY-MM-DD-<name>.md` and replaces Last closed in `STATUS.md`. Older closed work stays in `log/`. Open lists only work that is still unfinished.
