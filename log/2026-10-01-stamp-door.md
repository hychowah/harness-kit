# Stamp door

The running pin writes and grades a session only when `harness_commit` is the gitlink and `project_stamp` matches. An open session on another stamp fails `law.stamp`, and the write commands refuse it before they change the file. A sealed session on another stamp still passes links and the seal. The graph is not graded. The detail does not say to check out another commit.

`breaking`. An open session whose `harness_commit` is not the gitlink, or whose `project_stamp` is not the current project stamp, fails project `check`. A sealed session file still passes links and the seal and is not graded.
