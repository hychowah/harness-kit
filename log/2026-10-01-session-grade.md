# Session grade

`close-session` and `check` share one grade. Close sets the phase to `closed` in memory and writes the seal when that grade has no FAIL row. A SKIPPED row does not block the seal. Otherwise the session stays open. `check` appends the same rows when the stamp door says grade. `abandon` does not take the grade.

A `harness_commit` that is not in this clone is `law.stamp` with the reason "not in this clone". The gate does not run that commit's `harness.py`. Sealed text is hashed as UTF-8 with LF newlines. A file that is not UTF-8 fails the seal.

`compatible`. An older session file still passes `check` for links and the seal. It is graded when its `harness_commit` is this commit. The LF rule does not change a seal of the LF files the kit writes.
