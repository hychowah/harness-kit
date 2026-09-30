#!/usr/bin/env python3
"""A result is PASS, FAIL, WARN, or SKIPPED with a stable id.

The detail says how to fix it. check exits non-zero only on FAIL.
SKIPPED means the rule does not apply. A broken pack crashes; it is not a result.

Evidence predicates, and the only place their meaning is defined:

- exists: the glob matches at least min files, or directories that contain a file.
- schema: each match is JSON and satisfies the schema path named on the evidence.
- provenance: each match is a JSON object with a non-empty rationale, a basis path
  that exists under the project, and a compute path that exists when that key is set.

Optional evidence that is absent is SKIPPED. An unknown predicate crashes.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

PREDICATES = ("exists", "schema", "provenance")
STATUSES = ("PASS", "FAIL", "WARN", "SKIPPED")
LINE = re.compile(r"^(PASS|FAIL|WARN|SKIPPED)\s+(\S+)(?:\s+(.*))?$")


class Result:
    """One gate finding. The id stays stable so a later session can search for it."""

    def __init__(self, status: str, check_id: str, detail: str = "") -> None:
        if status not in STATUSES:
            raise ValueError(status)
        self.status = status
        self.check_id = check_id
        self.detail = detail

    def line(self) -> str:
        if self.detail:
            return f"{self.status} {self.check_id} {self.detail}"
        return f"{self.status} {self.check_id}"


def fail(check_id: str, detail: str) -> Result:
    return Result("FAIL", check_id, detail)


def warn(check_id: str, detail: str) -> Result:
    return Result("WARN", check_id, detail)


def skipped(check_id: str, detail: str) -> Result:
    return Result("SKIPPED", check_id, detail)


def ok(check_id: str, detail: str = "") -> Result:
    return Result("PASS", check_id, detail)


def has_fail(results: list[Result]) -> bool:
    return any(item.status == "FAIL" for item in results)


def _is_type(value: object, name: str) -> bool:
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, dict)
    if name == "null":
        return value is None
    return False


def _resolve_ref(root: dict, ref: object) -> dict | None:
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return None
    target: object = root
    for part in ref[2:].split("/"):
        if not isinstance(target, dict) or part not in target:
            return None
        target = target[part]
    return target if isinstance(target, dict) else None


def validate(instance: object, spec: dict, label: str, root: dict | None = None) -> list[str]:
    """Schema subset the gate and the pack loader run.

    A ``#/`` ref resolves against the schema root. Other refs are rejected.
    """
    schema_root = spec if root is None else root
    if "$ref" in spec:
        target = _resolve_ref(schema_root, spec["$ref"])
        if target is None:
            return [f"{label} schema ref {spec.get('$ref')} is missing"]
        return validate(instance, target, label, schema_root)
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
                errors.extend(validate(instance[key], prop, f"{label}.{key}", schema_root))
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
    if "minimum" in spec and isinstance(instance, int) and not isinstance(instance, bool):
        if instance < spec["minimum"]:
            errors.append(f"{label} is below {spec['minimum']}")
    if declared == "array" and isinstance(instance, list):
        if isinstance(spec.get("items"), dict):
            for index, item in enumerate(instance):
                errors.extend(validate(item, spec["items"], f"{label}[{index}]", schema_root))
        if "minItems" in spec and len(instance) < spec["minItems"]:
            errors.append(f"{label} needs at least {spec['minItems']}")
    return errors


def matching_paths(root: Path, pattern: str) -> list[Path]:
    """Files, or directories that contain a file, matching a relative glob."""
    if not pattern or pattern.startswith("/") or ".." in Path(pattern).parts:
        return []
    if any(char in pattern for char in "*?["):
        found = list(root.glob(pattern))
    else:
        direct = root / pattern
        found = [direct] if direct.exists() else []
    kept: list[Path] = []
    for path in found:
        if any(part in {".git", ".harness", "harness-kit"} for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            kept.append(path)
        elif path.is_dir() and any(child.is_file() for child in path.rglob("*")):
            kept.append(path)
    return kept


def _evidence_root(project: Path, session_folder: Path, item: dict) -> Path:
    # Session files (brief.md) live in the session folder. Project artifacts
    # are named from the project root. The pack picks which root.
    if item.get("root", "session") == "project":
        return project
    return session_folder


def _one(project: Path, session_folder: Path, item: dict) -> list[Result]:
    kind = item["predicate"]
    if kind not in PREDICATES:
        raise SystemExit(f"Unknown predicate {kind}.")
    optional = bool(item.get("optional"))
    pattern = item["glob"]
    root = _evidence_root(project, session_folder, item)
    matches = matching_paths(root, pattern)
    minimum = int(item.get("min", 1))
    check_id = f"evidence.{kind}"
    if not matches:
        if optional:
            return [skipped(check_id, f"{pattern} is absent")]
        return [fail(check_id, f"{pattern} is missing")]
    if kind == "exists":
        if len(matches) < minimum:
            return [fail(check_id, f"{pattern} matched {len(matches)}, needs {minimum}")]
        return [ok(check_id, pattern)]
    results: list[Result] = []
    for path in matches:
        if kind == "schema":
            schema_rel = item.get("schema")
            if not schema_rel:
                raise SystemExit("schema predicate needs a schema path.")
            schema_path = project / schema_rel
            if not schema_path.is_file():
                results.append(fail(check_id, f"schema file {schema_rel} is missing"))
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                spec = json.loads(schema_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                results.append(fail(check_id, f"{pattern} is not json: {exc}"))
                continue
            errors = validate(data, spec, pattern)
            if errors:
                results.append(fail(check_id, "; ".join(errors)))
            else:
                results.append(ok(check_id, pattern))
            continue
        results.extend(_provenance(project, path, pattern))
    return results


def _provenance(project: Path, path: Path, pattern: str) -> list[Result]:
    check_id = "evidence.provenance"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [fail(check_id, f"{pattern} is not json: {exc}")]
    if not isinstance(data, dict):
        return [fail(check_id, f"{pattern} needs an object with rationale")]
    rationale = data.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        return [fail(check_id, f"{pattern} needs a non-empty rationale")]
    basis = data.get("basis")
    if not isinstance(basis, str) or not basis.strip():
        return [fail(check_id, f"{pattern} needs a basis path")]
    basis_path = project / basis
    if not basis_path.exists():
        return [fail(check_id, f"{pattern} basis {basis} is missing")]
    compute = data.get("compute")
    if compute is not None:
        if not isinstance(compute, str) or not (project / compute).exists():
            return [fail(check_id, f"{pattern} compute path is missing")]
    return [ok(check_id, pattern)]


def eval_evidence(project: Path, session_folder: Path, items: list) -> list[Result]:
    results: list[Result] = []
    for item in items:
        results.extend(_one(project, session_folder, item))
    return results


def blocking_globs(project: Path, session_folder: Path, items: list) -> list[str]:
    """Glob names whose evidence failed. Phase errors name these files."""
    missing: list[str] = []
    for item in items:
        if any(row.status == "FAIL" for row in _one(project, session_folder, item)):
            missing.append(item["glob"])
    return missing


def run_project_checks(project: Path, command: str) -> list[Result]:
    """Run the pack command. Unparseable output is one FAIL. Ids stay the project's."""
    if not command or not str(command).strip():
        return []
    result = subprocess.run(
        command,
        shell=True,
        cwd=project,
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    parsed: list[Result] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = LINE.match(line)
        if not match:
            return [fail("project.checks", f"unparseable output: {line}")]
        parsed.append(Result(match.group(1), match.group(2), (match.group(3) or "").strip()))
    if result.returncode != 0 and not parsed:
        return [fail("project.checks", f"command exited {result.returncode}")]
    return parsed
