# Harness kit

This repository is the plugin consumers clone. It is also a git repo, so it keeps its own document and work log. `REPO.md` says how. Consumer plans and sessions are created in the consumer repo.

## Session start

1. Read `VERSIONING.md`, then `KERNEL.md` and `router.md`.
2. The version is `git rev-parse HEAD`. Read `STATUS.md` only after that hash is the commit you mean to work from.
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
- Edit a consumer's `harness-kit/` submodule as a substitute for a commit in this repo.
- Leave an old rule restated in `KERNEL.md` or a pack after the commit that replaced it. History of the work lives in `log/`. The old commit still has the old rule.
- Treat uncommitted edits as a version. Commit first. The new hash is the version.

## Done

`python3 scripts/test_harness.py` exits 0. The change is one commit. That commit hash is the version a project records as its `harness-kit` submodule. `VERSIONING.md` says why a dirty tree cannot be recorded.

Finished kit work writes one `log/YYYY-MM-DD-<name>.md` and replaces Last closed in `STATUS.md`. Older closed work stays in `log/`. Open lists only work that is still unfinished.
