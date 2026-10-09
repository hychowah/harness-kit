"""The project tree is one git repository.

The project root is the work tree whose index records harness-kit at its
root. That gitlink is the kit. Any other gitlink is a leaf: the path is in
this project, and nothing under it is. Another repository's plans, sessions,
kit, and pin are not in this tree. This module does not grade them.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from git_run import git_exec, git_out

KIT_DIR = "harness-kit"
IN = "in"
LEAF = "leaf"
KIT = "kit"
OUT = "out"

_LINK_CACHE: dict[tuple, dict[str, str]] = {}


def show_toplevel(start: Path) -> Path | None:
    """Work tree that contains start, or None when start is not in a repository."""
    if not start.exists():
        return None
    text = git_out(start, "rev-parse", "--show-toplevel")
    if not text:
        return None
    try:
        return Path(text).resolve()
    except OSError:
        return None


def own_toplevel(dest: Path) -> bool:
    """True when dest is a directory and is the root of its own work tree."""
    if not dest.is_dir():
        return False
    top = show_toplevel(dest)
    try:
        return top is not None and top == dest.resolve()
    except OSError:
        return False


def enclosing_repo(dest: Path) -> Path | None:
    """Work tree that contains dest, ignoring dest when dest is already a toplevel."""
    try:
        dest = dest.expanduser().resolve()
    except OSError:
        return None
    if dest.exists() and own_toplevel(dest):
        start = dest.parent
        if start == dest:
            return None
    elif dest.exists():
        start = dest
    else:
        start = dest.parent
        if not start.exists():
            return None
    top = show_toplevel(start)
    if top is None or top == dest:
        return None
    return top


def _git_dir(root: Path) -> Path | None:
    pointer = root / ".git"
    if pointer.is_dir():
        return pointer
    if not pointer.is_file():
        return None
    try:
        text = pointer.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if not line.startswith("gitdir:"):
            continue
        raw = line.split(":", 1)[1].strip()
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        try:
            return path.resolve()
        except OSError:
            return path
    return None


def _index_stamp(root: Path) -> tuple:
    git_dir = _git_dir(root)
    if git_dir is None:
        return ("none",)
    index = git_dir / "index"
    try:
        stat = index.stat()
    except OSError:
        return ("missing", str(git_dir))
    return (str(git_dir), stat.st_mtime_ns, stat.st_size)


def gitlinks(root: Path) -> dict[str, str]:
    """Gitlink path to commit, from this work tree's index. Paths are relative to root.

    ``git -C`` a subdirectory writes and lists paths on the enclosing repository.
    A directory that is not its own toplevel has no leaves of its own. Callers
    that pass the toplevel get paths from ``--full-name``.
    """
    if not own_toplevel(root):
        return {}
    try:
        resolved = root.resolve()
    except OSError:
        resolved = root
    key = (str(resolved), _index_stamp(resolved))
    cached = _LINK_CACHE.get(key)
    if cached is not None:
        return cached
    result = git_exec("-C", str(resolved), "ls-files", "-s", "-z", "--full-name")
    found: dict[str, str] = {}
    if result.returncode == 0:
        for record in result.stdout.split("\0"):
            if not record:
                continue
            meta, sep, path = record.partition("\t")
            if not sep or not path:
                continue
            bits = meta.split()
            if len(bits) < 3 or bits[0] != "160000":
                continue
            found[path.replace("\\", "/")] = bits[1]
    if len(_LINK_CACHE) > 32:
        _LINK_CACHE.clear()
    _LINK_CACHE[key] = found
    return found


def index_gitlink(root: Path, name: str) -> str | None:
    """Commit the index records for one submodule path, or None."""
    return gitlinks(root).get(name.replace("\\", "/"))


def is_project(root: Path) -> bool:
    """True when this toplevel's index records harness-kit at its root."""
    return index_gitlink(root, KIT_DIR) is not None


def leaves(root: Path) -> set[str]:
    """Gitlink paths other than the root kit."""
    return {path for path in gitlinks(root) if path != KIT_DIR}


def find_root(start: Path) -> Path | None:
    """Walk toplevels from start. The first toplevel that records harness-kit is the project.

    A kit checkout's toplevel is the kit, which is not a project. The walk steps
    to the parent and finds the project that records that kit.
    """
    try:
        current = start.expanduser().resolve()
    except OSError:
        return None
    seen: set[Path] = set()
    while True:
        top = show_toplevel(current)
        if top is None or top in seen:
            return None
        seen.add(top)
        if is_project(top):
            return top
        parent = top.parent
        if parent == top:
            return None
        current = parent


def _norm(rel: str) -> str:
    return rel.replace("\\", "/")


def classify(root: Path, rel: str) -> str:
    """``in``, ``leaf``, ``kit``, or ``out``.

    ``in`` is an ordinary project path. ``leaf`` is exactly some gitlink other
    than the root kit. ``kit`` is the root kit, or a harness-kit path that is
    not behind a leaf. ``out`` is ``..``, an absolute path, ``.harness``, or
    anything past a leaf.
    """
    if not isinstance(rel, str) or not rel or rel.strip() != rel:
        return OUT
    norm = _norm(rel)
    if norm.startswith("/") or norm.startswith("~"):
        return OUT
    parts = Path(norm).parts
    if ".." in parts or ".harness" in parts:
        return OUT
    if norm == KIT_DIR or norm.startswith(KIT_DIR + "/"):
        return KIT
    leaf_set = leaves(root)
    if norm in leaf_set:
        return LEAF
    for leaf in leaf_set:
        if norm.startswith(leaf + "/"):
            return OUT
    if KIT_DIR in parts:
        return KIT
    return IN


def bad_path(root: Path, rel: str) -> str | None:
    """Why rel cannot be a plan path or a write, or None when it can.

    A leaf is legal. A path past a leaf enters a submodule. The root kit and
    ``.harness`` enter the kit.
    """
    if not isinstance(rel, str) or not rel or rel.strip() != rel:
        return "blank or padded path"
    norm = _norm(rel)
    if norm.startswith("/") or norm.startswith("~"):
        return "absolute path"
    if ".." in Path(norm).parts:
        return "parent segment"
    kind = classify(root, norm)
    if kind == KIT:
        return "path enters the kit"
    if kind == OUT:
        if ".harness" in Path(norm).parts:
            return "path enters the kit"
        return "path enters a submodule"
    return None


def covers(prefix: str, rel: str, leaf_set: set[str]) -> bool:
    """Whether prefix covers rel.

    A normal directory covers its descendants. A leaf covers only itself, so a
    plan that names the submodule does not cover a path past it. A glob matches
    by name. Plan globs are rejected before they are used as prefixes.
    """
    cleaned = _norm(prefix).rstrip("/")
    norm = _norm(rel)
    if any(char in cleaned for char in "*?["):
        return fnmatch.fnmatch(norm, cleaned)
    if cleaned in leaf_set:
        return norm == cleaned
    return norm == cleaned or norm.startswith(cleaned + "/")


def _nul_split(blob: str) -> list[str]:
    parts = blob.split("\0")
    if parts and parts[-1] == "":
        parts.pop()
    return [part for part in parts if part]


def _changed_paths(root: Path) -> list[str]:
    """Paths this work tree shows as changed or untracked. A failure yields nothing."""
    found: list[str] = []
    if git_out(root, "rev-parse", "--verify", "HEAD") is not None:
        diff = git_exec("-C", str(root), "diff", "-z", "--name-only", "--find-renames", "HEAD")
        if diff.returncode == 0:
            found.extend(_nul_split(diff.stdout))
    others = git_exec("-C", str(root), "ls-files", "--others", "--exclude-standard", "-z")
    if others.returncode == 0:
        found.extend(_nul_split(others.stdout))
    return found


def _behind_leaf(rel: str, leaf_set: set[str]) -> bool:
    return any(rel.startswith(leaf + "/") for leaf in leaf_set)


def boundary_detail(root: Path) -> str | None:
    """One sentence when an unrecorded nested repository sits in this tree, else None.

    An unignored untracked directory that contains ``.git``, and is not the
    project and not inside a recorded leaf, is that repository. A changed path
    with a ``harness-kit`` segment that is not the root kit and not behind a
    leaf is the same fact. Gitignored scratch, including ``tmp/``, is absent
    from this list. A recorded child and that child's kit are not named.
    """
    leaf_set = leaves(root)
    found: list[str] = []
    for raw in _changed_paths(root):
        rel = _norm(raw).rstrip("/")
        if not rel or rel in leaf_set or _behind_leaf(rel, leaf_set):
            continue
        if rel == KIT_DIR or rel.startswith(KIT_DIR + "/"):
            continue
        parts = Path(rel).parts
        if KIT_DIR in parts:
            index = parts.index(KIT_DIR)
            found.append("/".join(parts[: index + 1]))
            continue
        candidate = root / rel
        if candidate.is_dir() and not candidate.is_symlink() and (candidate / ".git").exists():
            found.append(rel)
    if not found:
        return None
    top = min(found, key=lambda item: (len(Path(item).parts), item))
    return f"{top} is not recorded as a submodule. Record it as a submodule or remove it."
