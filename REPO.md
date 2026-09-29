# Repository

Standing document for the harness-kit git repository. Procedure that every consumer shares is `KERNEL.md` and the packs. This file is how the kit repository itself is kept.

## What this repo is

A git repository of shared procedure. `new-project` clones one commit of it into a consumer at `.harness/kit`. The pin stores that commit hash. The hash is the version. `VERSIONING.md` says to commit before that hash can change.

Work on the kit is logged here, in this repo. A consumer's plans, sessions, and domain law are created in the consumer's repo when `new-project` scaffolds them.

## Records

| Record | What it holds |
|---|---|
| The commit hash | The version. `git rev-parse HEAD` in this repo, `kit_commit` in a project's pin |
| `CHANGELOG.md` | Notes from the earlier numbered drafts |
| `REPO.md` | This document. How the kit repository is kept |
| `STATUS.md` | Live pointer: last closed piece of work, and what is still open |
| `log/YYYY-MM-DD-<name>.md` | One closed piece of work on this repo |

The numbered drafts `0.1.0`, `0.1.1`, and `0.2.0` are in `CHANGELOG.md` and in git. The hash is the reference after that.

## Closing work on the kit

1. Read `STATUS.md` at the start. Last closed and Open are the whole live picture. Open a log file when that pointer names it.
2. When the piece of work is finished, commit it. That commit is the version. Write one file under `log/`. Name the date, the ask, and what landed.
3. Replace **Last closed** with a link to that file. Keep an **Open** line only while something is still unfinished. Leave older closed work in `log/`. Do not paste it back into `STATUS.md`.
4. A finished log file stays as written. A correction is a new log file, and Last closed moves to it.
5. Run `python3 scripts/test_harness.py`.

A log entry can land in the same commit as the work it describes. The version still changes only when that commit exists. `VERSIONING.md` is the rule.

## Root of this repo

`plans/`, `sessions/`, and `project/` belong to a consumer. They stay out of this repo's root. A clone is the whole commit, so a project tree committed here would be copied into every consumer's `.harness/kit`.
