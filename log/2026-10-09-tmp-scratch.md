# Session scratch

A session keeps temporary scripts, data, and working notes in `tmp/<session-id>/`. That directory is not the record. A sweep removes every other child of `tmp/` except a regular `README.md`. `new-session` creates the directory and sweeps. `close-session` and `abandon` sweep after the seal. `clean-tmp` is the same sweep. `check` does not sweep.

`compatible`. An older sealed session still passes `check` for links and the seal. It is not graded again under this rule. An existing project adds these lines to `.gitignore` when it wants scratch to stay untracked:

```
/tmp/*
!/tmp/README.md
```

`check` does not require those lines. A force-added file under `tmp/` is still a product change.
