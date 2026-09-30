# Link protocol

Plans and sessions are project records. The kit builds the index. It does not store the index inside the kit.

## Identity

`project/project.json` `id` is the only project id. Every `plan.json` and `session.json` repeats it. `check` fails on a mismatch, which is how a copied plan from another repo gets caught.

## Edges

| From | Field | To |
|---|---|---|
| plan | `project_id` | `project/project.json` |
| plan | `paths` | files or directories inside the project |
| plan | `sessions` | `sessions/<id>/` |
| session | `plan_id` | `plans/<id>/` |
| session | `writes` | files or directories inside the project |
| session | `feature_id` | `project/features.json` when the pack has `uses_features` |
| feature | `sessions` | sessions that name it |
| `project/links.json` | all of the above | rebuilt, not hand-edited |

`harness.py link` rewrites `plan.json` `sessions`, `features.json` session lists, and `project/links.json` from the session files. Session files are the source of the edges. The plan's prose and `paths` stay as written.

## Path rules

A link path is relative to the project root. It contains no `..`. It is not absolute. It does not enter `.harness/`.

## When the map is stale

`check` compares `project/links.json` to a fresh build. If they differ, run `link`. Do not patch the index by hand.
