#!/usr/bin/env python3
"""Gate for the kit. Creates temporary projects and removes them."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
SOURCE = KIT / "scripts" / "harness.py"


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
    )


def must(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = run(script, *args)
    if result.returncode != 0:
        raise SystemExit(
            f"command failed: {' '.join(args)}\n{result.stdout}\n{result.stderr}"
        )
    return result


def write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def project_script(project: Path) -> Path:
    return project / ".harness" / "kit" / "scripts" / "harness.py"


def new_project(root: Path, name: str) -> tuple[Path, Path]:
    dest = root / name
    must(SOURCE, "new-project", str(dest), "--id", "zz-sample-project", "--name", "Sample")
    return dest, project_script(dest)


def assert_fails(script: Path, *args: str, contains: str) -> None:
    result = run(script, *args)
    if result.returncode == 0:
        raise SystemExit(f"expected failure: {' '.join(args)}")
    blob = result.stderr + result.stdout
    if contains not in blob:
        raise SystemExit(f"failure missing {contains!r}:\n{blob}")


def test_document_and_coding(root: Path) -> None:
    project, script = new_project(root, "work")
    must(script, "check", "--project", str(project))

    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "notes",
        "--title",
        "Notes",
        "--pack",
        "document",
    )
    must(
        script,
        "new-session",
        "--project",
        str(project),
        "--plan",
        "notes",
        "--id",
        "notes-1",
    )
    links = json.loads((project / "project" / "links.json").read_text(encoding="utf-8"))
    if links["project_id"] != "zz-sample-project":
        raise SystemExit("links.json lost the project id")
    if links["plans"][0]["sessions"] != ["notes-1"]:
        raise SystemExit(f"plan is not linked to the session: {links}")
    if links["sessions"][0]["plan_id"] != "notes":
        raise SystemExit("session is not linked to the plan")

    assert_fails(
        script,
        "new-session",
        "--project",
        str(project),
        "--plan",
        "notes",
        "--id",
        "notes-bad",
        "--write",
        ".harness/kit/KERNEL.md",
        contains="kit",
    )
    assert_fails(
        script,
        "phase",
        "--project",
        str(project),
        "--session",
        "notes-1",
        "--to",
        "gather",
        contains="brief.md",
    )
    session = project / "sessions" / "notes-1"
    write(session / "brief.md", "Question.\n\nDepth: low.\n\nno report\n")
    write(session / "gaps.md", "None.\n")
    must(script, "phase", "--project", str(project), "--session", "notes-1", "--to", "gather")
    must(script, "phase", "--project", str(project), "--session", "notes-1", "--to", "audit")
    write(session / "audit.md", "No unsupported claims.\n")
    must(script, "close-session", "--project", str(project), "--session", "notes-1")
    must(script, "check", "--project", str(project))

    must(
        script,
        "new-feature",
        "--project",
        str(project),
        "--id",
        "gate",
        "--title",
        "Gate",
    )
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "gate-plan",
        "--title",
        "Gate plan",
        "--pack",
        "coding",
    )
    must(
        script,
        "new-session",
        "--project",
        str(project),
        "--plan",
        "gate-plan",
        "--id",
        "gate-1",
        "--feature",
        "gate",
        "--write",
        "project/ARCHITECTURE.md",
    )
    coding = project / "sessions" / "gate-1"
    write(coding / "baseline.md", "verify: empty baseline\n")
    must(script, "phase", "--project", str(project), "--session", "gate-1", "--to", "implement")
    must(script, "phase", "--project", str(project), "--session", "gate-1", "--to", "verify")
    write(coding / "verify.md", "verify: ok\n")
    must(script, "note-architecture", "--project", str(project), "--session", "gate-1")
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        "gate-1",
        contains="ARCHITECTURE.md",
    )
    arch = project / "project" / "ARCHITECTURE.md"
    write(arch, arch.read_text(encoding="utf-8") + "\nSession gate-1 changed the map.\n")
    assert_fails(
        script,
        "mark-pass",
        "--project",
        str(project),
        "--feature",
        "gate",
        "--verifier",
        contains="Close these sessions",
    )
    must(script, "close-session", "--project", str(project), "--session", "gate-1")
    assert_fails(
        script,
        "mark-pass",
        "--project",
        str(project),
        "--feature",
        "gate",
        contains="--verifier",
    )
    must(script, "mark-pass", "--project", str(project), "--feature", "gate", "--verifier")
    must(script, "check", "--project", str(project))
    features = json.loads((project / "project" / "features.json").read_text(encoding="utf-8"))
    if features["features"][0]["passes"] is not True:
        raise SystemExit("feature did not pass")
    if "gate-1" not in features["features"][0]["sessions"]:
        raise SystemExit("feature is not linked to its session")

    original = (session / "session.md").read_text(encoding="utf-8")
    write(session / "session.md", original + "\nEdited.\n")
    assert_fails(script, "check", "--project", str(project), contains="fingerprint")
    write(session / "session.md", original)
    record = json.loads((session / "session.json").read_text(encoding="utf-8"))
    record["writes"] = ["../outside"]
    write(session / "session.json", json.dumps(record))
    assert_fails(script, "check", "--project", str(project), contains="parent")


def git_kit(kit: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-C",
            str(kit),
            "-c",
            "user.email=harness-kit@localhost",
            "-c",
            "user.name=harness-kit",
            *args,
        ],
        capture_output=True,
        text=True,
    )


def test_upgrade_and_sync(root: Path) -> None:
    project, script = new_project(root, "pin")
    law = (project / "project" / "LAW.md").read_bytes()
    custom = "\nProject note that upgrade must keep.\n"
    agents = project / "AGENTS.md"
    write(agents, agents.read_text(encoding="utf-8") + custom)

    shutil.rmtree(project / ".harness" / "kit")
    must(SOURCE, "sync", "--project", str(project))
    script = project_script(project)
    must(script, "check", "--project", str(project))
    if (project / "project" / "LAW.md").read_bytes() != law:
        raise SystemExit("sync changed domain law")

    kit = project / ".harness" / "kit"
    version_path = kit / "VERSION"
    write(version_path, "0.9.0\n")
    assert_fails(script, "upgrade", "--project", str(project), contains="dirty")
    changelog = (kit / "CHANGELOG.md").read_text(encoding="utf-8")
    write(kit / "CHANGELOG.md", "# Changelog\n\n## 0.9.0\n\nTest release.\n\n" + changelog)
    added = git_kit(kit, "add", "VERSION", "CHANGELOG.md")
    if added.returncode != 0:
        raise SystemExit(added.stderr)
    committed = git_kit(kit, "commit", "-m", "Test release 0.9.0")
    if committed.returncode != 0:
        raise SystemExit(committed.stderr)
    must(script, "upgrade", "--project", str(project))
    pin = json.loads((project / ".harness" / "pin.json").read_text(encoding="utf-8"))
    head = git_kit(kit, "rev-parse", "HEAD").stdout.strip()
    if pin["kit_version"] != "0.9.0" or pin["kit_commit"] != head:
        raise SystemExit(f"pin did not follow the kit commit: {pin} head={head}")
    stub = agents.read_text(encoding="utf-8")
    if "0.9.0" not in stub or custom not in stub:
        raise SystemExit("upgrade rewrote the project half of AGENTS.md or skipped the version")
    if (project / "project" / "LAW.md").read_bytes() != law:
        raise SystemExit("upgrade changed domain law")
    must(script, "check", "--project", str(project))
    kernel = kit / "KERNEL.md"
    write(kernel, kernel.read_text(encoding="utf-8") + "\n")
    assert_fails(script, "check", "--project", str(project), contains="uncommitted")
    restored = git_kit(kit, "checkout", "--", "KERNEL.md")
    if restored.returncode != 0:
        raise SystemExit(restored.stderr)
    must(script, "check", "--project", str(project))

    kit_text = (project / ".harness" / "kit" / "KERNEL.md").read_text(encoding="utf-8")
    if "zz-sample-project" in kit_text:
        raise SystemExit("project id leaked into the kit")


LAW_EXACT = {
    "KERNEL.md",
    "router.md",
    "worker-contract.md",
    "VERSIONING.md",
    "AGENTS.md",
    "README.md",
    "scripts/harness.py",
}
LAW_PREFIXES = ("packs/", "protocols/", "schemas/", "exemplars/", "templates/")


def changed_paths() -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(KIT), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr)
    names = set()
    for line in result.stdout.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            names.add(path)
    return names


def commit_paths(rev: str) -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(KIT), "diff-tree", "--no-commit-id", "--name-only", "-r", rev],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr or f"git diff-tree {rev} failed")
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def procedure_paths(names: set[str]) -> list[str]:
    return sorted(path for path in names if path in LAW_EXACT or path.startswith(LAW_PREFIXES))


def require_version_bump(names: set[str], where: str) -> None:
    procedure = procedure_paths(names)
    if not procedure:
        return
    missing = [name for name in ("VERSION", "CHANGELOG.md") if name not in names]
    if missing:
        raise SystemExit(
            f"{where} changes procedure without {', '.join(missing)}: " + ", ".join(procedure)
        )


def test_release_metadata() -> None:
    version = (KIT / "VERSION").read_text(encoding="utf-8").strip()
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise SystemExit(f"VERSION is not semver: {version}")
    if f"## {version}" not in (KIT / "CHANGELOG.md").read_text(encoding="utf-8"):
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    require_version_bump(changed_paths(), "working tree")
    require_version_bump(commit_paths("HEAD"), "HEAD")


def test_kit_has_no_project_records() -> None:
    for name in ("plans", "sessions", "project"):
        if (KIT / name).exists():
            raise SystemExit(f"kit repo contains {name}/")


LOG_REF = re.compile(r"log/\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md")


def test_kit_repo_record() -> None:
    for name in ("REPO.md", "STATUS.md"):
        if not (KIT / name).is_file():
            raise SystemExit(f"kit repo is missing {name}")
    status = (KIT / "STATUS.md").read_text(encoding="utf-8")
    if "## Last closed" not in status or "## Open" not in status:
        raise SystemExit("STATUS.md needs Last closed and Open")
    named = LOG_REF.findall(status)
    if not named:
        raise SystemExit("STATUS.md Last closed does not name a dated log file")
    for rel in named:
        if not (KIT / rel).is_file():
            raise SystemExit(f"STATUS.md names missing {rel}")
    if not list((KIT / "log").glob("*.md")):
        raise SystemExit("log/ has no entries")
    sample = {"STATUS.md", "REPO.md", "log/2026-09-29-repo-record.md"}
    if procedure_paths(sample):
        raise SystemExit("repo record files must not force a version bump")


def main() -> None:
    head = subprocess.run(
        ["git", "-C", str(KIT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if head.returncode != 0:
        raise SystemExit("harness-kit has no commit, so new-project cannot clone it")
    test_kit_has_no_project_records()
    test_kit_repo_record()
    test_release_metadata()
    with tempfile.TemporaryDirectory(prefix="harness-kit-") as tmp:
        root = Path(tmp)
        test_document_and_coding(root)
        test_upgrade_and_sync(root)
    print("test_harness ok")


if __name__ == "__main__":
    main()
