# Session protocol

A session is one pass of work on one plan. It lives in the project repo.

## Files

```text
sessions/<id>/session.json
sessions/<id>/session.md
sessions/<id>/status.json
sessions/<id>/design.md       coding decision, when this pack uses it
sessions/<id>/review.md       coding critique, when this pack uses it
sessions/<id>/verify.md       coding verify output, when this pack uses it
sessions/<id>/handoffs/<worker>.md   only after a worker returns
sessions/<id>/draft/<path>    first draft, when a human doc is owed
sessions/<id>/return/<path>   the rewrite that ships, when a human doc is owed
sessions/<id>/spawns.json     when a worker was recorded
sessions/<id>/abandon.json    when the session was abandoned
tmp/<id>/                    at the project root. Not sealed. Not a source.
```

`new-session` writes the blank `status.json`. Only `harness.py status` changes a row. `session.json` `phase` is the cursor, not a copy of the checklist.

The id starts with the day, then the feature slug: `2026-10-13-gate`. `new-session` adds today's date when the slug does not already start with `YYYY-MM-DD-`. A bare feature name is not stored as the id. With no `--id`, the slug is the feature id, or the plan id when the pack has no feature.

The pack graph in `pack.json` names entry files and complete evidence.

## Required links

- `project_id` matches `project/project.json`.
- `plan_id` names an open plan in this project. The session's pack matches the plan's pack.
- `writes` is the exact product files in one commit. It starts empty. It is not a copy of the plan, and it is not the session prose. A directory is not a member of the list. `--write` adds an exact file. `close-session --from-diff` replaces the list with the worktree product diff, seals the session, and stages that record. It may do this again only while `HEAD` does not already show the session closed. It does not `mark-pass`. An open plan does not own a path.
- `harness_commit` is the kit commit hash at creation. `project_stamp` is copied from `project/project.json` when that field is set. `upgrade` does not change either. `phase`, `status`, `spawn`, `preflight`, `note-architecture`, `close-session`, and `abandon` run only when that stamp is the pin.
- A pack with `uses_features` sets `feature_id` to a row in `project/features.json`.

## Phases

`phase --to`, `phase --enter`, and `close-session` enter a node when its entry evidence passes and each prior is `complete` or `skipped`, or that prior is the current phase and its complete evidence passes now. An empty evidence list passes. `--to` is only for a single-path pack, refuses a backward move, and refuses `closed`. `preflight` reports that rule and does not move the cursor. None of these commands write `status.json`. `status`, `spawn`, and `check` count a prior only when the checklist says `complete` or `skipped`.

`close-session` enters `closed` by that rule, then grades the session with `phase` set to `closed` in memory. The grade is the FAIL rows for the phase id, the checklist, spawns, and the feature link, plus complete evidence for every checklist row marked complete, plus the closed node's complete evidence even when that checklist row is still pending. A closed session also fails `docs.reader` or `docs.map` when `protocols/docs.md` says a reader is owed. It writes `immutable` and `fingerprint` when that grade has no FAIL row. A SKIPPED row is printed by `check` and does not block the seal or the process. Otherwise the session stays open. `check` appends the same list when the stamp door says grade. `abandon` seals the session without entering `closed`, without moving the cursor, and without that grade. A later `phase` on an abandoned session stops.

## Scratch

`tmp/<session-id>/` holds temporary scripts, data, and working notes for that session. It is not sealed. It is not a source.

A direct child of `tmp/` is kept only when it is a directory whose name is an open session id, or a regular file named `README.md`. Every other child is removed. A symlink is unlinked and not followed. `tmp` itself is not removed.

`new-session` creates `tmp/<session-id>/`, then runs that removal. `close-session` and `abandon` run it after the seal is written. `clean-tmp` runs it on its own. `check` does not.

## Resume

Resume only the session the user named. A new session does not open another session's prose to reuse its conclusion. It may read sources the plan lists under `paths`.

## Immutability

After close, `check` recomputes the fingerprint. A mismatch means the sealed text changed. Write a new session that points at the same plan.
