#!/usr/bin/env python3
"""Project-independent harness kit.

Run the copy inside a project after new-project. The pin and this script
must be the same checkout.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
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

KIT_ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- harness-kit:begin -->"
END = "<!-- harness-kit:end -->"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STATIC_TEMPLATES = (
    "project/LAW.md",
    "project/ARCHITECTURE.md",
    "project/STATUS.md",
    "project/gaps.md",
    "project/sources/README.md",
    "project/reports/README.md",
    "plans/README.md",
    "sessions/README.md",
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


def schema(name: str) -> dict:
    return read_json(KIT_ROOT / "schemas" / name)


def slug_ok(value: str) -> bool:
    return bool(SLUG_RE.match(value))


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug_ok(slug):
        die(f"Cannot derive an id from {name!r}. Pass --id as a lowercase slug.")
    return slug


def git_out(repo: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def head_commit(repo: Path) -> str:
    commit = git_out(repo, "rev-parse", "HEAD")
    if not commit:
        die(f"{repo} has no git commit. Commit the kit before cloning it into a project.")
    return commit


def find_project(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".harness" / "pin.json").is_file():
            return candidate
    die("No project found. Pass --project, or run from inside a project.")


def load_pin(project: Path) -> dict:
    path = project / ".harness" / "pin.json"
    if not path.is_file():
        die(f"Missing {path}. Create the project with new-project.")
    return read_json(path)


def require_checkout(project: Path) -> dict:
    pin = load_pin(project)
    pinned = (project / pin["kit_path"]).resolve()
    if pinned != KIT_ROOT:
        die(
            f"This script is {KIT_ROOT}, but the pin points at {pinned}. "
            "Run scripts/harness.py from the pinned kit."
        )
    return pin


def require_version(project: Path) -> dict:
    pin = require_checkout(project)
    head = head_commit(KIT_ROOT)
    if pin.get("kit_commit") != head:
        die(
            f"Pin commit {str(pin.get('kit_commit'))[:12]} does not match kit HEAD {head[:12]}. "
            "Commit the kit repo first, checkout that commit here, and run upgrade."
        )
    refuse_dirty_kit()
    return pin


def bad_path(rel: str) -> str | None:
    if not isinstance(rel, str) or not rel or rel.strip() != rel:
        return "blank or padded path"
    norm = rel.replace("\\", "/")
    if norm.startswith("/") or norm.startswith("~"):
        return "absolute path"
    parts = Path(norm).parts
    if ".." in parts:
        return "parent segment"
    if norm == ".harness" or norm.startswith(".harness/") or "/.harness/" in f"/{norm}":
        return "path enters the kit"
    return None


def pack_for(project: Path | None, pack_id: str) -> dict:
    return load_pack(KIT_ROOT, project, pack_id)


def refuse_dirty_kit() -> None:
    """A dirty kit checkout is a crash, not a check result row."""
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


def fingerprint(folder: Path, data: dict) -> str:
    """Seal the session record and each graded session file that is present."""
    digest = hashlib.sha256()
    digest.update(canonical_session(data))
    digest.update(b"\0")
    digest.update((folder / "session.md").read_bytes())
    for name in ("abandon.json", "status.json", "spawns.json"):
        path = folder / name
        if path.is_file():
            digest.update(b"\0")
            digest.update(path.read_bytes())
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
    return read_json(path)


def node_state(document: dict, node_id: str) -> str | None:
    row = document.get("nodes", {}).get(node_id)
    if not isinstance(row, dict):
        return None
    state = row.get("state")
    return state if isinstance(state, str) else None


def names_status_file(rel: str) -> bool:
    norm = rel.replace("\\", "/")
    return norm == "status.json" or norm.endswith("/status.json")


def covered(rel: str, patterns: list[str]) -> bool:
    norm = rel.replace("\\", "/")
    for pattern in patterns:
        cleaned = pattern.replace("\\", "/").rstrip("/")
        if any(char in cleaned for char in "*?["):
            if fnmatch.fnmatch(norm, cleaned):
                return True
        elif norm == cleaned or norm.startswith(cleaned + "/"):
            return True
    return False


def owned_files(project: Path, patterns: list[str]) -> list[str]:
    """Files a worker owns. The same matcher as evidence globs."""
    found: list[str] = []
    for pattern in patterns:
        for path in matching_paths(project, pattern):
            found.append(path.relative_to(project).as_posix())
    return found


def outside_sources(worker: dict, sources: list) -> list[str]:
    """Declared sources that miss this worker's reads or hit its forbidden list."""
    bad: list[str] = []
    for source in sources:
        if not isinstance(source, str) or not covered(source, worker["reads"]) or covered(source, worker["forbidden"]):
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


def stub_block(kit_commit: str) -> str:
    raw = (KIT_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8")
    raw = raw.replace("__KIT_COMMIT__", kit_commit)
    start = raw.index(BEGIN)
    end = raw.index(END) + len(END)
    return raw[start:end]


def refresh_stub(project: Path, kit_commit: str) -> None:
    path = project / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        die("AGENTS.md has no harness-kit markers. Upgrade will not rewrite a hand-edited router.")
    prefix, rest = text.split(BEGIN, 1)
    _, suffix = rest.split(END, 1)
    write_text(path, prefix + stub_block(kit_commit) + suffix)


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
        agents = (templates / "AGENTS.md").read_text(encoding="utf-8").replace("__KIT_COMMIT__", kit_commit)
        write_text(agents_path, agents)
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


def clone_kit(dest: Path) -> str:
    commit = head_commit(KIT_ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cloned = subprocess.run(
        ["git", "clone", "--local", str(KIT_ROOT), str(dest)],
        capture_output=True,
        text=True,
    )
    if cloned.returncode != 0:
        cloned = subprocess.run(
            ["git", "clone", str(KIT_ROOT), str(dest)],
            capture_output=True,
            text=True,
        )
        if cloned.returncode != 0:
            die(cloned.stderr.strip() or "git clone failed")
    detached = subprocess.run(
        ["git", "-C", str(dest), "checkout", "--detach", commit],
        capture_output=True,
        text=True,
    )
    if detached.returncode != 0:
        die(detached.stderr.strip() or "git checkout of kit commit failed")
    return commit


def cmd_new_project(args: argparse.Namespace) -> None:
    refuse_dirty_kit()
    dest = Path(args.dest).expanduser().resolve()
    if dest == KIT_ROOT or KIT_ROOT in dest.parents:
        die("Refusing to create a project inside the kit repo.")
    if dest.exists() and any(dest.iterdir()):
        die(f"{dest} exists and is not empty.")
    dest.mkdir(parents=True, exist_ok=True)
    kit_dest = dest / ".harness" / "kit"
    commit = clone_kit(kit_dest)
    project_id = args.id or slugify(dest.name)
    if not slug_ok(project_id):
        die("Project --id must be a lowercase slug.")
    name = args.name or dest.name
    write_json(
        dest / ".harness" / "pin.json",
        {
            "kit_path": ".harness/kit",
            "kit_remote": str(KIT_ROOT),
            "kit_commit": commit,
        },
    )
    scaffold(dest, kit_dest, project_id, name, commit)
    print(f"Created {dest} id={project_id} kit={commit[:12]}")


def cmd_adopt(args: argparse.Namespace) -> None:
    """Attach the kit to a repo that already has files. Do not treat those files as sessions."""
    refuse_dirty_kit()
    dest = Path(args.dest).expanduser().resolve()
    if dest == KIT_ROOT or KIT_ROOT in dest.parents:
        die("Refusing to adopt the kit repo.")
    if not dest.is_dir() or not any(dest.iterdir()):
        die(f"{dest} is empty. Use new-project for an empty directory.")
    kit_dest = dest / ".harness" / "kit"
    if kit_dest.exists():
        commit = git_out(kit_dest, "rev-parse", "HEAD")
        if not commit:
            die(f"{kit_dest} is not a git checkout.")
    else:
        commit = clone_kit(kit_dest)
    pin_path = dest / ".harness" / "pin.json"
    if not pin_path.exists():
        write_json(
            pin_path,
            {
                "kit_path": ".harness/kit",
                "kit_remote": str(KIT_ROOT),
                "kit_commit": commit,
            },
        )
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
    write_controls(dest, kit_dest, project_id, name, commit, overwrite=False)
    print(f"Adopted {dest} id={project_id} kit={commit[:12]}")


def cmd_sync(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    pin = load_pin(project)
    dest = project / pin["kit_path"]
    if not dest.exists():
        cloned = subprocess.run(
            ["git", "clone", pin["kit_remote"], str(dest)],
            capture_output=True,
            text=True,
        )
        if cloned.returncode != 0:
            die(cloned.stderr.strip() or f"Could not clone {pin['kit_remote']}")
        detached = subprocess.run(
            ["git", "-C", str(dest), "checkout", "--detach", pin["kit_commit"]],
            capture_output=True,
            text=True,
        )
        if detached.returncode != 0:
            die(detached.stderr.strip() or "Could not check out the pinned commit")
        print(f"Restored {dest}")
        return
    head = git_out(dest, "rev-parse", "HEAD")
    if head != pin["kit_commit"]:
        die(f"Kit HEAD {head} does not match pin commit {pin['kit_commit']}.")
    print("Kit already matches the pin.")


def cmd_upgrade(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    pin = require_checkout(project)
    refuse_dirty_kit()
    pin.pop("kit_version", None)
    pin["kit_commit"] = head_commit(KIT_ROOT)
    if args.remote:
        pin["kit_remote"] = args.remote
    errors = validate(pin, schema("pin.schema.json"), "pin")
    if errors:
        die("\n".join(errors))
    write_json(project / ".harness" / "pin.json", pin)
    refresh_stub(project, pin["kit_commit"])
    print(f"Pin is {pin['kit_commit'][:12]}")


def cmd_pin(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    pin = require_version(project)
    if not args.remote:
        die("Pass --remote.")
    pin["kit_remote"] = args.remote
    write_json(project / ".harness" / "pin.json", pin)
    print(f"kit_remote={args.remote}")


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
        reason = bad_path(extra)
        if reason:
            die(f"{extra}: {reason}")
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
        "## Paths\n\n"
        f"- `plans/{args.id}/plan.md`\n\n"
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
    session_id = args.id or f"{today()}-{plan['id']}"
    if not slug_ok(session_id):
        die("Session id must be a lowercase slug.")
    folder = project / "sessions" / session_id
    if folder.exists():
        die(f"Session {session_id} already exists.")
    writes = [f"plans/{plan['id']}/plan.md"]
    for extra in args.write or []:
        reason = bad_path(extra)
        if reason:
            die(f"{extra}: {reason}")
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
    (folder / "handoffs").mkdir()
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
    require_version(project)
    chosen = [name for name in ("to", "enter") if getattr(args, name)]
    if len(chosen) != 1:
        die("Pass one of --to or --enter.")
    folder, record = load_session(project, args.session)
    _refuse_abandoned(folder)
    if record["immutable"]:
        die("Session is closed.")
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
    require_version(project)
    folder, record = load_session(project, args.session)
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
    require_version(project)
    folder, record = load_session(project, args.session)
    if record["immutable"]:
        die("Session is closed.")
    if not pack_for(project, record["pack"])["architecture_on_close"]:
        die("architecture_changed belongs to a pack with architecture_on_close.")
    record["architecture_changed"] = True
    write_json(folder / "session.json", record)
    print(f"{record['id']} architecture_changed=true")


def cmd_close_session(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    require_version(project)
    folder, record = load_session(project, args.session)
    if record["immutable"]:
        die("Session is already closed.")
    _refuse_abandoned(folder)
    if not (folder / "session.md").is_file():
        die("session.md is missing.")
    spec = pack_for(project, record["pack"])
    _refuse_unready(project, folder, spec, record, find_node(spec, "closed"))
    for rel in record["writes"]:
        reason = bad_path(rel)
        if reason:
            die(f"{rel}: {reason}")
    if record["architecture_changed"]:
        architecture = (project / "project" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        if record["id"] not in architecture:
            die(f"Name session {record['id']} in project/ARCHITECTURE.md before close.")
    record["status"] = "closed"
    record["phase"] = "closed"
    record["immutable"] = True
    record["closed_at"] = today()
    record["fingerprint"] = None
    record["fingerprint"] = fingerprint(folder, record)
    errors = validate(record, schema("session.schema.json"), "session")
    if errors:
        die("\n".join(errors))
    write_json(folder / "session.json", record)
    assemble(project, write=True)
    print(f"Closed {record['id']}")


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
    require_version(project)
    folder, record = load_session(project, args.session)
    _refuse_abandoned(folder)
    if record["immutable"]:
        die("Session is closed.")
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
    require_version(project)
    if not slug_ok(args.instance):
        die("Instance must be a lowercase slug.")
    folder, record = load_session(project, args.session)
    _refuse_abandoned(folder)
    if record["immutable"]:
        die("Session is closed.")
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
        reason = bad_path(source)
        if reason:
            die(f"{source}: {reason}")
        sources.append(source)
    bad = outside_sources(worker, sources)
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
    require_version(project)
    if not isinstance(args.reason, str) or len(args.reason.strip()) < 5:
        die("Pass --reason with at least 5 characters.")
    folder, record = load_session(project, args.session)
    if (folder / "abandon.json").is_file() or record.get("immutable"):
        die("Session is already closed.")
    if not (folder / "session.md").is_file():
        die("session.md is missing.")
    write_json(
        folder / "abandon.json",
        {"abandoned": True, "reason": args.reason.strip(), "at": today()},
    )
    record["status"] = "closed"
    record["immutable"] = True
    record["closed_at"] = today()
    record["fingerprint"] = None
    record["fingerprint"] = fingerprint(folder, record)
    errors = validate(record, schema("session.schema.json"), "session")
    if errors:
        die("\n".join(errors))
    write_json(folder / "session.json", record)
    assemble(project, write=True)
    print(f"Abandoned {record['id']}")


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


def _stamp_door(item: dict, project: Path, pin: dict, *, strict: bool) -> tuple[str, str]:
    """missing, warn, fail, or grade.

    missing: no harness_commit. The caller records FAIL law.commit and does not grade.
    warn: stamps differ on a project-wide check.
    fail: stamps differ on check --session.
    grade: both stamps match. Grading still requires a pin that matches HEAD and a session
    that is not abandoned.
    """
    commit = item.get("harness_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        return "missing", ""
    session_stamp = item.get("project_stamp") or ""
    if not isinstance(session_stamp, str):
        session_stamp = ""
    if commit == pin.get("kit_commit") and session_stamp == project_stamp(project):
        return "grade", ""
    detail = f"checkout {commit} to grade this session"
    if session_stamp != project_stamp(project):
        detail += "; project_stamp does not match project/project.json"
    if strict:
        return "fail", detail
    return "warn", detail


def _abandon_results(folder: Path) -> tuple[list, bool]:
    path = folder / "abandon.json"
    if not path.is_file():
        return [], False
    try:
        document = read_json(path)
    except json.JSONDecodeError as exc:
        return [fail("abandon.record", f"abandon.json is not json: {exc}")], False
    reason = document.get("reason")
    if document.get("abandoned") is True and isinstance(reason, str) and reason.strip():
        return [], True
    return [fail("abandon.record", "abandon.json needs abandoned true and a reason")], False


def _status_results(project: Path, folder: Path, pack: dict) -> list:
    # status.json is the checklist. A complete row is legal only when complete evidence passes.
    document = read_status(folder)
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
        for source in outside_sources(worker, row.get("sources") or []):
            results.append(fail("spawn.sources", f"{source} is outside reads or inside forbidden"))
    return results


def collect_results(project: Path, strict_session: str | None = None) -> list:
    """Structural rules always run. Graph rules run only for a session whose stamps match."""
    refuse_dirty_kit()
    crash_on_collisions(KIT_ROOT, project)
    results = []
    pin_path = project / ".harness" / "pin.json"
    if not pin_path.is_file():
        return [fail("pin.missing", "missing .harness/pin.json")]
    try:
        pin = read_json(pin_path)
    except json.JSONDecodeError as exc:
        return [fail("pin.json", f"pin is not json: {exc}")]
    results.extend(_as_results("pin.schema", validate(pin, schema("pin.schema.json"), "pin")))
    if any(item.status == "FAIL" for item in results):
        return results
    pinned = (project / pin["kit_path"]).resolve()
    if pinned != KIT_ROOT:
        results.append(fail("pin.path", f"pin kit_path resolves to {pinned}, this script is {KIT_ROOT}"))
    head = git_out(KIT_ROOT, "rev-parse", "HEAD")
    pin_matches = False
    if head is None:
        results.append(fail("pin.git", "kit path is not a git checkout"))
    else:
        pin_matches = pin["kit_commit"] == head
        if not pin_matches:
            results.append(
                fail(
                    "pin.mismatch",
                    f"pin commit {pin['kit_commit'][:12]} does not match kit HEAD {head[:12]}",
                )
            )

    project_path = project / "project" / "project.json"
    features_path = project / "project" / "features.json"
    links_path = project / "project" / "links.json"
    for required in (project_path, features_path, links_path):
        if not required.is_file():
            results.append(fail("project.missing", f"missing {required.relative_to(project).as_posix()}"))
    if not project_path.is_file():
        return results
    project_doc = read_json(project_path)
    features_doc = read_json(features_path) if features_path.is_file() else {"features": []}
    results.extend(_as_results("schema.project", validate(project_doc, schema("project.schema.json"), "project")))
    results.extend(_as_results("schema.features", validate(features_doc, schema("features.schema.json"), "features")))
    if any(item.status == "FAIL" and item.check_id.startswith("schema.") for item in results):
        return results

    feature_ids = {item["id"] for item in features_doc["features"]}
    plans: dict[str, dict] = {}
    for path in plan_paths(project):
        plan = read_json(path)
        label = path.relative_to(project).as_posix()
        results.extend(_as_results("schema.plan", validate(plan, schema("plan.schema.json"), label)))
        if plan.get("project_id") != project_doc["id"]:
            results.append(fail("link.project", f"{label} project_id does not match {project_doc['id']}"))
        for rel in plan.get("paths", []):
            reason = bad_path(rel)
            if reason:
                results.append(fail("path.plan", f"{label} path {rel}: {reason}"))
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
            reason = bad_path(rel)
            if reason:
                results.append(fail("path.write", f"{label} write {rel}: {reason}"))
            elif names_status_file(rel):
                results.append(fail("status.writer", f"{label} write {rel} is the checklist"))
        if not (folder / "session.md").is_file():
            results.append(fail("session.prose", f"{label} is missing session.md"))
        if item.get("immutable"):
            if item.get("status") != "closed" or not item.get("fingerprint"):
                results.append(fail("seal.fields", f"{label} seal fields are incomplete"))
            elif (folder / "session.md").is_file() and fingerprint(folder, item) != item["fingerprint"]:
                results.append(fail("seal.fingerprint", f"{label} fingerprint mismatch; the sealed session changed"))
        elif item.get("fingerprint") is not None or item.get("status") != "open":
            results.append(fail("seal.open", f"{label} is open but carries a seal"))
        abandon_notes, abandoned = _abandon_results(folder)
        results.extend(abandon_notes)
        door, detail = _stamp_door(item, project, pin, strict=strict_session == item.get("id"))
        if door == "warn":
            results.append(warn("law.stamp", detail))
        elif door == "fail":
            results.append(fail("law.stamp", detail))
        if door != "grade" or not pin_matches or abandoned or not isinstance(item.get("pack"), str):
            continue
        spec = pack_for(project, item["pack"])
        if item.get("phase") not in {node["id"] for node in spec["nodes"]}:
            results.append(fail("phase.unknown", f"{label} phase {item.get('phase')} is not in the pack"))
        if spec["uses_features"] and item.get("feature_id") not in feature_ids:
            results.append(fail("link.feature", f"{label} feature_id is not in project/features.json"))
        if not spec["uses_features"] and item.get("feature_id") is not None:
            results.append(fail("link.feature", f"{label} names a feature and its pack does not"))
        results.extend(_status_results(project, folder, spec))
        results.extend(_spawn_results(project, folder, spec))
        command = spec.get("checks")
        if isinstance(command, str) and command.strip():
            graded_checks[spec["id"]] = command

    for command in graded_checks.values():
        results.extend(run_project_checks(project, command))

    if any(item.status == "FAIL" and item.check_id.startswith("schema.") for item in results):
        return results

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
    return results


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
        help="Project root. Default: walk upward for .harness/pin.json",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness", description="Harness kit commands")
    sub = parser.add_subparsers(dest="cmd", required=True)

    new_project = sub.add_parser("new-project", help="Clone the kit and scaffold an empty project")
    new_project.add_argument("dest")
    new_project.add_argument("--id", help="Project slug. Default: directory name")
    new_project.add_argument("--name", help="Human name. Default: directory name")
    new_project.set_defaults(func=cmd_new_project)

    adopt = sub.add_parser("adopt", help="Attach the kit to a non-empty repo without overwriting")
    adopt.add_argument("dest")
    adopt.add_argument("--id", help="Project slug when project.json is missing")
    adopt.add_argument("--name")
    adopt.set_defaults(func=cmd_adopt)

    sync = sub.add_parser("sync", help="Clone the pinned kit if it is missing")
    add_project_arg(sync)
    sync.set_defaults(func=cmd_sync)

    upgrade = sub.add_parser("upgrade", help="Record this kit checkout in the pin and refresh the stub")
    add_project_arg(upgrade)
    upgrade.add_argument("--remote", help="Also set kit_remote")
    upgrade.set_defaults(func=cmd_upgrade)

    pin = sub.add_parser("pin", help="Set kit_remote without moving the version")
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
    new_session.add_argument("--write", action="append", help="Extra project-relative write path")
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
    close_session.add_argument("--session", required=True)
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

    link = sub.add_parser("link", help="Rebuild project/links.json from sessions")
    add_project_arg(link)
    link.set_defaults(func=cmd_link)

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
