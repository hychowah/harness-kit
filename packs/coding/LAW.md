# Coding pack

Use this pack to change the project's code or documents-as-code. The kit does not know the build. The project puts the command in `project/project.json` `verify`. An empty string means the structural gate is the only command.

## Feature

`project/features.json` holds the rows. `new-feature` adds one with `passes: false`. A coding session names one `feature_id`. The session does not grow a second feature.

Entry files and complete evidence are `pack.json`. `uses_features` and `architecture_on_close` are set on this pack.

`baseline.md` records the verify command and what it printed before the edit. Run it first. A red baseline is a fact in that file, not a reason to skip it.

`verify.md` records the same command after the edit, plus the structural `check`.

## Architecture

When the session changes layout, package boundaries, or the public commands, set `architecture_changed` to true in `session.json` before close. `close-session` then requires `project/ARCHITECTURE.md` to contain the session id. The map and the change ship together.

## Verifier

`mark-pass --feature <id> --verifier` sets `passes: true`. It refuses when any session with that `feature_id` is still open, and it refuses without `--verifier`. The implement session stays the writer. The flag flip is a later step.

## Finished document sessions

A coding session may read a closed document session. It does not edit that session's sealed files. New written conclusions are a new document session.
