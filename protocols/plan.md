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

A plan does not own a product file. `protocols/session.md` says which session does. `paths` still names the area the plan is about. A glob is `path.plan`.

These paths are not a product change: `plans/`, `sessions/`, `project/links.json`, `.gitmodules`, the `harness-kit` gitlink, an `AGENTS.md` edit inside the generated markers, and a `features.json` edit that only changes `sessions` lists, `passes`, or `passed_on`.

A submodule path is a product change. Files inside it are not changes in this repository.
