# Worker contract

The parent fills this for every worker.

| Field | Content |
|---|---|
| Objective | One sentence, plus the plan id and the session path |
| Pack | The session's pack id |
| Write paths | Exact project-relative paths. Paths inside `.harness/` are forbidden. |
| Read | Named sources only. A new document session does not open a sibling session to copy its conclusion. |
| Stop | Coverage against the plan, or an explicit empty result |
| Return | Paths written, short coverage, conflicts, gaps. No pasted source dumps. |

## Handoff

Write `sessions/<id>/handoffs/<worker>.md` using `exemplars/handoff.md` as the shape.

## Empty

If the search or the read finds nothing, the handoff still exists. List what was opened. Say empty. Add a gap. An empty handoff is a valid result.

## Isolation

Two workers in one session do not share a write path. The parent merges. Workers do not spawn workers.
