# Plans

Each plan is `plans/<id>/plan.json` plus `plan.md`. Create one with:

```bash
python3 harness-kit/scripts/harness.py new-plan --id <slug> --title "<title>" --pack document
```

`--pack` is `document`, `coding`, or a project pack. The plan stores this project's id. See the kit's `protocols/plan.md`.
