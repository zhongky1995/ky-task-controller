"""Deterministic WorkerPacket projection from Blueprint, ContractSpec, and SolutionGraph.

Packets are the execution contract handed to workers.  Rendered prompts are a
convenience view of a packet and intentionally are never read back as input.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any

from control_plane.blueprint import validate_blueprint
from control_plane.solution_graph import VERIFIER_KINDS, validate_solution_graph


PACKET_VERSION = "1.0"
_PACKET_FIELDS = (
    "packetVersion", "packetId", "packetDigest", "blueprintDigest",
    "contractSpecDigest", "graphDigest", "nodeId", "laneName", "title",
    "purpose", "taskType", "interactionMode", "capabilityBindings",
    "dependsOn", "inputArtifacts", "outputContract", "unitSpecs",
    "sourceSpecs", "decisionSpecs", "standards", "constraints",
    "acceptanceCases", "writePolicySlice", "userApprovalRequired",
    "callbackContract",
)


def _fail(message: str) -> None:
    raise ValueError(f"WorkerPacket: {message}")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _stable_list(values: list[Any]) -> list[Any]:
    return sorted((deepcopy(value) for value in values), key=_canonical)


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


def _id_set(values: Any, label: str) -> set[str]:
    if not isinstance(values, list):
        _fail(f"{label} must be an array")
    result = {_id(value, f"{label} item") for value in values}
    if len(result) != len(values):
        _fail(f"{label} must contain unique IDs")
    return result


def _semantic_items(entries: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        _fail(f"{label} must be an array")
    result: list[dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, str):
            result.append({"id": _nonempty(entry, f"{label} item")})
        elif isinstance(entry, dict):
            item = deepcopy(entry)
            _nonempty(item.get("id"), f"{label} item.id")
            result.append(item)
        else:
            _fail(f"{label} items must be strings or objects")
    return result


def _applies_to(item: dict[str, Any], node: dict[str, Any], unit_ids: set[str]) -> bool:
    """Apply explicit scope; missing ``appliesTo`` means the item is global."""
    scope = item.get("appliesTo")
    if scope is None:
        return True
    if isinstance(scope, str):
        scope = [scope]
    if not isinstance(scope, list) or not all(isinstance(value, str) and value.strip() for value in scope):
        _fail(f"{item['id']}.appliesTo must be a string or string array")
    scopes = set(scope)
    return bool(scopes & ({node["id"], node["title"], *unit_ids}))


def _slice_items(entries: Any, selected_ids: set[str], node: dict[str, Any], unit_ids: set[str], label: str) -> list[dict[str, Any]]:
    items = _semantic_items(entries, label)
    known = {item["id"] for item in items}
    unknown = sorted(selected_ids - known)
    if unknown:
        _fail(f"node {node['id']} references unknown {label}: {', '.join(unknown)}")
    return _stable_list([item for item in items if item["id"] in selected_ids and _applies_to(item, node, unit_ids)])


def _binding_decision(item: dict[str, Any]) -> bool:
    return item.get("status") in {"binding", "approved"} or item.get("binding") is True


def _packet_digest_input(packet: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(packet)
    result.pop("packetDigest", None)
    callback = result.get("callbackContract")
    if isinstance(callback, dict):
        callback.pop("packetDigest", None)
    return result


def _output_contract(node: dict[str, Any]) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    for raw in node["outputContracts"]:
        if isinstance(raw, str):
            item: dict[str, Any] = {"id": _nonempty(raw, "outputContracts item")}
        elif isinstance(raw, dict):
            item = deepcopy(raw)
            _nonempty(item.get("id"), "outputContracts item.id")
        else:
            _fail("outputContracts items must be strings or objects")
        schema = item.pop("schema", item.pop("outputSchema", None))
        if schema is None:
            schema = {"type": "artifact", "artifactId": item["id"]}
        if not isinstance(schema, dict) or not schema:
            _fail(f"output contract {item['id']} schema must be a non-empty object")
        artifacts.append({**item, "schema": schema})
    return {
        "artifacts": _stable_list(artifacts),
        "schema": {"type": "object", "required": ["artifacts"], "properties": {"artifacts": {"type": "array"}}},
    }


def _write_policy_slice(blueprint: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    boundary = node["writeBoundary"]
    if boundary != "approved-target":
        return {"writeBoundary": boundary, "targets": [], "allowedActions": []}
    policy = blueprint.get("writePolicy")
    if not isinstance(policy, dict):
        _fail(f"approved-target node {node['id']} requires blueprint.writePolicy")
    targets = policy.get("targets")
    actions = policy.get("allowedActions")
    if not isinstance(targets, list) or not isinstance(actions, list) or not actions:
        _fail(f"approved-target node {node['id']} requires exact writePolicy targets and allowedActions")
    policy_by_id = {_id(target, "writePolicy.targets item"): deepcopy(target) for target in targets}
    graph_target_ids = {_id(target, "node.writeTargets item") for target in node["writeTargets"]}
    if not graph_target_ids:
        _fail(f"approved-target node {node['id']} requires write targets")
    missing = sorted(graph_target_ids - set(policy_by_id))
    if missing:
        _fail(f"node {node['id']} write targets are not approved: {', '.join(missing)}")
    return {
        "writeBoundary": boundary,
        "targets": _stable_list([policy_by_id[target_id] for target_id in graph_target_ids]),
        "allowedActions": sorted({_nonempty(action, "writePolicy.allowedActions item") for action in actions}),
        "destructiveActionsRequireApproval": bool(policy.get("destructiveActionsRequireApproval", False)),
    }


def _contract_spec(compile_result: Any) -> dict[str, Any]:
    if not isinstance(compile_result, dict):
        _fail("compile_result must be an object")
    contract = compile_result.get("contractSpec")
    if not isinstance(contract, dict):
        _fail("compile_result.contractSpec must be an object")
    return deepcopy(contract)


def _packet_for_node(blueprint: dict[str, Any], contract: dict[str, Any], graph: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    unit_specs = _semantic_items(contract.get("deliverable", {}).get("units", []), "deliverable.units")
    units_by_id = {item["id"]: item for item in unit_specs}
    unit_ids = _id_set(node["unitIds"], f"node {node['id']}.unitIds")
    missing_units = sorted(unit_ids - set(units_by_id))
    if missing_units:
        _fail(f"node {node['id']} references unknown units: {', '.join(missing_units)}")
    selected_units = _stable_list([units_by_id[unit_id] for unit_id in unit_ids if _applies_to(units_by_id[unit_id], node, unit_ids)])

    source_specs = _slice_items(contract.get("canonicalSources", []), _id_set(node["sourceIds"], f"node {node['id']}.sourceIds"), node, unit_ids, "sources")
    decisions = _slice_items(contract.get("decisionLedger", []), _id_set(node["decisionIds"], f"node {node['id']}.decisionIds"), node, unit_ids, "decisions")
    # Binding decisions and required sources with no scope are global constraints.
    source_specs = _stable_list(source_specs + [
        item for item in _semantic_items(contract.get("canonicalSources", []), "sources")
        if item.get("required") is True and item.get("appliesTo") is None and item not in source_specs
    ])
    decisions = _stable_list(decisions + [
        item for item in _semantic_items(contract.get("decisionLedger", []), "decisions")
        if _binding_decision(item) and item.get("appliesTo") is None and item not in decisions
    ])
    acceptance_ids = _id_set(node["acceptanceIds"], f"node {node['id']}.acceptanceIds")
    acceptance = _slice_items(contract.get("acceptance", []), acceptance_ids, node, unit_ids, "acceptance")
    if node["kind"] in VERIFIER_KINDS:
        # A scoped business/semantic case remains a final-review obligation even
        # when the review node has no matching deliverable unit of its own.
        acceptance = _stable_list(acceptance + [
            item for item in _semantic_items(contract.get("acceptance", []), "acceptance")
            if item["id"] in acceptance_ids
            and item.get("method") in {None, "business", "semantic"}
            and item not in acceptance
        ])
    if node["kind"] in VERIFIER_KINDS:
        acceptance = _stable_list([{**item, "verification": "business"} for item in acceptance])

    output_contract = _output_contract(node)
    packet: dict[str, Any] = {
        "packetVersion": PACKET_VERSION,
        "packetId": f"{graph['id']}:{node['id']}",
        "packetDigest": "",
        "blueprintDigest": graph["blueprintDigest"],
        "contractSpecDigest": _digest(contract),
        "graphDigest": graph["graphDigest"],
        "nodeId": node["id"],
        "laneName": node["id"],
        "title": node["title"],
        "purpose": node["purpose"],
        "taskType": blueprint["taskType"],
        "interactionMode": blueprint["interactionMode"],
        "capabilityBindings": _stable_list(node["capabilityBindings"]),
        "dependsOn": sorted(_id_set(node["dependsOn"], f"node {node['id']}.dependsOn")),
        "inputArtifacts": _stable_list(node["inputContracts"]),
        "outputContract": output_contract,
        "unitSpecs": selected_units,
        "sourceSpecs": source_specs,
        "decisionSpecs": decisions,
        "standards": deepcopy(blueprint["standards"]),
        "constraints": {
            "preserve": _stable_list(_semantic_items(contract.get("preserve", []), "preserve")),
            "allowedChanges": _stable_list(_semantic_items(contract.get("allowedChanges", []), "allowedChanges")),
            "forbidden": _stable_list(_semantic_items(contract.get("forbidden", []), "forbidden")),
            "nonGoals": deepcopy(blueprint["nonGoals"]),
            "assumptions": deepcopy(blueprint["assumptions"]),
            "capacity": deepcopy(blueprint["capacity"]),
        },
        "acceptanceCases": acceptance,
        "writePolicySlice": _write_policy_slice(blueprint, node),
        "userApprovalRequired": node["userApprovalRequired"],
        "callbackContract": {
            "packetDigest": "",
            "graphDigest": graph["graphDigest"],
            "blueprintDigest": graph["blueprintDigest"],
            "outputArtifactContract": deepcopy(output_contract),
        },
    }
    packet["packetDigest"] = _digest(_packet_digest_input(packet))
    packet["callbackContract"]["packetDigest"] = packet["packetDigest"]
    return validate_worker_packet(packet, blueprint, contract, graph)


def compile_worker_packets(blueprint: Any, compile_result: Any, graph: Any, routing_decision: Any) -> list[dict[str, Any]]:
    """Compile one validated WorkerPacket for every node in topological order."""
    bp = validate_blueprint(blueprint)
    contract = _contract_spec(compile_result)
    normalized_graph = validate_solution_graph(graph, routing_decision)
    if not normalized_graph["graphExecutable"]:
        _fail("graph is not executable; capability bindings are incomplete")
    if normalized_graph["blueprintDigest"] != _digest(_blueprint_digest_input(bp)):
        _fail("graph.blueprintDigest does not match blueprint")
    nodes = {node["id"]: node for node in normalized_graph["nodes"]}
    return [_packet_for_node(bp, contract, normalized_graph, nodes[node_id]) for node_id in normalized_graph["topologicalOrder"]]


def _blueprint_digest_input(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Keep the packet lineage digest identical to SolutionGraph's definition."""
    result = deepcopy(blueprint)
    for field in ("sources", "intentAnchors", "decisions", "acceptanceCases", "domains", "artifactClasses", "requiredCapabilities"):
        if isinstance(result.get(field), list):
            result[field] = _stable_list(result[field])
    policy = result.get("changePolicy")
    if isinstance(policy, dict):
        for field in ("preserve", "allowed", "forbidden"):
            if isinstance(policy.get(field), list):
                policy[field] = _stable_list(policy[field])
    policy = result.get("writePolicy")
    if isinstance(policy, dict):
        for field in ("targets", "allowedActions"):
            if isinstance(policy.get(field), list):
                policy[field] = _stable_list(policy[field])
    return result


def validate_worker_packet(packet: Any, blueprint: Any | None = None, contract_spec: Any | None = None, graph: Any | None = None) -> dict[str, Any]:
    """Validate a packet and, when lineage is supplied, its graph/blueprint references."""
    if not isinstance(packet, dict):
        _fail("packet must be an object")
    result = deepcopy(packet)
    missing = [field for field in _PACKET_FIELDS if field not in result]
    if missing:
        _fail("missing required fields: " + ", ".join(missing))
    if result["packetVersion"] != PACKET_VERSION:
        _fail(f"packetVersion must be {PACKET_VERSION}")
    for field in ("packetId", "packetDigest", "blueprintDigest", "contractSpecDigest", "graphDigest", "nodeId", "laneName", "title", "purpose", "taskType", "interactionMode"):
        _nonempty(result[field], field)
    if result["laneName"] != result["nodeId"]:
        _fail("laneName must equal nodeId")
    if result["packetDigest"] != _digest(_packet_digest_input(result)):
        _fail("packetDigest does not match packet content")
    if not isinstance(result["capabilityBindings"], list):
        _fail("capabilityBindings must be an array")
    result["capabilityBindings"] = _stable_list(result["capabilityBindings"])
    if not isinstance(result["dependsOn"], list) or result["dependsOn"] != sorted(set(result["dependsOn"])):
        _fail("dependsOn must be a sorted unique string array")
    if not isinstance(result["inputArtifacts"], list):
        _fail("inputArtifacts must be an array")
    for field in ("unitSpecs", "sourceSpecs", "decisionSpecs", "acceptanceCases"):
        _semantic_items(result[field], field)
    if not isinstance(result["outputContract"], dict) or not isinstance(result["outputContract"].get("schema"), dict) or not result["outputContract"]["schema"]:
        _fail("outputContract.schema must be a non-empty object")
    if not isinstance(result["outputContract"].get("artifacts"), list):
        _fail("outputContract.artifacts must be an array")
    if not isinstance(result["standards"], (list, dict, str, int, float, bool)) and result["standards"] is not None:
        _fail("standards must be JSON-compatible")
    constraints = result["constraints"]
    if not isinstance(constraints, dict) or set(constraints) != {"preserve", "allowedChanges", "forbidden", "nonGoals", "assumptions", "capacity"}:
        _fail("constraints must contain preserve, allowedChanges, forbidden, nonGoals, assumptions, capacity")
    policy = result["writePolicySlice"]
    if not isinstance(policy, dict) or policy.get("writeBoundary") not in {"none", "approved-target", "review-only"}:
        _fail("writePolicySlice has an invalid writeBoundary")
    if not isinstance(policy.get("targets"), list) or not isinstance(policy.get("allowedActions"), list):
        _fail("writePolicySlice targets and allowedActions must be arrays")
    if policy["writeBoundary"] == "approved-target":
        if not policy["targets"] or not policy["allowedActions"]:
            _fail("approved-target packet requires exact write targets and actions")
    elif policy["targets"] or policy["allowedActions"]:
        _fail("read-only packet must not carry write permissions")
    if not isinstance(result["userApprovalRequired"], bool):
        _fail("userApprovalRequired must be a boolean")
    callback = result["callbackContract"]
    if not isinstance(callback, dict):
        _fail("callbackContract must be an object")
    for field in ("packetDigest", "graphDigest", "blueprintDigest", "outputArtifactContract"):
        if field not in callback:
            _fail(f"callbackContract missing {field}")
    if callback["packetDigest"] != result["packetDigest"] or callback["graphDigest"] != result["graphDigest"] or callback["blueprintDigest"] != result["blueprintDigest"]:
        _fail("callbackContract lineage digests must match the packet")
    if callback["outputArtifactContract"] != result["outputContract"]:
        _fail("callbackContract output artifact contract must match outputContract")

    if graph is not None:
        normalized_graph = validate_solution_graph(graph)
        if result["graphDigest"] != normalized_graph["graphDigest"]:
            _fail("graphDigest does not match graph")
        nodes = {node["id"]: node for node in normalized_graph["nodes"]}
        node = nodes.get(result["nodeId"])
        if node is None:
            _fail("nodeId does not exist in graph")
        if result["dependsOn"] != node["dependsOn"]:
            _fail("dependsOn does not match graph node")
        if _stable_list(result["capabilityBindings"]) != _stable_list(node["capabilityBindings"]):
            _fail("capabilityBindings do not match graph node")
        requirements = {_id(value, "capabilityRequirements item") for value in node["capabilityRequirements"]}
        bindings = {_nonempty(item.get("capabilityId"), "capabilityBindings item.capabilityId") for item in result["capabilityBindings"] if isinstance(item, dict)}
        if not requirements <= bindings:
            _fail("packet is missing required graph capability bindings")
        if policy["writeBoundary"] != node["writeBoundary"]:
            _fail("writePolicySlice boundary does not match graph node")
        if node["writeBoundary"] != "approved-target" and (policy["targets"] or policy["allowedActions"]):
            _fail("read-only graph node carries write permissions")
        if node["kind"] in VERIFIER_KINDS and not result["acceptanceCases"]:
            _fail("review packet requires explicit acceptance coverage")

    if blueprint is not None:
        bp = validate_blueprint(blueprint)
        if result["blueprintDigest"] != _digest(_blueprint_digest_input(bp)):
            _fail("blueprintDigest does not match blueprint")
        reference_sets = {
            "unitSpecs": {_id(item, "deliverable.units item") for item in bp["deliverable"].get("units", [])},
            "sourceSpecs": {_id(item, "sources item") for item in bp["sources"]},
            "decisionSpecs": {_id(item, "decisions item") for item in bp["decisions"]},
            "acceptanceCases": {_id(item, "acceptanceCases item") for item in bp["acceptanceCases"]},
        }
        for field, known_ids in reference_sets.items():
            actual = {_id(item, f"{field} item") for item in result[field]}
            if not actual <= known_ids:
                _fail(f"{field} references an unknown blueprint item")
        if graph is not None:
            node = next(node for node in normalized_graph["nodes"] if node["id"] == result["nodeId"])
            unit_ids = _id_set(node["unitIds"], f"node {node['id']}.unitIds")
            expected_units = {
                item["id"] for item in _semantic_items(bp["deliverable"].get("units", []), "deliverable.units")
                if item["id"] in unit_ids and _applies_to(item, node, unit_ids)
            }
            if {_id(item, "unitSpecs item") for item in result["unitSpecs"]} != expected_units:
                _fail("unitSpecs do not match graph node references")
            expected_sources = {
                item["id"] for item in _slice_items(bp["sources"], _id_set(node["sourceIds"], f"node {node['id']}.sourceIds"), node, unit_ids, "sources")
            }
            expected_sources |= {
                item["id"] for item in _semantic_items(bp["sources"], "sources")
                if item.get("required") is True and item.get("appliesTo") is None
            }
            if {_id(item, "sourceSpecs item") for item in result["sourceSpecs"]} != expected_sources:
                _fail("sourceSpecs do not match graph node references")
            expected_decisions = {
                item["id"] for item in _slice_items(bp["decisions"], _id_set(node["decisionIds"], f"node {node['id']}.decisionIds"), node, unit_ids, "decisions")
            }
            expected_decisions |= {
                item["id"] for item in _semantic_items(bp["decisions"], "decisions")
                if _binding_decision(item) and item.get("appliesTo") is None
            }
            if {_id(item, "decisionSpecs item") for item in result["decisionSpecs"]} != expected_decisions:
                _fail("decisionSpecs do not match graph node references")
            acceptance_ids = _id_set(node["acceptanceIds"], f"node {node['id']}.acceptanceIds")
            expected_acceptance = {
                item["id"] for item in _slice_items(bp["acceptanceCases"], acceptance_ids, node, unit_ids, "acceptance")
            }
            if node["kind"] in VERIFIER_KINDS:
                expected_acceptance |= {
                    item["id"] for item in _semantic_items(bp["acceptanceCases"], "acceptance")
                    if item["id"] in acceptance_ids and item.get("method") in {None, "business", "semantic"}
                }
            if {_id(item, "acceptanceCases item") for item in result["acceptanceCases"]} != expected_acceptance:
                _fail("acceptanceCases do not match graph node references")
            if node["writeBoundary"] == "approved-target":
                approved = _write_policy_slice(bp, node)
                if policy != approved:
                    _fail("writePolicySlice does not match approved graph targets and actions")
    if contract_spec is not None and result["contractSpecDigest"] != _digest(contract_spec):
        _fail("contractSpecDigest does not match contractSpec")
    return result


def render_worker_prompt(packet: Any) -> str:
    """Render readable worker instructions from a validated WorkerPacket only."""
    value = validate_worker_packet(packet)
    lines = [
        f"Worker packet: {value['packetId']}",
        f"Packet digest: {value['packetDigest']}",
        f"Node: {value['nodeId']} ({value['title']})",
        f"Purpose: {value['purpose']}",
        f"Task type: {value['taskType']}; interaction mode: {value['interactionMode']}",
        "Dependencies: " + (", ".join(value["dependsOn"]) or "none"),
        "Capabilities: " + (", ".join(binding["capabilityId"] for binding in value["capabilityBindings"]) or "none"),
        "Output contract: " + _canonical(value["outputContract"]),
        "Callback must return packetDigest=" + value["callbackContract"]["packetDigest"],
    ]
    if value["writePolicySlice"]["writeBoundary"] == "approved-target":
        lines.append("Approved write targets: " + ", ".join(_id(target, "write target") for target in value["writePolicySlice"]["targets"]))
    else:
        lines.append("Write access: read-only")
    return "\n".join(lines)
