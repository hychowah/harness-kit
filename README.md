# harness-kit

A cloneable agent harness. The kit owns procedure. The project owns facts, plans, sessions, and code.

This draft combines two working harnesses:

- A short router, a class table, named write paths, gaps instead of guesses, and a gate that exits non-zero (from the humanoid research workspace).
- A separate document pack and coding pack, a version pin, phase preflight, an immutable finished session, and a verifier who is not the implementer (from the stock-research platform).

Domain method stays out of this repo. Equity phases, patent cards, sector modules, and site packs belong in the project that uses them. The kit can scaffold the folders. The project fills them.

## Layout

```text
harness-kit/                 this repo — the plugin, versioned on its own
  REPO.md                    standing document for this repo
  STATUS.md                  last closed kit work, and what is still open
  log/                       one file per closed piece of kit work
  CHANGELOG.md               what a consumer gets in each version
  VERSIONING.md              semver, changelog, tags, and how a project takes an update
  KERNEL.md                  rules shared by every project
  router.md                  classify the turn, then open one pack
  worker-contract.md
  packs/document/            research and other document work
  packs/coding/              one feature, baseline, verify
  protocols/                 how plans and sessions link to a project
  schemas/                   shapes the gate checks
  scripts/harness.py         init, plan, session, link, check, upgrade
  templates/                 files copied into a new project once

a project repo
  AGENTS.md                  stub. Upgrade rewrites only the generated block.
  .harness/pin.json          kit version, remote, and commit
  .harness/kit/              nested clone of this repo (gitignored)
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

That clones this repo into `my-app/.harness/kit`, writes the pin, and scaffolds `project/`, `plans/`, and `sessions/`. After that, run the copy inside the project so the pin and the script are the same checkout:

```bash
cd ~/Documents/my-app
python3 .harness/kit/scripts/harness.py new-plan --id first-cut --title "First cut" --pack document
python3 .harness/kit/scripts/harness.py new-session --plan first-cut --id first-cut-notes
python3 .harness/kit/scripts/harness.py check
```

`new-project` needs this kit to be a git repository with at least one commit. A local path is a valid remote. Set a shareable URL later with `pin --remote`.

## What lives where

| Concern | Where it lives | Who changes it |
|---|---|---|
| Classify, packs, gate, worker contract | `.harness/kit/` | Upgrade the kit |
| What this project is, vocabulary, done-conditions | `project/LAW.md` | The project |
| Human map of the project | `project/ARCHITECTURE.md` | The project, in the same change that makes the map stale |
| A plan and the paths it will touch | `plans/<id>/` | The project |
| A session, its phase, its handoffs | `sessions/<id>/` | The project |
| Index of plan ↔ session ↔ path | `project/links.json` | `harness.py link` rebuilds it |
| Verify command for code | `project/project.json` field `verify` | The project |

A session records `project_id`, `plan_id`, and `writes`. A plan records `project_id` and the project paths it covers. `check` fails when those ids do not match `project/project.json`, when a path escapes the project, or when a path points into `.harness/kit`.

## Upgrade

This repository is where versions are cut. A project does not edit `.harness/kit` to invent a local law. Commit and tag the change here (`v` plus `VERSION`), then move the project's clone:

```bash
git -C .harness/kit fetch
git -C .harness/kit checkout vX.Y.Z
python3 .harness/kit/scripts/harness.py upgrade
python3 .harness/kit/scripts/harness.py check
```

The nested clone is gitignored so kit history does not mix into the project diff. The pin is what the project commits.

`upgrade` rewrites `.harness/pin.json` and the generated block in `AGENTS.md`. It leaves `project/`, `plans/`, and `sessions/` alone, and it refuses a dirty kit checkout. A session keeps the `harness_version` it was created with. Minor and patch releases still accept that file. `VERSIONING.md` is the full contract.

Closing a session seals `session.md` and `session.json` with a fingerprint so a later kit does not need old work rewritten.

On a fresh clone of the project, the kit folder is absent until:

```bash
python3 /path/to/harness-kit/scripts/harness.py sync --project .
```

`sync` clones `kit_remote` and checks out `kit_commit` from the pin.

## Commands

Run `python3 .harness/kit/scripts/harness.py <command> --help`.

| Command | Effect |
|---|---|
| `new-project <dir>` | Clone the kit and scaffold a project |
| `sync` | Restore `.harness/kit` from the pin |
| `new-plan` | Add `plans/<id>/` linked to this project |
| `new-feature` | Add a row to `project/features.json` |
| `new-session` | Add `sessions/<id>/` linked to a plan |
| `phase` | Move a session to a later phase after preflight |
| `preflight` | Show the files the next phase still needs |
| `close-session` | Seal the session |
| `close-plan` | Mark a plan closed |
| `mark-pass` | Verifier sets a feature's `passes` flag |
| `link` | Rebuild `project/links.json` and the back-links |
| `check` | Exit non-zero when links, phase, pin, or seal fail |
| `upgrade` | Record the checkout now on disk; refresh the stub |
| `verify` | Run `project.json` `verify`, then `check` |

## Packs

**Document** (`packs/document/LAW.md`). A brief, then gather onto named paths, then an auditor who did not write the claims, then a report only if the brief names one. Missing evidence becomes `project/gaps.md`.

**Coding** (`packs/coding/LAW.md`). One feature from `project/features.json`. Baseline, then implement, then verify. The implementer does not mark `passes: true`. `mark-pass --verifier` refuses while that feature's session is still open.

A project that needs a third procedure adds `project/packs/<id>/` later. This draft ships two packs so the split is real. The kit does not load project packs yet. Add that when a third project actually needs a procedure the two packs cannot host.

## Working on the kit

`AGENTS.md` in this repo is the law for changing the kit. `REPO.md` is this repo's own document: status, work log, and changelog are three different records. `VERSIONING.md` says when `VERSION` moves. `python3 scripts/test_harness.py` is the gate. A change that only makes sense for one project belongs in that project's `project/LAW.md`.
