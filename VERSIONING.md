# Versioning

`harness-kit` is its own git repository. Projects clone it. They do not absorb it, and they do not edit the clone to change procedure.

The version is the commit hash. `git rev-parse HEAD` is the whole reference. A pin stores that hash in `kit_commit`. A session stores it in `harness_commit`. There is no separate version number.

## Commit first

A version changes when a commit exists. Uncommitted edits are not a version.

`new-project`, `upgrade`, and `check` refuse a dirty kit checkout. Commit in this repository first. The new hash is the version. Then check that commit out in the project's `.harness/kit` and run `upgrade`.

`upgrade` writes the hash into `.harness/pin.json` and refreshes the generated block in the project's `AGENTS.md`. It leaves plans, sessions, and `project/LAW.md` alone. It does not rewrite `harness_commit` on sessions already created.

`check` fails when the checkout is dirty, or when `HEAD` is not the pin's commit. A local edit inside `.harness/kit` is dropped by the next checkout.

## How a project takes an update

```bash
git -C .harness/kit fetch
git -C .harness/kit checkout <commit>
python3 .harness/kit/scripts/harness.py upgrade
python3 .harness/kit/scripts/harness.py check
```

`<commit>` is the hash from this repository. A tag may name a commit, and a tag can be moved. The pin stores the hash.

## Sessions and a later commit

`new-session` copies the hash of the kit that created the session. Later upgrades leave that field as it was. The checker that runs is the checkout the project has pinned. If a later commit makes `check` reject a session file an older commit accepted, say so in `log/` before a project moves its pin.

## What this file used to require

Numbered releases, a `VERSION` file, and a tag `v` plus that number were an earlier draft. The commits are still in git. The hash is the reference from here on. `CHANGELOG.md` keeps those old notes. New work is a commit, a log entry, and the hash.
