#!/usr/bin/env python3
"""Gate for the kit. Creates temporary projects and removes them."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import pin_move

KIT = Path(__file__).resolve().parents[1]
SOURCE = KIT / "scripts" / "harness.py"


def sid(name: str) -> str:
    """The session id new-session stores for a slug that has no date yet."""
    if re.match(r"^\d{4}-\d{2}-\d{2}-", name):
        return name
    return f"{date.today().isoformat()}-{name}"


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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _human_map(session_id: str) -> str:
    """A filled project page. Each graded region differs from the template."""
    page = (KIT / "templates" / "docs" / "index.html").read_text(encoding="utf-8")
    page = page.replace(
        "Say what this project does and why it exists.",
        "Sample stores notes and checks them.",
        1,
    )
    page = page.replace("<li>Fill this point in.</li>", "<li>Notes sit in the project.</li>", 1)
    page = page.replace("<li>Fill this point in.</li>", "<li>The kit checks the links.</li>", 1)
    page = page.replace("<li>Fill this point in.</li>", "<li>A teammate can open this page.</li>", 1)
    page = page.replace(
        '<p class="reading">Fill this section in.</p>',
        '<p class="reading">This project uses the document pack and the coding pack. Domain law is project/LAW.md.</p>',
        1,
    )
    page = page.replace(
        '<p class="reading">Fill this section in.</p>',
        '<p class="reading">Notes, plans, and sessions sit next to each other.</p>',
        1,
    )
    page = page.replace(
        '<p class="reading">Fill this section in.</p>',
        '<p class="reading">The kit checks links. The project holds the notes.</p>',
        1,
    )
    page = page.replace("Fill this step in.", "The project holds the notes. The kit checks the links.", 1)
    page = page.replace("Fill this step in", "Notes and the kit", 1)
    page = page.replace(
        '<p class="reading">None yet.</p>',
        f'<p class="reading">{session_id} wrote this map.</p>',
        1,
    )
    return page


def project_script(project: Path) -> Path:
    return project / "harness-kit" / "scripts" / "harness.py"


SKILL_URL = "git@github.com:hychowah/agent-skill.git"


def assert_skill_checkout(kit: Path) -> None:
    listed = git_kit(kit, "ls-files", "-s", "--", "agent-skill")
    parts = listed.stdout.split()
    if listed.returncode != 0 or len(parts) < 2 or parts[0] != "160000":
        raise SystemExit(f"{kit} has no agent-skill gitlink: {listed.stdout}")
    modules = (kit / ".gitmodules").read_text(encoding="utf-8")
    if '[submodule "agent-skill"]' not in modules or "\n\tpath = agent-skill\n" not in modules:
        raise SystemExit(f"{kit} .gitmodules does not name agent-skill")
    if f"url = {SKILL_URL}" not in modules:
        raise SystemExit(f"{kit} .gitmodules url is not the skill repository")
    head = git_kit(kit / "agent-skill", "rev-parse", "HEAD")
    if head.returncode != 0 or head.stdout.strip() != parts[1]:
        raise SystemExit(f"agent-skill HEAD {head.stdout.strip() or 'missing'} is not {parts[1]}")


def new_project(root: Path, name: str) -> tuple[Path, Path]:
    dest = root / name
    must(SOURCE, "new-project", str(dest), "--id", "zz-sample-project", "--name", "Sample")
    assert_skill_checkout(dest / "harness-kit")
    return dest, project_script(dest)


def fill_plan(project: Path, plan_id: str) -> None:
    path = project / "plans" / plan_id / "plan.md"
    text = path.read_text(encoding="utf-8")
    needle = "## Question\n\n## Done\n"
    if needle not in text:
        raise SystemExit(f"{plan_id} has no blank Question and Done")
    write(
        path,
        text.replace(needle, "## Question\n\nWhat changes.\n\n## Done\n\nThe change is on disk.\n", 1),
    )


def assert_fails(script: Path, *args: str, contains: str) -> None:
    result = run(script, *args)
    if result.returncode == 0:
        raise SystemExit(f"expected failure: {' '.join(args)}")
    blob = result.stderr + result.stdout
    if contains not in blob:
        raise SystemExit(f"failure missing {contains!r}:\n{blob}")


def test_session_grade(root: Path) -> None:
    """close-session seals only when the shared grade is empty."""
    project, script = new_project(root, "grade")
    pack = {
        "id": "gatepack",
        "uses_features": False,
        "architecture_on_close": False,
        "checks": None,
        "nodes": [
            {
                "id": "draft",
                "priors": [],
                "entry": [],
                "complete": [],
                "workers": [],
            },
            {
                "id": "closed",
                "priors": ["draft"],
                "entry": [],
                "complete": [{"predicate": "exists", "glob": "done.md", "root": "session"}],
                "workers": [],
            },
        ],
    }
    dest = project / "project" / "packs" / "gatepack"
    dest.mkdir(parents=True)
    write(dest / "pack.json", json.dumps(pack))
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "gate",
        "--title",
        "Gate",
        "--pack",
        "gatepack",
        "--path",
        "project/packs/gatepack",
    )
    fill_plan(project, "gate")
    must(script, "new-session", "--project", str(project), "--plan", "gate", "--id", sid("gate-1"))
    session = project / "sessions" / sid("gate-1")
    record_path = session / "session.json"
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        sid("gate-1"),
        contains="done.md",
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("immutable") or record.get("fingerprint") or record.get("phase") == "closed":
        raise SystemExit(f"failed grade must leave the session open: {record}")
    write(session / "done.md", "done\n")
    must(script, "close-session", "--project", str(project), "--session", sid("gate-1"), "--from-diff")
    commit_all(project, "Add the gate pack")
    (session / "done.md").unlink()
    assert_fails(script, "check", "--project", str(project), contains="done.md")
    write(session / "done.md", "done\n")
    must(script, "check", "--project", str(project))
    prose = session / "session.md"
    original = prose.read_bytes()
    prose.write_bytes(original.replace(b"\n", b"\r\n"))
    must(script, "check", "--project", str(project))
    prose.write_bytes(b"\xff")
    assert_fails(script, "check", "--project", str(project), contains="UTF-8")
    prose.write_bytes(original)
    status_file = session / "status.json"
    status_bytes = status_file.read_bytes()
    status_file.write_bytes(b"\xff")
    assert_fails(script, "check", "--project", str(project), contains="UTF-8")
    status_file.write_bytes(status_bytes)
    must(script, "check", "--project", str(project))
    optional = {
        "id": "optional",
        "uses_features": False,
        "architecture_on_close": False,
        "checks": None,
        "nodes": [
            {
                "id": "draft",
                "priors": [],
                "entry": [],
                "complete": [],
                "workers": [],
            },
            {
                "id": "closed",
                "priors": ["draft"],
                "entry": [],
                "complete": [
                    {"predicate": "exists", "glob": "maybe.md", "root": "session", "optional": True}
                ],
                "workers": [],
            },
        ],
    }
    optional_dir = project / "project" / "packs" / "optional"
    optional_dir.mkdir(parents=True)
    write(optional_dir / "pack.json", json.dumps(optional))
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "opt",
        "--title",
        "Optional",
        "--pack",
        "optional",
        "--path",
        "project/packs/optional",
    )
    fill_plan(project, "opt")
    must(script, "new-session", "--project", str(project), "--plan", "opt", "--id", sid("opt-1"))
    must(script, "close-session", "--project", str(project), "--session", sid("opt-1"), "--from-diff")
    commit_all(project, "Add the optional pack")
    skipped = run(script, "check", "--project", str(project))
    skipped_blob = skipped.stderr + skipped.stdout
    if skipped.returncode != 0 or "SKIPPED evidence.exists" not in skipped_blob:
        raise SystemExit(f"optional evidence should skip and still pass:\n{skipped_blob}")


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
        sid("notes-1"),
    )
    links = json.loads((project / "project" / "links.json").read_text(encoding="utf-8"))
    if links["project_id"] != "zz-sample-project":
        raise SystemExit("links.json lost the project id")
    if links["plans"][0]["sessions"] != [sid("notes-1")]:
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
        sid("notes-bad"),
        "--write",
        "harness-kit/KERNEL.md",
        contains="kit",
    )
    assert_fails(
        script,
        "phase",
        "--project",
        str(project),
        "--session",
        sid("notes-1"),
        "--to",
        "gather",
        contains="brief.md",
    )
    session = project / "sessions" / sid("notes-1")
    write(session / "brief.md", "Question.\n\nDepth: low.\n\nno report\n")
    write(session / "gaps.md", "None.\n")
    assert_fails(
        script,
        "preflight",
        "--project",
        str(project),
        "--session",
        sid("notes-1"),
        "--phase",
        "audit",
        contains="waits on",
    )
    must(script, "preflight", "--project", str(project), "--session", sid("notes-1"))
    assert_fails(
        script,
        "phase",
        "--project",
        str(project),
        "--session",
        sid("notes-1"),
        "--to",
        "audit",
        contains="waits on",
    )
    must(script, "phase", "--project", str(project), "--session", sid("notes-1"), "--to", "gather")
    must(script, "phase", "--project", str(project), "--session", sid("notes-1"), "--to", "audit")
    write(session / "audit.md", "No unsupported claims.\n")
    must(script, "close-session", "--project", str(project), "--session", sid("notes-1"))
    must(script, "check", "--project", str(project))
    commit_all(project, "Close the notes session")

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
        "--path",
        "docs/index.html",
        "--path",
        "project/features.json",
    )
    fill_plan(project, "gate-plan")
    must(
        script,
        "new-session",
        "--project",
        str(project),
        "--plan",
        "gate-plan",
        "--id",
        sid("gate-1"),
        "--feature",
        "gate",
        "--write",
        "docs/index.html",
    )
    coding = project / "sessions" / sid("gate-1")
    write(coding / "design.md", "The map names this session.\n")
    write(coding / "review.md", "The map matches the return.\n")
    write(coding / "verify.md", "verify: ok\n")
    write(coding / "handoffs" / "implement.md", "## Coverage\n\nThe map.\n")
    must(script, "note-architecture", "--project", str(project), "--session", sid("gate-1"))
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        sid("gate-1"),
        contains="docs/index.html",
    )
    arch = project / "docs" / "index.html"
    write(arch, arch.read_text(encoding="utf-8") + "\nSession gate-1 changed the map.\n")
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        sid("gate-1"),
        contains="docs.reader",
    )
    body = _human_map(sid("gate-1"))
    draft = body.replace(
        "Sample stores notes and checks them.",
        "DRAFT Sample stores notes and checks them.",
        1,
    )
    write(arch, body)
    write(coding / "draft" / "docs" / "index.html", draft)
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        sid("gate-1"),
        contains="docs.reader",
    )
    write(coding / "return" / "docs" / "index.html", draft)
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        sid("gate-1"),
        contains="is not the reader return",
    )
    write(coding / "draft" / "docs" / "index.html", body)
    write(coding / "return" / "docs" / "index.html", body)
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        sid("gate-1"),
        contains="still the draft",
    )
    write(coding / "draft" / "docs" / "index.html", draft)
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
    must(script, "close-session", "--project", str(project), "--session", sid("gate-1"), "--from-diff")
    commit_all(project, "Close the map session")
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
    saved_return = (coding / "return" / "docs" / "index.html").read_text(encoding="utf-8")
    (coding / "return" / "docs" / "index.html").unlink()
    assert_fails(script, "check", "--project", str(project), contains="docs.reader")
    write(coding / "return" / "docs" / "index.html", saved_return)
    must(script, "check", "--project", str(project))
    features = json.loads((project / "project" / "features.json").read_text(encoding="utf-8"))
    if features["features"][0]["passes"] is not True:
        raise SystemExit("feature did not pass")
    if sid("gate-1") not in features["features"][0]["sessions"]:
        raise SystemExit("feature is not linked to its session")

    original = (session / "session.md").read_text(encoding="utf-8")
    write(session / "session.md", original + "\nEdited.\n")
    assert_fails(script, "check", "--project", str(project), contains="fingerprint")
    write(session / "session.md", original)
    record = json.loads((session / "session.json").read_text(encoding="utf-8"))
    record["writes"] = ["../outside"]
    write(session / "session.json", json.dumps(record))
    assert_fails(script, "check", "--project", str(project), contains="parent")


def commit_all(project: Path, message: str) -> None:
    added = git_kit(project, "add", "-A")
    if added.returncode != 0:
        raise SystemExit(added.stderr)
    committed = git_kit(project, "commit", "-m", message)
    if committed.returncode != 0:
        raise SystemExit(committed.stderr + committed.stdout)


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
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "agents",
        "--title",
        "Agents",
        "--pack",
        "document",
        "--path",
        "AGENTS.md",
    )
    fill_plan(project, "agents")
    must(script, "new-session", "--project", str(project), "--plan", "agents", "--id", sid("agents-1"))
    _prep_document(script, project, sid("agents-1"))
    must(script, "close-session", "--project", str(project), "--from-diff")
    agents_add = git_kit(project, "add", "--", "AGENTS.md")
    if agents_add.returncode != 0:
        raise SystemExit(agents_add.stderr)
    agents_commit = git_kit(project, "commit", "-m", "Keep the project note")
    if agents_commit.returncode != 0:
        raise SystemExit(agents_commit.stderr + agents_commit.stdout)

    shutil.rmtree(project / "harness-kit")
    must(SOURCE, "sync", "--project", str(project))
    assert_skill_checkout(project / "harness-kit")
    script = project_script(project)
    must(script, "check", "--project", str(project))
    if (project / "project" / "LAW.md").read_bytes() != law:
        raise SystemExit("sync changed domain law")

    kit = project / "harness-kit"
    birth = git_kit(kit, "rev-parse", "HEAD").stdout.strip()
    kernel = kit / "KERNEL.md"
    write(kernel, kernel.read_text(encoding="utf-8") + "\nHash is the version.\n")
    assert_fails(script, "upgrade", "--project", str(project), contains="dirty")
    added = git_kit(kit, "add", "KERNEL.md")
    if added.returncode != 0:
        raise SystemExit(added.stderr)
    committed = git_kit(kit, "commit", "-m", "Test commit is the version")
    if committed.returncode != 0:
        raise SystemExit(committed.stderr)
    upgraded = must(script, "upgrade", "--project", str(project))
    recorded = git_kit(project, "ls-files", "-s", "--", "harness-kit").stdout.strip().split()
    head = git_kit(kit, "rev-parse", "HEAD").stdout.strip()
    if len(recorded) < 2 or recorded[0] != "160000" or recorded[1] != head:
        raise SystemExit(f"submodule record did not follow the kit commit: {recorded} head={head}")
    if f"Submodule record is {head}." not in upgraded.stdout:
        raise SystemExit(upgraded.stdout)
    if f"Previous submodule record: {birth}" not in upgraded.stdout:
        raise SystemExit(upgraded.stdout)
    if "No log file changed between those commits." not in upgraded.stdout:
        raise SystemExit(upgraded.stdout)
    stub = agents.read_text(encoding="utf-8")
    if head not in stub or birth not in stub or custom not in stub:
        raise SystemExit("upgrade rewrote the project half of AGENTS.md or skipped the commit")
    if "No log file changed between those commits." not in stub:
        raise SystemExit("upgrade left the move out of the generated block")
    if (project / "project" / "LAW.md").read_bytes() != law:
        raise SystemExit("upgrade changed domain law")
    must(script, "check", "--project", str(project))
    write(kernel, kernel.read_text(encoding="utf-8") + "\n")
    dirty = run(script, "check", "--project", str(project))
    dirty_blob = dirty.stderr + dirty.stdout
    if dirty.returncode == 0 or "pin.dirty" not in dirty_blob or "uncommitted" not in dirty_blob or "FAIL" in dirty_blob:
        raise SystemExit(f"dirty kit should crash, not a check row:\n{dirty_blob}")
    restored = git_kit(kit, "checkout", "--", "KERNEL.md")
    if restored.returncode != 0:
        raise SystemExit(restored.stderr)
    must(script, "check", "--project", str(project))

    kit_text = (project / "harness-kit" / "KERNEL.md").read_text(encoding="utf-8")
    if "zz-sample-project" in kit_text:
        raise SystemExit("project id leaked into the kit")

    legacy = project / ".harness"
    legacy.mkdir()
    write(
        legacy / "pin.json",
        json.dumps({"kit_path": ".harness/kit", "kit_remote": "example", "kit_commit": "a" * 40}),
    )
    assert_fails(script, "upgrade", "--project", str(project), contains="different commit")
    write(
        legacy / "pin.json",
        json.dumps({"kit_path": ".harness/kit", "kit_remote": "example", "kit_commit": head}),
    )
    (legacy / "kit").mkdir()
    assert_fails(script, "check", "--project", str(project), contains="pin.legacy")
    again = must(script, "upgrade", "--project", str(project))
    if f"Previous submodule record: {birth}" not in again.stdout:
        raise SystemExit(again.stdout)
    if "No log file changed between those commits." not in again.stdout:
        raise SystemExit(again.stdout)
    if (legacy / "pin.json").exists():
        raise SystemExit("upgrade left .harness/pin.json")
    assert_fails(script, "check", "--project", str(project), contains="pin.legacy")
    shutil.rmtree(legacy)
    must(script, "check", "--project", str(project))


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


def procedure_paths(names: set[str]) -> list[str]:
    """The one procedure set: law paths, plus the scripts that define grading and the move text."""
    exact = LAW_EXACT | {
        "scripts/checks.py",
        "scripts/pack.py",
        "scripts/pin_move.py",
        "scripts/tree.py",
    }
    return sorted(path for path in names if path in exact or path.startswith(LAW_PREFIXES))


def test_commit_is_the_version() -> None:
    if (KIT / "VERSION").exists():
        raise SystemExit("VERSION file is not the kit reference. The commit hash is.")
    head = subprocess.run(
        ["git", "-C", str(KIT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    commit = head.stdout.strip()
    if head.returncode != 0 or len(commit) < 40:
        raise SystemExit("kit HEAD is not a commit hash")


def test_entrypoint_yields() -> None:
    """The stub stops when project law does not call this turn kit work."""
    stub = (KIT / "templates" / "AGENTS.md").read_text(encoding="utf-8")
    if "Read in order:" in stub:
        raise SystemExit("stub still opens a pack law before project/LAW.md decides")
    for sentence in (
        "Whether this turn is a kit session is decided in `project/LAW.md`.",
        "open only the law it names and stop.",
        "That text is the move into this checkout.",
        "upgrade does not edit project/, plans/, or sessions/.",
        "Implement does not commit.",
        "Commit only when the user asks or the prompt says to commit.",
        "This block governs the repository that contains this file; a submodule is another repository; do not apply this block there.",
        "Scratch for a session goes in `tmp/<session-id>/`. That folder is not the record.",
        "A product commit is refused unless one session is closed in that commit and its `writes` are exactly those product paths.",
        "`check` reports `coverage.gap`.",
    ):
        if sentence not in stub:
            raise SystemExit(f"stub missing yield sentence: {sentence}")
    if "__PIN_MOVE__" not in stub:
        raise SystemExit("stub has no move slot")
    router = (KIT / "router.md").read_text(encoding="utf-8")
    if "classified the turn as kit work" not in router:
        raise SystemExit("router classes apply before project/LAW.md classifies the turn")
    opening = (KIT / "packs" / "document" / "LAW.md").read_text(encoding="utf-8").split("## Brief", 1)[0]
    if "research" in opening.lower():
        raise SystemExit("document pack opening still uses research as its job")
    readme = (KIT / "README.md").read_text(encoding="utf-8")
    if "packs/document/            research" in readme:
        raise SystemExit("README layout line still calls the document pack research")
    if "Whether this turn is kit work" not in readme:
        raise SystemExit("README still gives classify to the kit alone")
    kernel = (KIT / "KERNEL.md").read_text(encoding="utf-8")
    if "classified the turn as kit work" not in kernel:
        raise SystemExit("KERNEL still classifies before project/LAW.md")
    template_law = (KIT / "templates" / "project" / "LAW.md").read_text(encoding="utf-8")
    if "The kit still owns classify" in template_law:
        raise SystemExit("scaffolded project law still says the kit owns classify")
    if "decides whether a turn is kit work" not in template_law:
        raise SystemExit("scaffolded project law does not admit kit work")
    page = (KIT / "docs" / "index.html").read_text(encoding="utf-8")
    if "does not classify this turn as kit work" not in page:
        raise SystemExit("workflow page still classifies before project/LAW.md")
    if "coverage.gap" not in page:
        raise SystemExit("workflow page does not name coverage.gap")


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


def test_workflow_page() -> None:
    page_path = KIT / "docs" / "index.html"
    if not page_path.is_file():
        raise SystemExit("docs/index.html is missing")
    if not (KIT / "docs" / "site.css").is_file():
        raise SystemExit("docs/site.css is missing")
    page = page_path.read_text(encoding="utf-8")
    if "site.css" not in page:
        raise SystemExit("workflow page does not load site.css")
    for word in (
        "retrieve",
        "continue",
        "upgrade",
        "close-session",
        "mark-pass",
        "fingerprint",
        "KERNEL.md",
        "router.md",
    ):
        if word not in page:
            raise SystemExit(f"workflow page missing {word}")
    protocol = (KIT / "protocols" / "docs.md").read_text(encoding="utf-8")
    framing = "You are a teammate who can use this product. You have not read this code."
    if framing not in protocol:
        raise SystemExit("docs protocol is missing the reader framing")
    if "protocols/docs.md" not in page:
        raise SystemExit("workflow page does not link the docs protocol")
    if "project/ARCHITECTURE.md" in page:
        raise SystemExit("workflow page still calls the map project/ARCHITECTURE.md")
    if "../harness-kit/docs/site.css" not in page:
        raise SystemExit("workflow page does not name the project stylesheet")
    if not (KIT / "templates" / "docs" / "index.html").is_file():
        raise SystemExit("project page template is missing")
    for name in ("Project harness", "Code structure", "Architecture", "Sessions that changed the map"):
        if name not in page or name not in protocol:
            raise SystemExit(f"map section {name} is missing from the page or the docs protocol")
    if "../harness-kit/docs/site.css" not in protocol:
        raise SystemExit("docs protocol does not name the project stylesheet")
    if "static HTML page" not in protocol:
        raise SystemExit("docs protocol does not ask for the static page")
    for label, path in (
        ("KERNEL", KIT / "KERNEL.md"),
        ("coding law", KIT / "packs" / "coding" / "LAW.md"),
        ("AGENTS template", KIT / "templates" / "AGENTS.md"),
        ("README", KIT / "README.md"),
    ):
        if "project/ARCHITECTURE.md" in path.read_text(encoding="utf-8"):
            raise SystemExit(f"{label} still names project/ARCHITECTURE.md")
    for banned in ("leverage", "utilize", "robust", "seamless"):
        if banned in page.lower():
            raise SystemExit(f"workflow page uses {banned}")
    try:
        document = page.split('id="document"', 1)[1].split('id="coding"', 1)[0]
        coding = page.split('id="coding"', 1)[1].split('id="workers"', 1)[0]
    except IndexError as exc:
        raise SystemExit("workflow page is missing a document, coding, or workers section") from exc
    for earlier, later in (("brief", "gather"), ("gather", "audit"), ("audit", "closed")):
        if document.find(earlier) < 0 or document.find(later) < 0 or document.find(earlier) > document.find(later):
            raise SystemExit(f"document chart order broken: {earlier} before {later}")
    for earlier, later in (("work", "closed"),):
        if coding.find(earlier) < 0 or coding.find(later) < 0 or coding.find(earlier) > coding.find(later):
            raise SystemExit(f"coding chart order broken: {earlier} before {later}")


def test_stamp_graph_and_adopt(root: Path) -> None:
    project, script = new_project(root, "graph")
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
    must(script, "new-session", "--project", str(project), "--plan", "notes", "--id", sid("notes-1"))
    session = project / "sessions" / sid("notes-1")
    record_path = session / "session.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    original_commit = record["harness_commit"]
    record["harness_commit"] = "a" * 40
    write(record_path, json.dumps(record))
    must(script, "link", "--project", str(project))
    foreign = run(script, "check", "--project", str(project))
    if foreign.returncode == 0 or "FAIL law.stamp" not in foreign.stderr:
        raise SystemExit(f"an open foreign commit should fail:\n{foreign.stderr}")
    if "not in this clone" not in foreign.stderr or "checkout" in foreign.stderr:
        raise SystemExit(f"a missing commit should not order a checkout:\n{foreign.stderr}")
    parent = subprocess.run(
        ["git", "-C", str(project / "harness-kit"), "rev-parse", "HEAD^"],
        capture_output=True,
        text=True,
    )
    ancestor = parent.stdout.strip()
    if parent.returncode != 0 or len(ancestor) < 40:
        raise SystemExit(f"test clone has no parent commit:\n{parent.stderr}")
    record["harness_commit"] = ancestor
    write(record_path, json.dumps(record))
    must(script, "link", "--project", str(project))
    present = run(script, "check", "--project", str(project))
    if (
        present.returncode == 0
        or "FAIL law.stamp" not in present.stderr
        or "checkout" in present.stderr
        or "not in this clone" in present.stderr
    ):
        raise SystemExit(f"an open commit in this clone should fail without a checkout:\n{present.stderr}")
    before = {
        path.relative_to(session).as_posix(): path.read_bytes()
        for path in session.rglob("*")
        if path.is_file()
    }
    for args, needle in (
        (("phase", "--to", "gather"), "does not write or grade"),
        (("status", "--node", "brief", "--set", "complete"), "does not write or grade"),
        (("spawn", "--role", "scout", "--instance", "one"), "does not write or grade"),
        (("preflight", "--phase", "gather"), "does not write or grade"),
        (("note-architecture",), "does not write or grade"),
        (("close-session",), "does not write or grade"),
        (("abandon", "--reason", "wrong pin"), "does not write or grade"),
    ):
        assert_fails(script, *args, "--project", str(project), "--session", sid("notes-1"), contains=needle)
    after = {
        path.relative_to(session).as_posix(): path.read_bytes()
        for path in session.rglob("*")
        if path.is_file()
    }
    if before != after:
        raise SystemExit(f"a foreign pin changed the session: {sorted(set(before) ^ set(after))}")
    record["phase"] = "not-a-node"
    write(record_path, json.dumps(record))
    must(script, "link", "--project", str(project))
    ungraded = run(script, "check", "--project", str(project))
    if ungraded.returncode == 0 or "phase.unknown" in ungraded.stderr or "FAIL law.stamp" not in ungraded.stderr:
        raise SystemExit(f"a foreign stamp must not grade the phase:\n{ungraded.stderr}")
    strict = run(script, "check", "--project", str(project), "--session", sid("notes-1"))
    if strict.returncode == 0 or "FAIL law.stamp" not in strict.stderr or "phase.unknown" in strict.stderr:
        raise SystemExit(f"check --session should fail the foreign commit:\n{strict.stderr}")
    record["phase"] = "brief"
    record["harness_commit"] = original_commit
    write(record_path, json.dumps(record))
    must(script, "link", "--project", str(project))
    prose = session / "session.md"
    original_prose = prose.read_text(encoding="utf-8")
    record["harness_commit"] = original_commit
    write(record_path, json.dumps(record))
    must(script, "link", "--project", str(project))
    write(session / "brief.md", "Question.\n")
    write(session / "gaps.md", "None.\n")
    must(script, "phase", "--project", str(project), "--session", sid("notes-1"), "--to", "gather")
    must(script, "phase", "--project", str(project), "--session", sid("notes-1"), "--to", "audit")
    write(session / "audit.md", "No unsupported claims.\n")
    must(script, "close-session", "--project", str(project), "--session", sid("notes-1"))
    sealed_bytes = record_path.read_bytes()
    sealed = json.loads(sealed_bytes)
    sealed["harness_commit"] = "b" * 40
    sealed["fingerprint"] = None
    write(record_path, json.dumps(sealed))
    recomputed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]);"
            " from harness import fingerprint; folder=Path(sys.argv[2]);"
            " data=json.loads(Path(sys.argv[3]).read_text()); data['fingerprint']=None;"
            " print(fingerprint(folder, data))",
            str(project / "harness-kit" / "scripts"),
            str(session),
            str(record_path),
        ],
        capture_output=True,
        text=True,
    )
    if recomputed.returncode != 0 or len(recomputed.stdout.strip()) < 40:
        raise SystemExit(recomputed.stderr)
    sealed["fingerprint"] = recomputed.stdout.strip()
    write(record_path, json.dumps(sealed))
    must(script, "link", "--project", str(project))
    history = run(script, "check", "--project", str(project))
    if history.returncode != 0 or "WARN law.stamp" not in history.stderr or "checkout" in history.stderr:
        raise SystemExit(f"a sealed foreign commit should warn and pass:\n{history.stderr}\n{history.stdout}")
    if "not in this clone" not in history.stderr:
        raise SystemExit(f"a missing sealed commit should say it is not in this clone:\n{history.stderr}")
    sealed_strict = run(script, "check", "--project", str(project), "--session", sid("notes-1"))
    if (
        sealed_strict.returncode == 0
        or "FAIL law.stamp" not in sealed_strict.stderr
        or "checkout" in sealed_strict.stderr
    ):
        raise SystemExit(f"check --session on a sealed mismatch should fail:\n{sealed_strict.stderr}")
    write(prose, prose.read_text(encoding="utf-8") + "\nChanged after seal.\n")
    both = run(script, "check", "--project", str(project))
    if both.returncode == 0 or "fingerprint" not in both.stderr:
        raise SystemExit(f"fingerprint must fail across a stamp mismatch:\n{both.stderr}")
    write(prose, original_prose)
    write(record_path, sealed_bytes.decode("utf-8"))
    must(script, "link", "--project", str(project))
    must(script, "check", "--project", str(project))
    status_file = session / "status.json"
    status_bytes = status_file.read_bytes()
    write(status_file, status_bytes.decode("utf-8") + "\n")
    edited = run(script, "check", "--project", str(project))
    write(status_file, status_bytes.decode("utf-8"))
    if edited.returncode == 0 or "fingerprint" not in edited.stderr:
        raise SystemExit(f"editing status.json must break the seal:\n{edited.stderr}")
    must(script, "check", "--project", str(project))
    saved_commit = sealed["harness_commit"]
    del sealed["harness_commit"]
    write(record_path, json.dumps(sealed))
    missing = run(script, "check", "--project", str(project))
    sealed["harness_commit"] = saved_commit
    write(record_path, json.dumps(sealed))
    must(script, "link", "--project", str(project))
    if missing.returncode == 0 or "missing harness_commit" not in missing.stderr:
        raise SystemExit(f"missing harness_commit should fail:\n{missing.stderr}")

    ident_path = project / "project" / "project.json"
    ident = json.loads(ident_path.read_text(encoding="utf-8"))
    ident["project_stamp"] = "stamp-1"
    write(ident_path, json.dumps(ident))
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "again",
        "--title",
        "Again",
        "--pack",
        "document",
        "--path",
        "project/project.json",
    )
    fill_plan(project, "again")
    must(script, "new-session", "--project", str(project), "--plan", "again", "--id", sid("again-1"))
    ident["project_stamp"] = "stamp-2"
    write(ident_path, json.dumps(ident))
    moved = run(script, "check", "--project", str(project))
    moved_blob = moved.stderr + moved.stdout
    if moved.returncode == 0 or "FAIL law.stamp" not in moved.stderr or "WARN law.stamp" not in moved.stderr:
        raise SystemExit(f"an open project stamp mismatch should fail, and a sealed one should warn:\n{moved_blob}")
    birth_commit = ident["kit_commit_at_init"]
    ident["project_stamp"] = "stamp-1"
    ident["kit_commit_at_init"] = "c" * 40
    write(ident_path, json.dumps(ident))
    birth = run(script, "check", "--project", str(project))
    if birth.returncode != 0:
        raise SystemExit(f"kit_commit_at_init is not the live pin:\n{birth.stderr}")
    ident["kit_commit_at_init"] = birth_commit
    write(ident_path, json.dumps(ident))
    must(script, "abandon", "--project", str(project), "--session", sid("again-1"), "--reason", "stamp checked")

    survey = {
        "id": "survey",
        "uses_features": False,
        "architecture_on_close": False,
        "checks": None,
        "nodes": [
            {
                "id": "closed",
                "priors": ["join"],
                "entry": [],
                "complete": [],
                "workers": [],
            },
            {
                "id": "join",
                "priors": ["left", "right"],
                "entry": [],
                "complete": [],
                "workers": [],
            },
            {
                "id": "left",
                "priors": [],
                "entry": [],
                "complete": [{"predicate": "exists", "glob": "left.md", "root": "session"}],
                "workers": [],
            },
            {
                "id": "right",
                "priors": ["left"],
                "entry": [],
                "complete": [],
                "workers": [
                    {
                        "id": "scout",
                        "specialist": True,
                        "exclusive": True,
                        "reads": ["project/sources"],
                        "forbidden": ["project/LAW.md"],
                        "owns": ["notes/owned.txt"],
                    }
                ],
            },
        ],
    }
    pack_dir = project / "project" / "packs" / "survey"
    pack_dir.mkdir(parents=True)
    write(pack_dir / "pack.json", json.dumps(survey))
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "survey-plan",
        "--title",
        "Survey",
        "--pack",
        "survey",
        "--path",
        "project/packs/survey",
        "--path",
        "notes",
    )
    fill_plan(project, "survey-plan")
    must(script, "new-session", "--project", str(project), "--plan", "survey-plan", "--id", sid("survey-1"))
    opened = json.loads((project / "sessions" / sid("survey-1") / "session.json").read_text(encoding="utf-8"))
    if opened["phase"] != "left":
        raise SystemExit(f"a fork should start at a root, got {opened['phase']}")
    assert_fails(
        script,
        "preflight",
        "--project",
        str(project),
        "--session",
        sid("survey-1"),
        contains="--phase",
    )
    assert_fails(
        script,
        "spawn",
        "--project",
        str(project),
        "--session",
        sid("survey-1"),
        "--role",
        "scout",
        "--instance",
        "one",
        contains="waits on left",
    )
    assert_fails(
        script,
        "phase",
        "--project",
        str(project),
        "--session",
        sid("survey-1"),
        "--to",
        "join",
        contains="--enter",
    )
    write(project / "sessions" / sid("survey-1") / "left.md", "left\n")
    must(
        script,
        "status",
        "--project",
        str(project),
        "--session",
        sid("survey-1"),
        "--node",
        "left",
        "--set",
        "complete",
    )
    must(
        script,
        "status",
        "--project",
        str(project),
        "--session",
        sid("survey-1"),
        "--node",
        "right",
        "--set",
        "complete",
    )
    must(script, "phase", "--project", str(project), "--session", sid("survey-1"), "--enter", "join")
    (project / "notes").mkdir()
    write(project / "notes" / "owned.txt", "owned\n")
    assert_fails(script, "check", "--project", str(project), contains="spawn.missing")
    assert_fails(
        script,
        "spawn",
        "--project",
        str(project),
        "--session",
        sid("survey-1"),
        "--role",
        "scout",
        "--instance",
        "one",
        "--source",
        "project/LAW.md",
        contains="spawn.sources",
    )
    must(
        script,
        "spawn",
        "--project",
        str(project),
        "--session",
        sid("survey-1"),
        "--role",
        "scout",
        "--instance",
        "one",
        "--source",
        "project/sources/a.md",
    )
    checked = run(script, "check", "--project", str(project))
    if checked.returncode != 0:
        raise SystemExit(f"survey check failed:\n{checked.stderr}")
    if "spawn.missing" in checked.stderr or "spawn.sources" in checked.stderr:
        raise SystemExit(checked.stderr)
    spawn_path = project / "sessions" / sid("survey-1") / "spawns.json"
    original_spawns = spawn_path.read_text(encoding="utf-8")
    spawn_doc = json.loads(original_spawns)
    spawn_doc["spawns"].append(
        {"role": "scout", "instance": "two", "status": "returned", "sources": ["project/sources/a.md"]}
    )
    write(spawn_path, json.dumps(spawn_doc))
    assert_fails(script, "check", "--project", str(project), contains="spawn.exclusive")
    copied = json.loads(original_spawns)
    copied["spawns"][0]["sources"] = ["project/LAW.md"]
    copied["spawns"][0]["reads"] = ["project/LAW.md"]
    copied["spawns"][0]["forbidden"] = []
    write(spawn_path, json.dumps(copied))
    assert_fails(script, "check", "--project", str(project), contains="spawn.sources")
    write(spawn_path, original_spawns)

    must(script, "new-session", "--project", str(project), "--plan", "survey-plan", "--id", sid("survey-stop"))
    must(
        script,
        "abandon",
        "--project",
        str(project),
        "--session",
        sid("survey-stop"),
        "--reason",
        "spawn failed",
    )
    assert_fails(
        script,
        "phase",
        "--project",
        str(project),
        "--session",
        sid("survey-stop"),
        "--enter",
        "left",
        contains="new session",
    )
    if run(script, "check", "--project", str(project)).returncode != 0:
        raise SystemExit("an abandoned session should not fail the project check")
    must(script, "abandon", "--project", str(project), "--session", sid("survey-1"), "--reason", "survey checked")

    cards = {
        "id": "cards",
        "uses_features": False,
        "architecture_on_close": False,
        "checks": None,
        "nodes": [
            {
                "id": "draft",
                "priors": [],
                "entry": [],
                "complete": [
                    {
                        "predicate": "schema",
                        "glob": "card.json",
                        "root": "session",
                        "schema": "project/card.schema.json",
                    },
                    {"predicate": "provenance", "glob": "card.json", "root": "session"},
                    {
                        "predicate": "exists",
                        "glob": "extra.md",
                        "root": "session",
                        "optional": True,
                    },
                ],
                "workers": [],
            },
            {
                "id": "closed",
                "priors": ["draft"],
                "entry": [],
                "complete": [],
                "workers": [],
            },
        ],
    }
    cards_dir = project / "project" / "packs" / "cards"
    cards_dir.mkdir(parents=True)
    write(cards_dir / "pack.json", json.dumps(cards))
    write(
        project / "project" / "card.schema.json",
        json.dumps(
            {
                "type": "object",
                "additionalProperties": True,
                "required": ["name", "rationale", "basis"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "rationale": {"type": "string", "minLength": 1},
                    "basis": {"type": "string", "minLength": 1},
                },
            }
        ),
    )
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "cards-plan",
        "--title",
        "Cards",
        "--pack",
        "cards",
        "--path",
        "project/packs/cards",
        "--path",
        "project/card.schema.json",
    )
    fill_plan(project, "cards-plan")
    must(script, "new-session", "--project", str(project), "--plan", "cards-plan", "--id", sid("cards-1"))
    cards_session = project / "sessions" / sid("cards-1")
    write(cards_session / "card.json", "{")
    write(
        cards_session / "status.json",
        json.dumps({"nodes": {"draft": {"state": "complete"}, "closed": {"state": "pending"}}}),
    )
    bad_card = run(script, "check", "--project", str(project))
    bad_blob = bad_card.stderr + bad_card.stdout
    if bad_card.returncode == 0 or "evidence.schema" not in bad_blob or "evidence.provenance" not in bad_blob:
        raise SystemExit(f"schema and provenance should fail:\n{bad_blob}")
    write(
        cards_session / "card.json",
        json.dumps(
            {
                "name": "one",
                "rationale": "because the source says so",
                "basis": "project/sources/README.md",
            }
        ),
    )
    graded = run(script, "check", "--project", str(project))
    graded_blob = graded.stderr + graded.stdout
    if graded.returncode != 0 or "SKIPPED evidence.exists" not in graded_blob:
        raise SystemExit(f"optional evidence should skip and the gate should pass:\n{graded_blob}")
    cards["checks"] = "printf 'FAIL cards.broke broken\\n'"
    write(cards_dir / "pack.json", json.dumps(cards))
    assert_fails(script, "check", "--project", str(project), contains="cards.broke")
    cards["checks"] = "printf 'WARN cards.note noted\\n'"
    write(cards_dir / "pack.json", json.dumps(cards))
    warned_checks = run(script, "check", "--project", str(project))
    warned_blob = warned_checks.stderr + warned_checks.stdout
    if warned_checks.returncode != 0 or "WARN cards.note" not in warned_blob:
        raise SystemExit(f"a pack warning should not fail the process:\n{warned_blob}")

    saved = git_kit(project, "ls-files", "-s", "--", "harness-kit").stdout.strip().split()
    saved_commit = saved[1]
    survey_record_path = project / "sessions" / sid("survey-1") / "session.json"
    survey_record = json.loads(survey_record_path.read_text(encoding="utf-8"))
    saved_phase = survey_record["phase"]
    survey_record["phase"] = "not-a-node"
    write(survey_record_path, json.dumps(survey_record))
    must(script, "link", "--project", str(project))
    moved = git_kit(
        project,
        "update-index",
        "--cacheinfo",
        f"160000,{'c' * 40},harness-kit",
    )
    if moved.returncode != 0:
        raise SystemExit(moved.stderr)
    mismatched = run(script, "check", "--project", str(project))
    mismatched_blob = mismatched.stderr + mismatched.stdout
    restored_link = git_kit(
        project,
        "update-index",
        "--cacheinfo",
        f"160000,{saved_commit},harness-kit",
    )
    if restored_link.returncode != 0:
        raise SystemExit(restored_link.stderr)
    survey_record["phase"] = saved_phase
    write(survey_record_path, json.dumps(survey_record))
    must(script, "link", "--project", str(project))
    if mismatched.returncode == 0 or "FAIL pin.mismatch" not in mismatched_blob or "phase.unknown" in mismatched_blob:
        raise SystemExit(f"pin mismatch should fail and not grade the phase:\n{mismatched_blob}")
    must(script, "check", "--project", str(project))

    clash = project / "project" / "packs" / "document"
    clash.mkdir()
    write(clash / "pack.json", "{}")
    assert_fails(script, "check", "--project", str(project), contains="exists in the kit")

    adopted = root / "adopted"
    adopted.mkdir()
    write(adopted / "README.md", "keep me\n")
    must(SOURCE, "adopt", str(adopted), "--id", "adopted-sample", "--name", "Adopted")
    link = git_kit(adopted, "ls-files", "-s", "--", "harness-kit").stdout.strip().split()
    if len(link) < 2 or link[0] != "160000":
        raise SystemExit(f"adopt did not record a submodule: {link}")
    if (adopted / ".harness" / "pin.json").exists():
        raise SystemExit("adopt wrote a pin file")
    if (adopted / "README.md").read_text(encoding="utf-8") != "keep me\n":
        raise SystemExit("adopt overwrote an existing file")
    law = adopted / "project" / "LAW.md"
    write(law, "custom law\n")
    must(SOURCE, "adopt", str(adopted))
    if law.read_text(encoding="utf-8") != "custom law\n":
        raise SystemExit("a second adopt overwrote project law")
    adopted_script = project_script(adopted)
    must(
        adopted_script,
        "new-plan",
        "--project",
        str(adopted),
        "--id",
        "keep",
        "--title",
        "Keep",
        "--pack",
        "document",
    )
    plan_path = adopted / "plans" / "keep" / "plan.json"
    features_path = adopted / "project" / "features.json"
    plan_bytes = plan_path.read_bytes()
    feature_bytes = features_path.read_bytes()
    (adopted / "project" / "links.json").unlink()
    must(SOURCE, "adopt", str(adopted))
    if plan_path.read_bytes() != plan_bytes:
        raise SystemExit("adopt rewrote plan.json")
    if features_path.read_bytes() != feature_bytes:
        raise SystemExit("adopt rewrote features.json")
    if not (adopted / "project" / "links.json").is_file():
        raise SystemExit("adopt did not restore links.json")


def _scratch_commit_and_reexec() -> None:
    """new-project clones a commit. Exercise the worktree by committing a scratch copy."""
    if os.environ.get("HARNESS_KIT_TEST_ROOT") == "1":
        return
    porcelain = subprocess.run(
        ["git", "-C", str(KIT), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if porcelain.returncode != 0:
        raise SystemExit(porcelain.stderr)
    if not porcelain.stdout.strip():
        return
    scratch = Path(tempfile.mkdtemp(prefix="harness-kit-src-"))
    cloned = subprocess.run(
        ["git", "clone", "--local", str(KIT), str(scratch)],
        capture_output=True,
        text=True,
    )
    if cloned.returncode != 0:
        cloned = subprocess.run(
            ["git", "clone", str(KIT), str(scratch)],
            capture_output=True,
            text=True,
        )
        if cloned.returncode != 0:
            raise SystemExit(cloned.stderr)
    source_head = subprocess.run(
        ["git", "-C", str(KIT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if source_head.returncode != 0:
        raise SystemExit(source_head.stderr)
    detached_src = subprocess.run(
        [
            "git",
            "-C",
            str(scratch),
            "checkout",
            "--detach",
            source_head.stdout.strip(),
        ],
        capture_output=True,
        text=True,
    )
    if detached_src.returncode != 0:
        raise SystemExit(detached_src.stderr)
    skill_listed = subprocess.run(
        ["git", "-C", str(KIT), "ls-files", "-s", "--", "agent-skill"],
        capture_output=True,
        text=True,
    )
    if skill_listed.returncode != 0:
        raise SystemExit(skill_listed.stderr)
    skill_parts = skill_listed.stdout.split()
    skill_commit = skill_parts[1] if len(skill_parts) >= 2 and skill_parts[0] == "160000" else ""
    for path in KIT.rglob("*"):
        relative = path.relative_to(KIT)
        if ".git" in relative.parts or path.is_dir():
            continue
        if relative.parts[:1] == ("agent-skill",):
            continue
        dest = scratch / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    git = ["git", "-C", str(scratch), "-c", "user.email=harness-kit@localhost", "-c", "user.name=harness-kit"]
    if skill_commit:
        skill_dest = scratch / "agent-skill"
        cloned_skill = subprocess.run(
            ["git", "clone", "--local", str(KIT / "agent-skill"), str(skill_dest)],
            capture_output=True,
            text=True,
        )
        if cloned_skill.returncode != 0:
            cloned_skill = subprocess.run(
                ["git", "clone", "--no-hardlinks", str(KIT / "agent-skill"), str(skill_dest)],
                capture_output=True,
                text=True,
            )
            if cloned_skill.returncode != 0:
                raise SystemExit(cloned_skill.stderr)
        detached_skill = subprocess.run(
            ["git", "-C", str(skill_dest), "checkout", "--detach", skill_commit],
            capture_output=True,
            text=True,
        )
        if detached_skill.returncode != 0:
            raise SystemExit(detached_skill.stderr)
        cached = subprocess.run(
            [*git, "update-index", "--add", "--cacheinfo", f"160000,{skill_commit},agent-skill"],
            capture_output=True,
            text=True,
        )
        if cached.returncode != 0:
            raise SystemExit(cached.stderr)
    added = subprocess.run([*git, "add", "-A"], capture_output=True, text=True)
    if added.returncode != 0:
        raise SystemExit(added.stderr)
    committed = subprocess.run([*git, "commit", "-m", "Test the worktree"], capture_output=True, text=True)
    if committed.returncode != 0:
        raise SystemExit(committed.stderr)
    env = dict(os.environ)
    env["HARNESS_KIT_TEST_ROOT"] = "1"
    raise SystemExit(
        subprocess.run([sys.executable, str(scratch / "scripts" / "test_harness.py")], env=env).returncode
    )


def _repo_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _name_status(commit: str, parents: list[str]) -> list[tuple[str, str]]:
    if parents:
        diff = _repo_git(
            KIT,
            "diff-tree",
            "--no-commit-id",
            "--name-status",
            "-r",
            "--no-renames",
            parents[0],
            commit,
        )
    else:
        diff = _repo_git(
            KIT,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-status",
            "-r",
            "--no-renames",
            commit,
        )
    if diff.returncode != 0:
        raise SystemExit(diff.stderr)
    rows = []
    for line in diff.stdout.splitlines():
        status, _, path = line.partition("\t")
        if path:
            rows.append((status[:1], path))
    return rows


def test_log_move_gate() -> None:
    """A procedure commit adds a new log file, and it has one parent.

    One parent is what lets the move treat that log list as a sequence.
    scripts/pin_move.py is procedure because a change to it changes the text
    a project reads. procedure_paths is that one set.
    """
    listed = _repo_git(KIT, "rev-list", "--reverse", "HEAD")
    if listed.returncode != 0:
        raise SystemExit(listed.stderr)
    started = False
    seen: set[str] = set()
    for commit in listed.stdout.splitlines():
        parents = _repo_git(KIT, "log", "-1", "--format=%P", commit).stdout.split()
        rows = _name_status(commit, parents)
        log_rows = [(status, path) for status, path in rows if path.startswith("log/")]
        if not started:
            if any(status == "A" for status, _path in log_rows):
                started = True
            else:
                continue
        if len(parents) > 1:
            raise SystemExit(f"{commit} has more than one parent")
        for status, path in log_rows:
            if path in seen and status != "A":
                raise SystemExit(f"{commit} changes existing log file {path}")
        for status, path in log_rows:
            if status == "A":
                seen.add(path)
            elif status == "D":
                seen.discard(path)
        changed = {path for _status, path in rows}
        if procedure_paths(changed) and not log_rows:
            raise SystemExit(f"{commit} changes procedure without a log file")
    if not started:
        raise SystemExit("no log file was added")
    for path in sorted((KIT / "log").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if "compatible" in text or "breaking" in text:
            if pin_move.grading_line(text) is None:
                raise SystemExit(f"{path.name} names a grading word without a grading line")


def _tree_bytes(root: Path) -> dict[str, bytes]:
    found = {}
    if not root.is_dir():
        return found
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        found[path.relative_to(root).as_posix()] = path.read_bytes()
    return found


def _commit_kit(kit: Path, message: str) -> str:
    added = git_kit(kit, "add", "-A")
    if added.returncode != 0:
        raise SystemExit(added.stderr)
    committed = git_kit(kit, "commit", "-m", message)
    if committed.returncode != 0:
        raise SystemExit(committed.stderr)
    head = git_kit(kit, "rev-parse", "HEAD")
    if head.returncode != 0:
        raise SystemExit(head.stderr)
    return head.stdout.strip()


def test_pin_moves(root: Path) -> None:
    """upgrade prints the move. It does not edit project work."""
    aligned, aligned_script = new_project(root, "move-none")
    aligned_head = git_kit(aligned / "harness-kit", "rev-parse", "HEAD").stdout.strip()
    none = must(aligned_script, "upgrade", "--project", str(aligned))
    if f"Submodule record is {aligned_head}." not in none.stdout:
        raise SystemExit(none.stdout)
    if "Previous submodule record: none" not in none.stdout or "No log range." not in none.stdout:
        raise SystemExit(none.stdout)

    project, script = new_project(root, "move-break")
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "move",
        "--title",
        "Move",
        "--pack",
        "document",
    )
    must(script, "new-session", "--project", str(project), "--plan", "move", "--id", sid("move-1"))
    law = (project / "project" / "LAW.md").read_bytes()
    plans = _tree_bytes(project / "plans")
    sessions = _tree_bytes(project / "sessions")
    record_path = project / "sessions" / sid("move-1") / "session.json"
    original_commit = json.loads(record_path.read_text(encoding="utf-8"))["harness_commit"]
    kit = project / "harness-kit"
    grading = "`breaking`. check would reject a session an older commit accepted."
    write(kit / "log" / "2099-01-01-break.md", f"# Break\n\n{grading}\n")
    head = _commit_kit(kit, "Add a breaking log file")
    moved = must(script, "upgrade", "--project", str(project))
    stub = (project / "AGENTS.md").read_text(encoding="utf-8")
    for blob in (moved.stdout, stub):
        if f"Submodule record is {head}." not in blob:
            raise SystemExit(blob)
        if f"Previous submodule record: {original_commit}" not in blob:
            raise SystemExit(blob)
        if "harness-kit/log/2099-01-01-break.md" not in blob or grading not in blob:
            raise SystemExit(blob)
    if (project / "project" / "LAW.md").read_bytes() != law:
        raise SystemExit("upgrade changed domain law")
    if _tree_bytes(project / "plans") != plans or _tree_bytes(project / "sessions") != sessions:
        raise SystemExit("upgrade changed plans or sessions")
    if json.loads(record_path.read_text(encoding="utf-8"))["harness_commit"] != original_commit:
        raise SystemExit("upgrade changed harness_commit")

    held = must(script, "upgrade", "--project", str(project))
    if f"Previous submodule record: {original_commit}" not in held.stdout:
        raise SystemExit(held.stdout)
    if "harness-kit/log/2099-01-01-break.md" not in held.stdout:
        raise SystemExit(held.stdout)

    missing, missing_script = new_project(root, "move-missing")
    missing_head = git_kit(missing / "harness-kit", "rev-parse", "HEAD").stdout.strip()
    fake = "b" * 40
    staged = git_kit(
        missing,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{fake},harness-kit",
    )
    if staged.returncode != 0:
        raise SystemExit(staged.stderr)
    absent = must(missing_script, "upgrade", "--project", str(missing))
    if absent.returncode != 0:
        raise SystemExit(absent.stderr)
    if f"Previous submodule record: {fake} (not in this clone)" not in absent.stdout:
        raise SystemExit(absent.stdout)
    if "No log range." not in absent.stdout:
        raise SystemExit(absent.stdout)
    recorded = git_kit(missing, "ls-files", "-s", "--", "harness-kit").stdout.split()
    if len(recorded) < 2 or recorded[1] != missing_head:
        raise SystemExit(f"missing commit was not staged: {recorded}")

    parent, parent_script = new_project(root, "move-parent")
    parent_birth = git_kit(parent / "harness-kit", "rev-parse", "HEAD").stdout.strip()
    birth_subject = git_kit(parent, "log", "-1", "--format=%s")
    if birth_subject.returncode != 0 or birth_subject.stdout.strip() != "Scaffold the project":
        raise SystemExit(birth_subject.stdout or birth_subject.stderr)
    parent_kit = parent / "harness-kit"
    parent_line = "`breaking`. the parent still has the old gitlink."
    write(parent_kit / "log" / "2099-01-02-parent.md", f"# Parent\n\n{parent_line}\n")
    parent_head = _commit_kit(parent_kit, "Add a parent-pin log file")
    first = must(parent_script, "upgrade", "--project", str(parent))
    second = must(parent_script, "upgrade", "--project", str(parent))
    if first.stdout != second.stdout:
        raise SystemExit(f"{first.stdout}\n---\n{second.stdout}")
    if f"Previous submodule record: {parent_birth}" not in first.stdout:
        raise SystemExit(first.stdout)
    if f"Submodule record is {parent_head}." not in first.stdout or parent_line not in first.stdout:
        raise SystemExit(first.stdout)

    stray, stray_script = new_project(root, "move-stray")
    stray_kit = stray / "harness-kit"
    orphan = git_kit(stray_kit, "checkout", "--orphan", "stray")
    if orphan.returncode != 0:
        raise SystemExit(orphan.stderr)
    removed = git_kit(stray_kit, "rm", "-r", "-f", "-q", "log")
    if removed.returncode != 0:
        raise SystemExit(removed.stderr)
    (stray_kit / "log").mkdir()
    write(stray_kit / "log" / "only.md", "`breaking`. unrelated.\n")
    _commit_kit(stray_kit, "Unrelated log")
    unrelated = must(stray_script, "upgrade", "--project", str(stray))
    if unrelated.returncode != 0:
        raise SystemExit(unrelated.stderr)
    if "The log list is not a sequence." not in unrelated.stdout:
        raise SystemExit(unrelated.stdout)
    if "harness-kit/log/only.md" not in unrelated.stdout or "`breaking`. unrelated." not in unrelated.stdout:
        raise SystemExit(unrelated.stdout)
    if "removed" not in unrelated.stdout:
        raise SystemExit(unrelated.stdout)


def _prep_document(script: Path, project: Path, session_id: str) -> None:
    session = project / "sessions" / session_id
    write(session / "brief.md", "Question.\n\nDepth: low.\n\nno report\n")
    write(session / "gaps.md", "None.\n")
    must(script, "phase", "--project", str(project), "--session", session_id, "--to", "gather")
    must(script, "phase", "--project", str(project), "--session", session_id, "--to", "audit")
    write(session / "audit.md", "No unsupported claims.\n")


def test_human_docs(root: Path) -> None:
    """A notes session closes with no reader. A map and a README each need their own return."""
    project, script = new_project(root, "humandocs")
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "plain",
        "--title",
        "Plain",
        "--pack",
        "document",
    )
    must(script, "new-session", "--project", str(project), "--plan", "plain", "--id", sid("plain-1"))
    _prep_document(script, project, sid("plain-1"))
    must(script, "close-session", "--project", str(project), "--session", sid("plain-1"))
    must(script, "check", "--project", str(project))
    commit_all(project, "Close the plain session")

    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "page",
        "--title",
        "Page",
        "--pack",
        "document",
        "--path",
        "docs/index.html",
        "--path",
        "README.md",
    )
    fill_plan(project, "page")
    must(
        script,
        "new-session",
        "--project",
        str(project),
        "--plan",
        "page",
        "--id",
        sid("both-1"),
        "--write",
        "docs/index.html",
        "--write",
        "README.md",
    )
    _prep_document(script, project, sid("both-1"))
    arch = project / "docs" / "index.html"
    stamped = arch.read_text(encoding="utf-8") + "\nboth-1 wrote this.\n"
    write(arch, stamped)
    write(project / "sessions" / sid("both-1") / "draft" / "docs" / "index.html", stamped + "draft\n")
    write(project / "sessions" / sid("both-1") / "return" / "docs" / "index.html", stamped)
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        sid("both-1"),
        contains="docs.map",
    )
    bare = _human_map(sid("both-1")).replace("../harness-kit/docs/site.css", "site.css", 1)
    bare_draft = bare.replace(
        "Sample stores notes and checks them.",
        "DRAFT Sample stores notes and checks them.",
        1,
    )
    write(arch, bare)
    write(project / "sessions" / sid("both-1") / "draft" / "docs" / "index.html", bare_draft)
    write(project / "sessions" / sid("both-1") / "return" / "docs" / "index.html", bare)
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        sid("both-1"),
        contains="kit stylesheet",
    )
    filled = _human_map(sid("both-1"))
    filled_draft = filled.replace(
        "Sample stores notes and checks them.",
        "DRAFT Sample stores notes and checks them.",
        1,
    )
    empty_reading = filled.replace(
        '<p class="reading">This project uses the document pack and the coding pack. Domain law is project/LAW.md.</p>',
        '<p class="reading"></p>',
        1,
    )
    write(arch, empty_reading)
    write(project / "sessions" / sid("both-1") / "draft" / "docs" / "index.html", filled_draft)
    write(project / "sessions" / sid("both-1") / "return" / "docs" / "index.html", empty_reading)
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        sid("both-1"),
        contains="Project harness reading is empty",
    )
    empty_point = filled.replace("<li>Notes sit in the project.</li>", "<li></li>", 1)
    write(arch, empty_point)
    write(project / "sessions" / sid("both-1") / "return" / "docs" / "index.html", empty_point)
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        sid("both-1"),
        contains="point 1 is empty",
    )
    stale_architecture = filled.replace(
        "The kit checks links. The project holds the notes.",
        "Fill this section in.",
        1,
    )
    write(arch, stale_architecture)
    write(project / "sessions" / sid("both-1") / "return" / "docs" / "index.html", stale_architecture)
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        sid("both-1"),
        contains="Architecture reading is still the template",
    )
    body = _human_map(sid("both-1"))
    readme = "# Sample\n\nSample stores notes so a teammate can find them.\n"
    write(arch, body)
    write(project / "README.md", readme)
    write(project / "sessions" / sid("both-1") / "draft" / "docs" / "index.html", "Draft map.\n" + body)
    write(project / "sessions" / sid("both-1") / "return" / "docs" / "index.html", body)
    write(project / "sessions" / sid("both-1") / "draft" / "README.md", readme + "Draft line.\n")
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        sid("both-1"),
        contains="README.md",
    )
    write(project / "sessions" / sid("both-1") / "return" / "README.md", readme + "Draft line.\n")
    assert_fails(
        script,
        "close-session",
        "--project",
        str(project),
        "--session",
        sid("both-1"),
        contains="is not the reader return",
    )
    write(project / "sessions" / sid("both-1") / "return" / "README.md", readme)
    must(script, "close-session", "--project", str(project), "--session", sid("both-1"), "--from-diff")
    commit_all(project, "Close the page session")
    must(script, "check", "--project", str(project))


def test_coverage(root: Path) -> None:
    """One open session owns a dirty tree. The hook reads the index."""
    project, script = new_project(root, "cover")
    subject = git_kit(project, "log", "-1", "--format=%s")
    if subject.stdout.strip() != "Scaffold the project":
        raise SystemExit(subject.stdout or subject.stderr)
    hooks = git_kit(project, "config", "--get", "core.hooksPath")
    if hooks.stdout.strip() != "harness-kit/hooks":
        raise SystemExit(hooks.stdout or hooks.stderr)

    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "idle",
        "--title",
        "Idle",
        "--pack",
        "document",
    )
    must(script, "check", "--project", str(project))
    must(script, "new-session", "--project", str(project), "--plan", "idle", "--id", sid("idle-1"))
    idle_writes = json.loads((project / "sessions" / sid("idle-1") / "session.json").read_text(encoding="utf-8"))["writes"]
    if idle_writes != []:
        raise SystemExit(f"writes should start empty: {idle_writes}")
    must(script, "check", "--project", str(project))
    notes = project / "notes"
    notes.mkdir()
    assert_fails(
        script,
        "new-session",
        "--project",
        str(project),
        "--plan",
        "idle",
        "--id",
        sid("idle-dir"),
        "--write",
        "notes",
        contains="directory",
    )

    write(project / "README.md", "Notes.\n")
    must(script, "check", "--project", str(project))
    must(
        script,
        "new-session",
        "--project",
        str(project),
        "--plan",
        "idle",
        "--id",
        sid("idle-2"),
    )
    assert_fails(script, "check", "--project", str(project), contains="coverage.gap")
    assert_fails(script, "cover", "--project", str(project), contains="coverage.gap")
    must(script, "abandon", "--project", str(project), "--session", sid("idle-2"), "--reason", "duplicate")
    parked = git_kit(project, "add", "--", f"sessions/{sid('idle-2')}", "project/links.json", "plans/idle/plan.json")
    if parked.returncode != 0:
        raise SystemExit(parked.stderr)
    parked_commit = git_kit(project, "commit", "-m", "Abandon the extra session")
    if parked_commit.returncode != 0:
        raise SystemExit(parked_commit.stderr + parked_commit.stdout)
    must(script, "check", "--project", str(project))
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "readme",
        "--title",
        "Readme",
        "--pack",
        "document",
        "--path",
        "README.md",
    )
    fill_plan(project, "readme")
    blank = run(script, "check", "--project", str(project))
    if blank.returncode != 0 or "plan.blank" in (blank.stderr + blank.stdout):
        raise SystemExit(f"a blank plan is not coverage:\n{blank.stderr}")

    write(project / "notes" / "deep" / "a.txt", "a\n")
    must(script, "check", "--project", str(project))

    accent = "caf\u00e9.txt"
    write(project / accent, "cafe\n")
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "accent",
        "--title",
        "Accent",
        "--pack",
        "document",
        "--path",
        accent,
    )
    fill_plan(project, "accent")
    _prep_document(script, project, sid("idle-1"))
    readme = (project / "README.md").read_text(encoding="utf-8")
    write(project / "sessions" / sid("idle-1") / "draft" / "README.md", readme + "Draft.\n")
    write(project / "sessions" / sid("idle-1") / "return" / "README.md", readme)
    must(script, "close-session", "--project", str(project), "--from-diff")
    accent_add = git_kit(project, "add", "-A")
    if accent_add.returncode != 0:
        raise SystemExit(accent_add.stderr)
    accent_commit = git_kit(project, "commit", "-m", "Cover the accented name")
    if accent_commit.returncode != 0:
        raise SystemExit(accent_commit.stderr + accent_commit.stdout)
    must(script, "new-session", "--project", str(project), "--plan", "accent", "--id", sid("accent-2"))
    write(project / accent, "cafe\nmore\n")
    accented = run(script, "check", "--project", str(project))
    accent_blob = accented.stderr + accented.stdout
    if accented.returncode != 0 or "coverage.gap" in accent_blob or "\\303" in accent_blob:
        raise SystemExit(f"a non-ASCII path should stay a real path:\n{accent_blob}")
    write(project / accent, "cafe\n")
    must(script, "abandon", "--project", str(project), "--session", sid("accent-2"), "--reason", "restored")
    restored_add = git_kit(project, "add", "--", f"sessions/{sid('accent-2')}", "project/links.json", "plans/accent/plan.json")
    if restored_add.returncode != 0:
        raise SystemExit(restored_add.stderr)
    restored_commit = git_kit(project, "commit", "-m", "Abandon the accent session")
    if restored_commit.returncode != 0:
        raise SystemExit(restored_commit.stderr + restored_commit.stdout)

    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "left",
        "--title",
        "Left",
        "--pack",
        "document",
        "--path",
        "docs/index.html",
    )
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "right",
        "--title",
        "Right",
        "--pack",
        "document",
        "--path",
        "docs/index.html",
    )
    overlap = run(script, "check", "--project", str(project))
    overlap_blob = overlap.stderr + overlap.stdout
    if overlap.returncode != 0 or "plan.overlap" in overlap_blob:
        raise SystemExit(f"two plans may list one path:\n{overlap_blob}")
    must(script, "close-plan", "--project", str(project), "--plan", "right")
    must(script, "close-plan", "--project", str(project), "--plan", "left")
    must(script, "check", "--project", str(project))

    idle_record = project / "plans" / "idle" / "plan.json"
    idle = json.loads(idle_record.read_text(encoding="utf-8"))
    idle["paths"] = ["plans/idle/plan.md", "src/*.py"]
    write(idle_record, json.dumps(idle))
    assert_fails(script, "check", "--project", str(project), contains="path.plan")
    idle["paths"] = ["plans/idle/plan.md"]
    write(idle_record, json.dumps(idle))
    must(script, "link", "--project", str(project))
    must(script, "check", "--project", str(project))

    agents = project / "AGENTS.md"
    saved_agents = agents.read_text(encoding="utf-8")
    agents.write_text(saved_agents.replace("Do not edit it.", "Do not edit the kit.", 1), encoding="utf-8")
    marked = run(script, "check", "--project", str(project))
    if marked.returncode != 0 or "coverage.gap" in marked.stderr:
        raise SystemExit(f"a marker-only AGENTS edit should pass:\n{marked.stderr}")
    must(script, "new-session", "--project", str(project), "--plan", "idle", "--id", sid("agents-1"))
    agents.write_text(saved_agents + "\nProject note.\n", encoding="utf-8")
    outside = run(script, "check", "--project", str(project))
    if outside.returncode != 0 or "coverage.gap" in (outside.stderr + outside.stdout):
        raise SystemExit(f"one open session owns an AGENTS edit:\n{outside.stderr}")
    agents.write_text(saved_agents, encoding="utf-8")
    must(script, "abandon", "--project", str(project), "--session", sid("agents-1"), "--reason", "restored")
    agents_add = git_kit(project, "add", "--", f"sessions/{sid('agents-1')}", "project/links.json", "plans/idle/plan.json")
    if agents_add.returncode != 0:
        raise SystemExit(agents_add.stderr)
    agents_commit = git_kit(project, "commit", "-m", "Abandon the agents session")
    if agents_commit.returncode != 0:
        raise SystemExit(agents_commit.stderr + agents_commit.stdout)
    must(script, "check", "--project", str(project))

    must(script, "new-feature", "--project", str(project), "--id", "lamp", "--title", "Lamp")
    assert_fails(script, "check", "--project", str(project), contains="project/features.json")
    must(script, "new-session", "--project", str(project), "--plan", "idle", "--id", sid("feat-1"))
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "feat",
        "--title",
        "Feat",
        "--pack",
        "document",
        "--path",
        "project/features.json",
    )
    fill_plan(project, "feat")
    must(script, "check", "--project", str(project))
    _prep_document(script, project, sid("feat-1"))
    must(script, "close-session", "--project", str(project), "--from-diff")
    added = git_kit(project, "add", "--", "project/features.json")
    if added.returncode != 0:
        raise SystemExit(added.stderr)
    committed = git_kit(project, "commit", "-m", "Cover the feature row")
    if committed.returncode != 0:
        raise SystemExit(committed.stderr + committed.stdout)
    must(script, "close-plan", "--project", str(project), "--plan", "feat")
    must(script, "close-plan", "--project", str(project), "--plan", "readme")
    features_path = project / "project" / "features.json"
    features = json.loads(features_path.read_text(encoding="utf-8"))
    features["features"][0]["sessions"] = ["not-a-session"]
    write(features_path, json.dumps(features, indent=2) + "\n")
    sessions_only = run(script, "check", "--project", str(project))
    sessions_blob = sessions_only.stderr + sessions_only.stdout
    if "coverage.gap" in sessions_blob or "link.stale" not in sessions_blob:
        raise SystemExit(f"a sessions-only features edit should not be a product gap:\n{sessions_blob}")
    features["features"][0]["sessions"] = []
    features["features"][0]["title"] = "Lantern"
    write(features_path, json.dumps(features, indent=2) + "\n")
    assert_fails(script, "check", "--project", str(project), contains="project/features.json")
    features["features"][0]["title"] = "Lamp"
    write(features_path, json.dumps(features, indent=2) + "\n")
    must(script, "check", "--project", str(project))

    write(project / "extra.txt", "extra\n")
    staged = git_kit(project, "add", "--", "extra.txt")
    if staged.returncode != 0:
        raise SystemExit(staged.stderr)
    refused = git_kit(project, "commit", "-m", "Uncovered extra")
    if refused.returncode == 0 or "coverage.gap" not in refused.stderr:
        raise SystemExit(f"the hook should refuse an uncovered file:\n{refused.stderr}")
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "extra",
        "--title",
        "Extra",
        "--pack",
        "document",
        "--path",
        "extra.txt",
    )
    fill_plan(project, "extra")
    still = git_kit(project, "commit", "-m", "Plan is not a session")
    if still.returncode == 0 or "coverage.gap" not in still.stderr:
        raise SystemExit(f"an open plan should not cover a staged file:\n{still.stderr}")
    must(script, "new-session", "--project", str(project), "--plan", "extra", "--id", sid("extra-1"))
    _prep_document(script, project, sid("extra-1"))
    must(script, "close-session", "--project", str(project), "--from-diff")
    allowed = git_kit(project, "commit", "-m", "Cover extra")
    if allowed.returncode != 0:
        raise SystemExit(allowed.stderr + allowed.stdout)
    write(project / "extra.txt", "extra\nmore\n")
    closing = json.loads((project / "plans" / "extra" / "plan.json").read_text(encoding="utf-8"))
    closing["status"] = "closed"
    write(project / "plans" / "extra" / "plan.json", json.dumps(closing, indent=2) + "\n")
    staged_close = git_kit(project, "add", "--", "extra.txt", "plans/extra/plan.json")
    if staged_close.returncode != 0:
        raise SystemExit(staged_close.stderr)
    refused_close = git_kit(project, "commit", "-m", "Close with the change")
    if refused_close.returncode == 0 or "coverage.gap" not in refused_close.stderr:
        raise SystemExit(f"closing the plan in the product commit should fail:\n{refused_close.stderr}")
    dropped = git_kit(project, "checkout", "HEAD", "--", "extra.txt")
    if dropped.returncode != 0:
        raise SystemExit(dropped.stderr)
    closed_only = git_kit(project, "commit", "-m", "Close extra")
    if closed_only.returncode != 0:
        raise SystemExit(closed_only.stderr + closed_only.stdout)
    reopened = json.loads((project / "plans" / "extra" / "plan.json").read_text(encoding="utf-8"))
    reopened["status"] = "open"
    write(project / "plans" / "extra" / "plan.json", json.dumps(reopened, indent=2) + "\n")
    moved = git_kit(project, "mv", "extra.txt", "extra-renamed.txt")
    if moved.returncode != 0:
        raise SystemExit(moved.stderr)
    renamed = git_kit(project, "commit", "-m", "Rename extra")
    if renamed.returncode == 0 or "extra-renamed.txt" not in renamed.stderr:
        raise SystemExit(f"a rename should need coverage on both paths:\n{renamed.stderr}")
    must(script, "new-session", "--project", str(project), "--plan", "extra", "--id", sid("extra-2"))
    _prep_document(script, project, sid("extra-2"))
    must(script, "close-session", "--project", str(project), "--from-diff")
    renamed_ok = git_kit(project, "commit", "-m", "Cover the rename")
    if renamed_ok.returncode != 0:
        raise SystemExit(renamed_ok.stderr + renamed_ok.stdout)

    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "slice",
        "--title",
        "Slice",
        "--pack",
        "document",
        "--path",
        "docs/index.html",
        "--path",
        "README.md",
    )
    must(script, "new-session", "--project", str(project), "--plan", "slice", "--id", sid("slice-all"))
    whole = json.loads((project / "sessions" / sid("slice-all") / "session.json").read_text(encoding="utf-8"))["writes"]
    if whole != []:
        raise SystemExit(f"writes should start empty: {whole}")
    must(
        script,
        "new-session",
        "--project",
        str(project),
        "--plan",
        "slice",
        "--id",
        sid("slice-part"),
        "--write",
        "docs/index.html",
    )
    part = json.loads((project / "sessions" / sid("slice-part") / "session.json").read_text(encoding="utf-8"))["writes"]
    if part != ["docs/index.html"]:
        raise SystemExit(f"a write names that file only: {part}")
    must(
        script,
        "new-session",
        "--project",
        str(project),
        "--plan",
        "slice",
        "--id",
        sid("slice-off"),
        "--write",
        "gone.txt",
    )
    must(script, "abandon", "--project", str(project), "--session", sid("slice-all"), "--reason", "unused")
    must(script, "abandon", "--project", str(project), "--session", sid("slice-part"), "--reason", "unused")
    must(script, "abandon", "--project", str(project), "--session", sid("slice-off"), "--reason", "unused")
    must(script, "check", "--project", str(project))

    unset = git_kit(project, "config", "--unset", "core.hooksPath")
    if unset.returncode != 0:
        raise SystemExit(unset.stderr)
    assert_fails(script, "check", "--project", str(project), contains="hook.missing")
    still_unset = git_kit(project, "config", "--get", "core.hooksPath")
    if still_unset.returncode == 0:
        raise SystemExit(f"check wrote git config: {still_unset.stdout}")
    must(script, "upgrade", "--project", str(project))
    restored = git_kit(project, "config", "--get", "core.hooksPath")
    if restored.stdout.strip() != "harness-kit/hooks":
        raise SystemExit(restored.stdout or restored.stderr)
    must(script, "check", "--project", str(project))

    foreign = git_kit(project, "config", "core.hooksPath", "/tmp/not-kit-hooks")
    if foreign.returncode != 0:
        raise SystemExit(foreign.stderr)
    must(script, "upgrade", "--project", str(project))
    kept = git_kit(project, "config", "--get", "core.hooksPath")
    if kept.stdout.strip() != "/tmp/not-kit-hooks":
        raise SystemExit(f"upgrade replaced a foreign hooks path: {kept.stdout}")
    assert_fails(script, "check", "--project", str(project), contains="hook.missing")
    back = git_kit(project, "config", "core.hooksPath", "harness-kit/hooks")
    if back.returncode != 0:
        raise SystemExit(back.stderr)
    must(script, "check", "--project", str(project))

    hook = project / "project" / "hooks" / "pre-commit"
    write(hook, "#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    note = project / "plans" / "idle" / "plan.md"
    note.write_text(note.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    noted = git_kit(project, "add", "--", "plans/idle/plan.md")
    if noted.returncode != 0:
        raise SystemExit(noted.stderr)
    blocked = git_kit(project, "commit", "-m", "Project hook blocks")
    if blocked.returncode == 0:
        raise SystemExit("project hook should block the commit")
    write(hook, "#!/bin/sh\nexit 0\n")
    hook.chmod(0o755)
    passed = git_kit(project, "commit", "-m", "Project hook allows")
    if passed.returncode != 0:
        raise SystemExit(passed.stderr + passed.stdout)
    gap = git_kit(project, "add", "--", "plans/idle")
    if gap.returncode != 0:
        raise SystemExit(gap.stderr)
    # Stage a product file no closed session owns, then run the merge hook.
    write(project / "stray.txt", "stray\n")
    stray_add = git_kit(project, "add", "--", "stray.txt")
    if stray_add.returncode != 0:
        raise SystemExit(stray_add.stderr)
    merge_hook = git_kit(project, "hook", "run", "pre-merge-commit")
    if merge_hook.returncode == 0 or "coverage.gap" not in (merge_hook.stderr + merge_hook.stdout):
        raise SystemExit(f"pre-merge-commit should refuse stray.txt:\n{merge_hook.stderr}\n{merge_hook.stdout}")
    cleared = git_kit(project, "reset", "--", "stray.txt", "plans/idle")
    if cleared.returncode != 0:
        raise SystemExit(cleared.stderr)
    (project / "stray.txt").unlink()


def test_tmp_scratch(root: Path) -> None:
    """Scratch stays only for an open session. check does not delete it."""
    project, script = new_project(root, "scratch")
    readme = project / "tmp" / "README.md"
    if not readme.is_file() or "not the record" not in readme.read_text(encoding="utf-8"):
        raise SystemExit("scaffold tmp/README.md does not say it is not the record")
    tracked = git_kit(project, "ls-files", "tmp/README.md")
    if tracked.stdout.strip() != "tmp/README.md":
        raise SystemExit(f"tmp/README.md is not tracked:\n{tracked.stdout}")
    loose = project / "tmp" / "loose.txt"
    write(loose, "loose\n")
    ignored = git_kit(project, "check-ignore", "-q", "tmp/loose.txt")
    if ignored.returncode != 0:
        raise SystemExit("tmp/loose.txt is not ignored")
    added = git_kit(project, "add", "-A")
    if added.returncode != 0:
        raise SystemExit(added.stderr)
    staged = git_kit(project, "diff", "--cached", "--name-only")
    if staged.stdout.strip():
        raise SystemExit(f"git add staged scratch or another file:\n{staged.stdout}")
    outside = root / "outside-target.txt"
    write(outside, "safe\n")
    link = project / "tmp" / "escape"
    link.symlink_to(outside)
    must(script, "check", "--project", str(project))
    if not loose.is_file() or not link.is_symlink():
        raise SystemExit("check removed scratch")
    if outside.read_text(encoding="utf-8") != "safe\n":
        raise SystemExit("check followed a scratch symlink")
    cleaned = must(script, "clean-tmp", "--project", str(project))
    for name in ("tmp/escape", "tmp/loose.txt"):
        if name not in cleaned.stdout:
            raise SystemExit(f"clean-tmp did not report {name}:\n{cleaned.stdout}")
    if loose.exists() or link.exists() or link.is_symlink():
        raise SystemExit("clean-tmp left a loose file or a symlink")
    if outside.read_text(encoding="utf-8") != "safe\n":
        raise SystemExit("clean-tmp followed a symlink")
    if not readme.is_file():
        raise SystemExit("clean-tmp removed tmp/README.md")
    again = must(script, "clean-tmp", "--project", str(project))
    if again.stdout.strip() != "tmp clean":
        raise SystemExit(f"second clean-tmp: {again.stdout}")

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
    write(loose, "loose\n")
    opened = must(
        script,
        "new-session",
        "--project",
        str(project),
        "--plan",
        "notes",
        "--id",
        sid("notes-1"),
    )
    if opened.stdout.strip() != f"Session {sid('notes-1')}":
        raise SystemExit(f"new-session printed extra text:\n{opened.stdout}")
    scratch = project / "tmp" / sid("notes-1")
    if not scratch.is_dir():
        raise SystemExit("new-session did not create tmp/notes-1")
    if loose.exists():
        raise SystemExit("new-session left a loose file")
    note = scratch / "note.txt"
    write(note, "note\n")
    nested = git_kit(project, "check-ignore", "-q", f"tmp/{sid('notes-1')}/note.txt")
    if nested.returncode != 0:
        raise SystemExit(f"tmp/{sid('notes-1')}/note.txt is not ignored")
    sibling = project / "tmp" / "sibling.txt"
    write(sibling, "sibling\n")
    must(script, "clean-tmp", "--project", str(project))
    if not note.is_file():
        raise SystemExit("clean-tmp removed an open session's file")
    if sibling.exists():
        raise SystemExit("clean-tmp left a loose sibling")

    session = project / "sessions" / sid("notes-1")
    write(session / "brief.md", "Question.\n\nDepth: low.\n\nno report\n")
    write(session / "gaps.md", "None.\n")
    must(script, "phase", "--project", str(project), "--session", sid("notes-1"), "--to", "gather")
    must(script, "phase", "--project", str(project), "--session", sid("notes-1"), "--to", "audit")
    write(session / "audit.md", "No unsupported claims.\n")
    write(scratch / "fresh.txt", "fresh\n")
    closed = must(script, "close-session", "--project", str(project), "--session", sid("notes-1"))
    if closed.stdout.strip() != f"Closed {sid('notes-1')}":
        raise SystemExit(f"close-session printed extra text:\n{closed.stdout}")
    if scratch.exists():
        raise SystemExit("close-session left tmp/notes-1")
    write(project / "tmp" / sid("notes-1") / "again.txt", "again\n")
    (project / "tmp" / sid("notes-1") / "escape").symlink_to(outside)
    must(script, "clean-tmp", "--project", str(project))
    if (project / "tmp" / sid("notes-1")).exists():
        raise SystemExit("clean-tmp kept a directory for a closed session")
    if outside.read_text(encoding="utf-8") != "safe\n":
        raise SystemExit("clean-tmp followed a symlink inside a directory")

    opened_again = must(
        script,
        "new-session",
        "--project",
        str(project),
        "--plan",
        "notes",
        "--id",
        sid("notes-2"),
    )
    if opened_again.stdout.strip() != f"Session {sid('notes-2')}":
        raise SystemExit(f"new-session printed extra text:\n{opened_again.stdout}")
    second = project / "tmp" / sid("notes-2")
    write(second / "note.txt", "note\n")
    abandoned = must(
        script,
        "abandon",
        "--project",
        str(project),
        "--session",
        sid("notes-2"),
        "--reason",
        "Stop this pass",
    )
    if abandoned.stdout.strip() != f"Abandoned {sid('notes-2')}":
        raise SystemExit(f"abandon printed extra text:\n{abandoned.stdout}")
    if second.exists():
        raise SystemExit("abandon left tmp/notes-2")

    stub = (KIT / "templates" / "AGENTS.md").read_text(encoding="utf-8")
    sentence = "Scratch for a session goes in `tmp/<session-id>/`. That folder is not the record."
    if sentence not in stub:
        raise SystemExit("stub is missing the scratch sentence")
    kit_readme = (KIT / "README.md").read_text(encoding="utf-8")
    if "| `clean-tmp` |" not in kit_readme:
        raise SystemExit("README is missing the clean-tmp command")
    page = (KIT / "docs" / "index.html").read_text(encoding="utf-8")
    if "<code>clean-tmp</code>" not in page:
        raise SystemExit("workflow page is missing clean-tmp")
    log = KIT / "log" / "2026-10-09-agent-skill.md"
    if not log.is_file():
        raise SystemExit("agent-skill log is missing")
    if pin_move.grading_line(log.read_text(encoding="utf-8")) is None:
        raise SystemExit("agent-skill log has no grading line")
    if "compatible" not in pin_move.grading_line(log.read_text(encoding="utf-8")):
        raise SystemExit("agent-skill log grading line is not compatible")
    status = (KIT / "STATUS.md").read_text(encoding="utf-8")
    if "log/2026-10-13-owning-session.md" not in status:
        raise SystemExit("STATUS.md does not point at the owning-session log")
    owned_log = KIT / "log" / "2026-10-13-owning-session.md"
    if not owned_log.is_file():
        raise SystemExit("owning-session log is missing")
    owned_line = pin_move.grading_line(owned_log.read_text(encoding="utf-8"))
    if owned_line is None or "breaking" not in owned_line:
        raise SystemExit("owning-session log grading line is not breaking")
    tree_log = KIT / "log" / "2026-10-09-project-tree.md"
    if not tree_log.is_file():
        raise SystemExit("project-tree log is missing")
    if not (KIT / "log" / "2026-10-09-tmp-scratch.md").is_file():
        raise SystemExit("tmp scratch log is missing")


def test_missing_skill_crashes(root: Path) -> None:
    """The empty directory git clone leaves is not a skill checkout. upgrade fills it."""
    project, script = new_project(root, "skill-missing")
    skill = project / "harness-kit" / "agent-skill"
    shutil.rmtree(skill)
    skill.mkdir()
    result = run(script, "check", "--project", str(project))
    blob = result.stderr + result.stdout
    if (
        result.returncode == 0
        or "agent-skill" not in blob
        or "missing" not in blob
        or "FAIL" in blob
        or "pin.dirty" in blob
    ):
        raise SystemExit(f"missing skill should crash, not a check row:\n{blob}")
    must(script, "upgrade", "--project", str(project))
    assert_skill_checkout(project / "harness-kit")


def _skill_record(kit: Path) -> str:
    parts = git_kit(kit, "ls-files", "-s", "--", "agent-skill").stdout.split()
    if len(parts) < 2 or parts[0] != "160000":
        raise SystemExit(f"{kit} has no agent-skill gitlink")
    return parts[1]


def _assert_skill_crash(result: subprocess.CompletedProcess[str], recorded: str) -> None:
    blob = result.stderr + result.stdout
    if (
        result.returncode == 0
        or "agent-skill" not in blob
        or recorded not in blob
        or "FAIL" in blob
        or "pin.dirty" in blob
        or "uncommitted" in blob
    ):
        raise SystemExit(f"skill checkout should crash, not a check row:\n{blob}")


def test_removed_skill_crashes(root: Path) -> None:
    """Deleting the skill directory crashes with the recorded commit. upgrade fills it."""
    project, script = new_project(root, "skill-removed")
    kit = project / "harness-kit"
    recorded = _skill_record(kit)
    shutil.rmtree(kit / "agent-skill")
    _assert_skill_crash(run(script, "check", "--project", str(project)), recorded)
    must(script, "upgrade", "--project", str(project))
    assert_skill_checkout(kit)


def test_drifted_skill_crashes(root: Path) -> None:
    """A different skill commit crashes. upgrade does not replace it."""
    project, script = new_project(root, "skill-drift")
    kit = project / "harness-kit"
    recorded = _skill_record(kit)
    other = git_kit(kit / "agent-skill", "rev-parse", "HEAD^")
    if other.returncode != 0 or not other.stdout.strip():
        raise SystemExit(other.stderr)
    moved = git_kit(kit / "agent-skill", "checkout", "--detach", other.stdout.strip())
    if moved.returncode != 0:
        raise SystemExit(moved.stderr)
    _assert_skill_crash(run(script, "check", "--project", str(project)), recorded)
    upgraded = run(script, "upgrade", "--project", str(project))
    _assert_skill_crash(upgraded, recorded)
    head = git_kit(kit / "agent-skill", "rev-parse", "HEAD").stdout.strip()
    if head != other.stdout.strip():
        raise SystemExit(f"upgrade replaced agent-skill HEAD {head}")


def _status(repo: Path) -> str:
    result = git_kit(repo, "status", "--porcelain")
    if result.returncode != 0:
        raise SystemExit(result.stderr)
    return result.stdout


def _head(repo: Path) -> str:
    result = git_kit(repo, "rev-parse", "HEAD")
    if result.returncode != 0:
        raise SystemExit(result.stderr)
    return result.stdout.strip()


def _plan_paths(project: Path, plan_id: str, paths: list[str]) -> None:
    record_path = project / "plans" / plan_id / "plan.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["paths"] = paths
    write(record_path, json.dumps(record, indent=2) + "\n")


def test_project_tree(root: Path) -> None:
    """A nested repository is another project. This check does not enter it."""
    import checks

    parent, parent_script = new_project(root, "outer")
    child, _child_script = new_project(root, "inner")
    empty = git_kit(child / "harness-kit", "commit", "--allow-empty", "-m", "child kit pin")
    if empty.returncode != 0:
        raise SystemExit(empty.stderr + empty.stdout)
    child_kit = _head(child / "harness-kit")
    parent_kit = _head(parent / "harness-kit")
    if child_kit == parent_kit:
        raise SystemExit("child kit commit should differ from the parent kit")
    pinned = git_kit(child, "update-index", "--cacheinfo", f"160000,{child_kit},harness-kit")
    if pinned.returncode != 0:
        raise SystemExit(pinned.stderr)
    committed = git_kit(child, "commit", "-m", "Pin the child kit")
    if committed.returncode != 0:
        raise SystemExit(committed.stderr + committed.stdout)
    widget = parent / "widget"
    shutil.move(str(child), str(widget))
    child_script = widget / "harness-kit" / "scripts" / "harness.py"
    widget_head = _head(widget)
    recorded = git_kit(
        parent, "update-index", "--add", "--cacheinfo", f"160000,{widget_head},widget"
    )
    if recorded.returncode != 0:
        raise SystemExit(recorded.stderr)
    if _head(widget / "harness-kit") == parent_kit:
        raise SystemExit("nested kit commit matches the parent")

    parent_head = _head(parent)
    parent_status = _status(parent)
    child_head = _head(widget)
    child_status = _status(widget)
    crossed = subprocess.run(
        [sys.executable, str(parent_script), "check"],
        cwd=widget,
        capture_output=True,
        text=True,
    )
    crossed_blob = crossed.stderr + crossed.stdout
    if (
        crossed.returncode == 0
        or str(widget) not in crossed_blob
        or str(parent / "harness-kit") not in crossed_blob
    ):
        raise SystemExit(f"parent script in the child should name both checkouts:\n{crossed_blob}")
    if _head(parent) != parent_head or _status(parent) != parent_status:
        raise SystemExit("parent script wrote the parent")
    if _head(widget) != child_head or _status(widget) != child_status:
        raise SystemExit("parent script wrote the child")

    must(
        parent_script,
        "new-plan",
        "--project",
        str(parent),
        "--id",
        "hold",
        "--title",
        "Hold",
        "--pack",
        "document",
    )
    _plan_paths(parent, "hold", ["plans/hold/plan.md", "widget/docs/index.html"])
    entered = run(parent_script, "check", "--project", str(parent))
    entered_blob = entered.stderr + entered.stdout
    if entered.returncode == 0 or "path.plan" not in entered_blob or "path enters a submodule" not in entered_blob:
        raise SystemExit(f"a path under the child should be path.plan:\n{entered_blob}")
    _plan_paths(parent, "hold", ["plans/hold/plan.md", "widget"])
    fill_plan(parent, "hold")
    must(parent_script, "new-session", "--project", str(parent), "--plan", "hold", "--id", sid("hold-1"))
    must(parent_script, "link", "--project", str(parent))
    held = must(parent_script, "check", "--project", str(parent))
    held_blob = held.stdout + held.stderr
    if "path.plan" in held_blob or "project.boundary" in held_blob:
        raise SystemExit(f"the submodule path is the gitlink, not the files inside it:\n{held_blob}")

    must(
        child_script,
        "new-plan",
        "--project",
        str(widget),
        "--id",
        "child-hold",
        "--title",
        "Child",
        "--pack",
        "document",
    )
    _plan_paths(widget, "child-hold", ["plans/child-hold/plan.md", "harness-kit/KERNEL.md"])
    child_bad = run(child_script, "check", "--project", str(widget))
    child_bad_blob = child_bad.stderr + child_bad.stdout
    if child_bad.returncode == 0 or "path.plan" not in child_bad_blob:
        raise SystemExit(f"child check should reject its own kit path:\n{child_bad_blob}")
    parent_quiet = must(parent_script, "check", "--project", str(parent))
    parent_quiet_blob = parent_quiet.stdout + parent_quiet.stderr
    if "child-hold" in parent_quiet_blob or "KERNEL.md" in parent_quiet_blob:
        raise SystemExit(f"parent check looked at the child:\n{parent_quiet_blob}")
    _plan_paths(widget, "child-hold", ["plans/child-hold/plan.md"])
    _plan_paths(parent, "hold", ["plans/hold/plan.md", "widget", "src/*.py"])
    parent_bad = run(parent_script, "check", "--project", str(parent))
    parent_bad_blob = parent_bad.stderr + parent_bad.stdout
    if "src/*.py" not in parent_bad_blob:
        raise SystemExit(f"parent glob should be path.plan:\n{parent_bad_blob}")
    child_quiet = must(child_script, "check", "--project", str(widget))
    child_quiet_blob = child_quiet.stdout + child_quiet.stderr
    if "src/*.py" in child_quiet_blob or "hold" in child_quiet_blob:
        raise SystemExit(f"child check looked at the parent:\n{child_quiet_blob}")
    _plan_paths(parent, "hold", ["plans/hold/plan.md", "widget"])
    must(parent_script, "link", "--project", str(parent))
    must(parent_script, "check", "--project", str(parent))
    must(child_script, "check", "--project", str(widget))

    write(widget / "only-child.txt", "only\n")
    rels = [path.relative_to(parent).as_posix() for path in checks.matching_paths(parent, "**/*")]
    if any(rel.startswith("widget/") for rel in rels):
        raise SystemExit(f"a glob matched a file inside the child: {rels}")
    leaf_hits = [path.relative_to(parent).as_posix() for path in checks.matching_paths(parent, "widget")]
    if leaf_hits != ["widget"]:
        raise SystemExit(f"the leaf itself should match: {leaf_hits}")
    (widget / "only-child.txt").unlink()

    stray = parent / "stray"
    stray.mkdir()
    created = subprocess.run(["git", "init", str(stray)], capture_output=True, text=True)
    if created.returncode != 0:
        raise SystemExit(created.stderr)
    write(stray / "a.txt", "a\n")
    bounded = run(parent_script, "check", "--project", str(parent))
    bounded_blob = bounded.stderr + bounded.stdout
    if bounded.returncode == 0 or "project.boundary" not in bounded_blob or "stray" not in bounded_blob:
        raise SystemExit(f"an unrecorded nested repository should be project.boundary:\n{bounded_blob}")
    shutil.rmtree(stray)
    must(parent_script, "check", "--project", str(parent))
    nested = parent / "tmp" / "nested"
    nested.mkdir()
    ignored = subprocess.run(["git", "init", str(nested)], capture_output=True, text=True)
    if ignored.returncode != 0:
        raise SystemExit(ignored.stderr)
    ignored_check = must(parent_script, "check", "--project", str(parent))
    if "project.boundary" in ignored_check.stdout + ignored_check.stderr:
        raise SystemExit("gitignored scratch should not be project.boundary")


def test_nested_birth(root: Path) -> None:
    """new-project inside a project stages a leaf and does not commit the parent."""
    import tree

    parent, parent_script = new_project(root, "birth-outer")
    kit_before = git_kit(parent, "ls-files", "-s", "--", "harness-kit").stdout
    head_before = _head(parent)
    hooks_before = git_kit(parent, "config", "--get", "core.hooksPath").stdout.strip()
    dest = parent / "inner"
    must(SOURCE, "new-project", str(dest), "--id", "inner", "--name", "Inner")
    if not tree.own_toplevel(dest):
        raise SystemExit("inner is not its own repository")
    if _head(parent) != head_before:
        raise SystemExit("new-project committed the enclosing project")
    if git_kit(parent, "ls-files", "-s", "--", "harness-kit").stdout != kit_before:
        raise SystemExit("new-project moved the parent kit hash")
    if git_kit(parent, "config", "--get", "core.hooksPath").stdout.strip() != hooks_before:
        raise SystemExit("new-project rewrote the parent hook path")
    child_hooks = git_kit(dest, "config", "--get", "core.hooksPath").stdout.strip()
    if child_hooks != "harness-kit/hooks":
        raise SystemExit(f"child hooks are {child_hooks}")
    link = git_kit(parent, "ls-files", "-s", "--", "inner").stdout.split()
    if len(link) < 4 or link[0] != "160000":
        raise SystemExit(f"inner was not staged as a gitlink: {link}")
    modules = (parent / ".gitmodules").read_text(encoding="utf-8")
    if '[submodule "inner"]' not in modules or "\n\tpath = inner\n" not in modules:
        raise SystemExit(modules)
    cached = git_kit(parent, "diff", "--cached", "--name-only").stdout.split()
    if "inner" not in cached:
        raise SystemExit(f"inner gitlink is not staged: {cached}")
    assert_fails(parent_script, "check", "--project", str(parent), contains="coverage.gap")
    must(
        parent_script,
        "new-plan",
        "--project",
        str(parent),
        "--id",
        "nest",
        "--title",
        "Nest",
        "--pack",
        "document",
        "--path",
        "inner",
    )
    must(parent_script, "new-session", "--project", str(parent), "--plan", "nest", "--id", sid("nest-1"))
    must(parent_script, "check", "--project", str(parent))

    plain = root / "plain"
    plain.mkdir()
    init = subprocess.run(["git", "init", str(plain)], capture_output=True, text=True)
    if init.returncode != 0:
        raise SystemExit(init.stderr)
    write(plain / "keep.txt", "keep\n")
    added = git_kit(plain, "add", "keep.txt")
    if added.returncode != 0:
        raise SystemExit(added.stderr)
    made = git_kit(plain, "commit", "-m", "Keep")
    if made.returncode != 0:
        raise SystemExit(made.stderr + made.stdout)
    plain_head = _head(plain)
    plain_status = _status(plain)
    refused = run(SOURCE, "new-project", str(plain / "nope"), "--id", "nope", "--name", "Nope")
    refused_blob = refused.stderr + refused.stdout
    if refused.returncode == 0 or "not a harness project" not in refused_blob:
        raise SystemExit(f"new-project inside a plain repo should die:\n{refused_blob}")
    if (plain / "nope").exists() or _head(plain) != plain_head or _status(plain) != plain_status:
        raise SystemExit("new-project changed the plain repository")

    loose = parent / "loose"
    write(loose / "note.txt", "n\n")
    index_before = git_kit(parent, "ls-files", "-s").stdout
    adopted = run(SOURCE, "adopt", str(loose))
    if adopted.returncode == 0 or "inside another repository" not in adopted.stderr + adopted.stdout:
        raise SystemExit(f"adopt of a subdirectory should die:\n{adopted.stderr}")
    if git_kit(parent, "ls-files", "-s").stdout != index_before or (loose / "harness-kit").exists():
        raise SystemExit("adopt wrote into the enclosing project")

    held = parent / "held"
    held.mkdir()
    held_init = subprocess.run(["git", "init", str(held)], capture_output=True, text=True)
    if held_init.returncode != 0:
        raise SystemExit(held_init.stderr)
    write(held / "keep.txt", "keep\n")
    held_add = git_kit(held, "add", "keep.txt")
    if held_add.returncode != 0:
        raise SystemExit(held_add.stderr)
    held_commit = git_kit(held, "commit", "-m", "Keep")
    if held_commit.returncode != 0:
        raise SystemExit(held_commit.stderr + held_commit.stdout)
    parent_at_adopt = _head(parent)
    child_at_adopt = _head(held)
    must(SOURCE, "adopt", str(held), "--id", "held", "--name", "Held")
    if _head(parent) != parent_at_adopt:
        raise SystemExit("adopt committed the enclosing project")
    if _head(held) != child_at_adopt:
        raise SystemExit("adopt committed the adopted repository")
    staged_held = git_kit(parent, "ls-files", "-s", "--", "held").stdout.split()
    if len(staged_held) < 4 or staged_held[0] != "160000":
        raise SystemExit(f"held was not staged as a gitlink: {staged_held}")
    held_modules = (parent / ".gitmodules").read_text(encoding="utf-8")
    if '[submodule "held"]' not in held_modules or "\n\tpath = held\n" not in held_modules:
        raise SystemExit(held_modules)
    child_kit = git_kit(held, "ls-files", "-s", "--", "harness-kit").stdout.split()
    if len(child_kit) < 2 or child_kit[0] != "160000":
        raise SystemExit(f"adopt did not record the kit: {child_kit}")

    shutil.rmtree(dest)
    again = run(SOURCE, "new-project", str(dest), "--id", "inner", "--name", "Inner")
    if again.returncode == 0 or "already a submodule" not in again.stderr + again.stdout or dest.exists():
        raise SystemExit(f"an existing gitlink should refuse before init:\n{again.stderr}\n{again.stdout}")


def test_dated_id_and_close_gates(root: Path) -> None:
    """A bare slug gains today's date. A coding close needs a design and a handoff."""
    project, script = new_project(root, "dated")
    day = date.today().isoformat()
    must(
        script,
        "new-plan",
        "--project",
        str(project),
        "--id",
        "plain",
        "--title",
        "Plain",
        "--pack",
        "document",
    )
    must(script, "new-session", "--project", str(project), "--plan", "plain")
    plain = json.loads((project / "sessions" / f"{day}-plain" / "session.json").read_text(encoding="utf-8"))
    if plain["id"] != f"{day}-plain":
        raise SystemExit(f"omitted --id should be the day plus the plan: {plain['id']}")
    must(script, "abandon", "--project", str(project), "--session", f"{day}-plain", "--reason", "id checked")
    parked = git_kit(project, "add", "--", f"sessions/{day}-plain", "project/links.json", "plans/plain/plan.json")
    if parked.returncode != 0:
        raise SystemExit(parked.stderr)
    parked_commit = git_kit(project, "commit", "-m", "Abandon the plain session")
    if parked_commit.returncode != 0:
        raise SystemExit(parked_commit.stderr + parked_commit.stdout)

    must(script, "new-feature", "--project", str(project), "--id", "gate", "--title", "Gate")
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
        "--feature",
        "gate",
        "--id",
        "gate",
    )
    stored = json.loads((project / "sessions" / f"{day}-gate" / "session.json").read_text(encoding="utf-8"))
    if stored["id"] != f"{day}-gate":
        raise SystemExit(f"a bare slug should gain the day: {stored['id']}")
    kept = f"{day}-kept"
    must(
        script,
        "new-session",
        "--project",
        str(project),
        "--plan",
        "gate-plan",
        "--feature",
        "gate",
        "--id",
        kept,
    )
    if not (project / "sessions" / kept).is_dir():
        raise SystemExit("an id that already starts with a day should be kept")
    must(script, "abandon", "--project", str(project), "--session", kept, "--reason", "id kept")
    kept_add = git_kit(project, "add", "--", f"sessions/{kept}", "project/links.json", "plans/gate-plan/plan.json")
    if kept_add.returncode != 0:
        raise SystemExit(kept_add.stderr)
    kept_commit = git_kit(project, "commit", "-m", "Abandon the kept session")
    if kept_commit.returncode != 0:
        raise SystemExit(kept_commit.stderr + kept_commit.stdout)

    write(project / "owned.txt", "owned\n")
    assert_fails(script, "check", "--project", str(project), contains="session.design")
    coding = project / "sessions" / f"{day}-gate"
    write(coding / "design.md", "The map names this session.\n")
    must(script, "check", "--project", str(project))
    write(coding / "review.md", "The critique.\n")
    write(coding / "verify.md", "verify: empty\n")
    assert_fails(script, "close-session", "--project", str(project), "--from-diff", contains="session.handoff")
    write(coding / "handoffs" / "implement.md", "## Coverage\n\nowned.txt\n")
    must(script, "close-session", "--project", str(project), "--from-diff")


def main() -> None:
    _scratch_commit_and_reexec()
    head = subprocess.run(
        ["git", "-C", str(KIT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if head.returncode != 0:
        raise SystemExit("harness-kit has no commit, so new-project cannot clone it")
    test_kit_has_no_project_records()
    test_entrypoint_yields()
    test_kit_repo_record()
    test_commit_is_the_version()
    test_workflow_page()
    test_log_move_gate()
    with tempfile.TemporaryDirectory(prefix="harness-kit-") as tmp:
        root = Path(tmp)
        test_session_grade(root)
        test_coverage(root)
        test_dated_id_and_close_gates(root)
        test_tmp_scratch(root)
        test_project_tree(root)
        test_nested_birth(root)
        test_document_and_coding(root)
        test_human_docs(root)
        test_upgrade_and_sync(root)
        test_missing_skill_crashes(root)
        test_removed_skill_crashes(root)
        test_drifted_skill_crashes(root)
        test_pin_moves(root)
        test_stamp_graph_and_adopt(root)
    print("test_harness ok")


if __name__ == "__main__":
    main()
