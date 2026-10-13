# Coding pack

`design.md` is the decision for this commit. `review.md` is the later critique. `verify.md` is the project verify command and what it printed, including an empty command. These are not pack workers and not handoffs.

A handoff file exists only for a worker that returned. `handoffs/parent.md` exists only when the parent edited a product path. `new-session` does not create the directory.

The cursor is `work`, then `closed`. Closed needs those three files and, when `writes` is non-empty, one handoff body. The cursor is not the commit ticket. The plan stays the question. Its paths cover no product file.

Use this pack to change the project's code or documents-as-code. The kit does not know the build. The project puts the command in `project/project.json` `verify`. An empty string means the structural gate is the only command.

## Feature

`project/features.json` holds the rows. `new-feature` adds one with `passes: false`. A coding session names one `feature_id`. The session does not grow a second feature.

Entry files and complete evidence are `pack.json`. `uses_features` and `architecture_on_close` are set on this pack.

## Architecture

Set `architecture_changed` when this session changes layout, package boundaries, public commands, or `docs/index.html`. `protocols/docs.md` is the close rule.

## Verifier

`mark-pass --feature <id> --verifier` sets `passes: true`. It refuses when any session with that `feature_id` is still open, and it refuses without `--verifier`. The implement session stays the writer. The flag flip is a later step.

## Finished document sessions

A coding session may read a closed document session. It does not edit that session's sealed files. New written conclusions are a new document session.
