# Kernel

Rules that apply in every project. Domain facts live in that project's `project/LAW.md`.

## Boundary

The kit checkout is `harness-kit/` at the project root. It is a git submodule. The pin is the submodule commit the parent repository records. The checkout is not a copy of the kit's files in the parent diff. Do not edit it. A path under `harness-kit/` is a kit path, not a product path. The project is everything else the kit scaffolds: `project/`, `plans/`, `sessions/`, and the stub `AGENTS.md`. There is one location.

Procedure is upgradable. A project fact is not. If a rule names a file that only one project has, it belongs in `project/LAW.md`.

`upgrade` may stage the submodule commit and rewrite the generated block in `AGENTS.md`. It leaves plans, sessions, and domain law untouched. `pin --remote` may rewrite the submodule URL in `.gitmodules` and does not move that commit.

## Disk is the record

A conclusion that exists only in chat does not exist for the next session. Plans, sessions, handoffs, gaps, and feature rows are files.

## Classify, then open one law

This section applies only after `project/LAW.md` has classified the turn as kit work. A turn that file keeps is not classified here.

`router.md` names the class. A work session names one pack. Read that pack's `LAW.md`. Then read `project/LAW.md` again for vocabulary and done-conditions. Project law wins on vocabulary and done-conditions. Kit law wins on sessions, links, workers, and the gate.

## Parent and workers

The parent classifies, names write paths, and merges. A worker does not spawn workers. Workers return paths, coverage, and gaps. They do not paste the sources into the parent.

Write paths stay inside the project. A path under `harness-kit/` is a kit path, not a product path.

## Generator and evaluator

The session that writes an artifact does not grade it. Document work records the grade in `audit.md`. Coding work leaves `passes: false` until `mark-pass --verifier`, and that command refuses while the feature's session is still open.

## Gate

`harness.py check` is the gate. A session is done when `check` exits 0 after `close-session`. Prose that says "please follow the rules" is not a gate.

## Gaps

When a source does not say a fact, add a row to `project/gaps.md` (document pack) or a gap section in the session. Do not fill the hole with a fluent sentence.

## Version

The harness kit is a separate git repository. The version is the commit hash. `VERSIONING.md` is that contract. A project holds that repository as the `harness-kit/` submodule. The parent records the commit. `.gitmodules` records the remote. There is no pin file.

Do not edit law files inside the submodule. A procedure change is a commit in the kit repository. Commit before the version changes. The project checks out that commit and runs `upgrade`, which stages the submodule commit and rewrites the generated `AGENTS.md` block. `VERSIONING.md` says what happens when the checkout is dirty or `HEAD` is not the recorded commit.

Each session copies `harness_commit` at creation. `upgrade` does not change it. If a later commit makes `check` reject an older session file, `log/` says so before a project moves its pin.

`close-session` and `abandon` store a fingerprint of the canonical `session.json` (every field except `fingerprint`), a NUL, the bytes of `session.md`, and then, for each of `abandon.json`, `status.json`, and `spawns.json` that exists, another NUL plus that file's bytes, in that order. Those text files are hashed as UTF-8 with newlines normalized to LF. A file that is not UTF-8 fails the seal. `check` fails if those bytes change afterward. The fingerprint catches an accidental edit. It is not an access control. Evidence outside that set is graded again by `check`. It is not copied into the hash.

## Depth

A plan carries `depth`: `low`, `medium`, or `high`.

| Depth | Document pack | Coding pack |
|---|---|---|
| `low` | One worker, one write path | Read the feature, then baseline |
| `medium` | A few workers, non-overlapping paths | Default. One feature. |
| `high` | Broad gather, still non-overlapping paths, one report writer | Explore, then one feature. The feature does not get larger. |

## Exemplars

A contrastive quality pair lives in the project's `project/exemplars/` and is not kit law. Files in this repo's `exemplars/` are shapes only.

## Links

Every plan and session stores `project_id` from `project/project.json`. A session stores `plan_id` and `writes`. A plan stores the project paths it covers. `project/links.json` is the index. `harness.py link` rebuilds it. `check` fails if the index is stale or a link does not resolve.
