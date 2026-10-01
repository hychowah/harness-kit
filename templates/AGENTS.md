<!-- harness-kit:begin -->
# Project router

Procedure is the harness kit submodule at `harness-kit/` (commit __KIT_COMMIT__). That directory is a clone of the harness-kit repository. Do not edit it. A kit change is a commit in that repository, then checkout that commit in the submodule and run `upgrade` here. The version is the submodule commit. Domain law is `project/LAW.md` in this repo. The kit is replaceable. This project is not.

Whether this turn is a kit session is decided in `project/LAW.md`. Read that file before this submodule. If it does not classify the turn as kit work, open only the law it names and stop. If it does, read `KERNEL.md`, `router.md`, and one pack `LAW.md`, then `project/LAW.md` again for vocabulary and done-conditions. Upgrade rewrites this block and leaves every line below it alone.

From the project root:

```bash
python3 harness-kit/scripts/harness.py check
python3 harness-kit/scripts/harness.py link
```

Plans live in `plans/`. Sessions live in `sessions/`. The index is `project/links.json`.
<!-- harness-kit:end -->

## This project

Add project-specific orientation below this line. Upgrade rewrites only the block above.

Domain law: `project/LAW.md`. Human map: `project/ARCHITECTURE.md`. Status: `project/STATUS.md`.
