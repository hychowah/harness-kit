"""The move from the parent's previous harness-kit gitlink to this checkout.

The previous record is the latest gitlink the parent can show that is not
this checkout: the index, if it differs; otherwise the gitlink in the parent
HEAD commit, if it differs; otherwise the newest older value of that path
in the parent history. If git can show none, it is the previous hash already
written in the generated block for this same checkout. Otherwise there is none.
Call this before the gitlink is staged. Git wins when it can show a hash.
A later upgrade does not replace a recorded previous hash with none.

The file set is the tree diff of log/ between the two commits. Order is the
order a walk from the previous commit first touches each path, and only when
that walk lists every path in the diff. Otherwise the text says the list is
not a sequence. The grading line is the first line that, after an optional
"Grading change:" prefix, starts with compatible or breaking, backticks
optional. A file without one says so. A path missing at this checkout is
removed. The body is not copied.

This does not read or write project/, plans/, or sessions/, does not change
harness_commit, and does not decide that the project has adapted.
"""

from __future__ import annotations

import re
from pathlib import Path

_HASH = re.compile(r"[0-9a-f]{40,64}")
_RECORD = re.compile(r"^Submodule record is ([0-9a-f]{40,64})\.$", re.MULTILINE)
_PREVIOUS = re.compile(r"^Previous submodule record: (.+)$", re.MULTILINE)
_BEGIN = "<!-- harness-kit:begin -->"
_END = "<!-- harness-kit:end -->"
_NOT_IN_CLONE = " (not in this clone)"
_GRADING_PREFIX = "Grading change:"


def grading_line(text: str) -> str | None:
    """First line that states compatible or breaking, or None."""
    for raw in text.splitlines():
        line = raw.strip()
        body = line
        if body.startswith(_GRADING_PREFIX):
            body = body[len(_GRADING_PREFIX) :].lstrip()
        if body.startswith("`"):
            body = body[1:]
        for word in ("compatible", "breaking"):
            if not body.startswith(word):
                continue
            rest = body[len(word) :]
            if rest.startswith("`"):
                rest = rest[1:]
            if rest == "" or not rest[0].isalnum():
                return line
    return None


def birth_text(checkout: str) -> str:
    """Move text for a new stub. There is no previous submodule record."""
    return _render(checkout, None, missing=False, notes=None, sequence=True)


def move_text(project: Path, kit: Path, checkout: str) -> str:
    """Move text for this checkout. Call before the gitlink is staged."""
    previous = previous_gitlink(project, checkout)
    if previous is None:
        return birth_text(checkout)
    if not _commit_in_clone(kit, previous):
        return _render(checkout, previous, missing=True, notes=None, sequence=False)
    rows = _diff_log(kit, previous, checkout)
    if not rows:
        return _render(checkout, previous, missing=False, notes=[], sequence=True)
    walk = _walk_log(kit, previous, checkout)
    by_status = {path: status for status, path in rows}
    diff_paths = [path for status, path in rows]
    if set(diff_paths) <= set(walk):
        order = [path for path in walk if path in by_status]
        sequence = True
    else:
        order = diff_paths
        sequence = False
    notes = [(path, _note(kit, checkout, path, by_status[path])) for path in order]
    return _render(checkout, previous, missing=False, notes=notes, sequence=sequence)


def previous_gitlink(project: Path, checkout: str) -> str | None:
    """Latest harness-kit gitlink the parent can show that is not checkout."""
    harness = _harness()
    index = harness.gitlink(project)
    if index and index != checkout:
        return index
    head = harness.git_out(project, "rev-parse", "HEAD")
    if head:
        head_link = _gitlink_at(project, "HEAD")
        if head_link and head_link != checkout:
            return head_link
        older = _older_gitlink(project, checkout)
        if older:
            return older
    return _previous_in_block(project, checkout)


def _render(
    checkout: str,
    previous: str | None,
    *,
    missing: bool,
    notes: list[tuple[str, str]] | None,
    sequence: bool,
) -> str:
    lines = [f"Submodule record is {checkout}."]
    if previous is None:
        lines.append("Previous submodule record: none")
        lines.append("No log range.")
    elif missing:
        lines.append(f"Previous submodule record: {previous}{_NOT_IN_CLONE}")
        lines.append("No log range.")
    elif not notes:
        lines.append(f"Previous submodule record: {previous}")
        lines.append("No log file changed between those commits.")
    else:
        lines.append(f"Previous submodule record: {previous}")
        if not sequence:
            lines.append("The log list is not a sequence.")
        for path, note in notes:
            lines.append(f"- harness-kit/{path} — {note}")
    return "\n".join(lines) + "\n"


def _harness():
    import harness

    return harness


def _git(repo: Path, *args: str):
    return _harness().git_exec("-C", str(repo), *args)


def _die(message: str) -> None:
    _harness().die(message)


def _gitlink_at(project: Path, rev: str) -> str | None:
    result = _git(project, "rev-parse", f"{rev}:harness-kit")
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if _HASH.fullmatch(value):
        return value
    return None


def _older_gitlink(project: Path, checkout: str) -> str | None:
    result = _git(project, "log", "--format=%H", "--", "harness-kit")
    if result.returncode != 0:
        return None
    for commit in result.stdout.splitlines():
        link = _gitlink_at(project, commit)
        if link and link != checkout:
            return link
    return None


def _previous_in_block(project: Path, checkout: str) -> str | None:
    path = project / "AGENTS.md"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    if _BEGIN in text and _END in text:
        text = text.split(_BEGIN, 1)[1].split(_END, 1)[0]
    record = _RECORD.search(text)
    prev = _PREVIOUS.search(text)
    if record is None or record.group(1) != checkout or prev is None:
        return None
    value = prev.group(1).strip()
    if value.endswith(_NOT_IN_CLONE):
        value = value[: -len(_NOT_IN_CLONE)].strip()
    if value == "none" or not _HASH.fullmatch(value) or value == checkout:
        return None
    return value


def _commit_in_clone(kit: Path, commit: str) -> bool:
    result = _git(kit, "cat-file", "-e", f"{commit}^{{commit}}")
    return result.returncode == 0


def _diff_log(kit: Path, previous: str, checkout: str) -> list[tuple[str, str]]:
    result = _git(
        kit,
        "diff",
        "--name-status",
        "--no-renames",
        previous,
        checkout,
        "--",
        "log",
    )
    if result.returncode != 0:
        _die(result.stderr.strip() or "could not diff log/")
    rows = []
    for line in result.stdout.splitlines():
        status, _, path = line.partition("\t")
        if not path.startswith("log/"):
            continue
        rows.append((status[:1], path))
    return rows


def _walk_log(kit: Path, previous: str, checkout: str) -> list[str]:
    listed = _git(kit, "rev-list", "--reverse", f"{previous}..{checkout}")
    if listed.returncode != 0:
        return []
    order: list[str] = []
    seen: set[str] = set()
    for commit in listed.stdout.splitlines():
        shown = _git(
            kit,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "--root",
            commit,
            "--",
            "log",
        )
        if shown.returncode != 0:
            continue
        for path in shown.stdout.splitlines():
            if path.startswith("log/") and path not in seen:
                seen.add(path)
                order.append(path)
    return order


def _note(kit: Path, checkout: str, path: str, status: str) -> str:
    if status == "D":
        return "removed"
    try:
        shown = _git(kit, "show", f"{checkout}:{path}")
    except UnicodeDecodeError:
        _die(f"{path} is not readable")
    if shown.returncode != 0:
        _die(f"{path} is not readable")
    line = grading_line(shown.stdout)
    if line is None:
        return "no grading line"
    return line
