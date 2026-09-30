# Pack graph

2026-09-30. The kit could not host a project whose work is a graph. Packs were two hard-coded phase lists, and `check` returned bare sentences.

A pack is now a graph in `pack.json`. `document` and `coding` are single-path graphs in that shape. A project adds `project/packs/<id>/pack.json`. The same id in both places crashes. The kit does not import project Python.

`check` prints `PASS`, `FAIL`, `WARN`, or `SKIPPED` with a stable id and exits non-zero only on `FAIL`. `status.json` is the session checklist. A specialist path counts only with a returned spawn, or the session is abandoned. Abandon is a finished record. Project-wide `check` warns and does not grade a session whose kit commit or project stamp does not match. `adopt` attaches the kit to a non-empty repo and overwrites nothing.

Grading change: `compatible`. Older session files that still match the session schema still pass check (links and the seal). A session is graded only when its stamps match. A warning names the checkout. An older `harness_commit` is not graded under the new graph.
