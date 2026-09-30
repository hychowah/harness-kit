# Router

Read `KERNEL.md` first. Then classify. Then open one file, not the whole kit.

| Class | When | Open | Write |
|---|---|---|---|
| `retrieve` | The user named a plan, a session, a status file, or `project/links.json` | That file | Nothing |
| `continue` | No new question, and no plan was named | `project/STATUS.md`, open rows in `project/links.json` | Nothing. Report what is open and stop. |
| `plan` | The user wants a plan created or revised | `protocols/plan.md` | `plans/<id>/` only, plus `link` |
| `work` | The user wants the plan carried out | The pack `LAW.md` for that plan | A session under `sessions/<id>/`, and the project paths the session lists |
| `audit` | Grade claims or a feature you did not just write | The pack `LAW.md` for that plan | `sessions/<id>/audit.md`, or `mark-pass` after the implement session is closed |
| `upgrade` | Move the kit forward | `VERSIONING.md` | A commit already made in the harness-kit repo. The hash is the version. Checkout that commit in `.harness/kit`, then the pin and the generated `AGENTS.md` block. |

`work` and `audit` open the `LAW.md` next to that plan's `pack.json`: `packs/<id>/LAW.md` in the kit, or `project/packs/<id>/LAW.md` for a project pack.

If the turn is both a domain fact and a kit change, put the fact in the project and the procedure in the kit. Do not invent a third class for it.
