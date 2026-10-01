# Session protocol

A session is one pass of work on one plan. It lives in the project repo.

## Files

```text
sessions/<id>/session.json
sessions/<id>/session.md
sessions/<id>/status.json
sessions/<id>/handoffs/
sessions/<id>/spawns.json    when a worker was recorded
sessions/<id>/abandon.json   when the session was abandoned
```

`new-session` writes the blank `status.json`. Only `harness.py status` changes a row. `session.json` `phase` is the cursor, not a copy of the checklist.

The pack graph in `pack.json` names entry files and complete evidence.

## Required links

- `project_id` matches `project/project.json`.
- `plan_id` names an open plan in this project. The session's pack matches the plan's pack.
- `writes` lists project-relative paths this session may change. `new-session` starts the list with the plan's `plan.md`.
- `harness_commit` is the kit commit hash at creation. `project_stamp` is copied from `project/project.json` when that field is set. `upgrade` does not change either. `phase`, `status`, `spawn`, `preflight`, `note-architecture`, `close-session`, and `abandon` run only when that stamp is the pin.
- A pack with `uses_features` sets `feature_id` to a row in `project/features.json`.

## Phases

`phase --to`, `phase --enter`, and `close-session` enter a node when its entry evidence passes and each prior is `complete` or `skipped`, or that prior is the current phase and its complete evidence passes now. An empty evidence list passes. `--to` is only for a single-path pack, refuses a backward move, and refuses `closed`. `preflight` reports that rule and does not move the cursor. None of these commands write `status.json`. `status`, `spawn`, and `check` count a prior only when the checklist says `complete` or `skipped`.

`close-session` enters `closed` by that rule, then grades the session with `phase` set to `closed` in memory. The grade is the FAIL rows for the phase id, the checklist, spawns, and the feature link, plus complete evidence for every checklist row marked complete, plus the closed node's complete evidence even when that checklist row is still pending. It writes `immutable` and `fingerprint` when that grade has no FAIL row. A SKIPPED row is printed by `check` and does not block the seal or the process. Otherwise the session stays open. `check` appends the same list when the stamp door says grade. `abandon` seals the session without entering `closed`, without moving the cursor, and without that grade. A later `phase` on an abandoned session stops.

## Resume

Resume only the session the user named. A new session does not open another session's prose to reuse its conclusion. It may read sources the plan lists under `paths`.

## Immutability

After close, `check` recomputes the fingerprint. A mismatch means the sealed text changed. Write a new session that points at the same plan.
