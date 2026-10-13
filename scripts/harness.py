#!/usr/bin/env python3
"""Project-independent harness kit.

Run the copy inside a project after new-project. The pin and this script
must be the same checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from checks import (
    blocking_globs,
    eval_evidence,
    fail,
    has_fail,
    matching_paths,
    run_project_checks,
    validate,
    warn,
)
from pack import (
    crash_on_collisions,
    find_node,
    find_worker,
    load_pack,
    path_order,
    priors_for_enter,
    single_path,
    start_node,
    unsatisfied_priors,
)
from git_run import git_exec, git_out
from pin_move import birth_text, move_text
import tree

KIT_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = "agent-skill"
BEGIN = "<!-- harness-kit:begin -->"
END = "<!-- harness-kit:end -->"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STATIC_TEMPLATES = (
    "project/LAW.md",
    "docs/index.html",
    "project/STATUS.md",
    "project/gaps.md",
    "project/sources/README.md",
    "project/reports/README.md",
    "plans/README.md",
    "sessions/README.md",
    "tmp/README.md",
)


def die(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def today() -> str:
    return date.today().isoformat()


def dated_id(body: str) -> str:
    """A session id is the day plus a slug. A body that already starts with a day is kept."""
    if re.match(r"^\d{4}-\d{2}-\d{2}-", body):
        return body
    return f"{today()}-{body}"


def schema(name: str) -> dict:
    return read_json(KIT_ROOT / "schemas" / name)


def slug_ok(value: str) -> bool:
    return bool(SLUG_RE.match(value))


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug_ok(slug):
        die(f"Cannot derive an id from {name!r}. Pass --id as a lowercase slug.")
    return slug


KIT_DIR = "harness-kit"


def head_commit(repo: Path) -> str:
    commit = git_out(repo, "rev-parse", "HEAD")
    if not commit:
        die(f"{repo} has no git commit. Commit the kit before cloning it into a project.")
    return commit


def find_project(explicit: str | None) -> Path:
    """The project root. ``--project`` is that directory. Otherwise walk toplevels."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    found = tree.find_root(Path.cwd())
    if found is None:
        die("No project found. Pass --project, or run from inside a project.")
    return found


def index_gitlink(repo: Path, name: str) -> str | None:
    """Commit the index records for one submodule path."""
    return tree.index_gitlink(repo, name)


def gitlink(project: Path) -> str | None:
    """Commit the parent index records for the harness-kit submodule."""
    return index_gitlink(project, KIT_DIR)


def submodule_checkout(project: Path) -> Path:
    return (project / KIT_DIR).resolve()


def gitmodules_url(repo: Path, name: str) -> str | None:
    path = repo / ".gitmodules"
    if not path.is_file():
        return None
    section = False
    header = f'[submodule "{name}"]'
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line == header:
            section = True
            continue
        if line.startswith("[") and section:
            break
        if section and line.startswith("url ="):
            return line.split("=", 1)[1].strip()
    return None


def submodule_url(project: Path) -> str | None:
    return gitmodules_url(project, KIT_DIR)


def skill_mismatch(recorded: str, head: str | None) -> str:
    shown = head or "missing"
    return f"{SKILL_DIR} HEAD {shown} does not match the submodule record {recorded}."


def skill_head(path: Path) -> str | None:
    """HEAD of a skill checkout. An empty directory is not one: git would walk upward."""
    if not path.exists():
        return None
    top = git_out(path, "rev-parse", "--show-toplevel")
    if not top:
        return None
    try:
        if Path(top).resolve() != path.resolve():
            return None
    except OSError:
        return None
    return git_out(path, "rev-parse", "HEAD")


def local_skill_source(kit: Path, recorded: str, dest: Path) -> Path | None:
    """A checkout on this machine that already has the skill commit."""
    candidates = [KIT_ROOT / SKILL_DIR]
    origin = git_out(kit, "remote", "get-url", "origin")
    if origin:
        candidates.append(Path(origin) / SKILL_DIR)
    for candidate in candidates:
        try:
            if candidate.resolve() == dest.resolve():
                continue
        except OSError:
            continue
        if candidate.is_dir() and git_out(candidate, "cat-file", "-t", recorded) == "commit":
            return candidate
    return None


def materialize_skill(kit: Path) -> None:
    """Check out agent-skill at the gitlink this kit commit records.

    A local checkout that already contains the commit is copied first, so a
    project scaffold does not fetch. The url in .gitmodules is the other path.
    """
    recorded = index_gitlink(kit, SKILL_DIR)
    if not recorded:
        die(f"{kit} has no {SKILL_DIR} submodule record.")
    dest = kit / SKILL_DIR
    if dest.exists():
        head = skill_head(dest)
        if head == recorded:
            return
        if head is None and dest.is_dir() and not any(dest.iterdir()):
            dest.rmdir()
        else:
            die(skill_mismatch(recorded, head))
    source = local_skill_source(kit, recorded, dest)
    if source:
        cloned = git_exec("clone", "--local", str(source), str(dest))
    else:
        url = gitmodules_url(kit, SKILL_DIR)
        if not url:
            die(f"{kit} has no url for {SKILL_DIR}.")
        cloned = git_exec("clone", url, str(dest))
    if cloned.returncode != 0:
        die(cloned.stderr.strip() or f"Could not clone {SKILL_DIR}")
    detached = git_exec("-C", str(dest), "checkout", "--detach", recorded)
    if detached.returncode != 0:
        die(detached.stderr.strip() or f"Could not check out {SKILL_DIR} {recorded}")


def require_skill_checkout() -> None:
    """This kit checkout includes the skill commit. A miss is a crash, not a check row."""
    recorded = index_gitlink(KIT_ROOT, SKILL_DIR)
    if not recorded:
        die(f"{KIT_ROOT} has no {SKILL_DIR} submodule record.")
    head = skill_head(KIT_ROOT / SKILL_DIR)
    if head != recorded:
        die(skill_mismatch(recorded, head))


def recorded_commit(project: Path) -> str:
    """Return the gitlink. Die unless this script is that submodule."""
    recorded = gitlink(project)
    if not recorded:
        die(f"{project} has no {KIT_DIR} submodule. Attach it with new-project or adopt.")
    checkout = submodule_checkout(project)
    if checkout != KIT_ROOT:
        die(
            f"This script is {KIT_ROOT}, but {project}'s {KIT_DIR} is {checkout}. "
            f"Run scripts/harness.py from {KIT_DIR}."
        )
    return recorded


def require_version(project: Path) -> str:
    recorded = recorded_commit(project)
    head = head_commit(KIT_ROOT)
    if recorded != head:
        die(
            f"Submodule record {recorded[:12]} does not match kit HEAD {head[:12]}. "
            "Commit the kit repo first, checkout that commit here, and run upgrade."
        )
    refuse_dirty_kit()
    if (project / ".harness").exists():
        die("Remove .harness/. The kit is the harness-kit submodule. check reports pin.legacy until it is gone.")
    return recorded


def bad_path(root: Path, rel: str) -> str | None:
    """Wrapper. The tree decides which paths belong to this repository."""
    return tree.bad_path(root, rel)


def pack_for(project: Path | None, pack_id: str) -> dict:
    return load_pack(KIT_ROOT, project, pack_id)


def refuse_dirty_kit() -> None:
    """A dirty kit checkout is a crash, not a check result row.

    The skill commit is checked first. A missing or different agent-skill
    checkout is also a dirty git status, and that message would hide the commit.
    """
    require_skill_checkout()
    if git_out(KIT_ROOT, "status", "--porcelain"):
        die(
            "pin.dirty kit checkout has uncommitted changes. "
            "Commit them in the harness-kit repo before the version can change."
        )


def plan_paths(project: Path) -> list[Path]:
    root = project / "plans"
    if not root.is_dir():
        return []
    return sorted(root.glob("*/plan.json"))


def open_session_ids(project: Path) -> set[str]:
    """Session ids whose status is open. A file that cannot be read is not open."""
    found: set[str] = set()
    for path in session_paths(project):
        try:
            item = read_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if item.get("status") == "open" and isinstance(item.get("id"), str):
            found.add(item["id"])
    return found


def _keep_scratch(path: Path, open_ids: set[str]) -> bool:
    """A regular readme, or a real directory named for an open session."""
    if path.is_symlink():
        return False
    if path.name == "README.md" and path.is_file():
        return True
    return path.name in open_ids and path.is_dir()


def _remove_unfollowed(path: Path) -> None:
    """Delete path. Unlink a symlink. Do not follow it."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        path.unlink()
        return
    for child in list(path.iterdir()):
        _remove_unfollowed(child)
    path.rmdir()


def clean_tmp(project: Path) -> list[str]:
    """Remove scratch that is not an open session directory or tmp/README.md.

    Creates tmp/ when it is missing. Does not remove tmp/ itself.
    Returns project-relative paths that were removed.
    """
    root = project / "tmp"
    root.mkdir(parents=True, exist_ok=True)
    open_ids = open_session_ids(project)
    removed: list[str] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if _keep_scratch(child, open_ids):
            continue
        rel = child.relative_to(project).as_posix()
        if tree.classify(project, rel) == tree.LEAF:
            continue
        try:
            _remove_unfollowed(child)
        except OSError as exc:
            die(f"tmp.clean {rel}: {exc}")
        removed.append(rel)
    return removed


def session_paths(project: Path) -> list[Path]:
    root = project / "sessions"
    if not root.is_dir():
        return []
    return sorted(root.glob("*/session.json"))


def session_folder(project: Path, session_id: str) -> Path:
    folder = project / "sessions" / session_id
    if not (folder / "session.json").is_file():
        die(f"No session {session_id}.")
    return folder


def load_session(project: Path, session_id: str) -> tuple[Path, dict]:
    folder = session_folder(project, session_id)
    return folder, read_json(folder / "session.json")


def canonical_session(data: dict) -> bytes:
    body = {key: value for key, value in data.items() if key != "fingerprint"}
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return encoded.encode("utf-8")


def seal_bytes(path: Path) -> bytes:
    """UTF-8 text with LF newlines. A file that is not UTF-8 cannot be sealed."""
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name} is not UTF-8") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def fingerprint(folder: Path, data: dict) -> str:
    """Seal the session record and each graded session file that is present.

    Text files are hashed as UTF-8 with LF newlines. That is a no-op for the
    LF files this kit writes, so an older seal still matches.
    """
    digest = hashlib.sha256()
    digest.update(canonical_session(data))
    digest.update(b"\0")
    digest.update(seal_bytes(folder / "session.md"))
    for name in ("design.md", "review.md"):
        path = folder / name
        if path.is_file():
            digest.update(b"\0")
            digest.update(seal_bytes(path))
    for name in ("abandon.json", "status.json", "spawns.json"):
        path = folder / name
        if path.is_file():
            digest.update(b"\0")
            digest.update(seal_bytes(path))
    return digest.hexdigest()


def project_stamp(project: Path) -> str:
    document = read_json(project / "project" / "project.json")
    stamp = document.get("project_stamp") or ""
    return stamp if isinstance(stamp, str) else ""


def status_path(folder: Path) -> Path:
    return folder / "status.json"


def blank_status(pack: dict) -> dict:
    return {"nodes": {node["id"]: {"state": "pending"} for node in pack["nodes"]}}


def read_status(folder: Path) -> dict | None:
    path = status_path(folder)
    if not path.is_file():
        return None
    try:
        return read_json(path)
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name} is not UTF-8") from exc


def node_state(document: dict, node_id: str) -> str | None:
    row = document.get("nodes", {}).get(node_id)
    if not isinstance(row, dict):
        return None
    state = row.get("state")
    return state if isinstance(state, str) else None


def names_status_file(rel: str) -> bool:
    norm = rel.replace("\\", "/")
    return norm == "status.json" or norm.endswith("/status.json")


def covered(rel: str, patterns: list[str], leaf_set: set[str]) -> bool:
    """True when one pattern covers rel. A leaf pattern covers only itself."""
    return any(tree.covers(pattern, rel, leaf_set) for pattern in patterns)


def _glob_path(rel: str) -> bool:
    return any(char in rel.replace("\\", "/") for char in "*?[")


def _show(project: Path, spec: str) -> str | None:
    result = git_exec("-C", str(project), "show", spec)
    if result.returncode != 0:
        return None
    return result.stdout


def _section_body(text: str | None, name: str) -> str:
    """Text under one markdown heading, until the next heading of the same rank."""
    if not text:
        return ""
    marker = f"## {name}"
    start = None
    for line in text.splitlines(keepends=True):
        if start is None:
            if line.strip() == marker:
                start = ""
            continue
        if line.startswith("## "):
            break
        start += line
    return (start or "").strip()


def _outside_markers(text: str) -> str | None:
    if BEGIN not in text or END not in text:
        return None
    prefix, rest = text.split(BEGIN, 1)
    if END not in rest:
        return None
    _block, suffix = rest.split(END, 1)
    return prefix + suffix


def _strip_sessions(document: dict) -> dict:
    features = document.get("features")
    if not isinstance(features, list):
        return document
    cleaned = []
    for feature in features:
        if isinstance(feature, dict):
            cleaned.append(
                {
                    key: value
                    for key, value in feature.items()
                    if key not in {"sessions", "passes", "passed_on"}
                }
            )
        else:
            cleaned.append(feature)
    stripped = dict(document)
    stripped["features"] = cleaned
    return stripped


def _parse_json(text: str | None) -> object | None:
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _side_text(project: Path, rel: str, staged: bool) -> str | None:
    if staged:
        return _show(project, f":{rel}")
    path = project / rel
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _not_product(project: Path, rel: str, staged: bool) -> bool:
    """Paths that are not a product change. The list lives here and in protocols/plan.md."""
    norm = rel.replace("\\", "/")
    if norm in {"project/links.json", ".gitmodules", KIT_DIR}:
        return True
    if norm.startswith(("plans/", "sessions/", f"{KIT_DIR}/")):
        return True
    if norm == "AGENTS.md":
        head = _show(project, f"HEAD:{norm}")
        side = _side_text(project, norm, staged)
        old = _outside_markers(head or "")
        new = _outside_markers(side or "")
        if old is not None and new is not None and old == new:
            return True
    if norm == "project/features.json":
        before = _parse_json(_show(project, f"HEAD:{norm}"))
        after = _parse_json(_side_text(project, norm, staged))
        if isinstance(before, dict) and isinstance(after, dict):
            if _strip_sessions(before) == _strip_sessions(after):
                return True
    return False


def _parse_name_status(blob: str) -> list[str]:
    """NUL records from `git diff -z --name-status`. Renames contribute both paths.

    Without `-z`, git quotes a non-ASCII name, and that quoted form does not
    match the product path.
    """
    parts = blob.split("\0")
    if parts and parts[-1] == "":
        parts.pop()
    found: list[str] = []
    index = 0
    while index < len(parts):
        status = parts[index]
        if not status:
            index += 1
            continue
        kind = status[0]
        if kind in {"R", "C"}:
            if index + 2 >= len(parts):
                break
            found.append(parts[index + 1])
            found.append(parts[index + 2])
            index += 3
        else:
            if index + 1 >= len(parts):
                break
            found.append(parts[index + 1])
            index += 2
    return found


def _diff_paths(project: Path, staged: bool) -> list[str]:
    """Changed paths. No commit yet means no rows. Renames count on both sides."""
    if git_out(project, "rev-parse", "--verify", "HEAD") is None:
        return []
    args = ["diff", "-z", "--name-status", "--find-renames"]
    if staged:
        args.append("--cached")
    else:
        args.append("HEAD")
    diff = git_exec("-C", str(project), *args)
    if diff.returncode != 0:
        die(diff.stderr.strip() or "git diff failed")
    found = _parse_name_status(diff.stdout)
    if staged:
        return found
    others = git_exec("-C", str(project), "ls-files", "--others", "--exclude-standard", "-z")
    if others.returncode != 0:
        die(others.stderr.strip() or "git ls-files failed")
    for rel in others.stdout.split("\0"):
        if rel:
            found.append(rel)
    return found


def _product_paths(project: Path, staged: bool) -> list[str]:
    """Product files in the diff. A directory is not a member of the list."""
    seen: set[str] = set()
    found: list[str] = []
    for rel in _diff_paths(project, staged):
        norm = rel.replace("\\", "/")
        if norm in seen or _not_product(project, norm, staged):
            continue
        seen.add(norm)
        found.append(norm)
    return found


def _session_records(project: Path, staged: bool) -> list[dict]:
    """Session records from the worktree, or from the index when staged."""
    records: list[dict] = []
    if not staged:
        for path in session_paths(project):
            try:
                item = read_json(path)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(item, dict):
                records.append(item)
        return records
    listed = git_exec("-C", str(project), "ls-files", "--cached", "-z", "--", "sessions")
    if listed.returncode != 0:
        die(listed.stderr.strip() or "git ls-files failed")
    for rel in listed.stdout.split("\0"):
        if not rel.endswith("/session.json") or rel.count("/") != 2:
            continue
        parsed = _parse_json(_show(project, f":{rel}"))
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def _closed_in_head(project: Path, session_id: str) -> bool:
    if not session_id:
        return False
    parsed = _parse_json(_show(project, f"HEAD:sessions/{session_id}/session.json"))
    return isinstance(parsed, dict) and parsed.get("status") == "closed"


def _utf8_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def _index_text(project: Path, rel: str) -> str:
    return _show(project, f":{rel}") or ""


def _handoff_ok(texts: list[str]) -> bool:
    for text in texts:
        if _section_body(text, "Coverage").strip() or _section_body(text, "Not found").strip():
            return True
    return False


def _handoff_texts(project: Path, session_id: str, staged: bool) -> list[str]:
    if not staged:
        root = project / "sessions" / session_id / "handoffs"
        if not root.is_dir():
            return []
        found = []
        for path in sorted(root.rglob("*")):
            if path.is_file():
                found.append(_utf8_text(path))
        return found
    listed = git_exec(
        "-C",
        str(project),
        "ls-files",
        "--cached",
        "-z",
        "--",
        f"sessions/{session_id}/handoffs",
    )
    if listed.returncode != 0:
        die(listed.stderr.strip() or "git ls-files failed")
    found = []
    for rel in listed.stdout.split("\0"):
        if rel:
            found.append(_index_text(project, rel))
    return found


def _coding_record_results(
    session_id: str,
    design: str,
    review: str,
    verify: str,
    handoff: bool,
    writes: list[str],
) -> list:
    """Close evidence for a coding session. The cursor is not the ticket."""
    results = []
    if not design.strip():
        results.append(fail("session.design", f"{session_id} design.md is empty"))
    if not review.strip():
        results.append(fail("session.review", f"{session_id} review.md is empty"))
    if not verify.strip():
        results.append(fail("session.verify", f"{session_id} verify.md is empty"))
    if writes and not handoff:
        results.append(fail("session.handoff", f"{session_id} needs a handoff body"))
    return results


def _coding_texts(project: Path, session_id: str, staged: bool) -> tuple[str, str, str, bool]:
    if staged:
        base = f"sessions/{session_id}"
        return (
            _index_text(project, f"{base}/design.md"),
            _index_text(project, f"{base}/review.md"),
            _index_text(project, f"{base}/verify.md"),
            _handoff_ok(_handoff_texts(project, session_id, True)),
        )
    folder = project / "sessions" / session_id
    return (
        _utf8_text(folder / "design.md"),
        _utf8_text(folder / "review.md"),
        _utf8_text(folder / "verify.md"),
        _handoff_ok(_handoff_texts(project, session_id, False)),
    )


def coverage_results(project: Path, staged: bool) -> list:
    """One session owns the exact product files.

    While the tree is dirty, check wants one open session. A coding session
    already has a non-empty design.md. writes is not compared yet.

    The hook reads the index. It wants one session that is closed there and
    was not closed at HEAD, and whose writes are exactly the staged product
    paths. An open plan covers nothing. A directory covers nothing.

    Not product: plans/, sessions/, project/links.json, .gitmodules,
    the harness-kit gitlink, an AGENTS.md edit inside the generated
    markers, and a features.json edit that only changes sessions lists,
    passes, or passed_on.
    A submodule path is a product change. Files inside it are not changes
    in this repository.
    """
    paths = _product_paths(project, staged)
    if not paths:
        return []
    sessions = _session_records(project, staged)
    if not staged:
        opens = [item for item in sessions if item.get("status") == "open"]
        if len(opens) != 1:
            found = ", ".join(str(item.get("id") or "?") for item in opens) or "none"
            return [fail("coverage.gap", f"{', '.join(paths)} needs one open session ({found})")]
        session = opens[0]
        session_id = str(session.get("id") or "session")
        if session.get("pack") == "coding":
            design, _review, _verify, _handoff = _coding_texts(project, session_id, False)
            if not design.strip():
                return [fail("session.design", f"{session_id} design.md is empty")]
        return []
    fresh = [
        item
        for item in sessions
        if item.get("status") == "closed" and not _closed_in_head(project, str(item.get("id") or ""))
    ]
    if len(fresh) != 1:
        return [fail("coverage.gap", f"{', '.join(paths)} needs one session closed in this commit")]
    session = fresh[0]
    session_id = str(session.get("id") or "session")
    writes = [
        item.replace("\\", "/")
        for item in (session.get("writes") or [])
        if isinstance(item, str)
    ]
    if set(writes) != set(paths):
        return [fail("coverage.gap", f"{session_id} writes are not the product paths")]
    if session.get("pack") == "coding":
        design, review, verify, handoff = _coding_texts(project, session_id, True)
        return _coding_record_results(session_id, design, review, verify, handoff, writes)
    return []


HOOKS_PATH = f"{KIT_DIR}/hooks"


def hooks_setting(project: Path) -> str | None:
    return git_out(project, "config", "--get", "core.hooksPath")


def hooks_are_kit(project: Path, value: str) -> bool:
    norm = value.replace("\\", "/").rstrip("/")
    if norm == HOOKS_PATH:
        return True
    try:
        return Path(value).expanduser().resolve() == (project / HOOKS_PATH).resolve()
    except OSError:
        return False


def ensure_kit_hooks(project: Path) -> None:
    """Point core.hooksPath at the kit hooks when it is unset or already there.

    A foreign value is left in place. This does not write a project file.
    """
    current = hooks_setting(project)
    if current is not None:
        return
    result = git_exec("-C", str(project), "config", "core.hooksPath", HOOKS_PATH)
    if result.returncode != 0:
        die(result.stderr.strip() or "could not set core.hooksPath")


def hook_results(project: Path) -> list:
    current = hooks_setting(project)
    if current is not None and hooks_are_kit(project, current):
        return []
    return [fail("hook.missing", "core.hooksPath is not harness-kit/hooks")]


def _checked(project: Path, results: list) -> list:
    results.extend(hook_results(project))
    results.extend(coverage_results(project, False))
    if not any(getattr(item, "check_id", None) == "project.boundary" for item in results):
        detail = tree.boundary_detail(project)
        if detail:
            results.append(fail("project.boundary", detail))
    return results


def commit_scaffold(project: Path) -> None:
    """Commit the birth tree before the hook is installed."""
    added = git_exec("-C", str(project), "add", "-A")
    if added.returncode != 0:
        die(added.stderr.strip() or "could not stage the scaffold")
    committed = git_exec(
        "-C",
        str(project),
        "-c",
        "user.email=harness-kit@localhost",
        "-c",
        "user.name=harness-kit",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "Scaffold the project",
    )
    if committed.returncode != 0:
        die(committed.stderr.strip() or "could not commit the scaffold")


def owned_files(project: Path, patterns: list[str]) -> list[str]:
    """Files a worker owns. The same matcher as evidence globs."""
    found: list[str] = []
    for pattern in patterns:
        for path in matching_paths(project, pattern):
            found.append(path.relative_to(project).as_posix())
    return found


def outside_sources(worker: dict, sources: list, leaf_set: set[str]) -> list[str]:
    """Declared sources that miss this worker's reads or hit its forbidden list."""
    bad: list[str] = []
    for source in sources:
        if (
            not isinstance(source, str)
            or not covered(source, worker["reads"], leaf_set)
            or covered(source, worker["forbidden"], leaf_set)
        ):
            bad.append(source if isinstance(source, str) else "source")
    return bad


def assemble(project: Path, write: bool) -> dict:
    """Build the link index. Session files are the source of session edges."""
    project_doc = read_json(project / "project" / "project.json")
    sessions = [read_json(path) for path in session_paths(project)]
    by_plan: dict[str, list[str]] = {}
    by_feature: dict[str, list[str]] = {}
    for item in sessions:
        by_plan.setdefault(item["plan_id"], []).append(item["id"])
        if item.get("feature_id"):
            by_feature.setdefault(item["feature_id"], []).append(item["id"])

    plan_rows = []
    for path in plan_paths(project):
        plan = read_json(path)
        plan["sessions"] = sorted(by_plan.get(plan["id"], []))
        if write:
            write_json(path, plan)
        plan_rows.append(
            {
                "id": plan["id"],
                "path": path.relative_to(project).as_posix(),
                "status": plan["status"],
                "pack": plan["pack"],
                "sessions": plan["sessions"],
                "paths": plan["paths"],
            }
        )

    features_path = project / "project" / "features.json"
    features_doc = read_json(features_path)
    for feature in features_doc["features"]:
        feature["sessions"] = sorted(by_feature.get(feature["id"], []))
    if write:
        write_json(features_path, features_doc)

    session_rows = []
    for path in session_paths(project):
        item = read_json(path)
        session_rows.append(
            {
                "id": item["id"],
                "path": path.relative_to(project).as_posix(),
                "plan_id": item["plan_id"],
                "pack": item["pack"],
                "status": item["status"],
                "phase": item["phase"],
                "feature_id": item["feature_id"],
                "writes": item["writes"],
                "harness_commit": item.get("harness_commit") or "",
            }
        )
    links = {
        "project_id": project_doc["id"],
        "plans": plan_rows,
        "sessions": session_rows,
        "features": features_doc["features"],
    }
    if write:
        write_json(project / "project" / "links.json", links)
    return links


def render_stub(kit_commit: str, move: str) -> str:
    raw = (KIT_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8")
    return raw.replace("__KIT_COMMIT__", kit_commit).replace("__PIN_MOVE__", move.rstrip("\n"))


def stub_block(kit_commit: str, move: str) -> str:
    raw = render_stub(kit_commit, move)
    start = raw.index(BEGIN)
    end = raw.index(END) + len(END)
    return raw[start:end]


def refresh_stub(project: Path, kit_commit: str, move: str) -> None:
    path = project / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        die("AGENTS.md has no harness-kit markers. Upgrade will not rewrite a hand-edited router.")
    prefix, rest = text.split(BEGIN, 1)
    _, suffix = rest.split(END, 1)
    write_text(path, prefix + stub_block(kit_commit, move) + suffix)


def write_controls(
    project: Path,
    kit: Path,
    project_id: str,
    name: str,
    kit_commit: str,
    *,
    overwrite: bool,
) -> None:
    """Write kit control files. adopt passes overwrite False and leaves existing bytes."""
    templates = kit / "templates"
    agents_path = project / "AGENTS.md"
    if overwrite or not agents_path.exists():
        write_text(agents_path, render_stub(kit_commit, birth_text(kit_commit)))
    ignore_path = project / ".gitignore"
    if overwrite or not ignore_path.exists():
        write_text(ignore_path, (templates / "gitignore").read_text(encoding="utf-8"))
    for relative in STATIC_TEMPLATES:
        dest = project / relative
        if overwrite or not dest.exists():
            write_text(dest, (templates / relative).read_text(encoding="utf-8"))
    ident_path = project / "project" / "project.json"
    if overwrite or not ident_path.exists():
        write_json(
            ident_path,
            {
                "id": project_id,
                "name": name,
                "created": today(),
                "verify": "",
                "kit_commit_at_init": kit_commit,
            },
        )
    features_path = project / "project" / "features.json"
    if overwrite or not features_path.exists():
        write_json(features_path, {"features": []})
    links_path = project / "project" / "links.json"
    if overwrite:
        assemble(project, write=True)
    elif not links_path.exists():
        # Rebuild the index in memory. Do not rewrite plans or features that already exist.
        write_json(links_path, assemble(project, write=False))


def scaffold(project: Path, kit: Path, project_id: str, name: str, kit_commit: str) -> None:
    write_controls(project, kit, project_id, name, kit_commit, overwrite=True)


def ensure_repo(dest: Path) -> None:
    """dest is its own toplevel when this returns, even if an ancestor work tree exists."""
    if tree.own_toplevel(dest):
        return
    created = git_exec("init", str(dest))
    if created.returncode != 0:
        die(created.stderr.strip() or "git init failed")
    if not tree.own_toplevel(dest):
        die(f"{dest} is not its own git repository.")


def origin_url() -> str:
    return git_out(KIT_ROOT, "remote", "get-url", "origin") or str(KIT_ROOT)


def write_gitmodules_section(project: Path, name: str, path: str, url: str) -> None:
    """Write one ``.gitmodules`` section keyed by the full submodule name.

    The header must match that name. A name that merely contains ``harness-kit``
    is a different submodule.
    """
    file_path = project / ".gitmodules"
    text = file_path.read_text(encoding="utf-8") if file_path.is_file() else ""
    header = f'[submodule "{name}"]'
    lines = text.splitlines()
    out: list[str] = []
    section = False
    found = False
    replaced_url = False
    replaced_path = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if section and not replaced_path:
                out.append(f"\tpath = {path}")
            if section and not replaced_url:
                out.append(f"\turl = {url}")
            section = stripped == header
            if section:
                found = True
                replaced_url = False
                replaced_path = False
            out.append(line)
            continue
        if section and stripped.startswith("path ="):
            out.append(f"\tpath = {path}")
            replaced_path = True
            continue
        if section and stripped.startswith("url ="):
            out.append(f"\turl = {url}")
            replaced_url = True
            continue
        out.append(line)
    if section and not replaced_path:
        out.append(f"\tpath = {path}")
    if section and not replaced_url:
        out.append(f"\turl = {url}")
    if not found:
        if out and out[-1] != "":
            out.append("")
        out.extend([header, f"\tpath = {path}", f"\turl = {url}"])
    body = "\n".join(out).rstrip() + "\n"
    write_text(file_path, body)


def write_gitmodules(project: Path, url: str) -> None:
    """Set the kit URL. ``pin --remote`` does not rewrite any other submodule."""
    write_gitmodules_section(project, KIT_DIR, KIT_DIR, url)


def record_leaf(outer: Path, rel: str, commit: str) -> None:
    """Stage one leaf on the enclosing toplevel. Do not commit that repository.

    The index path is relative to the toplevel. ``git -C`` a subdirectory would
    record the path on the enclosing root under the last component alone.
    """
    staged = git_exec(
        "-C",
        str(outer),
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{commit},{rel}",
    )
    if staged.returncode != 0:
        die(staged.stderr.strip() or "could not record the submodule")
    write_gitmodules_section(outer, rel, rel, str((outer / rel).resolve()))
    added = git_exec("-C", str(outer), "add", "--", ".gitmodules")
    if added.returncode != 0:
        die(added.stderr.strip() or "could not stage .gitmodules")


def stage_gitlink(project: Path) -> str:
    checkout = project / KIT_DIR
    commit = git_out(checkout, "rev-parse", "HEAD")
    if not commit:
        die(f"{checkout} is not a git checkout.")
    staged = git_exec(
        "-C",
        str(project),
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{commit},{KIT_DIR}",
    )
    if staged.returncode != 0:
        die(staged.stderr.strip() or "could not record the harness-kit submodule")
    added = git_exec("-C", str(project), "add", "--", ".gitmodules")
    if added.returncode != 0:
        die(added.stderr.strip() or "could not stage .gitmodules")
    return commit


def clone_kit(dest: Path) -> str:
    commit = head_commit(KIT_ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cloned = git_exec("clone", "--local", str(KIT_ROOT), str(dest))
    if cloned.returncode != 0:
        cloned = git_exec("clone", str(KIT_ROOT), str(dest))
        if cloned.returncode != 0:
            die(cloned.stderr.strip() or "git clone failed")
    detached = git_exec("-C", str(dest), "checkout", "--detach", commit)
    if detached.returncode != 0:
        die(detached.stderr.strip() or "git checkout of kit commit failed")
    materialize_skill(dest)
    return commit


def attach_submodule(project: Path) -> str:
    """Clone this kit to harness-kit/ and record that commit as the gitlink."""
    ensure_repo(project)
    dest = project / KIT_DIR
    if dest.exists():
        commit = git_out(dest, "rev-parse", "HEAD")
        if not commit:
            die(f"{dest} is not a git checkout.")
    else:
        commit = clone_kit(dest)
    # Record the checkout that holds this commit. pin --remote points .gitmodules
    # at the published remote after the objects are already local.
    write_gitmodules(project, str(KIT_ROOT))
    return stage_gitlink(project)


def drop_legacy_pin(project: Path) -> None:
    """upgrade may remove the old pin file. check still fails while .harness/ remains."""
    path = project / ".harness" / "pin.json"
    if not path.is_file():
        return
    try:
        pin = read_json(path)
    except json.JSONDecodeError as exc:
        die(f".harness/pin.json is not json: {exc}")
    head = head_commit(KIT_ROOT)
    if pin.get("kit_commit") != head:
        die(
            ".harness/pin.json records a different commit from this kit. "
            "Refusing to move the version and the anchor in one step."
        )
    path.unlink()


def create_project(dest: Path, project_id: str, name: str) -> str:
    """Create one project toplevel at dest and commit that scaffold.

    If dest is inside a harness project, stage a leaf on that project for this
    new repository and do not commit the enclosing project. Never modify a
    repository that is not a harness project. Refuse if the enclosing index
    already has a gitlink at that path.
    """
    dest = dest.resolve()
    if dest == KIT_ROOT or KIT_ROOT in dest.parents:
        die("Refusing to create a project inside the kit repo.")
    outer = tree.enclosing_repo(dest)
    rel = None
    if outer is not None:
        rel = dest.relative_to(outer).as_posix()
        if tree.index_gitlink(outer, rel):
            die(f"{rel} is already a submodule of {outer}.")
        if not tree.is_project(outer):
            die(f"{outer} is not a harness project. Refusing to create a project inside it.")
    if dest.exists() and any(dest.iterdir()):
        die(f"{dest} exists and is not empty.")
    dest.mkdir(parents=True, exist_ok=True)
    commit = attach_submodule(dest)
    scaffold(dest, dest / KIT_DIR, project_id, name, commit)
    commit_scaffold(dest)
    ensure_kit_hooks(dest)
    if outer is not None and rel is not None:
        head = git_out(dest, "rev-parse", "HEAD")
        if not head:
            die(f"{dest} has no commit to record.")
        record_leaf(outer, rel, head)
    return commit


def cmd_new_project(args: argparse.Namespace) -> None:
    refuse_dirty_kit()
    dest = Path(args.dest).expanduser().resolve()
    project_id = args.id or slugify(dest.name)
    if not slug_ok(project_id):
        die("Project --id must be a lowercase slug.")
    name = args.name or dest.name
    commit = create_project(dest, project_id, name)
    print(f"Created {dest} id={project_id} kit={commit[:12]}")


def cmd_adopt(args: argparse.Namespace) -> None:
    """Attach the kit to a repo that already has files. Do not treat those files as sessions."""
    refuse_dirty_kit()
    dest = Path(args.dest).expanduser().resolve()
    if dest == KIT_ROOT or KIT_ROOT in dest.parents:
        die("Refusing to adopt the kit repo.")
    if not dest.is_dir() or not any(dest.iterdir()):
        die(f"{dest} is empty. Use new-project for an empty directory.")
    if not tree.own_toplevel(dest) and tree.enclosing_repo(dest) is not None:
        die(f"{dest} is inside another repository.")
    if gitlink(dest) and (dest / KIT_DIR).is_dir():
        commit = git_out(dest / KIT_DIR, "rev-parse", "HEAD")
        if not commit:
            die(f"{dest / KIT_DIR} is not a git checkout.")
    else:
        commit = attach_submodule(dest)
    ident_path = dest / "project" / "project.json"
    if ident_path.is_file():
        ident = read_json(ident_path)
        project_id = ident["id"]
        name = ident.get("name") or project_id
    else:
        project_id = args.id or slugify(dest.name)
        if not slug_ok(project_id):
            die("Project --id must be a lowercase slug.")
        name = args.name or dest.name
    write_controls(dest, dest / KIT_DIR, project_id, name, commit, overwrite=False)
    ensure_kit_hooks(dest)
    # The child already has history. Stage the same leaf new-project would, and
    # do not commit either repository here.
    outer = tree.enclosing_repo(dest)
    if outer is not None and tree.is_project(outer):
        rel = dest.relative_to(outer).as_posix()
        if tree.index_gitlink(outer, rel) is None:
            head = git_out(dest, "rev-parse", "HEAD")
            if not head:
                die(f"{dest} has no commit to record.")
            record_leaf(outer, rel, head)
    print(f"Adopted {dest} id={project_id} kit={commit[:12]}")


def cmd_sync(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    recorded = gitlink(project)
    if not recorded:
        die(f"No {KIT_DIR} submodule record. Attach it with adopt.")
    dest = project / KIT_DIR
    if not dest.exists():
        url = submodule_url(project) or origin_url()
        cloned = git_exec("clone", url, str(dest))
        if cloned.returncode != 0:
            die(cloned.stderr.strip() or f"Could not clone {url}")
        detached = git_exec("-C", str(dest), "checkout", "--detach", recorded)
        if detached.returncode != 0:
            die(detached.stderr.strip() or "Could not check out the recorded commit")
        materialize_skill(dest)
        ensure_kit_hooks(project)
        print(f"Restored {dest}")
        return
    head = git_out(dest, "rev-parse", "HEAD")
    if head != recorded:
        die(f"Kit HEAD {head} does not match the submodule record {recorded}.")
    materialize_skill(dest)
    ensure_kit_hooks(project)
    print("Kit already matches the submodule record.")


def cmd_upgrade(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    # git checkout leaves a new skill gitlink as an empty directory.
    recorded_skill = index_gitlink(KIT_ROOT, SKILL_DIR)
    if recorded_skill and skill_head(KIT_ROOT / SKILL_DIR) != recorded_skill:
        materialize_skill(KIT_ROOT)
    refuse_dirty_kit()
    drop_legacy_pin(project)
    if not (project / KIT_DIR).exists():
        ensure_repo(project)
        clone_kit(project / KIT_DIR)
        write_gitmodules(project, str(KIT_ROOT))
    elif submodule_checkout(project) != KIT_ROOT:
        die(
            f"This script is {KIT_ROOT}, but {project}'s {KIT_DIR} is {submodule_checkout(project)}. "
            f"Run upgrade from the {KIT_DIR} checkout."
        )
    if args.remote:
        write_gitmodules(project, args.remote)
        git_exec("-C", str(project / KIT_DIR), "remote", "set-url", "origin", args.remote)
    commit = git_out(project / KIT_DIR, "rev-parse", "HEAD")
    if not commit:
        die(f"{project / KIT_DIR} is not a git checkout.")
    text = move_text(project, KIT_ROOT, commit)
    staged = stage_gitlink(project)
    if staged != commit:
        die(f"Staged {staged} but the checkout is {commit}.")
    refresh_stub(project, commit, text)
    ensure_kit_hooks(project)
    sys.stdout.write(text)


def cmd_pin(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    require_version(project)
    if not args.remote:
        die("Pass --remote.")
    write_gitmodules(project, args.remote)
    git_exec("-C", str(project), "add", "--", ".gitmodules")
    if (project / KIT_DIR).is_dir():
        git_exec("-C", str(project / KIT_DIR), "remote", "set-url", "origin", args.remote)
    print(f"submodule url={args.remote}")


def cmd_new_plan(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    require_version(project)
    if not slug_ok(args.id):
        die("Plan id must be a lowercase slug.")
    pack_for(project, args.pack)
    if args.depth not in ("low", "medium", "high"):
        die("Depth must be low, medium, or high.")
    folder = project / "plans" / args.id
    if folder.exists():
        die(f"Plan {args.id} already exists.")
    project_doc = read_json(project / "project" / "project.json")
    paths = [f"plans/{args.id}/plan.md"]
    for extra in args.path or []:
        reason = bad_path(project, extra)
        if reason:
            die(f"{extra}: {reason}")
        if _glob_path(extra):
            die(f"{extra}: plan paths are prefixes")
        paths.append(extra)
    record = {
        "id": args.id,
        "project_id": project_doc["id"],
        "title": args.title,
        "status": "open",
        "pack": args.pack,
        "depth": args.depth,
        "created": today(),
        "paths": paths,
        "sessions": [],
    }
    errors = validate(record, schema("plan.schema.json"), "plan")
    if errors:
        die("\n".join(errors))
    folder.mkdir(parents=True)
    write_json(folder / "plan.json", record)
    write_text(
        folder / "plan.md",
        f"# {args.title}\n\n"
        f"- Project: `{project_doc['id']}`\n"
        f"- Pack: `{args.pack}`\n"
        f"- Depth: `{args.depth}`\n\n"
        "## Question\n\n"
        "## Done\n",
    )
    assemble(project, write=True)
    print(f"Plan {args.id}")


def cmd_new_feature(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    require_version(project)
    if not slug_ok(args.id):
        die("Feature id must be a lowercase slug.")
    path = project / "project" / "features.json"
    document = read_json(path)
    if any(item["id"] == args.id for item in document["features"]):
        die(f"Feature {args.id} already exists.")
    document["features"].append(
        {
            "id": args.id,
            "title": args.title,
            "passes": False,
            "sessions": [],
            "passed_on": None,
        }
    )
    errors = validate(document, schema("features.schema.json"), "features")
    if errors:
        die("\n".join(errors))
    write_json(path, document)
    assemble(project, write=True)
    print(f"Feature {args.id}")


def cmd_new_session(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    require_version(project)
    plan_path = project / "plans" / args.plan / "plan.json"
    if not plan_path.is_file():
        die(f"No plan {args.plan}.")
    plan = read_json(plan_path)
    if plan["status"] != "open":
        die("Plan is closed.")
    project_doc = read_json(project / "project" / "project.json")
    if plan["project_id"] != project_doc["id"]:
        die("Plan project_id does not match this project.")
    pack_name = plan["pack"]
    spec = pack_for(project, pack_name)
    feature_id = None
    if spec["uses_features"]:
        if not args.feature:
            die("This pack needs --feature.")
        features = read_json(project / "project" / "features.json")
        if args.feature not in {item["id"] for item in features["features"]}:
            die(f"Unknown feature {args.feature}.")
        feature_id = args.feature
    elif args.feature:
        die("This pack does not take --feature.")
    session_id = dated_id(args.id or feature_id or plan["id"])
    if not slug_ok(session_id):
        die("Session id must be a lowercase slug.")
    folder = project / "sessions" / session_id
    if folder.exists():
        die(f"Session {session_id} already exists.")
    writes: list[str] = []
    for extra in args.write or []:
        reason = bad_path(project, extra)
        if reason:
            die(f"{extra}: {reason}")
        if (project / extra).is_dir():
            die(f"{extra} is a directory")
        if extra not in writes:
            writes.append(extra)
    phase = start_node(spec)
    record = {
        "id": session_id,
        "project_id": project_doc["id"],
        "plan_id": plan["id"],
        "pack": pack_name,
        "status": "open",
        "phase": phase,
        "depth": plan["depth"],
        "created": today(),
        "harness_commit": head_commit(KIT_ROOT),
        "project_stamp": project_stamp(project),
        "writes": writes,
        "feature_id": feature_id,
        "architecture_changed": False,
        "immutable": False,
        "fingerprint": None,
        "closed_at": None,
    }
    errors = validate(record, schema("session.schema.json"), "session")
    if errors:
        die("\n".join(errors))
    folder.mkdir(parents=True)
    write_json(folder / "session.json", record)
    write_text(
        folder / "session.md",
        f"# Session {session_id}\n\n"
        f"- Project: `{project_doc['id']}`\n"
        f"- Plan: `{plan['id']}`\n"
        f"- Pack: `{pack_name}`\n"
        f"- Kit: `{record['harness_commit']}`\n\n"
        "## Outcome\n\n"
        "## Gaps\n",
    )
    write_json(status_path(folder), blank_status(spec))
    assemble(project, write=True)
    scratch = project / "tmp" / session_id
    try:
        scratch.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        die(f"tmp.clean {session_id}: {exc}")
    clean_tmp(project)
    print(f"Session {session_id}")


def _entry_gaps(project: Path, folder: Path, node: dict) -> list[str]:
    return blocking_globs(project, folder, node["entry"])


def _prior_states(folder: Path, spec: dict) -> dict[str, str | None]:
    document = read_status(folder) or blank_status(spec)
    return {node["id"]: node_state(document, node["id"]) for node in spec["nodes"]}


def _current_if_complete(project: Path, folder: Path, spec: dict, phase: object) -> str | None:
    """The session phase, when its complete evidence passes. Otherwise none."""
    if not isinstance(phase, str):
        return None
    node = next((item for item in spec["nodes"] if item["id"] == phase), None)
    if node is None:
        return None
    if blocking_globs(project, folder, node["complete"]):
        return None
    return phase


def _enter_blockers(project: Path, folder: Path, spec: dict, record: dict, node: dict) -> list[str]:
    """Reasons the enter rule fails. Empty means the node can be entered. Writes nothing."""
    reasons: list[str] = []
    current = _current_if_complete(project, folder, spec, record.get("phase"))
    blocked = priors_for_enter(node["priors"], _prior_states(folder, spec), current)
    if blocked:
        reasons.append(
            f"{node['id']} waits on " + ", ".join(blocked) + ". Mark that node complete or skipped."
        )
    missing = _entry_gaps(project, folder, node)
    if missing:
        reasons.append(f"{node['id']} needs " + ", ".join(missing))
    return reasons


def _refuse_unready(project: Path, folder: Path, spec: dict, record: dict, node: dict) -> None:
    reasons = _enter_blockers(project, folder, spec, record, node)
    if reasons:
        die(" ".join(reasons))


def _refuse_abandoned(folder: Path) -> None:
    if (folder / "abandon.json").is_file():
        die("Session is abandoned. Start a new session.")


def _open_phase_names(spec: dict) -> str:
    return ", ".join(node["id"] for node in spec["nodes"] if node["id"] != "closed")


def cmd_phase(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    pin = require_version(project)
    chosen = [name for name in ("to", "enter") if getattr(args, name)]
    if len(chosen) != 1:
        die("Pass one of --to or --enter.")
    folder, record = load_session(project, args.session)
    _refuse_abandoned(folder)
    if record["immutable"]:
        die("Session is closed.")
    require_session_stamp(project, record, pin)
    spec = pack_for(project, record["pack"])
    target = args.to or args.enter
    node = find_node(spec, target)
    if target == "closed":
        die("Use close-session to close. Open phases: " + _open_phase_names(spec))
    if args.to:
        if not single_path(spec):
            die("Forked graph. Use phase --enter.")
        order = path_order(spec)
        if record["phase"] not in order or target not in order:
            die("Forked graph. Use phase --enter.")
        if order.index(target) < order.index(record["phase"]):
            die("Phase does not move backward.")
    _refuse_unready(project, folder, spec, record, node)
    record["phase"] = target
    write_json(folder / "session.json", record)
    assemble(project, write=True)
    print(f"{record['id']} phase={target}")


def cmd_preflight(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    pin = require_version(project)
    folder, record = load_session(project, args.session)
    require_session_stamp(project, record, pin)
    spec = pack_for(project, record["pack"])
    target = args.phase
    if not target:
        order = path_order(spec)
        if record["phase"] not in order:
            die("Pass --phase.")
        index = order.index(record["phase"])
        target = order[min(index + 1, len(order) - 1)]
    node = find_node(spec, target)
    reasons = _enter_blockers(project, folder, spec, record, node)
    if reasons:
        die(" ".join(reasons))
    print(f"{target} ready")


def cmd_note_architecture(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    pin = require_version(project)
    folder, record = load_session(project, args.session)
    if record["immutable"]:
        die("Session is closed.")
    require_session_stamp(project, record, pin)
    if not pack_for(project, record["pack"])["architecture_on_close"]:
        die("architecture_changed belongs to a pack with architecture_on_close.")
    record["architecture_changed"] = True
    write_json(folder / "session.json", record)
    print(f"{record['id']} architecture_changed=true")


def _from_diff_target(project: Path) -> str:
    """The one open session, or the one closed session HEAD does not have yet."""
    open_ids: list[str] = []
    reseal: list[str] = []
    for path in session_paths(project):
        try:
            item = read_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        session_id = item.get("id")
        if not isinstance(session_id, str):
            continue
        if item.get("status") == "open":
            open_ids.append(session_id)
        elif item.get("status") == "closed" and not _closed_in_head(project, session_id):
            reseal.append(session_id)
    if len(open_ids) == 1 and not reseal:
        return open_ids[0]
    if not open_ids and len(reseal) == 1:
        return reseal[0]
    die("close-session --from-diff needs one open session.")


def _stage_session_record(project: Path, record: dict) -> None:
    paths = [
        f"sessions/{record['id']}",
        "project/links.json",
        f"plans/{record['plan_id']}/plan.json",
    ]
    if record.get("feature_id"):
        paths.append("project/features.json")
    staged = git_exec("-C", str(project), "add", "--", *paths)
    if staged.returncode != 0:
        die(staged.stderr.strip() or "could not stage the session")


def cmd_close_session(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    pin = require_version(project)
    if args.from_diff:
        found = _from_diff_target(project)
        if args.session and args.session != found:
            die(f"--from-diff found {found}.")
        session_id = found
    elif args.session:
        session_id = args.session
    else:
        die("Pass --session or --from-diff.")
    folder, record = load_session(project, session_id)
    if args.from_diff and _closed_in_head(project, session_id):
        die("HEAD already has this session closed.")
    if record["immutable"] and not args.from_diff:
        die("Session is already closed.")
    _refuse_abandoned(folder)
    if not (folder / "session.md").is_file():
        die("session.md is missing.")
    require_session_stamp(project, record, pin)
    if args.from_diff:
        paths = _product_paths(project, False)
        if not paths:
            die("close-session --from-diff has no product diff")
        record["writes"] = paths
    spec = pack_for(project, record["pack"])
    try:
        _refuse_unready(project, folder, spec, record, find_node(spec, "closed"))
    except ValueError as exc:
        die(str(exc))
    for rel in record["writes"]:
        reason = bad_path(project, rel)
        if reason:
            die(f"{rel}: {reason}")
    graded = dict(record)
    graded["phase"] = "closed"
    graded["status"] = "closed"
    try:
        grade = session_grade(project, folder, graded, spec, feature_id_set(project))
    except ValueError as exc:
        die(str(exc))
    grade.extend(live_owner_results(project, pin, True, include=graded, skip_dirty=False))
    blocking = [item for item in grade if item.status == "FAIL"]
    if blocking:
        die("\n".join(item.line() for item in blocking))
    record["status"] = "closed"
    record["phase"] = "closed"
    record["immutable"] = True
    record["closed_at"] = today()
    record["fingerprint"] = None
    try:
        record["fingerprint"] = fingerprint(folder, record)
    except ValueError as exc:
        die(str(exc))
    errors = validate(record, schema("session.schema.json"), "session")
    if errors:
        die("\n".join(errors))
    write_json(folder / "session.json", record)
    assemble(project, write=True)
    if args.from_diff:
        _stage_session_record(project, record)
    print(f"Closed {record['id']}")
    clean_tmp(project)


def cmd_close_plan(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    require_version(project)
    path = project / "plans" / args.plan / "plan.json"
    if not path.is_file():
        die(f"No plan {args.plan}.")
    plan = read_json(path)
    open_sessions = []
    for session_path in session_paths(project):
        item = read_json(session_path)
        if item["plan_id"] == plan["id"] and item["status"] == "open":
            open_sessions.append(item["id"])
    if open_sessions:
        die("Close these sessions first: " + ", ".join(open_sessions))
    plan["status"] = "closed"
    write_json(path, plan)
    assemble(project, write=True)
    print(f"Closed plan {plan['id']}")


def cmd_status(args: argparse.Namespace) -> None:
    """new-session writes the blank status.json. Only status changes a row."""
    project = find_project(args.project)
    pin = require_version(project)
    folder, record = load_session(project, args.session)
    _refuse_abandoned(folder)
    if record["immutable"]:
        die("Session is closed.")
    require_session_stamp(project, record, pin)
    allowed = {"pending", "in_progress", "complete", "failed", "blocked", "skipped"}
    if args.set not in allowed:
        die("State must be pending, in_progress, complete, failed, blocked, or skipped.")
    spec = pack_for(project, record["pack"])
    node = find_node(spec, args.node)
    document = read_status(folder) or blank_status(spec)
    if args.set == "skipped" and not (args.reason or "").strip():
        die("A skipped node needs --reason.")
    if args.set == "complete":
        missing = blocking_globs(project, folder, node["complete"])
        if missing:
            die(f"{args.node} complete needs " + ", ".join(missing))
    if args.set in {"in_progress", "complete", "failed"}:
        blocked = unsatisfied_priors(node["priors"], _prior_states(folder, spec))
        if blocked:
            die(f"{args.node} waits on " + ", ".join(blocked) + ". Mark that node complete or skipped.")
    row = {"state": args.set}
    if args.set == "skipped":
        row["skip_reason"] = args.reason
    document.setdefault("nodes", {})[args.node] = row
    write_json(status_path(folder), document)
    print(f"{args.node} {args.set}")


def cmd_spawn(args: argparse.Namespace) -> None:
    """Record a returned worker: role, instance, and declared sources.

    reads, forbidden, owns, and exclusive stay on the worker. A row is a return.
    """
    project = find_project(args.project)
    pin = require_version(project)
    if not slug_ok(args.instance):
        die("Instance must be a lowercase slug.")
    folder, record = load_session(project, args.session)
    _refuse_abandoned(folder)
    if record["immutable"]:
        die("Session is closed.")
    require_session_stamp(project, record, pin)
    spec = pack_for(project, record["pack"])
    worker = find_worker(spec, args.role)
    blocked = unsatisfied_priors(worker["priors"], _prior_states(folder, spec))
    if blocked:
        die(f"{args.role} waits on " + ", ".join(blocked) + ".")
    path = folder / "spawns.json"
    document = read_json(path) if path.is_file() else {"spawns": []}
    rows = document.setdefault("spawns", [])
    if worker["exclusive"] and any(row.get("role") == args.role for row in rows):
        die(f"{args.role} is exclusive.")
    if any(row.get("role") == args.role and row.get("instance") == args.instance for row in rows):
        die(f"Spawn {args.role} {args.instance} already exists.")
    sources = []
    for source in args.source or []:
        reason = bad_path(project, source)
        if reason:
            die(f"{source}: {reason}")
        sources.append(source)
    bad = outside_sources(worker, sources, tree.leaves(project))
    if bad:
        die("spawn.sources " + ", ".join(bad) + " is outside reads or inside forbidden")
    rows.append(
        {
            "role": args.role,
            "instance": args.instance,
            "sources": sources,
        }
    )
    write_json(path, document)
    print(f"Spawn {args.role} {args.instance}")


def cmd_abandon(args: argparse.Namespace) -> None:
    """Seal the session as a terminal stop. Later phase commands refuse it."""
    project = find_project(args.project)
    pin = require_version(project)
    if not isinstance(args.reason, str) or len(args.reason.strip()) < 5:
        die("Pass --reason with at least 5 characters.")
    folder, record = load_session(project, args.session)
    if (folder / "abandon.json").is_file() or record.get("immutable"):
        die("Session is already closed.")
    if not (folder / "session.md").is_file():
        die("session.md is missing.")
    require_session_stamp(project, record, pin)
    write_json(
        folder / "abandon.json",
        {"abandoned": True, "reason": args.reason.strip(), "at": today()},
    )
    record["status"] = "closed"
    record["immutable"] = True
    record["closed_at"] = today()
    record["fingerprint"] = None
    try:
        record["fingerprint"] = fingerprint(folder, record)
    except ValueError as exc:
        die(str(exc))
    errors = validate(record, schema("session.schema.json"), "session")
    if errors:
        die("\n".join(errors))
    write_json(folder / "session.json", record)
    assemble(project, write=True)
    print(f"Abandoned {record['id']}")
    clean_tmp(project)


def cmd_mark_pass(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    require_version(project)
    if not args.verifier:
        die("mark-pass requires --verifier. The implementer does not flip this flag.")
    path = project / "project" / "features.json"
    document = read_json(path)
    feature = next((item for item in document["features"] if item["id"] == args.feature), None)
    if feature is None:
        die(f"Unknown feature {args.feature}.")
    open_sessions = []
    for session_path in session_paths(project):
        item = read_json(session_path)
        if item["feature_id"] == args.feature and item["status"] == "open":
            open_sessions.append(item["id"])
    if open_sessions:
        die("Close these sessions first: " + ", ".join(open_sessions))
    feature["passes"] = True
    feature["passed_on"] = today()
    errors = validate(document, schema("features.schema.json"), "features")
    if errors:
        die("\n".join(errors))
    write_json(path, document)
    assemble(project, write=True)
    print(f"Feature {args.feature} passes")


def _as_results(check_id: str, messages: list[str]) -> list:
    return [fail(check_id, message) for message in messages]


def _commit_in_clone(commit: str) -> bool:
    """True when this kit clone can see that commit. Does not run its harness.py."""
    result = git_exec("-C", str(KIT_ROOT), "cat-file", "-e", f"{commit}^{{commit}}")
    return result.returncode == 0


def stamp_door(item: dict, project: Path, kit_commit: str) -> tuple[str, str]:
    """Whether the running pin may write and grade this session.

    grade: harness_commit is the gitlink and project_stamp matches
    project.json. Two empty project stamps match. Writers may change the
    session. check grades it when HEAD is that same gitlink.

    history: the stamps differ and the session is sealed. check verifies
    links and the seal, warns law.stamp, and does not grade.

    foreign: the stamps differ and the session is open. check fails
    law.stamp and does not grade. Writers die. This pin does not finish
    another pin's live session.

    missing: no harness_commit. The caller records FAIL law.commit.

    The detail names the session and both commits. It does not say to
    check out another commit. A checkout that is not the gitlink is
    pin.mismatch and still does not grade. This does not run another
    commit's harness.py. A commit object that is not in this clone says
    so and does not name a checkout.
    """
    commit = item.get("harness_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        return "missing", ""
    session_stamp = item.get("project_stamp") or ""
    if not isinstance(session_stamp, str):
        session_stamp = ""
    if commit == kit_commit and session_stamp == project_stamp(project):
        return "grade", ""
    sealed = bool(item.get("immutable"))
    kind = "history" if sealed else "foreign"
    shown = commit if _commit_in_clone(commit) else f"{commit} (not in this clone)"
    name = item.get("id") or "session"
    if kind == "foreign":
        detail = f"{name} is open on {shown}; this pin {kit_commit} does not write or grade it"
    else:
        detail = (
            f"{name} is sealed on {shown}; links and the seal were checked; the graph was not"
        )
    if session_stamp != project_stamp(project):
        detail += "; project_stamp does not match project/project.json"
    return kind, detail


def require_session_stamp(project: Path, record: dict, kit_commit: str) -> None:
    """Die unless this pin may change the session. Not a check id."""
    kind, detail = stamp_door(record, project, kit_commit)
    if kind != "grade":
        die(detail or f"{record.get('id', 'session')} has no harness_commit")


def _abandon_results(folder: Path) -> tuple[list, bool]:
    path = folder / "abandon.json"
    if not path.is_file():
        return [], False
    try:
        document = read_json(path)
    except UnicodeDecodeError:
        return [fail("seal.fingerprint", "abandon.json is not UTF-8")], False
    except json.JSONDecodeError as exc:
        return [fail("abandon.record", f"abandon.json is not json: {exc}")], False
    reason = document.get("reason")
    if document.get("abandoned") is True and isinstance(reason, str) and reason.strip():
        return [], True
    return [fail("abandon.record", "abandon.json needs abandoned true and a reason")], False


def _status_results(project: Path, folder: Path, pack: dict) -> list:
    # status.json is the checklist. A complete row is legal only when complete evidence passes.
    try:
        document = read_status(folder)
    except ValueError as exc:
        return [fail("seal.fingerprint", str(exc))]
    if document is None:
        return [fail("status.missing", "status.json is missing")]
    nodes = document.get("nodes")
    if not isinstance(nodes, dict):
        return [fail("status.shape", "status.json nodes must be an object")]
    results = []
    known = [node["id"] for node in pack["nodes"]]
    allowed = {"pending", "in_progress", "complete", "failed", "blocked", "skipped"}
    for node_id in known:
        row = nodes.get(node_id)
        if not isinstance(row, dict) or row.get("state") not in allowed:
            results.append(fail("status.shape", f"{node_id} needs a state"))
            continue
        state = row["state"]
        node = find_node(pack, node_id)
        if state == "skipped" and not str(row.get("skip_reason") or "").strip():
            results.append(fail("status.skip", f"{node_id} is skipped without skip_reason"))
        if state in {"in_progress", "complete", "failed"}:
            states = {item["id"]: node_state(document, item["id"]) for item in pack["nodes"]}
            for prior in unsatisfied_priors(node["priors"], states):
                results.append(fail("status.prior", f"{node_id} waits on {prior}"))
        if state == "complete":
            for item in eval_evidence(project, folder, node["complete"]):
                if item.status == "PASS":
                    continue
                item.detail = f"{node_id} {item.detail}".strip()
                results.append(item)
    for extra in sorted(set(nodes) - set(known)):
        results.append(fail("status.shape", f"unknown node {extra}"))
    return results


def _spawn_results(project: Path, folder: Path, pack: dict) -> list:
    path = folder / "spawns.json"
    document = {"spawns": []}
    if path.is_file():
        try:
            document = read_json(path)
        except UnicodeDecodeError:
            return [fail("seal.fingerprint", "spawns.json is not UTF-8")]
        except json.JSONDecodeError as exc:
            return [fail("spawn.record", f"spawns.json is not json: {exc}")]
    rows = document.get("spawns")
    if not isinstance(rows, list):
        return [fail("spawn.record", "spawns.json needs a spawns list")]
    results = []
    by_role: dict[str, dict] = {}
    for node in pack["nodes"]:
        for worker in node["workers"]:
            by_role[worker["id"]] = worker
            if worker["exclusive"]:
                instances = [row for row in rows if row.get("role") == worker["id"]]
                if len(instances) > 1:
                    results.append(
                        fail(
                            "spawn.exclusive",
                            f"{worker['id']} is exclusive and has more than one spawn",
                        )
                    )
            if not worker["specialist"]:
                continue
            files = owned_files(project, worker["owns"])
            returned = [row for row in rows if row.get("role") == worker["id"]]
            if files and not returned:
                results.append(
                    fail(
                        "spawn.missing",
                        f"{worker['id']} owns {files[0]} without a returned spawn",
                    )
                )
    for row in rows:
        role = row.get("role")
        worker = by_role.get(role) if isinstance(role, str) else None
        if worker is None:
            results.append(fail("spawn.record", f"{role} is not a worker in the pack"))
            continue
        for source in outside_sources(worker, row.get("sources") or [], tree.leaves(project)):
            results.append(fail("spawn.sources", f"{source} is outside reads or inside forbidden"))
    return results


def feature_id_set(project: Path) -> set[str]:
    path = project / "project" / "features.json"
    if not path.is_file():
        return set()
    document = read_json(path)
    return {item["id"] for item in document.get("features", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}


MAP_PATH = "docs/index.html"
MAP_STYLESHEET = "../harness-kit/docs/site.css"
MAP_SECTIONS = (
    ("harness", "Project harness"),
    ("structure", "Code structure"),
    ("architecture", "Architecture"),
    ("sessions", "Sessions that changed the map"),
)
MAP_MARKERS = (
    ("<!DOCTYPE html>", "<!DOCTYPE html>"),
    (MAP_STYLESHEET, "the kit stylesheet"),
    ('class="skip"', 'class="skip"'),
    ('class="top"', 'class="top"'),
    ('class="lede"', 'class="lede"'),
    ('class="points"', 'class="points"'),
    ('class="toc"', 'class="toc"'),
    ('id="content"', 'id="content"'),
    ('class="reading"', 'class="reading"'),
)


def _human_doc(rel: str) -> bool:
    """A path the docs grade can see. Comments are not paths."""
    norm = rel.replace("\\", "/")
    if norm.startswith(f"{KIT_DIR}/"):
        return False
    if norm == MAP_PATH or norm.rsplit("/", 1)[-1] == "README.md":
        return True
    rest = norm[len("docs/") :] if norm.startswith("docs/") else ""
    return bool(rest) and "/" not in rest and rest.endswith(".md")


def _owed_docs(project: Path, record: dict) -> list[str]:
    writes = []
    for item in record.get("writes") or []:
        if not isinstance(item, str) or bad_path(project, item):
            continue
        norm = item.replace("\\", "/")
        if norm not in writes:
            writes.append(norm)
    owed: list[str] = []
    if record.get("architecture_changed") or MAP_PATH in writes:
        owed.append(MAP_PATH)
    for rel in writes:
        if _human_doc(rel) and rel not in owed:
            owed.append(rel)
    return owed


def _read_compared(path: Path) -> tuple[str | None, str | None]:
    """Text with LF newlines, or None and a short reason."""
    if not path.is_file():
        return None, "is missing"
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, "is not UTF-8"
    return text.replace("\r\n", "\n").replace("\r", "\n"), None


def _tag_inner(text: str, tag: str, class_name: str) -> str | None:
    """Inner HTML of the first tag whose class list contains class_name."""
    match = re.search(
        rf'<{tag}\b[^>]*\bclass="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>',
        text,
    )
    if not match:
        return None
    close = text.lower().find(f"</{tag}>", match.end())
    if close < 0:
        return None
    return text[match.end() : close]


def _section_slice(text: str, section_id: str) -> str | None:
    match = re.search(rf'<section\b[^>]*\bid="{re.escape(section_id)}"', text)
    if not match:
        return None
    close = text.lower().find("</section>", match.end())
    if close < 0:
        return None
    return text[match.start() : close + len("</section>")]


def _visible(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html).strip()


def _li_inners(html: str) -> list[str]:
    found = []
    pos = 0
    while True:
        match = re.search(r"<li\b[^>]*>", html[pos:])
        if not match:
            return found
        start = pos + match.end()
        close = html.lower().find("</li>", start)
        if close < 0:
            return found
        found.append(html[start:close])
        pos = close + len("</li>")


def _prose_result(label: str, shipped: str | None, template: str | None):
    """One reading region must exist, say something, and leave the template."""
    if shipped is None:
        return fail("docs.map", f"{MAP_PATH} is missing {label}.")
    visible = _visible(shipped)
    if not visible:
        return fail("docs.map", f"{MAP_PATH} {label} is empty.")
    if template is not None and visible == _visible(template):
        return fail("docs.map", f"{MAP_PATH} {label} is still the template.")
    return None


def _map_results(shipped: str, session_id: str) -> list:
    """The project page must keep the kit site's shape and must leave the template."""
    template, template_error = _read_compared(KIT_ROOT / "templates" / "docs" / "index.html")
    if template is None:
        return [fail("docs.map", f"{MAP_PATH} template {template_error}")]
    results = []
    for marker, label in MAP_MARKERS:
        if marker not in shipped:
            results.append(fail("docs.map", f"{MAP_PATH} is missing {label}."))
    if session_id and session_id not in shipped:
        results.append(fail("docs.map", f"Name session {session_id} in {MAP_PATH}."))
    lede = _tag_inner(shipped, "p", "lede")
    template_lede = _tag_inner(template, "p", "lede")
    if lede is None:
        results.append(fail("docs.map", f"{MAP_PATH} is missing the lede."))
    elif not _visible(lede):
        results.append(fail("docs.map", f"{MAP_PATH} lede is empty."))
    elif template_lede is not None and lede.strip() == template_lede.strip():
        results.append(fail("docs.map", f"{MAP_PATH} lede is still the template."))
    points = _tag_inner(shipped, "ol", "points")
    template_points = _tag_inner(template, "ol", "points")
    if points is None:
        results.append(fail("docs.map", f"{MAP_PATH} is missing the points."))
    else:
        items = _li_inners(points)
        template_texts = {_visible(item) for item in _li_inners(template_points or "")}
        template_texts.discard("")
        if not items:
            results.append(fail("docs.map", f"{MAP_PATH} points are empty."))
        for index, item in enumerate(items, start=1):
            visible = _visible(item)
            if not visible:
                results.append(fail("docs.map", f"{MAP_PATH} point {index} is empty."))
            elif visible in template_texts:
                results.append(fail("docs.map", f"{MAP_PATH} point {index} is still the template."))
    for section_id, heading in MAP_SECTIONS:
        body = _section_slice(shipped, section_id)
        template_body = _section_slice(template, section_id)
        if body is None:
            results.append(fail("docs.map", f"{MAP_PATH} is missing {heading}."))
            continue
        if f">{heading}<" not in body:
            results.append(fail("docs.map", f"{MAP_PATH} is missing the {heading} heading."))
        reading = _prose_result(
            f"{heading} reading",
            _tag_inner(body, "p", "reading"),
            _tag_inner(template_body, "p", "reading") if template_body else None,
        )
        if reading is not None:
            results.append(reading)
        if section_id == "architecture" and not re.search(r'class="[^"]*\bchart\b', body or ""):
            results.append(fail("docs.map", f"{MAP_PATH} Architecture is missing a chart."))
    return results


def _docs_results(project: Path, folder: Path, record: dict) -> list:
    """A closed session's draft differs from its return.

    The live file is graded once, in live_owner_results. The fingerprint
    does not cover these files.
    """
    if record.get("phase") != "closed" and record.get("status") != "closed":
        return []
    results = []
    for rel in _owed_docs(project, record):
        draft, draft_error = _read_compared(folder / "draft" / rel)
        returned, return_error = _read_compared(folder / "return" / rel)
        if draft is None:
            results.append(fail("docs.reader", f"draft for {rel} {draft_error}"))
        if returned is None:
            results.append(fail("docs.reader", f"return for {rel} {return_error}"))
        if draft is None or returned is None:
            continue
        if draft == returned:
            results.append(fail("docs.reader", f"{rel} is still the draft"))
    return results


def live_owner_results(
    project: Path,
    pin: str,
    pin_matches: bool,
    include: dict | None = None,
    skip_dirty: bool = True,
) -> list:
    """The live human file equals exactly one graded return.

    While a path is dirty and the one open session owes it, skip that
    comparison. closed_at is not an order. Any other match count is one
    docs.reader. docs.map runs once, on that matching return.
    """
    if not pin_matches:
        return []
    owners: dict[str, list[tuple[Path, dict]]] = {}
    open_owed: set[str] = set()
    open_count = 0
    for path in session_paths(project):
        try:
            item = read_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(item, dict):
            continue
        if include is not None and item.get("id") == include.get("id"):
            item = include
        if (path.parent / "abandon.json").is_file():
            continue
        door, _detail = stamp_door(item, project, pin)
        if door != "grade":
            continue
        closing = include is not None and item is include
        if item.get("status") == "open" and not closing:
            open_count += 1
            if open_count == 1:
                open_owed = set(_owed_docs(project, item))
            continue
        if item.get("phase") != "closed" and item.get("status") != "closed":
            continue
        for rel in _owed_docs(project, item):
            owners.setdefault(rel, []).append((path.parent, item))
    skip: set[str] = set()
    if skip_dirty and open_count == 1:
        skip = {rel for rel in _product_paths(project, False) if rel in open_owed}
    results = []
    for rel, rows in owners.items():
        if rel in skip:
            continue
        shipped, _shipped_error = _read_compared(project / rel)
        matches = []
        for folder, item in rows:
            returned, _return_error = _read_compared(folder / "return" / rel)
            if shipped is not None and returned is not None and shipped == returned:
                matches.append(item)
        if len(matches) != 1:
            results.append(fail("docs.reader", f"{rel} is not the reader return"))
            continue
        if rel == MAP_PATH and shipped is not None:
            results.extend(_map_results(shipped, str(matches[0].get("id") or "")))
    return results


def session_grade(project: Path, folder: Path, record: dict, spec: dict, features: set[str]) -> list:
    """Grade rows for this session. PASS is omitted.

    Phase id, checklist, spawns, and the feature link. A checklist row marked
    complete must have its complete evidence. When phase is closed, the closed
    node's complete evidence is required even if that checklist row is still
    pending, and docs.reader or docs.map is appended when a human doc is owed.
    FAIL blocks `close-session`. SKIPPED is reported and does not.
    `check` calls this only when the stamp door says grade. `close-session`
    calls it only after the stamp door says grade, with phase set to closed
    in memory. Abandon does not.
    """
    results = []
    label = record.get("id") or folder.name
    phase = record.get("phase")
    known = {node["id"] for node in spec["nodes"]}
    if phase not in known:
        results.append(fail("phase.unknown", f"{label} phase {phase} is not in the pack"))
    if spec["uses_features"] and record.get("feature_id") not in features:
        results.append(fail("link.feature", f"{label} feature_id is not in project/features.json"))
    if not spec["uses_features"] and record.get("feature_id") is not None:
        results.append(fail("link.feature", f"{label} names a feature and its pack does not"))
    results.extend(_status_results(project, folder, spec))
    results.extend(_spawn_results(project, folder, spec))
    if phase == "closed":
        results.extend(_docs_results(project, folder, record))
        if record.get("pack") == "coding":
            session_id = str(record.get("id") or folder.name)
            design, review, verify, handoff = _coding_texts(project, session_id, False)
            writes = [
                item.replace("\\", "/")
                for item in (record.get("writes") or [])
                if isinstance(item, str)
            ]
            results.extend(
                _coding_record_results(session_id, design, review, verify, handoff, writes)
            )
    if phase == "closed" and "closed" in known:
        document = read_status(folder)
        closed_state = node_state(document, "closed") if document else None
        if closed_state != "complete":
            for item in eval_evidence(project, folder, find_node(spec, "closed")["complete"]):
                if item.status == "PASS":
                    continue
                item.detail = f"closed {item.detail}".strip()
                results.append(item)
    return [item for item in results if item.status != "PASS"]


def collect_results(project: Path, strict_session: str | None = None) -> list:
    """Structural rules always run. Graph rules run only for a session whose stamps match."""
    refuse_dirty_kit()
    crash_on_collisions(KIT_ROOT, project)
    if (project / ".harness").exists():
        return _checked(
            project,
            [
                fail(
                    "pin.legacy",
                    "Remove .harness/. The kit is the harness-kit submodule.",
                )
            ],
        )
    results = []
    recorded = gitlink(project)
    if not recorded:
        return _checked(project, [fail("pin.missing", f"{KIT_DIR} is not a submodule of this project")])
    checkout = submodule_checkout(project)
    if not checkout.is_dir():
        return _checked(
            project,
            [fail("pin.missing", f"{KIT_DIR} submodule directory is missing. Run sync.")],
        )
    if checkout != KIT_ROOT:
        results.append(
            fail(
                "pin.path",
                f"{project} submodule resolves to {checkout}, this script is {KIT_ROOT}",
            )
        )
    head = git_out(KIT_ROOT, "rev-parse", "HEAD")
    pin_matches = False
    if head is None:
        results.append(fail("pin.git", "kit path is not a git checkout"))
    else:
        pin_matches = recorded == head
        if not pin_matches:
            results.append(
                fail(
                    "pin.mismatch",
                    f"submodule record {recorded[:12]} does not match kit HEAD {head[:12]}",
                )
            )

    project_path = project / "project" / "project.json"
    features_path = project / "project" / "features.json"
    links_path = project / "project" / "links.json"
    for required in (project_path, features_path, links_path):
        if not required.is_file():
            results.append(fail("project.missing", f"missing {required.relative_to(project).as_posix()}"))
    if not project_path.is_file():
        return _checked(project, results)
    project_doc = read_json(project_path)
    features_doc = read_json(features_path) if features_path.is_file() else {"features": []}
    results.extend(_as_results("schema.project", validate(project_doc, schema("project.schema.json"), "project")))
    results.extend(_as_results("schema.features", validate(features_doc, schema("features.schema.json"), "features")))
    if any(item.status == "FAIL" and item.check_id.startswith("schema.") for item in results):
        return _checked(project, results)

    feature_ids = {item["id"] for item in features_doc["features"]}
    plans: dict[str, dict] = {}
    for path in plan_paths(project):
        plan = read_json(path)
        label = path.relative_to(project).as_posix()
        results.extend(_as_results("schema.plan", validate(plan, schema("plan.schema.json"), label)))
        if plan.get("project_id") != project_doc["id"]:
            results.append(fail("link.project", f"{label} project_id does not match {project_doc['id']}"))
        for rel in plan.get("paths", []):
            reason = bad_path(project, rel) if isinstance(rel, str) else "blank or padded path"
            if reason:
                results.append(fail("path.plan", f"{label} path {rel}: {reason}"))
            elif _glob_path(rel):
                results.append(fail("path.plan", f"{label} path {rel}: plan paths are prefixes"))
        plans[plan.get("id", label)] = plan

    if strict_session and not (project / "sessions" / strict_session / "session.json").is_file():
        die(f"No session {strict_session}.")

    graded_checks: dict[str, str] = {}
    for path in session_paths(project):
        item = read_json(path)
        folder = path.parent
        label = path.relative_to(project).as_posix()
        commit_missing = not (
            isinstance(item.get("harness_commit"), str)
            and re.fullmatch(r"[0-9a-f]{40,64}", item.get("harness_commit", ""))
        )
        schema_notes = validate(item, schema("session.schema.json"), label)
        if commit_missing:
            schema_notes = [note for note in schema_notes if "harness_commit" not in note]
            results.append(fail("law.commit", f"{label} missing harness_commit"))
        results.extend(_as_results("schema.session", schema_notes))
        if item.get("project_id") != project_doc["id"]:
            results.append(fail("link.project", f"{label} project_id does not match {project_doc['id']}"))
        plan = plans.get(item.get("plan_id"))
        if plan is None:
            results.append(fail("link.plan", f"{label} plan_id {item.get('plan_id')} does not exist"))
        elif plan.get("pack") != item.get("pack"):
            results.append(fail("link.pack", f"{label} pack does not match its plan"))
        for rel in item.get("writes", []):
            reason = bad_path(project, rel)
            if reason:
                results.append(fail("path.write", f"{label} write {rel}: {reason}"))
            elif names_status_file(rel):
                results.append(fail("status.writer", f"{label} write {rel} is the checklist"))
        if not (folder / "session.md").is_file():
            results.append(fail("session.prose", f"{label} is missing session.md"))
        if item.get("immutable"):
            if item.get("status") != "closed" or not item.get("fingerprint"):
                results.append(fail("seal.fields", f"{label} seal fields are incomplete"))
            elif (folder / "session.md").is_file():
                try:
                    sealed = fingerprint(folder, item)
                except ValueError as exc:
                    results.append(fail("seal.fingerprint", f"{label} {exc}"))
                else:
                    if sealed != item["fingerprint"]:
                        results.append(
                            fail("seal.fingerprint", f"{label} fingerprint mismatch; the sealed session changed")
                        )
        elif item.get("fingerprint") is not None or item.get("status") != "open":
            results.append(fail("seal.open", f"{label} is open but carries a seal"))
        abandon_notes, abandoned = _abandon_results(folder)
        results.extend(abandon_notes)
        door, detail = stamp_door(item, project, recorded or "")
        strict = strict_session == item.get("id")
        if door == "history":
            results.append(fail("law.stamp", detail) if strict else warn("law.stamp", detail))
        elif door == "foreign":
            results.append(fail("law.stamp", detail))
        if door != "grade" or not pin_matches or abandoned or not isinstance(item.get("pack"), str):
            continue
        spec = pack_for(project, item["pack"])
        results.extend(session_grade(project, folder, item, spec, feature_ids))
        command = spec.get("checks")
        if isinstance(command, str) and command.strip():
            graded_checks[spec["id"]] = command

    for command in graded_checks.values():
        results.extend(run_project_checks(project, command))

    if pin_matches and head:
        results.extend(live_owner_results(project, head, True, skip_dirty=True))

    if any(item.status == "FAIL" and item.check_id.startswith("schema.") for item in results):
        return _checked(project, results)

    expected = assemble(project, write=False)
    for plan in plans.values():
        repaired = next(row["sessions"] for row in expected["plans"] if row["id"] == plan["id"])
        if plan["sessions"] != repaired:
            results.append(fail("link.stale", f"plan {plan['id']} session list is stale; run link"))
    for feature in features_doc["features"]:
        repaired = next(row["sessions"] for row in expected["features"] if row["id"] == feature["id"])
        if feature["sessions"] != repaired:
            results.append(fail("link.stale", f"feature {feature['id']} session list is stale; run link"))
    if not links_path.is_file() or read_json(links_path) != expected:
        results.append(fail("link.stale", "project/links.json is stale; run link"))
    elif links_path.is_file():
        results.extend(_as_results("schema.links", validate(read_json(links_path), schema("links.schema.json"), "links")))
    return _checked(project, results)


def cmd_clean_tmp(args: argparse.Namespace) -> None:
    """Remove scratch that is not an open session directory. Does not grade."""
    project = find_project(args.project)
    removed = clean_tmp(project)
    if not removed:
        print("tmp clean")
        return
    for rel in removed:
        print(rel)


def cmd_cover(args: argparse.Namespace) -> None:
    """Print coverage rows for the worktree, or for the index with --staged.

    Does not grade the kit checkout and does not write git config.
    """
    project = find_project(args.project)
    results = coverage_results(project, staged=bool(args.staged))
    for item in results:
        if item.status != "PASS":
            print(item.line(), file=sys.stderr)
    if has_fail(results):
        raise SystemExit(1)


def cmd_link(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    require_version(project)
    links = assemble(project, write=True)
    print(
        f"Linked project {links['project_id']}: "
        f"{len(links['plans'])} plans, {len(links['sessions'])} sessions"
    )


def cmd_check(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    results = collect_results(project, strict_session=args.session)
    for item in results:
        if item.status != "PASS":
            print(item.line(), file=sys.stderr)
    if has_fail(results):
        raise SystemExit(1)
    project_id = read_json(project / "project" / "project.json")["id"]
    print(f"check ok {project_id}")


def cmd_verify(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    require_version(project)
    command = read_json(project / "project" / "project.json")["verify"].strip()
    if command:
        result = subprocess.run(command, shell=True, cwd=project)
        if result.returncode != 0:
            die(f"verify command exited {result.returncode}")
    cmd_check(args)


def add_project_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        help="Project root. Default: walk upward for the harness-kit submodule",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness", description="Harness kit commands")
    sub = parser.add_subparsers(dest="cmd", required=True)

    new_project = sub.add_parser(
        "new-project",
        help=(
            "Add the kit as a submodule, scaffold an empty project, and commit that scaffold. "
            "Inside a project, stage the new repository and do not commit the enclosing project."
        ),
    )
    new_project.add_argument("dest")
    new_project.add_argument("--id", help="Project slug. Default: directory name")
    new_project.add_argument("--name", help="Human name. Default: directory name")
    new_project.set_defaults(func=cmd_new_project)

    adopt = sub.add_parser(
        "adopt",
        help=(
            "Attach the kit to a non-empty repo without overwriting. "
            "When that repo is already inside a project, stage it there and do not commit either repository. "
            "A directory inside another repository that is not its own toplevel is refused."
        ),
    )
    adopt.add_argument("dest")
    adopt.add_argument("--id", help="Project slug when project.json is missing")
    adopt.add_argument("--name")
    adopt.set_defaults(func=cmd_adopt)

    sync = sub.add_parser("sync", help="Clone the harness-kit submodule if it is missing")
    add_project_arg(sync)
    sync.set_defaults(func=cmd_sync)

    upgrade = sub.add_parser("upgrade", help="Record this kit checkout as the submodule and refresh the stub")
    add_project_arg(upgrade)
    upgrade.add_argument("--remote", help="Also set kit_remote")
    upgrade.set_defaults(func=cmd_upgrade)

    pin = sub.add_parser("pin", help="Set the submodule URL without moving the version")
    add_project_arg(pin)
    pin.add_argument("--remote", required=True)
    pin.set_defaults(func=cmd_pin)

    new_plan = sub.add_parser("new-plan", help="Create a plan linked to this project")
    add_project_arg(new_plan)
    new_plan.add_argument("--id", required=True)
    new_plan.add_argument("--title", required=True)
    new_plan.add_argument("--pack", required=True, help="Pack id. A project pack lives in project/packs/<id>/")
    new_plan.add_argument("--depth", default="medium", choices=("low", "medium", "high"))
    new_plan.add_argument("--path", action="append", help="Extra project-relative path")
    new_plan.set_defaults(func=cmd_new_plan)

    new_feature = sub.add_parser("new-feature", help="Add a coding feature row")
    add_project_arg(new_feature)
    new_feature.add_argument("--id", required=True)
    new_feature.add_argument("--title", required=True)
    new_feature.set_defaults(func=cmd_new_feature)

    new_session = sub.add_parser("new-session", help="Create a session linked to a plan")
    add_project_arg(new_session)
    new_session.add_argument("--plan", required=True)
    new_session.add_argument("--id")
    new_session.add_argument("--feature")
    new_session.add_argument(
        "--write",
        action="append",
        help="Exact product file this session may write. A directory is refused. The default list is empty",
    )
    new_session.set_defaults(func=cmd_new_session)

    phase = sub.add_parser("phase", help="Enter a node on the pack graph")
    add_project_arg(phase)
    phase.add_argument("--session", required=True)
    phase.add_argument("--to", help="Enter a node on a single-path pack")
    phase.add_argument("--enter", help="Enter a node whose priors are complete or skipped")
    phase.set_defaults(func=cmd_phase)

    status = sub.add_parser("status", help="Write one checklist row in status.json")
    add_project_arg(status)
    status.add_argument("--session", required=True)
    status.add_argument("--node", required=True)
    status.add_argument("--set", required=True, dest="set")
    status.add_argument("--reason", help="Required when --set skipped")
    status.set_defaults(func=cmd_status)

    spawn = sub.add_parser("spawn", help="Record a returned worker")
    add_project_arg(spawn)
    spawn.add_argument("--session", required=True)
    spawn.add_argument("--role", required=True)
    spawn.add_argument("--instance", required=True)
    spawn.add_argument("--source", action="append", help="Project-relative source the worker declared")
    spawn.set_defaults(func=cmd_spawn)

    abandon = sub.add_parser("abandon", help="Seal a session that cannot continue")
    add_project_arg(abandon)
    abandon.add_argument("--session", required=True)
    abandon.add_argument("--reason", required=True)
    abandon.set_defaults(func=cmd_abandon)

    preflight = sub.add_parser("preflight", help="Report whether a node can be entered, without moving")
    add_project_arg(preflight)
    preflight.add_argument("--session", required=True)
    preflight.add_argument("--phase")
    preflight.set_defaults(func=cmd_preflight)

    note = sub.add_parser("note-architecture", help="Set architecture_changed when the pack has architecture_on_close")
    add_project_arg(note)
    note.add_argument("--session", required=True)
    note.set_defaults(func=cmd_note_architecture)

    close_session = sub.add_parser("close-session", help="Seal a session")
    add_project_arg(close_session)
    close_session.add_argument("--session")
    close_session.add_argument(
        "--from-diff",
        action="store_true",
        help="Set writes from the product diff, seal the session, and stage that record",
    )
    close_session.set_defaults(func=cmd_close_session)

    close_plan = sub.add_parser("close-plan", help="Close a plan that has no open sessions")
    add_project_arg(close_plan)
    close_plan.add_argument("--plan", required=True)
    close_plan.set_defaults(func=cmd_close_plan)

    mark_pass = sub.add_parser("mark-pass", help="Verifier marks a feature passed")
    add_project_arg(mark_pass)
    mark_pass.add_argument("--feature", required=True)
    mark_pass.add_argument("--verifier", action="store_true")
    mark_pass.set_defaults(func=cmd_mark_pass)

    clean = sub.add_parser("clean-tmp", help="Remove scratch that is not an open session directory")
    add_project_arg(clean)
    clean.set_defaults(func=cmd_clean_tmp)

    link = sub.add_parser("link", help="Rebuild project/links.json from sessions")
    add_project_arg(link)
    link.set_defaults(func=cmd_link)

    cover = sub.add_parser("cover", help="Fail when product files are not owned by one session")
    add_project_arg(cover)
    cover.add_argument("--staged", action="store_true", help="Read the index instead of the worktree")
    cover.set_defaults(func=cmd_cover)

    check = sub.add_parser("check", help="Exit non-zero on FAIL. WARN does not fail the process")
    add_project_arg(check)
    check.add_argument(
        "--session",
        help="Fail this session when its stamp does not match, and do not grade its graph",
    )
    check.set_defaults(func=cmd_check)

    verify = sub.add_parser("verify", help="Run project.json verify, then check")
    add_project_arg(verify)
    verify.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
