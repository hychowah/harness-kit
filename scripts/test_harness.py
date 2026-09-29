#!/usr/bin/env python3
"""Gate for the kit. Creates temporary projects and removes them."""

from __future__ import annotations

import json
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

    version_path = project / ".harness" / "kit" / "VERSION"
    write(version_path, "0.1.1\n")
    must(script, "upgrade", "--project", str(project))
    pin = json.loads((project / ".harness" / "pin.json").read_text(encoding="utf-8"))
    if pin["kit_version"] != "0.1.1":
        raise SystemExit(f"pin did not move: {pin}")
    stub = agents.read_text(encoding="utf-8")
    if "0.1.1" not in stub or custom not in stub:
        raise SystemExit("upgrade rewrote the project half of AGENTS.md or skipped the version")
    if (project / "project" / "LAW.md").read_bytes() != law:
        raise SystemExit("upgrade changed domain law")
    must(script, "check", "--project", str(project))

    kit_text = (project / ".harness" / "kit" / "KERNEL.md").read_text(encoding="utf-8")
    if "zz-sample-project" in kit_text:
        raise SystemExit("project id leaked into the kit")


def test_kit_has_no_project_records() -> None:
    for name in ("plans", "sessions", "project"):
        if (KIT / name).exists():
            raise SystemExit(f"kit repo contains {name}/")


def main() -> None:
    head = subprocess.run(
        ["git", "-C", str(KIT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if head.returncode != 0:
        raise SystemExit("harness-kit has no commit, so new-project cannot clone it")
    test_kit_has_no_project_records()
    with tempfile.TemporaryDirectory(prefix="harness-kit-") as tmp:
        root = Path(tmp)
        test_document_and_coding(root)
        test_upgrade_and_sync(root)
    print("test_harness ok")


if __name__ == "__main__":
    main()
