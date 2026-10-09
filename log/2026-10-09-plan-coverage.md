# Plan coverage

A product change is covered when one open plan lists it and that plan's Question and Done are filled in. `check` reports `coverage.gap`, `plan.blank`, or `plan.overlap`. `git commit` runs the same rule on the index. `check` reports `hook.missing` until `core.hooksPath` is `harness-kit/hooks`.

`breaking`. `check` fails `hook.missing` until the hook path is the kit hook, `plan.overlap` when two open plans cover one path, and `coverage.gap` or `plan.blank` when a product diff is outside one written open plan. `upgrade` sets the hook path when it was unset and does not edit plans. A sealed session is not regraded.
