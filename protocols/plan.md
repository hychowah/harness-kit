# Plan protocol

A plan is a project file. It is not a kit file.

## Files

```text
plans/<id>/plan.json
plans/<id>/plan.md
```

`plan.json` is the link record. `plan.md` is the prose. The id is a slug: lowercase letters, digits, and hyphens.

## Required links

- `project_id` matches `project/project.json`.
- `pack` is `document` or `coding`.
- `paths` lists project-relative files or directories this plan will touch. The plan's own `plan.md` is always one of them.
- `sessions` lists session ids. `harness.py link` fills this from the sessions that point back. Edit the prose, then run `link`, rather than hand-editing the list.

## Lifecycle

`new-plan` creates status `open`. `close-plan` sets `closed`. A closed plan does not accept a new session.

Archive a superseded plan by closing it and writing a new plan. Leave the old directory in place so session links still resolve.
