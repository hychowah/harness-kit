<!-- harness-kit:begin -->
# Project router

Procedure is the harness kit pinned at `.harness/kit` (version __KIT_VERSION__). That directory is a clone of the harness-kit repository. Do not edit it. A kit change is a commit in that repository, then `checkout` and `upgrade` here. Domain law is `project/LAW.md` in this repo. The kit is replaceable. This project is not.

Read in order: this file, `.harness/pin.json`, `.harness/kit/KERNEL.md`, `.harness/kit/router.md`, the pack `LAW.md` for the session you are in, then `project/LAW.md`.

From the project root:

```bash
python3 .harness/kit/scripts/harness.py check
python3 .harness/kit/scripts/harness.py link
```

Plans live in `plans/`. Sessions live in `sessions/`. The index is `project/links.json`.
<!-- harness-kit:end -->

## This project

Add project-specific orientation below this line. Upgrade rewrites only the block above.

Domain law: `project/LAW.md`. Human map: `project/ARCHITECTURE.md`. Status: `project/STATUS.md`.
