# Sessions

Each session is `sessions/<id>/`. Create one with:

```bash
python3 .harness/kit/scripts/harness.py new-session --plan <plan-id> --id <slug>
```

A session stores the project id, the plan id, and the project paths it may write. See the kit's `protocols/session.md`.
