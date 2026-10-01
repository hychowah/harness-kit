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
    return project / "harness-kit" / "scripts" / "harness.py"


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
        "harness-kit/KERNEL.md",
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
    assert_fails(
        script,
        "preflight",
        "--project",
        str(project),
        "--session",
        "notes-1",
        "--phase",
        "audit",
        contains="waits on",
    )
    must(script, "preflight", "--project", str(project), "--session", "notes-1")
    assert_fails(
        script,
        "phase",
        "--project",
        str(project),
        "--session",
        "notes-1",
        "--to",
        "audit",
        contains="waits on",
    )
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

    shutil.rmtree(project / "harness-kit")
    must(SOURCE, "sync", "--project", str(project))
    script = project_script(project)
    must(script, "check", "--project", str(project))
    if (project / "project" / "LAW.md").read_bytes() != law:
        raise SystemExit("sync changed domain law")

    kit = project / "harness-kit"
    kernel = kit / "KERNEL.md"
    write(kernel, kernel.read_text(encoding="utf-8") + "\nHash is the version.\n")
    assert_fails(script, "upgrade", "--project", str(project), contains="dirty")
    added = git_kit(kit, "add", "KERNEL.md")
    if added.returncode != 0:
        raise SystemExit(added.stderr)
    committed = git_kit(kit, "commit", "-m", "Test commit is the version")
    if committed.returncode != 0:
        raise SystemExit(committed.stderr)
    must(script, "upgrade", "--project", str(project))
    recorded = git_kit(project, "ls-files", "-s", "--", "harness-kit").stdout.strip().split()
    head = git_kit(kit, "rev-parse", "HEAD").stdout.strip()
    if len(recorded) < 2 or recorded[0] != "160000" or recorded[1] != head:
        raise SystemExit(f"submodule record did not follow the kit commit: {recorded} head={head}")
    stub = agents.read_text(encoding="utf-8")
    if head not in stub or custom not in stub:
        raise SystemExit("upgrade rewrote the project half of AGENTS.md or skipped the commit")
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
    must(script, "upgrade", "--project", str(project))
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
    return sorted(path for path in names if path in LAW_EXACT or path.startswith(LAW_PREFIXES))


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
    ):
        if sentence not in stub:
            raise SystemExit(f"stub missing yield sentence: {sentence}")
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
    try:
        document = page.split('id="document"', 1)[1].split('id="coding"', 1)[0]
        coding = page.split('id="coding"', 1)[1].split('id="workers"', 1)[0]
    except IndexError as exc:
        raise SystemExit("workflow page is missing a document, coding, or workers section") from exc
    for earlier, later in (("brief", "gather"), ("gather", "audit"), ("audit", "closed")):
        if document.find(earlier) < 0 or document.find(later) < 0 or document.find(earlier) > document.find(later):
            raise SystemExit(f"document chart order broken: {earlier} before {later}")
    for earlier, later in (("baseline", "implement"), ("implement", "verify"), ("verify", "closed")):
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
    must(script, "new-session", "--project", str(project), "--plan", "notes", "--id", "notes-1")
    session = project / "sessions" / "notes-1"
    record_path = session / "session.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    original_commit = record["harness_commit"]
    record["harness_commit"] = "a" * 40
    write(record_path, json.dumps(record))
    must(script, "link", "--project", str(project))
    warned = run(script, "check", "--project", str(project))
    if warned.returncode != 0 or "WARN law.stamp" not in warned.stderr:
        raise SystemExit(f"foreign commit should warn:\n{warned.stderr}")
    record["phase"] = "not-a-node"
    write(record_path, json.dumps(record))
    must(script, "link", "--project", str(project))
    ungraded = run(script, "check", "--project", str(project))
    if ungraded.returncode != 0 or "phase.unknown" in ungraded.stderr or "WARN law.stamp" not in ungraded.stderr:
        raise SystemExit(f"a foreign stamp must not grade the phase:\n{ungraded.stderr}")
    record["phase"] = "brief"
    write(record_path, json.dumps(record))
    must(script, "link", "--project", str(project))
    strict = run(script, "check", "--project", str(project), "--session", "notes-1")
    if strict.returncode == 0 or "FAIL law.stamp" not in strict.stderr:
        raise SystemExit(f"check --session should fail the foreign commit:\n{strict.stderr}")
    prose = session / "session.md"
    original_prose = prose.read_text(encoding="utf-8")
    record["harness_commit"] = original_commit
    write(record_path, json.dumps(record))
    must(script, "link", "--project", str(project))
    write(session / "brief.md", "Question.\n")
    write(session / "gaps.md", "None.\n")
    must(script, "phase", "--project", str(project), "--session", "notes-1", "--to", "gather")
    must(script, "phase", "--project", str(project), "--session", "notes-1", "--to", "audit")
    write(session / "audit.md", "No unsupported claims.\n")
    must(script, "close-session", "--project", str(project), "--session", "notes-1")
    sealed = json.loads(record_path.read_text(encoding="utf-8"))
    sealed["harness_commit"] = "b" * 40
    write(record_path, json.dumps(sealed))
    write(prose, prose.read_text(encoding="utf-8") + "\nChanged after seal.\n")
    both = run(script, "check", "--project", str(project))
    if both.returncode == 0 or "fingerprint" not in both.stderr:
        raise SystemExit(f"fingerprint must fail across a stamp mismatch:\n{both.stderr}")
    write(prose, original_prose)
    sealed["harness_commit"] = original_commit
    write(record_path, json.dumps(sealed))
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
    )
    must(script, "new-session", "--project", str(project), "--plan", "again", "--id", "again-1")
    ident["project_stamp"] = "stamp-2"
    write(ident_path, json.dumps(ident))
    moved = run(script, "check", "--project", str(project))
    if moved.returncode != 0 or "WARN law.stamp" not in moved.stderr:
        raise SystemExit(f"project stamp mismatch should warn:\n{moved.stderr}")
    ident["project_stamp"] = "stamp-1"
    write(ident_path, json.dumps(ident))

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
    )
    must(script, "new-session", "--project", str(project), "--plan", "survey-plan", "--id", "survey-1")
    opened = json.loads((project / "sessions" / "survey-1" / "session.json").read_text(encoding="utf-8"))
    if opened["phase"] != "left":
        raise SystemExit(f"a fork should start at a root, got {opened['phase']}")
    assert_fails(
        script,
        "preflight",
        "--project",
        str(project),
        "--session",
        "survey-1",
        contains="--phase",
    )
    assert_fails(
        script,
        "spawn",
        "--project",
        str(project),
        "--session",
        "survey-1",
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
        "survey-1",
        "--to",
        "join",
        contains="--enter",
    )
    write(project / "sessions" / "survey-1" / "left.md", "left\n")
    must(
        script,
        "status",
        "--project",
        str(project),
        "--session",
        "survey-1",
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
        "survey-1",
        "--node",
        "right",
        "--set",
        "complete",
    )
    must(script, "phase", "--project", str(project), "--session", "survey-1", "--enter", "join")
    (project / "notes").mkdir()
    write(project / "notes" / "owned.txt", "owned\n")
    assert_fails(script, "check", "--project", str(project), contains="spawn.missing")
    assert_fails(
        script,
        "spawn",
        "--project",
        str(project),
        "--session",
        "survey-1",
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
        "survey-1",
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
    spawn_path = project / "sessions" / "survey-1" / "spawns.json"
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

    must(script, "new-session", "--project", str(project), "--plan", "survey-plan", "--id", "survey-stop")
    must(
        script,
        "abandon",
        "--project",
        str(project),
        "--session",
        "survey-stop",
        "--reason",
        "spawn failed",
    )
    assert_fails(
        script,
        "phase",
        "--project",
        str(project),
        "--session",
        "survey-stop",
        "--enter",
        "left",
        contains="new session",
    )
    if run(script, "check", "--project", str(project)).returncode != 0:
        raise SystemExit("an abandoned session should not fail the project check")

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
    )
    must(script, "new-session", "--project", str(project), "--plan", "cards-plan", "--id", "cards-1")
    cards_session = project / "sessions" / "cards-1"
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
    survey_record_path = project / "sessions" / "survey-1" / "session.json"
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
    for path in KIT.rglob("*"):
        relative = path.relative_to(KIT)
        if ".git" in relative.parts or path.is_dir():
            continue
        dest = scratch / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    git = ["git", "-C", str(scratch), "-c", "user.email=harness-kit@localhost", "-c", "user.name=harness-kit"]
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
    with tempfile.TemporaryDirectory(prefix="harness-kit-") as tmp:
        root = Path(tmp)
        test_document_and_coding(root)
        test_upgrade_and_sync(root)
        test_stamp_graph_and_adopt(root)
    print("test_harness ok")


if __name__ == "__main__":
    main()
