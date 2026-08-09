"""Deterministic, executable SolutionGraph construction and validation.

The graph is deliberately independent from controller state.  It turns a
TaskBlueprint, shadow routing result, and checked-in scenario pack into a
stable execution plan which can be projected to legacy lane definitions.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any

from control_plane.blueprint import validate_blueprint


GRAPH_VERSION = "1.0"
NODE_FIELDS = (
    "id", "title", "kind", "purpose", "dependsOn", "inputContracts",
    "outputContracts", "capabilityRequirements", "capabilityBindings", "unitIds",
    "sourceIds", "decisionIds", "acceptanceIds", "writeBoundary", "writeTargets",
    "workerRequired", "userApprovalRequired",
)
WRITE_BOUNDARIES = {"none", "approved-target", "review-only"}
VERIFIER_KINDS = {"verifier", "review"}


def _fail(message: str) -> None:
    raise ValueError(f"SolutionGraph: {message}")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} must be a non-empty string")
    return value.strip()


def _id(value: Any, label: str) -> str:
    if isinstance(value, str):
        return _nonempty(value, label)
    if isinstance(value, dict):
        return _nonempty(value.get("id"), f"{label}.id")
    _fail(f"{label} must be an ID string or object with id")


def _stable_list(values: list[Any]) -> list[Any]:
    """Canonicalize unordered contract/reference lists without altering ordered output."""
    return sorted((deepcopy(item) for item in values), key=_canonical)


def _id_list(values: Any, label: str) -> list[str]:
    if not isinstance(values, list):
        _fail(f"{label} must be an array")
    items = [_id(value, f"{label} item") for value in values]
    if len(set(items)) != len(items):
        _fail(f"{label} must contain unique IDs")
    return sorted(items)


def _selected_capabilities(routing_decision: Any) -> dict[str, set[str]]:
    if not isinstance(routing_decision, dict):
        _fail("routing_decision must be an object")
    selected = routing_decision.get("selected", [])
    if not isinstance(selected, list):
        _fail("routing_decision.selected must be an array")
    result: dict[str, set[str]] = {}
    for item in selected:
        if isinstance(item, str):
            capability_id, role = _nonempty(item, "routing selected item"), "worker"
        elif isinstance(item, dict):
            capability_id = _nonempty(item.get("id", item.get("capabilityId")), "routing selected item.id")
            role = item.get("role", "worker")
            if not isinstance(role, str) or not role.strip():
                _fail("routing selected item.role must be a non-empty string")
        else:
            _fail("routing_decision.selected items must be strings or objects")
        result.setdefault(capability_id, set()).add(role)
    return result


def _binding_id(binding: dict[str, Any]) -> str:
    return _nonempty(binding.get("capabilityId", binding.get("id")), "capability binding.capabilityId")


def _normalize_binding(value: Any) -> dict[str, str]:
    if isinstance(value, str):
        return {"capabilityId": _nonempty(value, "capability binding"), "role": "worker"}
    if not isinstance(value, dict):
        _fail("capabilityBindings items must be strings or objects")
    return {
        "capabilityId": _binding_id(value),
        "role": _nonempty(value.get("role", "worker"), "capability binding.role"),
    }


def _target_id(value: Any) -> str:
    return _id(value, "writeTargets item")


def _reachable(start: str, target: str, adjacency: dict[str, set[str]]) -> bool:
    pending = list(adjacency[start])
    seen: set[str] = set()
    while pending:
        item = pending.pop()
        if item == target:
            return True
        if item not in seen:
            seen.add(item)
            pending.extend(adjacency[item] - seen)
    return False


def _topological_order(node_ids: set[str], dependencies: dict[str, set[str]]) -> list[str]:
    remaining = {node_id: set(depends) for node_id, depends in dependencies.items()}
    order: list[str] = []
    ready = sorted(node_id for node_id in node_ids if not remaining[node_id])
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for candidate in sorted(node_ids - set(order)):
            if node_id in remaining[candidate]:
                remaining[candidate].remove(node_id)
                if not remaining[candidate] and candidate not in ready:
                    ready.append(candidate)
        ready.sort()
    if len(order) != len(node_ids):
        _fail("graph must be a DAG; cycle detected")
    return order


def _graph_digest_input(graph: dict[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in graph.items() if key != "graphDigest"}


def _blueprint_digest_input(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Normalize Blueprint collections that define sets rather than sequences."""
    result = deepcopy(blueprint)
    for field in ("sources", "intentAnchors", "decisions", "acceptanceCases", "domains", "artifactClasses", "requiredCapabilities"):
        if isinstance(result.get(field), list):
            result[field] = _stable_list(result[field])
    policy = result.get("changePolicy")
    if isinstance(policy, dict):
        for field in ("preserve", "allowed", "forbidden"):
            if isinstance(policy.get(field), list):
                policy[field] = _stable_list(policy[field])
    write_policy = result.get("writePolicy")
    if isinstance(write_policy, dict):
        for field in ("targets", "allowedActions"):
            if isinstance(write_policy.get(field), list):
                write_policy[field] = _stable_list(write_policy[field])
    return result


def _write_targets_from_blueprint(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    policy = blueprint.get("writePolicy")
    if isinstance(policy, dict) and isinstance(policy.get("targets"), list):
        return _stable_list(policy["targets"])
    return [{"id": blueprint["deliverable"]["target"]}]


def _explicitly_applies_to_node(case: dict[str, Any], node_id: str, title: str) -> bool:
    applies_to = case.get("appliesTo")
    if isinstance(applies_to, str):
        applies_to = [applies_to]
    return isinstance(applies_to, list) and any(
        isinstance(value, str) and value in {node_id, title} for value in applies_to
    )


def _acceptance_ids_for_node(
    template: dict[str, Any], blueprint: dict[str, Any], pack_case_ids: set[str], node_id: str, title: str, kind: str,
) -> list[str]:
    """Route only declared pack cases; conservatively retain custom cases.

    A template must never assume that a client Blueprint carries a pack's case
    IDs.  Pack-owned cases are therefore intersected with the Blueprint.  A
    user-defined business/semantic (or legacy untyped) case stays with review;
    a mechanical custom case must opt into a lane with appliesTo.
    """
    blueprint_cases = {
        _id(case, "acceptance"): case for case in blueprint["acceptanceCases"]
    }
    configured = _id_list(template.get("acceptanceIds", []), f"node {node_id}.acceptanceIds")
    selected = {case_id for case_id in configured if case_id in pack_case_ids and case_id in blueprint_cases}
    for case_id, case in blueprint_cases.items():
        if case_id in pack_case_ids:
            continue
        method = case.get("method")
        if kind in VERIFIER_KINDS and method in {None, "business", "semantic"}:
            selected.add(case_id)
        elif _explicitly_applies_to_node(case, node_id, title):
            selected.add(case_id)
    return sorted(selected)


def _template_node(
    template: dict[str, Any], blueprint: dict[str, Any], selected: dict[str, set[str]], pack_case_ids: set[str],
) -> dict[str, Any]:
    node_id = _nonempty(template.get("id"), "graphTemplate node.id")
    kind = _nonempty(template.get("kind", "work"), f"graphTemplate node {node_id}.kind")
    requirements = _id_list(template.get("capabilityRequirements", []), f"node {node_id}.capabilityRequirements")
    bindings: list[dict[str, str]] = []
    configured = template.get("capabilityBindings", [])
    if not isinstance(configured, list):
        _fail(f"node {node_id}.capabilityBindings must be an array")
    configured_by_id = {_binding_id(_normalize_binding(item)): _normalize_binding(item) for item in configured}
    for capability_id in requirements:
        binding = configured_by_id.get(capability_id, {"capabilityId": capability_id})
        role = binding.get("role", "verifier" if kind in VERIFIER_KINDS else "worker")
        if kind in VERIFIER_KINDS:
            role = "verifier"
        if capability_id in selected:
            bindings.append({"capabilityId": capability_id, "role": role})
    write_targets = template.get("writeTargets", [])
    if write_targets == "$approvedTargets":
        write_targets = _write_targets_from_blueprint(blueprint)
    if not isinstance(write_targets, list):
        _fail(f"node {node_id}.writeTargets must be an array or $approvedTargets")
    return {
        "id": node_id,
        "title": _nonempty(template.get("title", node_id.replace("-", " ").title()), f"node {node_id}.title"),
        "kind": kind,
        "purpose": _nonempty(template.get("purpose", f"Complete {node_id}"), f"node {node_id}.purpose"),
        "dependsOn": _id_list(template.get("dependsOn", []), f"node {node_id}.dependsOn"),
        "inputContracts": _stable_list(template.get("inputContracts", [])),
        "outputContracts": _stable_list(template.get("outputContracts", [])),
        "capabilityRequirements": requirements,
        "capabilityBindings": _stable_list(bindings),
        "unitIds": _id_list(template.get("unitIds", []), f"node {node_id}.unitIds"),
        "sourceIds": _id_list(template.get("sourceIds", [_id(item, "source") for item in blueprint["sources"]]), f"node {node_id}.sourceIds"),
        "decisionIds": _id_list(template.get("decisionIds", [_id(item, "decision") for item in blueprint["decisions"]]), f"node {node_id}.decisionIds"),
        "acceptanceIds": _acceptance_ids_for_node(template, blueprint, pack_case_ids, node_id, _nonempty(template.get("title", node_id.replace("-", " ").title()), f"node {node_id}.title"), kind),
        "writeBoundary": template.get("writeBoundary", "none"),
        "writeTargets": _stable_list(write_targets),
        "workerRequired": bool(template.get("workerRequired", kind not in {"user-approval", "approval"})),
        "userApprovalRequired": bool(template.get("userApprovalRequired", kind in {"user-approval", "approval"})),
    }


def build_solution_graph(blueprint: Any, routing_decision: Any, scenario_pack: Any) -> dict[str, Any]:
    """Build a deterministic SolutionGraph from validated upstream contracts."""
    bp = validate_blueprint(blueprint)
    if not isinstance(scenario_pack, dict):
        _fail("scenario_pack must be an object")
    pack_id = _nonempty(scenario_pack.get("id"), "scenario_pack.id")
    pack_version = _nonempty(scenario_pack.get("version"), "scenario_pack.version")
    fingerprint = scenario_pack.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        fingerprint = _digest({key: value for key, value in scenario_pack.items() if key != "fingerprint"})
    template = scenario_pack.get("graphTemplate")
    if not isinstance(template, dict) or not isinstance(template.get("nodes"), list) or not isinstance(template.get("edges"), list):
        _fail("scenario_pack.graphTemplate requires nodes and edges arrays")
    selected = _selected_capabilities(routing_decision)
    pack_cases = scenario_pack.get("acceptanceCases", [])
    if not isinstance(pack_cases, list):
        _fail("scenario_pack.acceptanceCases must be an array")
    pack_case_ids = {_id(case, "scenario_pack.acceptanceCases item") for case in pack_cases}
    nodes = [_template_node(node, bp, selected, pack_case_ids) for node in template["nodes"] if isinstance(node, dict)]
    if len(nodes) != len(template["nodes"]):
        _fail("scenario_pack.graphTemplate.nodes must contain objects")
    edge_pairs: set[tuple[str, str]] = set()
    for edge in template["edges"]:
        if not isinstance(edge, dict):
            _fail("scenario_pack.graphTemplate.edges must contain objects")
        edge_pairs.add((_nonempty(edge.get("from"), "graphTemplate edge.from"), _nonempty(edge.get("to"), "graphTemplate edge.to")))
    for node in nodes:
        edge_pairs.update((dependency, node["id"]) for dependency in node["dependsOn"])
    graph: dict[str, Any] = {
        "graphVersion": GRAPH_VERSION,
        "id": f"{bp['id']}:{pack_id}",
        "blueprintDigest": _digest(_blueprint_digest_input(bp)),
        "scenarioPack": {"id": pack_id, "version": pack_version, "fingerprint": fingerprint},
        "routingDigest": _digest(_routing_digest_input(routing_decision)),
        "nodes": sorted(nodes, key=lambda item: item["id"]),
        "edges": [{"from": source, "to": target} for source, target in sorted(edge_pairs)],
        "topologicalOrder": _topological_order(
            {node["id"] for node in nodes},
            {node["id"]: set(node["dependsOn"]) for node in nodes},
        ),
        "graphExecutable": True,
        "blockers": [],
        "graphDigest": "",
    }
    graph = validate_solution_graph(graph, routing_decision)
    graph["graphDigest"] = _digest(_graph_digest_input(graph))
    return graph


def _routing_digest_input(routing_decision: Any) -> Any:
    """Routing selection is a set; reorder it before assigning a digest."""
    value = deepcopy(routing_decision)
    if isinstance(value, dict):
        for field in ("selected", "missing", "fallback", "rejected", "reasons"):
            if isinstance(value.get(field), list):
                value[field] = _stable_list(value[field])
    return value


def validate_solution_graph(graph: Any, routing_decision: Any | None = None) -> dict[str, Any]:
    """Validate structural safety and return a normalized executable-status graph.

    Malformed graph shape, cycles, ambiguous target writes, and absent review
    ancestry are contract errors.  Missing route capabilities produce a valid but
    non-executable graph with explicit blockers.
    """
    if not isinstance(graph, dict):
        _fail("graph must be an object")
    result = deepcopy(graph)
    required = ("graphVersion", "id", "blueprintDigest", "scenarioPack", "routingDigest", "nodes", "edges", "topologicalOrder", "graphDigest")
    missing = [field for field in required if field not in result]
    if missing:
        _fail("missing required fields: " + ", ".join(missing))
    _nonempty(result["graphVersion"], "graphVersion")
    _nonempty(result["id"], "id")
    _nonempty(result["blueprintDigest"], "blueprintDigest")
    _nonempty(result["routingDigest"], "routingDigest")
    pack = result["scenarioPack"]
    if not isinstance(pack, dict):
        _fail("scenarioPack must be an object")
    for field in ("id", "version", "fingerprint"):
        _nonempty(pack.get(field), f"scenarioPack.{field}")
    if not isinstance(result["nodes"], list) or not isinstance(result["edges"], list):
        _fail("nodes and edges must be arrays")

    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    for raw in result["nodes"]:
        if not isinstance(raw, dict):
            _fail("nodes must contain objects")
        node = deepcopy(raw)
        node_id = _nonempty(node.get("id"), "node.id")
        if node_id in node_ids:
            _fail(f"node IDs must be unique: {node_id}")
        node_ids.add(node_id)
        missing_node = [field for field in NODE_FIELDS if field not in node]
        if missing_node:
            _fail(f"node {node_id} missing required fields: " + ", ".join(missing_node))
        for field in ("title", "kind", "purpose"):
            _nonempty(node[field], f"node {node_id}.{field}")
        for field in ("dependsOn", "unitIds", "sourceIds", "decisionIds", "acceptanceIds", "capabilityRequirements"):
            node[field] = _id_list(node[field], f"node {node_id}.{field}")
        for field in ("inputContracts", "outputContracts", "writeTargets"):
            if not isinstance(node[field], list):
                _fail(f"node {node_id}.{field} must be an array")
            node[field] = _stable_list(node[field])
        if not isinstance(node["capabilityBindings"], list):
            _fail(f"node {node_id}.capabilityBindings must be an array")
        node["capabilityBindings"] = _stable_list([_normalize_binding(item) for item in node["capabilityBindings"]])
        binding_ids = [_binding_id(item) for item in node["capabilityBindings"]]
        if len(set(binding_ids)) != len(binding_ids):
            _fail(f"node {node_id}.capabilityBindings must not bind a capability twice")
        if node["writeBoundary"] not in WRITE_BOUNDARIES:
            _fail(f"node {node_id}.writeBoundary is invalid")
        if not isinstance(node["workerRequired"], bool) or not isinstance(node["userApprovalRequired"], bool):
            _fail(f"node {node_id} workerRequired and userApprovalRequired must be booleans")
        if node["writeBoundary"] == "approved-target" and not node["writeTargets"]:
            _fail(f"approved-target node {node_id} requires writeTargets")
        if node["kind"] in VERIFIER_KINDS and not any(binding["role"] == "verifier" for binding in node["capabilityBindings"]):
            _fail(f"verifier node {node_id} requires a verifier role binding")
        nodes.append(node)

    dependencies = {node["id"]: set(node["dependsOn"]) for node in nodes}
    for node_id, depends in dependencies.items():
        missing_refs = sorted(depends - node_ids)
        if missing_refs:
            _fail(f"node {node_id} dependsOn missing nodes: {', '.join(missing_refs)}")
        if node_id in depends:
            _fail(f"node {node_id} cannot depend on itself")
    edge_pairs: set[tuple[str, str]] = set()
    for raw in result["edges"]:
        if not isinstance(raw, dict):
            _fail("edges must contain objects")
        pair = (_nonempty(raw.get("from"), "edge.from"), _nonempty(raw.get("to"), "edge.to"))
        if pair in edge_pairs:
            _fail(f"edges must be unique: {pair[0]} -> {pair[1]}")
        if pair[0] not in node_ids or pair[1] not in node_ids:
            _fail(f"edge references missing node: {pair[0]} -> {pair[1]}")
        edge_pairs.add(pair)
    implied_pairs = {(dependency, node_id) for node_id, depends in dependencies.items() for dependency in depends}
    if edge_pairs != implied_pairs:
        _fail("edges must exactly match node dependsOn relationships")
    order = _topological_order(node_ids, dependencies)
    if result["topologicalOrder"] != order:
        _fail("topologicalOrder must be the deterministic topological order")

    adjacency = {node_id: set() for node_id in node_ids}
    for source, target in edge_pairs:
        adjacency[source].add(target)
    writers = [node for node in nodes if node["writeBoundary"] == "approved-target"]
    for index, left in enumerate(writers):
        left_targets = {_target_id(item) for item in left["writeTargets"]}
        for right in writers[index + 1:]:
            if left_targets & {_target_id(item) for item in right["writeTargets"]} and not (
                _reachable(left["id"], right["id"], adjacency) or _reachable(right["id"], left["id"], adjacency)
            ):
                _fail(f"unordered approved-target writers share target(s): {left['id']}, {right['id']}")
    for node in nodes:
        if node["kind"] in VERIFIER_KINDS and writers and not any(_reachable(writer["id"], node["id"], adjacency) for writer in writers):
            _fail(f"review node {node['id']} must depend on an approved-target writer")

    selected = _selected_capabilities(routing_decision) if routing_decision is not None else None
    blockers: list[dict[str, str]] = []
    for node in nodes:
        bindings = {_binding_id(binding): binding for binding in node["capabilityBindings"]}
        for capability_id in node["capabilityRequirements"]:
            binding = bindings.get(capability_id)
            if binding is None:
                blockers.append({"nodeId": node["id"], "capabilityId": capability_id, "reason": "required capability is not bound"})
                continue
            if selected is not None and capability_id not in selected:
                blockers.append({"nodeId": node["id"], "capabilityId": capability_id, "reason": "required capability is not selected by routing"})
            if node["kind"] in VERIFIER_KINDS and binding["role"] != "verifier":
                blockers.append({"nodeId": node["id"], "capabilityId": capability_id, "reason": "verifier node is not bound with verifier role"})
    blockers.sort(key=_canonical)
    result["nodes"] = sorted(nodes, key=lambda item: item["id"])
    result["edges"] = [{"from": source, "to": target} for source, target in sorted(edge_pairs)]
    result["topologicalOrder"] = order
    result["blockers"] = blockers
    result["graphExecutable"] = not blockers
    if "graphDigest" in result and result["graphDigest"]:
        expected = _digest(_graph_digest_input(result))
        if result["graphDigest"] != expected:
            _fail("graphDigest does not match graph content")
    return result


def projection_to_lane_definitions(graph: Any) -> dict[str, Any]:
    """Project a graph to lane input without coupling graph metadata to state."""
    normalized = validate_solution_graph(graph)
    nodes = {node["id"]: node for node in normalized["nodes"]}
    lane_definitions: list[dict[str, Any]] = []
    mapping: list[dict[str, Any]] = []
    for node_id in normalized["topologicalOrder"]:
        node = nodes[node_id]
        lane_kind = "review" if node["kind"] in VERIFIER_KINDS else node["kind"]
        metadata = {
            "nodeId": node_id,
            "dependsOn": node["dependsOn"],
            "capabilityRequirements": node["capabilityRequirements"],
            "unitIds": node["unitIds"],
            "sourceIds": node["sourceIds"],
            "decisionIds": node["decisionIds"],
            "acceptanceIds": node["acceptanceIds"],
            "writeTargets": node["writeTargets"],
            "workerRequired": node["workerRequired"],
            "userApprovalRequired": node["userApprovalRequired"],
        }
        lane_definitions.append({
            "name": node_id,
            "kind": lane_kind,
            "writeBoundary": node["writeBoundary"],
            "notes": f"SolutionGraph node {node_id}; dependsOn={','.join(node['dependsOn']) or 'none'}",
            "metadata": metadata,
        })
        mapping.append({"nodeId": node_id, "laneName": node_id, **metadata})
    return {"laneDefinitions": lane_definitions, "mapping": mapping}
