# harness-kit

A cloneable agent harness. The kit owns procedure. The project owns facts, plans, sessions, and code.

This draft combines two working harnesses:

- A short router, a class table, named write paths, gaps instead of guesses, and a gate that exits non-zero (from the humanoid research workspace).
- A separate document pack and coding pack, a version pin, phase preflight, an immutable finished session, and a verifier who is not the implementer (from the stock-research platform).

Domain method stays out of this repo. Equity phases, patent cards, sector modules, and site packs belong in the project that uses them. The kit can scaffold the folders. The project fills them.

## Reading the workflow

Open [`docs/index.html`](docs/index.html) in a browser. The page draws the router, both packs, the workers, the gate, and an upgrade as flowcharts. The law files remain the procedure.

## Layout

```text
harness-kit/                 this repo — the plugin, versioned on its own
  REPO.md                    standing document for this repo
  STATUS.md                  last closed kit work, and what is still open
  log/                       one file per closed piece of kit work
  CHANGELOG.md               notes from the earlier numbered drafts
  VERSIONING.md              the version is the commit hash; commit before it changes
  KERNEL.md                  rules shared by every project
  router.md                  classify the turn, then open one pack
  worker-contract.md
  packs/document/            documents whose product is claims on disk
  packs/coding/              one feature, baseline, verify
  protocols/                 how plans and sessions link to a project
  schemas/                   shapes the gate checks
  scripts/harness.py         new-project, adopt, check, upgrade
  scripts/pack.py            load a pack graph
  scripts/checks.py          result lines and evidence predicates
  templates/                 files copied into a new project once
  docs/index.html            flowchart of the workflow, for a human reader

a project repo
  AGENTS.md                  stub. Upgrade rewrites only the generated block.
  .gitmodules                submodule URL for harness-kit
  harness-kit/               this repo as a submodule. The parent commit records the hash.
  project/                   domain law, architecture, features, gaps
  plans/<id>/                a plan linked to this project
  sessions/<id>/             a session linked to a plan and to project paths
  project/links.json         rebuildable index of those links
```

## New project

From any directory, point at this kit:

```bash
python3 ~/Documents/harness-kit/scripts/harness.py new-project ~/Documents/my-app --name "My App"
```

That adds this repo as the `my-app/harness-kit/` submodule, records the commit, and scaffolds `project/`, `plans/`, and `sessions/`. After that, run the copy inside the project so the submodule and the script are the same checkout:

```bash
cd ~/Documents/my-app
python3 harness-kit/scripts/harness.py new-plan --id first-cut --title "First cut" --pack document
python3 harness-kit/scripts/harness.py new-session --plan first-cut --id first-cut-notes
python3 harness-kit/scripts/harness.py check
```

`new-project` needs this kit to be a git repository with at least one commit. `.gitmodules` starts as the checkout you cloned from, so an unpushed commit can be restored with `sync`. Set a shareable URL later with `pin --remote`.

## What lives where

| Concern | Where it lives | Who changes it |
|---|---|---|
| Whether this turn is kit work | `project/LAW.md` | The project |
| Class table, packs, gate, worker contract | `harness-kit/` | Upgrade the kit |
| Vocabulary and done-conditions | `project/LAW.md` | The project |
| Human map of the project | `project/ARCHITECTURE.md` | The project, in the same change that makes the map stale |
| A plan and the paths it will touch | `plans/<id>/` | The project |
| A session, its phase, its handoffs | `sessions/<id>/` | The project |
| Index of plan ↔ session ↔ path | `project/links.json` | `harness.py link` rebuilds it |
| Verify command for code | `project/project.json` field `verify` | The project |

A session records `project_id`, `plan_id`, and `writes`. A plan records `project_id` and the project paths it covers. `check` fails when those ids do not match `project/project.json`, when a path escapes the project, or when a path points into `harness-kit/`.

## Upgrade

This repository is where versions are cut, and a version is a commit hash. A project does not edit `harness-kit/` to invent a local law. Commit here first. Then move the project's submodule to that hash:

```bash
git -C harness-kit fetch
git -C harness-kit checkout <commit>
python3 harness-kit/scripts/harness.py upgrade
python3 harness-kit/scripts/harness.py check
```

The submodule commit is what the project records. Kit file history stays in this repository.

`upgrade` stages that commit and rewrites the generated block in `AGENTS.md`. It leaves `project/`, `plans/`, and `sessions/` alone, and it refuses a dirty kit checkout. A session keeps the `harness_commit` it was created with. `VERSIONING.md` is the full contract.

Closing a session seals it with a fingerprint so a later kit does not need old work rewritten. `KERNEL.md` names the sealed bytes.

On a fresh clone of the project, the kit folder is absent until:

```bash
python3 /path/to/harness-kit/scripts/harness.py sync --project .
```

`sync` clones the URL in `.gitmodules` and checks out the recorded submodule commit.

## Commands

Run `python3 harness-kit/scripts/harness.py <command> --help`.

| Command | Effect |
|---|---|
| `new-project <dir>` | Add the kit as a submodule and scaffold an empty project |
| `adopt <dir>` | Attach the kit submodule to a non-empty repo. Writes only missing control files |
| `sync` | Restore `harness-kit/` from the submodule record |
| `new-plan` | Add `plans/<id>/` linked to this project |
| `new-feature` | Add a row to `project/features.json` |
| `new-session` | Add `sessions/<id>/` linked to a plan |
| `phase` | Enter a node (`--to` on one path, `--enter` when the graph forks) |
| `status` | Write one row of `sessions/<id>/status.json` |
| `spawn` | Record a returned worker |
| `abandon` | Seal a session that cannot continue |
| `preflight` | Report whether a node can be entered, without moving |
| `close-session` | Seal the session |
| `close-plan` | Mark a plan closed |
| `mark-pass` | Verifier sets a feature's `passes` flag |
| `link` | Rebuild `project/links.json` and the back-links |
| `check` | Exit non-zero on `FAIL`. `WARN` is printed and does not fail the process |
| `upgrade` | Record the checkout now on disk; refresh the stub |
| `verify` | Run `project.json` `verify`, then `check` |

## Packs

**Document** (`packs/document/LAW.md`). A brief, then gather onto named paths, then an auditor who did not write the claims, then a report only if the brief names one. Missing evidence becomes `project/gaps.md`.

**Coding** (`packs/coding/LAW.md`). One feature from `project/features.json`. Baseline, then implement, then verify. The implementer does not mark `passes: true`. `mark-pass --verifier` refuses while that feature's session is still open.

A project that needs another procedure adds `project/packs/<id>/pack.json` in the same shape as the shipped packs. The kit loads that file and does not import project Python. The same id in both places crashes. Domain checks are an optional command on the pack. It prints `PASS`, `FAIL`, `WARN`, or `SKIPPED` lines. The kit does not interpret those ids.

## Working on the kit

`AGENTS.md` in this repo is the law for changing the kit. `REPO.md` is this repo's own document. `STATUS.md` and `log/` are the work record. `VERSIONING.md` says the version is the commit hash, and that the commit comes first. `python3 scripts/test_harness.py` is the gate. A change that only makes sense for one project belongs in that project's `project/LAW.md`.
