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
- `pack` is a pack id: `document`, `coding`, or a project pack under `project/packs/<id>/`.
- `paths` lists project-relative files or directories this plan will touch. The plan's own `plan.md` is always one of them.
- `sessions` lists session ids. `harness.py link` fills this from the sessions that point back. Edit the prose, then run `link`, rather than hand-editing the list.

## Lifecycle

`new-plan` creates status `open`. `close-plan` sets `closed`. A closed plan does not accept a new session.

Archive a superseded plan by closing it and writing a new plan. Leave the old directory in place so session links still resolve.

## Coverage

A product change is covered when one open plan's `paths` contains it and that plan's Question and Done are not blank. `plan.json` `paths` is the only list. `plan.md` does not copy it.

These paths are not a product change: `plans/`, `sessions/`, `project/links.json`, `.gitmodules`, the `harness-kit` gitlink, an `AGENTS.md` edit inside the generated markers, and a `features.json` edit that only changes `sessions` lists.

`check` reports `coverage.gap`, `plan.blank`, and `plan.overlap`. The commit hook runs the same rule on the index and reads plans from the index. A closed plan does not cover. Close it after the product commit, in a later commit. Plan paths are prefixes. A glob is `path.plan`.
