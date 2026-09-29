# Repository

Standing document for the harness-kit git repository. Procedure that every consumer shares is `KERNEL.md` and the packs. What a consumer receives in a release is `CHANGELOG.md`. This file is how the kit repository itself is kept.

## What this repo is

A git repository of shared procedure. `new-project` clones one commit of it into a consumer at `.harness/kit`. The pin in that consumer stores the commit. Release rules are `VERSIONING.md`. The current release is the text of `VERSION`, and the tag `v` plus that text.

Work on the kit is logged here, in this repo. A consumer's plans, sessions, and domain law are created in the consumer's repo when `new-project` scaffolds them.

## Records

| Record | What it holds |
|---|---|
| `CHANGELOG.md` | What a consumer gains in each version |
| `VERSION` and tag `v` + version | The release name, on one commit |
| `REPO.md` | This document. How the kit repository is kept |
| `STATUS.md` | Live pointer: last closed piece of work, and what is still open |
| `log/YYYY-MM-DD-<name>.md` | One closed piece of work on this repo |

`0.1.0` and `0.1.1` are in `CHANGELOG.md`. The work log starts at `0.2.0`.

## Closing work on the kit

1. Read `STATUS.md` at the start. Last closed and Open are the whole live picture. Open a log file when that pointer names it.
2. When the piece of work is finished, write one file under `log/`. Name the date, the ask, what landed, and the version if this commit moves `VERSION`.
3. Replace **Last closed** with a link to that file. Keep an **Open** line only while something is still unfinished. Leave older closed work in `log/`. Do not paste it back into `STATUS.md`.
4. A finished log file stays as written. A correction is a new log file, and Last closed moves to it.
5. Run `python3 scripts/test_harness.py`.

Editing `REPO.md`, `STATUS.md`, or `log/` does not by itself move `VERSION`. A procedure change still updates `VERSION` and `CHANGELOG.md` in the same commit, and that commit's log file names the version. The bump class is in `VERSIONING.md`.

## Root of this repo

`plans/`, `sessions/`, and `project/` belong to a consumer. They stay out of this repo's root. A clone is the whole commit, so a project tree committed here would be copied into every consumer's `.harness/kit`.
