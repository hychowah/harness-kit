# Changelog

## 0.1.1

The kit is its own repository, and a project takes updates by checking out a commit of that repository.

- `VERSIONING.md` states semver, the same-commit changelog rule, and the promise that a minor or patch release still accepts existing session files.
- `check` fails when `.harness/kit` is dirty or is not the pinned commit. `upgrade` refuses a dirty checkout.
- `new-project` clones the committed kit. Uncommitted edits in the kit repo are not part of the new project.

## 0.1.0

First draft of a project-independent kit.

- Short router, two packs (document and coding), mechanical `check`.
- Plans, sessions, and domain law are scaffolded into the project repo.
- The kit is a nested clone recorded by `.harness/pin.json`, so a project can move kit versions without editing its own plans or law.
