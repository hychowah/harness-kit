# Session protocol

A session is one pass of work on one plan. It lives in the project repo.

## Files

```text
sessions/<id>/session.json
sessions/<id>/session.md
sessions/<id>/handoffs/
```

The pack's `pack.json` names the phase files (`brief.md`, `baseline.md`, `audit.md`, `verify.md`).

## Required links

- `project_id` matches `project/project.json`.
- `plan_id` names an open plan in this project. The session's pack matches the plan's pack.
- `writes` lists project-relative paths this session may change. `new-session` starts the list with the plan's `plan.md`.
- `harness_commit` is the kit commit hash at creation. `upgrade` does not change it.
- A coding session also sets `feature_id` to a row in `project/features.json`.

## Phases

`harness.py phase --to <phase>` checks `preflight` in the pack, then moves `session.json`. Skipping a file the next phase needs is a failed preflight, not a judgment call.

`close-session` requires the pack's `closed` preflight files, sets `immutable`, and writes `fingerprint`.

## Resume

Resume only the session the user named. A new session does not open another session's prose to reuse its conclusion. It may read sources the plan lists under `paths`.

## Immutability

After close, `check` recomputes the fingerprint. A mismatch means the sealed text changed. Write a new session that points at the same plan.
