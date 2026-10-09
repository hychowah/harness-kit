# Project tree

One repository is one project. The root `harness-kit` gitlink is the kit. Any other gitlink is a leaf: that path is in this project, and nothing under it is. `check` does not grade inside a submodule. `upgrade` does not move that submodule's kit pin. `new-project` inside a project creates the new repository and stages it on the enclosing project without committing the enclosing project.

`breaking`. A plan path or a session write that enters a submodule fails `path.plan` or `path.write`. Name the submodule path. `check` does not grade inside it. An unrecorded nested repository fails `project.boundary` until that path is recorded as a submodule or removed. `upgrade` does not move that submodule's kit pin. A session that does not enter a submodule still passes links and the seal.
