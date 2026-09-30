# Versioning

`harness-kit` is its own git repository. Projects clone it. They do not absorb it, and they do not edit the clone to change procedure.

The version is the commit hash. `git rev-parse HEAD` is the whole reference. The parent repository stores that hash as the `harness-kit` submodule commit. A session stores it in `harness_commit`. There is no separate version number and no pin file.

## Commit first

A version changes when a commit exists. Uncommitted edits are not a version.

A dirty kit checkout crashes. The message includes `pin.dirty` and `uncommitted`. It is not a check result row. Commit in this repository first. The new hash is the version. Then check that commit out in the project's `harness-kit/` submodule and run `upgrade`.

`upgrade` stages that hash as the submodule commit and refreshes the generated block in the project's `AGENTS.md`. It leaves plans, sessions, and `project/LAW.md` alone. It does not rewrite `harness_commit` on sessions already created. If `.harness/pin.json` is still present and names this same commit, `upgrade` deletes that file and leaves the rest of `.harness/` on disk. `check` then prints `FAIL pin.legacy` until `.harness/` is gone. If that file names a different commit, `upgrade` refuses.

`check` crashes on a dirty checkout, as above. It does not print a result row for that. When `HEAD` is not the submodule commit, `check` prints `FAIL pin.mismatch` and does not grade the graph. A local edit inside `harness-kit/` is dropped by the next checkout.

## How a project takes an update

```bash
git -C harness-kit fetch
git -C harness-kit checkout <commit>
python3 harness-kit/scripts/harness.py upgrade
python3 harness-kit/scripts/harness.py check
```

`<commit>` is the hash from this repository. A tag may name a commit, and a tag can be moved. The submodule record stores the hash.

## Sessions and a later commit

`new-session` copies the hash of the kit that created the session into `harness_commit`, and copies `project_stamp` from `project/project.json` when that field is set. Later upgrades leave both as they were. Project-wide `check` always enforces links and the seal. It grades the graph only when both stamps match the submodule commit and the current project stamp. A mismatch is `WARN law.stamp` and names the checkout to use. `check --session` on that session is `FAIL law.stamp`. A grading change says `compatible` or `breaking` in that commit's `log/` file before a project moves its submodule. `compatible` means an older session file still passes `check` (links and the seal). It is not graded under the new graph. A warning names the checkout. `breaking` means `check` would reject a session an older commit accepted.

## What this file used to require

Numbered releases, a `VERSION` file, and a tag `v` plus that number were an earlier draft. The commits are still in git. The hash is the reference from here on. `CHANGELOG.md` keeps those old notes. New work is a commit, a log entry, and the hash.
