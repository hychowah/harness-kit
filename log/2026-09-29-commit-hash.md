# 2026-09-29 — Commit hash is the version

The kit is identified by its git commit. A numbered `VERSION` file is not the reference.

Asked to drop the separate version number, use the commit hash, and require a commit before that version can change.

Landed:

- The pin stores `kit_commit`. A session stores `harness_commit`. `project.json` stores `kit_commit_at_init`. The `VERSION` file is gone.
- `new-project`, `upgrade`, and `check` refuse a dirty kit checkout. Commit in this repo first. The new hash is the version. Then checkout that commit in the project and run `upgrade`.
- `upgrade` does not rewrite `harness_commit` on a session that already exists.
- `CHANGELOG.md` keeps the notes for `0.1.0`, `0.1.1`, and `0.2.0`. Those numbers are not how a project pins the kit.

The remote for this repository is `git@github.com:hychowah/harness-kit.git`.
