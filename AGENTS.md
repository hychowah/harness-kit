# Harness kit

This repository is the plugin. It is not a project.

## Session start

1. Read `VERSIONING.md`, then `KERNEL.md` and `router.md`.
2. Read `VERSION` and the matching section of `CHANGELOG.md`.
3. Run `python3 scripts/test_harness.py`. If it fails, stop and fix the kit.

## What a change may do

- Tighten procedure that every project can use: router, packs, protocols, schemas, the CLI, the gate.
- Keep the document pack free of any one domain's objects (no tickers, no patent numbers, no product catalogs).
- Keep the coding pack free of any one project's build system. The project's `verify` command lives in that project's `project/project.json`.

## What a change must not do

- Add a plan, a session, or a domain fact for a single project.
- Teach the kit a proper noun that is only true in one repo.
- Make `upgrade` rewrite `project/`, `plans/`, or `sessions/` in a consumer project.
- Edit a consumer's `.harness/kit` clone as a substitute for a commit in this repo.
- Leave an old rule restated in `KERNEL.md` or a pack after the version that replaced it. History lives in `CHANGELOG.md` and in the old tag.

## Done

`python3 scripts/test_harness.py` exits 0. A procedure change updates `VERSION` and `CHANGELOG.md` in the same commit, then tags `v` plus the version. The bump class is in `VERSIONING.md`. Minor and patch releases still accept session files written by the previous release.
