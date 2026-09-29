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
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- harness-kit:begin -->"
END = "<!-- harness-kit:end -->"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PACKS = ("document", "coding")
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
    path.write_text(text, encoding="utf-8", newline="\n")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def version() -> str:
    return (KIT_ROOT / "VERSION").read_text(encoding="utf-8").strip()


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


def _is_type(value: object, name: str) -> bool:
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, dict)
    if name == "null":
        return value is None
    return False


def validate(instance: object, spec: dict, label: str) -> list[str]:
    errors: list[str] = []
    declared = spec.get("type")
    if declared == "object" or "properties" in spec:
        if not isinstance(instance, dict):
            return [f"{label} is not an object"]
        props = spec.get("properties", {})
        if spec.get("additionalProperties") is False:
            for key in sorted(set(instance) - set(props)):
                errors.append(f"{label} has unknown field {key}")
        for key in spec.get("required", []):
            if key not in instance:
                errors.append(f"{label} missing {key}")
        for key, prop in props.items():
            if key in instance:
                errors.extend(validate(instance[key], prop, f"{label}.{key}"))
        return errors
    if isinstance(declared, list):
        if not any(_is_type(instance, item) for item in declared):
            return [f"{label} has the wrong type"]
    elif declared and not _is_type(instance, declared):
        return [f"{label} has the wrong type"]
    if "enum" in spec and instance not in spec["enum"]:
        errors.append(f"{label} must be one of {spec['enum']}")
    if "pattern" in spec and isinstance(instance, str) and not re.search(spec["pattern"], instance):
        errors.append(f"{label} does not match {spec['pattern']}")
    if "minLength" in spec and isinstance(instance, str) and len(instance) < spec["minLength"]:
        errors.append(f"{label} is empty")
    if declared == "array" and isinstance(instance, list) and isinstance(spec.get("items"), dict):
        for index, item in enumerate(instance):
            errors.extend(validate(item, spec["items"], f"{label}[{index}]"))
    return errors


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
    if pin.get("kit_version") != version():
        die(
            f"Pin version {pin.get('kit_version')} does not match kit VERSION {version()}. "
            "Run upgrade on the checkout you want to use."
        )
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


def pack_spec(pack_id: str) -> dict:
    path = KIT_ROOT / "packs" / pack_id / "pack.json"
    if not path.is_file():
        die(f"Unknown pack {pack_id}.")
    return read_json(path)


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
    digest = hashlib.sha256()
    digest.update(canonical_session(data))
    digest.update(b"\0")
    digest.update((folder / "session.md").read_bytes())
    return digest.hexdigest()


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
                "harness_version": item["harness_version"],
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


def stub_block(kit_version: str) -> str:
    raw = (KIT_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8")
    raw = raw.replace("__KIT_VERSION__", kit_version)
    start = raw.index(BEGIN)
    end = raw.index(END) + len(END)
    return raw[start:end]


def refresh_stub(project: Path, kit_version: str) -> None:
    path = project / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        die("AGENTS.md has no harness-kit markers. Upgrade will not rewrite a hand-edited router.")
    prefix, rest = text.split(BEGIN, 1)
    _, suffix = rest.split(END, 1)
    write_text(path, prefix + stub_block(kit_version) + suffix)


def scaffold(project: Path, kit: Path, project_id: str, name: str, kit_version: str) -> None:
    templates = kit / "templates"
    agents = (templates / "AGENTS.md").read_text(encoding="utf-8").replace("__KIT_VERSION__", kit_version)
    write_text(project / "AGENTS.md", agents)
    write_text(project / ".gitignore", (templates / "gitignore").read_text(encoding="utf-8"))
    for relative in STATIC_TEMPLATES:
        write_text(project / relative, (templates / relative).read_text(encoding="utf-8"))
    write_json(
        project / "project" / "project.json",
        {
            "id": project_id,
            "name": name,
            "created": today(),
            "verify": "",
            "kit_version_at_init": kit_version,
        },
    )
    write_json(project / "project" / "features.json", {"features": []})
    assemble(project, write=True)


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
    kit_version = (kit_dest / "VERSION").read_text(encoding="utf-8").strip()
    write_json(
        dest / ".harness" / "pin.json",
        {
            "kit_path": ".harness/kit",
            "kit_version": kit_version,
            "kit_remote": str(KIT_ROOT),
            "kit_commit": commit,
        },
    )
    scaffold(dest, kit_dest, project_id, name, kit_version)
    print(f"Created {dest} id={project_id} kit={kit_version} commit={commit[:12]}")


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
    pin["kit_version"] = version()
    pin["kit_commit"] = head_commit(KIT_ROOT)
    if args.remote:
        pin["kit_remote"] = args.remote
    errors = validate(pin, schema("pin.schema.json"), "pin")
    if errors:
        die("\n".join(errors))
    write_json(project / ".harness" / "pin.json", pin)
    refresh_stub(project, pin["kit_version"])
    print(f"Pin is {pin['kit_version']} {pin['kit_commit'][:12]}")


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
    if args.pack not in PACKS:
        die("Pack must be document or coding.")
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
    pack = plan["pack"]
    feature_id = None
    if pack == "coding":
        if not args.feature:
            die("A coding session needs --feature.")
        features = read_json(project / "project" / "features.json")
        if args.feature not in {item["id"] for item in features["features"]}:
            die(f"Unknown feature {args.feature}.")
        feature_id = args.feature
    elif args.feature:
        die("A document session does not take --feature.")
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
    phase = pack_spec(pack)["phases"][0]
    record = {
        "id": session_id,
        "project_id": project_doc["id"],
        "plan_id": plan["id"],
        "pack": pack,
        "status": "open",
        "phase": phase,
        "depth": plan["depth"],
        "created": today(),
        "harness_version": version(),
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
        f"- Pack: `{pack}`\n"
        f"- Kit: `{version()}`\n\n"
        "## Outcome\n\n"
        "## Gaps\n",
    )
    assemble(project, write=True)
    print(f"Session {session_id}")


def missing_preflight(folder: Path, pack: dict, phase: str) -> list[str]:
    return [name for name in pack["preflight"].get(phase, []) if not (folder / name).exists()]


def cmd_phase(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    require_version(project)
    folder, record = load_session(project, args.session)
    if record["immutable"]:
        die("Session is closed.")
    spec = pack_spec(record["pack"])
    if args.to == "closed" or args.to not in spec["phases"]:
        die("Use close-session to close. Open phases: " + ", ".join(spec["phases"][:-1]))
    if spec["phases"].index(args.to) < spec["phases"].index(record["phase"]):
        die("Phase does not move backward.")
    missing = missing_preflight(folder, spec, args.to)
    if missing:
        die(f"{args.to} needs " + ", ".join(missing))
    record["phase"] = args.to
    write_json(folder / "session.json", record)
    assemble(project, write=True)
    print(f"{record['id']} phase={args.to}")


def cmd_preflight(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    require_version(project)
    folder, record = load_session(project, args.session)
    spec = pack_spec(record["pack"])
    target = args.phase
    if not target:
        order = spec["phases"]
        target = order[min(order.index(record["phase"]) + 1, len(order) - 1)]
    missing = missing_preflight(folder, spec, target)
    if missing:
        die(f"{target} needs " + ", ".join(missing))
    print(f"{target} ready")


def cmd_note_architecture(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    require_version(project)
    folder, record = load_session(project, args.session)
    if record["immutable"]:
        die("Session is closed.")
    if record["pack"] != "coding":
        die("architecture_changed belongs to a coding session.")
    record["architecture_changed"] = True
    write_json(folder / "session.json", record)
    print(f"{record['id']} architecture_changed=true")


def cmd_close_session(args: argparse.Namespace) -> None:
    project = find_project(args.project)
    require_version(project)
    folder, record = load_session(project, args.session)
    if record["immutable"]:
        die("Session is already closed.")
    if not (folder / "session.md").is_file():
        die("session.md is missing.")
    spec = pack_spec(record["pack"])
    missing = missing_preflight(folder, spec, "closed")
    if missing:
        die("Close needs " + ", ".join(missing))
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


def collect_errors(project: Path) -> list[str]:
    errors: list[str] = []
    pin_path = project / ".harness" / "pin.json"
    if not pin_path.is_file():
        return ["missing .harness/pin.json"]
    try:
        pin = read_json(pin_path)
    except json.JSONDecodeError as exc:
        return [f"pin is not json: {exc}"]
    errors.extend(validate(pin, schema("pin.schema.json"), "pin"))
    if errors:
        return errors
    pinned = (project / pin["kit_path"]).resolve()
    if pinned != KIT_ROOT:
        errors.append(f"pin kit_path resolves to {pinned}, this script is {KIT_ROOT}")
    if pin["kit_version"] != version():
        errors.append(f"pin version {pin['kit_version']} does not match kit VERSION {version()}")
    head = git_out(KIT_ROOT, "rev-parse", "HEAD")
    if head and pin["kit_commit"] != head:
        errors.append(f"pin commit {pin['kit_commit'][:12]} does not match kit HEAD {head[:12]}")

    project_path = project / "project" / "project.json"
    features_path = project / "project" / "features.json"
    links_path = project / "project" / "links.json"
    for required in (project_path, features_path, links_path):
        if not required.is_file():
            errors.append(f"missing {required.relative_to(project).as_posix()}")
    if errors and not project_path.is_file():
        return errors
    project_doc = read_json(project_path)
    features_doc = read_json(features_path) if features_path.is_file() else {"features": []}
    errors.extend(validate(project_doc, schema("project.schema.json"), "project"))
    errors.extend(validate(features_doc, schema("features.schema.json"), "features"))
    if errors:
        return errors

    feature_ids = {item["id"] for item in features_doc["features"]}
    plans: dict[str, dict] = {}
    for path in plan_paths(project):
        plan = read_json(path)
        label = path.relative_to(project).as_posix()
        errors.extend(validate(plan, schema("plan.schema.json"), label))
        if plan.get("project_id") != project_doc["id"]:
            errors.append(f"{label} project_id does not match {project_doc['id']}")
        for rel in plan.get("paths", []):
            reason = bad_path(rel)
            if reason:
                errors.append(f"{label} path {rel}: {reason}")
        plans[plan.get("id", label)] = plan

    sessions: dict[str, dict] = {}
    for path in session_paths(project):
        item = read_json(path)
        folder = path.parent
        label = path.relative_to(project).as_posix()
        errors.extend(validate(item, schema("session.schema.json"), label))
        if item.get("project_id") != project_doc["id"]:
            errors.append(f"{label} project_id does not match {project_doc['id']}")
        plan = plans.get(item.get("plan_id"))
        if plan is None:
            errors.append(f"{label} plan_id {item.get('plan_id')} does not exist")
        elif plan.get("pack") != item.get("pack"):
            errors.append(f"{label} pack does not match its plan")
        if item.get("pack") in PACKS and item.get("phase") not in pack_spec(item["pack"])["phases"]:
            errors.append(f"{label} phase {item.get('phase')} is not in the {item.get('pack')} pack")
        for rel in item.get("writes", []):
            reason = bad_path(rel)
            if reason:
                errors.append(f"{label} write {rel}: {reason}")
        if item.get("pack") == "coding" and item.get("feature_id") not in feature_ids:
            errors.append(f"{label} feature_id is not in project/features.json")
        if item.get("pack") == "document" and item.get("feature_id") is not None:
            errors.append(f"{label} is a document session with a feature_id")
        if not (folder / "session.md").is_file():
            errors.append(f"{label} is missing session.md")
        if item.get("immutable"):
            if item.get("status") != "closed" or not item.get("fingerprint"):
                errors.append(f"{label} seal fields are incomplete")
            elif (folder / "session.md").is_file() and fingerprint(folder, item) != item["fingerprint"]:
                errors.append(f"{label} fingerprint mismatch; the sealed session changed")
        elif item.get("fingerprint") is not None or item.get("status") != "open":
            errors.append(f"{label} is open but carries a seal")
        sessions[item.get("id", label)] = item

    if errors:
        return errors

    expected = assemble(project, write=False)
    for plan in plans.values():
        repaired = next(row["sessions"] for row in expected["plans"] if row["id"] == plan["id"])
        if plan["sessions"] != repaired:
            errors.append(f"plan {plan['id']} session list is stale; run link")
    for feature in features_doc["features"]:
        repaired = next(row["sessions"] for row in expected["features"] if row["id"] == feature["id"])
        if feature["sessions"] != repaired:
            errors.append(f"feature {feature['id']} session list is stale; run link")
    if not links_path.is_file() or read_json(links_path) != expected:
        errors.append("project/links.json is stale; run link")
    else:
        errors.extend(validate(read_json(links_path), schema("links.schema.json"), "links"))
    return errors


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
    errors = collect_errors(project)
    if errors:
        print("\n".join(errors), file=sys.stderr)
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

    new_project = sub.add_parser("new-project", help="Clone the kit and scaffold a project")
    new_project.add_argument("dest")
    new_project.add_argument("--id", help="Project slug. Default: directory name")
    new_project.add_argument("--name", help="Human name. Default: directory name")
    new_project.set_defaults(func=cmd_new_project)

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
    new_plan.add_argument("--pack", required=True, choices=PACKS)
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

    phase = sub.add_parser("phase", help="Move a session forward after preflight")
    add_project_arg(phase)
    phase.add_argument("--session", required=True)
    phase.add_argument("--to", required=True)
    phase.set_defaults(func=cmd_phase)

    preflight = sub.add_parser("preflight", help="Report files the next phase needs")
    add_project_arg(preflight)
    preflight.add_argument("--session", required=True)
    preflight.add_argument("--phase")
    preflight.set_defaults(func=cmd_preflight)

    note = sub.add_parser("note-architecture", help="Mark a coding session as an architecture change")
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

    check = sub.add_parser("check", help="Exit non-zero when the project and pin disagree")
    add_project_arg(check)
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
