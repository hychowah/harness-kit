# Harness kit

This repository is the plugin. It is not a project.

## Session start

1. Read `KERNEL.md` and `router.md`.
2. Read `VERSION` and `CHANGELOG.md`.
3. Run `python3 scripts/test_harness.py`. If it fails, stop and fix the kit.

## What a change may do

- Tighten procedure that every project can use: router, packs, protocols, schemas, the CLI, the gate.
- Keep the document pack free of any one domain's objects (no tickers, no patent numbers, no product catalogs).
- Keep the coding pack free of any one project's build system. The project's `verify` command lives in that project's `project/project.json`.

## What a change must not do

- Add a plan, a session, or a domain fact for a single project.
- Teach the kit a proper noun that is only true in one repo.
- Make `upgrade` rewrite `project/`, `plans/`, or `sessions/` in a consumer project.

## Done

`python3 scripts/test_harness.py` exits 0, and `VERSION` moves when the procedure changes. Record the move in `CHANGELOG.md`.
