# Procedure set

The log gate walks one procedure set. It is the law paths plus `scripts/checks.py`, `scripts/pack.py`, and `scripts/pin_move.py`. A procedure commit adds a new log file, and it has one parent. One parent is what lets the move treat that log list as a sequence. A change to `scripts/pin_move.py` changes the text a project reads, so that commit adds a log file.

`compatible`. An older session file still passes `check` for links and the seal. It is graded only when its stamp is this commit. Nothing in `project/`, `plans/`, or `sessions/` has to be edited.
