# Kernel

Rules that apply in every project. Domain facts live in that project's `project/LAW.md`.

## Boundary

The kit is `.harness/kit`. The project is everything else in the project repo that the kit scaffolds: `project/`, `plans/`, `sessions/`, and the stub `AGENTS.md`.

Procedure is upgradable. A project fact is not. If a rule names a file that only one project has, it belongs in `project/LAW.md`.

`upgrade` may rewrite `.harness/pin.json` and the generated block in `AGENTS.md`. It leaves plans, sessions, and domain law untouched.

## Disk is the record

A conclusion that exists only in chat does not exist for the next session. Plans, sessions, handoffs, gaps, and feature rows are files.

## Classify, then open one law

`router.md` names the class. A work session names one pack. Read that pack's `LAW.md`. Then read `project/LAW.md`. Project law wins on vocabulary and done-conditions. Kit law wins on sessions, links, workers, and the gate.

## Parent and workers

The parent classifies, names write paths, and merges. A worker does not spawn workers. A spawn without write paths is invalid. Workers return paths, coverage, and gaps. They do not paste the sources into the parent.

Write paths stay inside the project. A path under `.harness/` is a kit path, not a product path.

## Generator and evaluator

The session that writes an artifact does not grade it. Document work records the grade in `audit.md`. Coding work leaves `passes: false` until `mark-pass --verifier`, and that command refuses while the feature's session is still open.

## Gate

`harness.py check` is the gate. A session is done when `check` exits 0 after `close-session`. Prose that says "please follow the rules" is not a gate.

## Gaps

When a source does not say a fact, add a row to `project/gaps.md` (document pack) or a gap section in the session. Do not fill the hole with a fluent sentence.

## Version

The harness kit is a separate git repository. `VERSIONING.md` in that repo is the release contract: semver, changelog, and tags. A project holds a clone at `.harness/kit` and a pin at `.harness/pin.json` (version, remote, commit).

Do not edit law files inside the clone. A procedure change is a commit in the kit repository. The project checks out that commit and runs `upgrade`, which rewrites the pin and the generated `AGENTS.md` block. `check` fails when the clone is dirty or its `HEAD` is not the pinned commit.

Each session copies `harness_version` at creation. `upgrade` does not change it. A minor or patch release still accepts that session file. A major release names the break in `CHANGELOG.md`.

`close-session` stores a fingerprint of `session.json` (except the fingerprint field) and `session.md`. `check` fails if those bytes change afterward. The fingerprint catches an accidental edit. It is not an access control.

## Depth

A plan carries `depth`: `low`, `medium`, or `high`.

| Depth | Document pack | Coding pack |
|---|---|---|
| `low` | One worker, one write path | Read the feature, then baseline |
| `medium` | A few workers, non-overlapping paths | Default. One feature. |
| `high` | Broad gather, still non-overlapping paths, one report writer | Explore, then one feature. The feature does not get larger. |

## Links

Every plan and session stores `project_id` from `project/project.json`. A session stores `plan_id` and `writes`. A plan stores the project paths it covers. `project/links.json` is the index. `harness.py link` rebuilds it. `check` fails if the index is stale or a link does not resolve.
