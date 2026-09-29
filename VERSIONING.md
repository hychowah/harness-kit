# Versioning

`harness-kit` is its own git repository. Projects clone it. They do not absorb it, and they do not edit the clone to change procedure.

`VERSION` is the law version. `CHANGELOG.md` is the release note a consumer reads. `log/` is the work record of this repository, and `REPO.md` describes it. A git tag `v` plus that version names the release commit. The pin in a project stores the commit, because a tag can be moved and a commit cannot. Do not move a release tag. Ship a new version instead.

## What moves the version

Bump `VERSION` and add a `CHANGELOG.md` section in the same commit as any change to live procedure:

- `KERNEL.md`, `router.md`, `worker-contract.md`, `VERSIONING.md`, `AGENTS.md`, `README.md`
- `packs/`, `protocols/`, `schemas/`, `exemplars/`, `templates/`
- `scripts/harness.py`

A test-only change does not bump the version. A wording change that does not change what `check` accepts is a patch, and it still bumps.

These files are the kit repository's own record. Editing only them does not bump the version:

- `REPO.md` — standing document for this repo
- `STATUS.md` — live pointer for kit work
- `log/` — one file per closed piece of kit work

When a procedure change and its log entry land in one commit, `VERSION` moves once, because of the procedure change. `REPO.md` says how the log is written. `CHANGELOG.md` stays the note a consumer reads.

| Bump | When |
|---|---|
| Patch `x.y.Z` | Behavior of `check`, `upgrade`, and the packs is unchanged. Wording, examples, and bugfixes that still accept yesterday's session files. |
| Minor `x.Y.0` | New command, new optional field, or a new rule old sessions can ignore. Old `session.json`, `plan.json`, and `pin.json` files still pass `check`. |
| Major `X.0.0` | `check` rejects a file the previous release accepted, or a command changes meaning. `CHANGELOG.md` names each break and the migration. `upgrade` still does not rewrite `project/`, `plans/`, or `sessions/`. |

Live files describe current law only. Do not leave a second copy of an old rule inside `KERNEL.md` or a pack. The old rule is the old tag.

## How a project takes an update

The nested checkout `.harness/kit` stays a detached commit of this repo. Procedure changes happen here, get committed, and get tagged. The project then checks out that commit and runs `upgrade`.

```bash
git -C .harness/kit fetch
git -C .harness/kit checkout vX.Y.Z
python3 .harness/kit/scripts/harness.py upgrade
python3 .harness/kit/scripts/harness.py check
```

`upgrade` records `VERSION` and the commit into `.harness/pin.json`, and refreshes the generated block in the project's `AGENTS.md`. It leaves plans, sessions, and `project/LAW.md` alone.

`check` fails when that checkout is dirty, when `HEAD` is not the pin's commit, or when `VERSION` is not the pin's version. A local edit inside `.harness/kit` is not a kit release. The next checkout drops it.

`new-project` clones the current commit of this repo. Uncommitted edits in this repo are not part of that clone.

## Sessions and a later release

`new-session` copies `harness_version` from the kit that created the session. `upgrade` does not change that field. A minor or patch release must still accept those session files. A major release says so in `CHANGELOG.md` before a project moves its pin.

The checker that runs is the checkout the project has pinned. Finishing a session on 0.1.0 and later upgrading the project does not rewrite that session. It also does not re-grade the session with a private fork of the kit.
