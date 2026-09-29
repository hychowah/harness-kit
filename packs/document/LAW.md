# Document pack

Use this pack for research, notes, and other documents whose product is claims on disk. Domain objects (which sources count, which template a card uses) live in `project/LAW.md`.

## Phases

| Phase | Produces | Starts only when |
|---|---|---|
| `brief` | `sessions/<id>/brief.md` | The session exists |
| `gather` | Handoffs and the files named as write paths | `brief.md` exists |
| `audit` | `sessions/<id>/audit.md` | `brief.md` and session `gaps.md` exist |
| `closed` | A sealed session | `audit.md` exists |

`harness.py phase` enforces the file column. `harness.py preflight` reports it without moving the phase.

## Brief

`brief.md` states the question, the depth (`low`, `medium`, `high`), the write paths, and either a report path or the sentence "no report".

The report path, when present, sits under `project/reports/` or another project path already listed in `writes`. One session has one report writer.

## Gather

Workers follow `worker-contract.md`. Paths do not overlap. A new session does not read another session's conclusion to answer the brief. It reads sources the plan lists, and sources it fetches into a project path the session listed.

## Claims

A claim in a gathered file or a report is allowed when one of these is true:

1. The session cites a file under a project source path the brief named.
2. The operator stated it, and the text says so.
3. It is copied from a file the plan already lists under `paths`.

Anything else is a row in the session `gaps.md`, summarized into `project/gaps.md` when the session closes. The report does not fill a gap with a smooth sentence.

Conflicting sources stay side by side. They do not collapse into one number.

## Audit

The auditor reads the brief, the handoffs, the write paths, and `gaps.md`. The auditor writes `audit.md` and does not edit the gathered files. `audit.md` lists unsupported claims. The parent fixes or gaps them before `close-session`.

## Close

`close-session` seals the session. The next question on the same plan is a new session.
