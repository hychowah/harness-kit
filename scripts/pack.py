#!/usr/bin/env python3
"""A pack is a graph of work nodes.

The kit ships document and coding as data. A project adds project/packs/<id>/
with the same schema. Names in a pack are that pack's vocabulary, not kit law.
The same id in both places crashes.

schemas/pack.schema.json is the shape. This module crashes when that shape
misses, then applies the graph rules the schema does not express: priors name
real nodes, there are no cycles, worker ids are unique, an omitted worker
priors list copies the node's, and exactly one root is not closed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from checks import PREDICATES, validate

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def die(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _slug(value: object) -> bool:
    return isinstance(value, str) and bool(SLUG_RE.match(value))


def kit_pack_dir(kit_root: Path, pack_id: str) -> Path:
    return kit_root / "packs" / pack_id / "pack.json"


def project_pack_dir(project: Path, pack_id: str) -> Path:
    return project / "project" / "packs" / pack_id / "pack.json"


def crash_on_collisions(kit_root: Path, project: Path) -> None:
    root = project / "project" / "packs"
    if not root.is_dir():
        return
    for path in sorted(root.iterdir()):
        if (path / "pack.json").is_file() and kit_pack_dir(kit_root, path.name).is_file():
            die(f"Pack {path.name} exists in the kit and in the project.")


def load_pack(kit_root: Path, project: Path | None, pack_id: str) -> dict:
    if not _slug(pack_id):
        die(f"Unknown pack {pack_id}.")
    if project is not None:
        crash_on_collisions(kit_root, project)
    kit_path = kit_pack_dir(kit_root, pack_id)
    proj_path = project_pack_dir(project, pack_id) if project is not None else None
    path = proj_path if proj_path is not None and proj_path.is_file() else kit_path
    if not path.is_file():
        die(f"Unknown pack {pack_id}.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"Broken pack {pack_id}: {exc}")
    spec_path = kit_root / "schemas" / "pack.schema.json"
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        die(f"Broken pack schema: {exc}")
    errors = validate(raw, spec, f"pack {pack_id}")
    if errors:
        die(f"Broken pack {pack_id}: " + "; ".join(errors))
    if raw.get("id") != pack_id:
        die(f"Broken pack {pack_id}: id does not match the directory")
    return _normalize(raw)


def _evidence(item: dict, pack_id: str) -> dict:
    """Fill defaults. schema evidence names a schema file; the schema cannot say that."""
    if item.get("predicate") not in PREDICATES:
        die(f"Unknown predicate {item.get('predicate')}.")
    if item["predicate"] == "schema" and not isinstance(item.get("schema"), str):
        die(f"Broken pack {pack_id}: schema evidence needs a schema path")
    cleaned = dict(item)
    cleaned["root"] = item.get("root", "session")
    cleaned["min"] = item.get("min", 1)
    cleaned["optional"] = item.get("optional", False)
    return cleaned


def _worker(item: dict, node_priors: list) -> dict:
    """A missing priors key copies the node's priors. An explicit list stays as written."""
    return {
        "id": item["id"],
        "specialist": item["specialist"],
        "exclusive": item["exclusive"],
        "priors": list(node_priors) if "priors" not in item else list(item["priors"]),
        "reads": list(item.get("reads", [])),
        "forbidden": list(item.get("forbidden", [])),
        "owns": list(item.get("owns", [])),
    }


def _normalize(raw: dict) -> dict:
    pack_id = raw.get("id")
    nodes = raw["nodes"]
    cleaned_nodes = []
    seen: set[str] = set()
    for node in nodes:
        if node["id"] in seen:
            die(f"Broken pack {pack_id}: node ids must be unique slugs")
        seen.add(node["id"])
        workers = [_worker(item, list(node["priors"])) for item in node["workers"]]
        cleaned_nodes.append(
            {
                "id": node["id"],
                "priors": list(node["priors"]),
                "entry": [_evidence(item, str(pack_id)) for item in node["entry"]],
                "complete": [_evidence(item, str(pack_id)) for item in node["complete"]],
                "workers": workers,
            }
        )
    known = {node["id"] for node in cleaned_nodes}
    if "closed" not in known:
        die(f"Broken pack {pack_id}: missing the closed node")
    worker_ids: set[str] = set()
    for node in cleaned_nodes:
        for prior in node["priors"]:
            if prior not in known:
                die(f"Broken pack {pack_id}: prior {prior} is not a node")
        for worker in node["workers"]:
            if worker["id"] in worker_ids:
                die(f"Broken pack {pack_id}: worker {worker['id']} is repeated")
            worker_ids.add(worker["id"])
            for prior in worker["priors"]:
                if prior not in known:
                    die(f"Broken pack {pack_id}: worker prior {prior} is not a node")
    _reject_cycles(str(pack_id), cleaned_nodes)
    roots = [node["id"] for node in cleaned_nodes if not node["priors"] and node["id"] != "closed"]
    if len(roots) != 1:
        die(f"Broken pack {pack_id}: need exactly one root other than closed")
    return {
        "id": pack_id,
        "uses_features": raw["uses_features"],
        "architecture_on_close": raw["architecture_on_close"],
        "checks": raw.get("checks"),
        "nodes": cleaned_nodes,
    }


def _reject_cycles(pack_id: str, nodes: list[dict]) -> None:
    by_id = {node["id"]: node for node in nodes}
    state: dict[str, str] = {}

    def visit(node_id: str) -> None:
        mark = state.get(node_id)
        if mark == "done":
            return
        if mark == "open":
            die(f"Broken pack {pack_id}: cycle at {node_id}")
        state[node_id] = "open"
        for prior in by_id[node_id]["priors"]:
            visit(prior)
        state[node_id] = "done"

    for node in nodes:
        visit(node["id"])


def find_node(pack: dict, node_id: str) -> dict:
    for node in pack["nodes"]:
        if node["id"] == node_id:
            return node
    die(f"Unknown node {node_id} in pack {pack['id']}.")


def find_worker(pack: dict, role: str) -> dict:
    for node in pack["nodes"]:
        for worker in node["workers"]:
            if worker["id"] == role:
                return worker
    die(f"Unknown worker {role} in pack {pack['id']}.")


def single_path(pack: dict) -> bool:
    """True when path_order names every node. phase --to is defined only then."""
    return len(path_order(pack)) == len(pack["nodes"])


def start_node(pack: dict) -> str:
    """The one root that is not closed. Load rejects every other shape."""
    for node in pack["nodes"]:
        if not node["priors"] and node["id"] != "closed":
            return node["id"]
    die("Broken pack: no root")


def unsatisfied_priors(priors: list[str], states: dict[str, str | None]) -> list[str]:
    """Priors the checklist does not mark complete or skipped.

    status, spawn, and check use this. Enter uses priors_for_enter.
    """
    return [prior for prior in priors if states.get(prior) not in {"complete", "skipped"}]


def priors_for_enter(
    priors: list[str],
    states: dict[str, str | None],
    current: str | None,
) -> list[str]:
    """Checklist priors, treating current as satisfied.

    The caller passes current only when that phase's complete evidence passes now.
    """
    blocked = unsatisfied_priors(priors, states)
    if current is None:
        return blocked
    return [prior for prior in blocked if prior != current]


def path_order(pack: dict) -> list[str]:
    """Start-to-closed order of a single-path pack. Empty when the graph forks."""
    by_id = {node["id"]: node for node in pack["nodes"]}
    roots = [node["id"] for node in pack["nodes"] if not node["priors"]]
    if len(roots) != 1:
        return []
    order: list[str] = []
    current: str | None = roots[0]
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        order.append(current)
        children = [node["id"] for node in pack["nodes"] if node["priors"] == [current]]
        if len(children) > 1:
            return []
        current = children[0] if children else None
    if len(order) != len(by_id):
        return []
    return order
