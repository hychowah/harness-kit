# Versioning

`harness-kit` is its own git repository. Projects clone it. They do not absorb it, and they do not edit the clone to change procedure.

The version is the commit hash. `git rev-parse HEAD` is the whole reference. The parent repository stores that hash as the `harness-kit` submodule commit. A session stores it in `harness_commit`. There is no separate version number and no pin file.

## The commit is the version

A version changes when a commit exists. Uncommitted edits are not a version.

A dirty kit checkout crashes. The message includes `pin.dirty` and `uncommitted`. It is not a check result row. The new hash is the version after a commit exists in this repository. `AGENTS.md` says when that commit is made. Then check that commit out in the project's `harness-kit/` submodule and run `upgrade`.

`agent-skill/` is a second repository recorded by one commit. That commit is the skill set. A checkout whose `agent-skill` HEAD is missing, or is not that commit, crashes. The message names `agent-skill` and the recorded commit. It is not a check result row. `upgrade` and `sync` check out that commit when the directory is missing or empty. A directory that already has a different commit crashes and is not replaced. `check` does not check out the commit.

`upgrade` stages that hash as the submodule commit and refreshes the generated block in the project's `AGENTS.md`. `upgrade` prints the move into this checkout and writes that same text into the generated block. The next session reads it there. Plans, sessions, `project/LAW.md`, and `harness_commit` stay as they were. If `.harness/pin.json` is still present and names this same commit, `upgrade` deletes that file and leaves the rest of `.harness/` on disk. `check` then prints `FAIL pin.legacy` until `.harness/` is gone. If that file names a different commit, `upgrade` refuses.

`check` crashes on a dirty checkout, as above. It does not print a result row for that. When `HEAD` is not the submodule commit, `check` prints `FAIL pin.mismatch` and does not grade the graph. A local edit inside `harness-kit/` is dropped by the next checkout.

A nested project pins its own kit. This checkout does not run that repository's `harness.py` and does not move that pin.

## How a project takes an update

```bash
git -C harness-kit fetch
git -C harness-kit checkout <commit>
python3 harness-kit/scripts/harness.py upgrade
python3 harness-kit/scripts/harness.py check
```

`<commit>` is the hash from this repository. A tag may name a commit, and a tag can be moved. The submodule record stores the hash.

## Sessions and a later commit

`new-session` copies the hash of the kit that created the session into `harness_commit`, and copies `project_stamp` from `project/project.json` when that field is set. Later upgrades leave both as they were. Project-wide `check` always enforces links and the seal. It grades the graph only when both stamps match the submodule commit and the current project stamp. Two empty project stamps match. An open session whose stamps differ fails `law.stamp`. `phase`, `status`, `spawn`, `preflight`, `note-architecture`, `close-session`, and `abandon` refuse that session before they write. A sealed session whose stamps differ is `WARN law.stamp`: links and the seal were checked, and the graph was not. `check --session` on either mismatch is `FAIL law.stamp`. The detail names the session and both commits. It does not say to check out another commit. If that commit is not in this clone, the detail says so. `check` does not run that commit's `harness.py`. A grading change says `compatible` or `breaking` on its own line in that commit's `log/` file, before a project moves its submodule. That line is the whole consequence for a project repo: what it must change, or that it must change nothing, in words `check` already uses. `compatible` means an older sealed session file still passes `check` for links and the seal and is not graded under the new graph. `breaking` means `check` would reject a session an older commit accepted. `upgrade` shows the line and does not apply it.

## What this file used to require

Numbered releases, a `VERSION` file, and a tag `v` plus that number were an earlier draft. The commits are still in git. The hash is the reference from here on. `CHANGELOG.md` keeps those old notes. New work is a commit, a log entry, and the hash.
