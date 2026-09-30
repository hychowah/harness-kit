# Submodule

The kit checkout is `harness-kit/` at the project root, as a git submodule. The parent repository records the commit. `.gitmodules` records the URL. There is no pin file.

`new-project` and `adopt` clone this commit into that directory and stage the gitlink. `upgrade` stages the checkout's `HEAD` and refreshes the generated `AGENTS.md` block. `pin --remote` changes the URL and does not move the commit. `sync` clones the URL and checks out the recorded commit.

An old `.harness/pin.json` that names this same commit is deleted by `upgrade`. `check` prints `FAIL pin.legacy` until `.harness/` is gone. A different commit in that file makes `upgrade` refuse.

`compatible`. An older session file still passes `check` for links and the seal. It is graded when its `harness_commit` is the submodule commit. A project that still has `.harness/` is not graded.
