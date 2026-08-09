"""TaskBlueprint v1 validation and deterministic contract-spec compilation.

This module intentionally uses only the Python standard library.  The JSON schema
is an interchange contract, while these checks remain the runtime authority.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any


INTERACTION_MODES = {"execute", "discuss_only", "plan_only"}
REQUIRED_FIELDS = (
    "blueprintVersion", "id", "taskType", "interactionMode", "outcome",
    "deliverable", "sources", "intentAnchors", "decisions", "changePolicy",
    "acceptanceCases", "approvals", "standards", "assumptions", "nonGoals",
    "capacity", "changeTriggers",
)
SEMANTIC_FIELDS = ("sources", "intentAnchors", "acceptanceCases")
BLUEPRINT_ONLY_FIELDS = ("standards", "assumptions", "nonGoals", "capacity", "changeTriggers")


def _fail(message: str) -> None:
    raise ValueError(f"TaskBlueprint: {message}")


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field} must be a non-empty string")
    return value.strip()


def _array(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{field} must be an array")
    return value


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{field} must be an object")
    return value


def _item_id(item: Any, field: str) -> str:
    return _nonempty(item if isinstance(item, str) else _object(item, field).get("id"), f"{field}.id")


def _required_marked(value: Any) -> bool:
    if isinstance(value, dict):
        return value.get("required") is True
    if isinstance(value, list):
        return any(isinstance(item, dict) and item.get("required") is True for item in value)
    return False


def validate_blueprint(blueprint: Any) -> dict[str, Any]:
    """Validate and return a deep-copied TaskBlueprint v1 document.

    The exception type is deliberately a plain ``ValueError`` so callers do not
    need a third-party schema validator to surface actionable validation errors.
    """
    raw = _object(blueprint, "blueprint")
    missing = [field for field in REQUIRED_FIELDS if field not in raw]
    if missing:
        _fail("missing required fields: " + ", ".join(missing))
    result = deepcopy(raw)
    _nonempty(result["blueprintVersion"], "blueprintVersion")
    _nonempty(result["id"], "id")
    _nonempty(result["taskType"], "taskType")
    if result["interactionMode"] not in INTERACTION_MODES:
        _fail("interactionMode must be execute, discuss_only, or plan_only")

    outcome = _object(result["outcome"], "outcome")
    _nonempty(outcome.get("businessGoal"), "outcome.businessGoal")
    _nonempty(outcome.get("supportedDecision"), "outcome.supportedDecision")

    deliverable = _object(result["deliverable"], "deliverable")
    for field in ("id", "kind", "target", "format", "useMode", "artifactClass"):
        _nonempty(deliverable.get(field), f"deliverable.{field}")
    audience = deliverable.get("audience")
    if not (isinstance(audience, str) and audience.strip()) and not (
        isinstance(audience, list) and audience and all(isinstance(x, str) and x.strip() for x in audience)
    ):
        _fail("deliverable.audience must be a non-empty string or array")
    if not isinstance(deliverable.get("standalone"), bool):
        _fail("deliverable.standalone must be a boolean")
    units = deliverable.get("units", [])
    _array(units, "deliverable.units")
    unit_ids = [_item_id(unit, "deliverable.units item") for unit in units]
    if len(set(unit_ids)) != len(unit_ids):
        _fail("deliverable.units IDs must be unique")
    if "deliveryPackage" in deliverable:
        _object(deliverable["deliveryPackage"], "deliverable.deliveryPackage")

    for field in SEMANTIC_FIELDS:
        _array(result[field], field)
    if not result["sources"]:
        _fail("sources must be non-empty")
    for item in result["sources"]:
        _item_id(item, "sources item")
    for item in result["intentAnchors"]:
        _item_id(item, "intentAnchors item")
    for item in result["acceptanceCases"]:
        entry = _object(item, "acceptanceCases item")
        _item_id(entry, "acceptanceCases item")
        if not any(isinstance(entry.get(key), str) and entry[key].strip() for key in ("description", "statement")):
            _fail("acceptanceCases item must include description or statement")

    decisions = _array(result["decisions"], "decisions")
    for decision in decisions:
        entry = _object(decision, "decisions item")
        _item_id(entry, "decisions item")
        _nonempty(entry.get("statement"), "decisions item.statement")
    policy = _object(result["changePolicy"], "changePolicy")
    for field in ("preserve", "allowed", "forbidden"):
        entries = _array(policy.get(field), f"changePolicy.{field}")
        for entry in entries:
            _item_id(entry, f"changePolicy.{field} item")
    approvals = _object(result["approvals"], "approvals")
    for field in ("sampleGate", "userApprovalGate"):
        if field in approvals and not isinstance(approvals[field], dict):
            _fail(f"approvals.{field} must be an object")
    sample_gate = approvals.get("sampleGate", {})
    if sample_gate.get("required") is True:
        _nonempty(sample_gate.get("lane"), "approvals.sampleGate.lane")
        if not isinstance(sample_gate.get("blocks"), list) or not sample_gate["blocks"]:
            _fail("approvals.sampleGate.blocks must be a non-empty array when required")
        if not isinstance(sample_gate.get("acceptanceIds"), list) or not sample_gate["acceptanceIds"]:
            _fail("approvals.sampleGate.acceptanceIds must be a non-empty array when required")
    user_gate = approvals.get("userApprovalGate", {})
    if user_gate.get("required") is True and (not isinstance(user_gate.get("blocks"), list) or not user_gate["blocks"]):
        _fail("approvals.userApprovalGate.blocks must be a non-empty array when required")
    if "writePolicy" in result and result["writePolicy"] is not None:
        write_policy = _object(result["writePolicy"], "writePolicy")
        targets = _array(write_policy.get("targets"), "writePolicy.targets")
        if not targets:
            _fail("writePolicy.targets must be non-empty")
        seen_targets: set[str] = set()
        for target in targets:
            target_entry = _object(target, "writePolicy.targets item")
            target_id = _nonempty(target_entry.get("id"), "writePolicy.targets item.id")
            _nonempty(target_entry.get("locator"), "writePolicy.targets item.locator")
            if target_id in seen_targets:
                _fail(f"writePolicy target IDs must be unique: {target_id}")
            seen_targets.add(target_id)
        actions = _array(write_policy.get("allowedActions"), "writePolicy.allowedActions")
        if not actions or not all(isinstance(action, str) and action.strip() for action in actions):
            _fail("writePolicy.allowedActions must be a non-empty string array")
        if not isinstance(write_policy.get("destructiveActionsRequireApproval"), bool):
            _fail("writePolicy.destructiveActionsRequireApproval must be a boolean")
    for field in BLUEPRINT_ONLY_FIELDS:
        value = result[field]
        if not isinstance(value, (dict, list, str, int, float, bool)) and value is not None:
            _fail(f"{field} must be JSON-compatible")

    # ContractSpec has a single global semantic ID namespace.
    all_ids = [deliverable["id"], *unit_ids]
    for field in ("sources", "intentAnchors", "acceptanceCases", "decisions"):
        all_ids.extend(_item_id(item, f"{field} item") for item in result[field])
    for field in ("preserve", "allowed", "forbidden"):
        all_ids.extend(_item_id(item, f"changePolicy.{field} item") for item in policy[field])
    if len(set(all_ids)) != len(all_ids):
        _fail("IDs must be globally unique across deliverable and semantic collections")
    return result


def _lanes(lane_definitions: Any) -> list[dict[str, Any]]:
    lanes = lane_definitions.get("lanes", []) if isinstance(lane_definitions, dict) else lane_definitions
    if not isinstance(lanes, list):
        _fail("lane_definitions must be an array or object with a lanes array")
    names: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for lane in lanes:
        item = _object(lane, "lane definition")
        name = _nonempty(item.get("name"), "lane definition.name")
        if name in names:
            _fail(f"lane definition names must be unique: {name}")
        names.add(name)
        normalized.append(deepcopy(item))
    return normalized


def _semantic_items(entries: list[Any]) -> list[dict[str, Any]]:
    return [{"id": item} if isinstance(item, str) else deepcopy(item) for item in entries]


def _decision_status(decision: dict[str, Any]) -> str:
    value = decision.get("status", decision.get("state", ""))
    if value in {"binding", "approved"} or decision.get("binding") is True:
        return "binding"
    if value == "superseded":
        return "superseded"
    return "advisory"


def _gate(raw: dict[str, Any] | None, kind: str, deliverable_id: str) -> dict[str, Any]:
    gate = deepcopy(raw or {})
    gate["required"] = bool(gate.get("required", False))
    if kind == "user" and gate["required"]:
        gate.setdefault("artifactId", deliverable_id)
    return gate


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def compile_blueprint(blueprint: Any, lane_definitions: Any) -> dict[str, Any]:
    """Compile a valid blueprint into a contractSpec 2.0 compatibility projection."""
    bp = validate_blueprint(blueprint)
    lanes = _lanes(lane_definitions)
    lane_names = {lane["name"] for lane in lanes}
    trace: dict[str, list[dict[str, Any]]] = {key: [] for key in ("mapped", "defaulted", "inferred", "unmapped", "conflicts")}

    def mapped(source: str, target: str) -> None:
        trace["mapped"].append({"source": source, "target": target, "mode": "direct"})

    deliverable = deepcopy(bp["deliverable"])
    if isinstance(deliverable["audience"], str):
        deliverable["audience"] = [deliverable["audience"]]
        trace["inferred"].append({"source": "deliverable.audience", "target": "deliverable.audience", "reason": "normalized scalar to array"})
    mapped("deliverable", "deliverable")
    for unit in deliverable.get("units", []):
        mapped(f"deliverable.units.{unit['id']}", "deliverable.units")

    policy = bp["changePolicy"]
    contract: dict[str, Any] = {
        "specVersion": "2.0",
        "interactionMode": bp["interactionMode"],
        "deliverable": deliverable,
        "canonicalSources": _semantic_items(bp["sources"]),
        "preserve": _semantic_items(policy["preserve"]),
        "allowedChanges": _semantic_items(policy["allowed"]),
        "forbidden": _semantic_items(policy["forbidden"]),
        "acceptance": _semantic_items(bp["acceptanceCases"]),
        "intentAnchors": _semantic_items(bp["intentAnchors"]),
        "decisionLedger": [],
        "sampleGate": _gate(bp["approvals"].get("sampleGate"), "sample", deliverable["id"]),
        "userApprovalGate": _gate(bp["approvals"].get("userApprovalGate"), "user", deliverable["id"]),
    }
    trace["defaulted"].append({"source": "specVersion", "target": "specVersion", "value": "2.0"})
    for source, target in (("sources", "canonicalSources"), ("changePolicy.preserve", "preserve"),
                           ("changePolicy.allowed", "allowedChanges"), ("changePolicy.forbidden", "forbidden"),
                           ("acceptanceCases", "acceptance"), ("intentAnchors", "intentAnchors")):
        mapped(source, target)
    for decision in bp["decisions"]:
        item = deepcopy(decision)
        item["status"] = _decision_status(item)
        contract["decisionLedger"].append(item)
        mapped(f"decisions.{item['id']}", "decisionLedger")
    mapped("approvals.sampleGate", "sampleGate")
    mapped("approvals.userApprovalGate", "userApprovalGate")
    if bp.get("writePolicy") is not None:
        contract["writePolicy"] = deepcopy(bp["writePolicy"])
        mapped("writePolicy", "writePolicy")

    for field in BLUEPRINT_ONLY_FIELDS:
        entry = {"source": field, "target": None, "reason": "no contractSpec 2.0 field"}
        trace["unmapped"].append(entry)
    approved_target = any(lane.get("writeBoundary") == "approved-target" for lane in lanes)
    client_facing = "client-facing" in bp["taskType"].lower() or "client_facing" in bp["taskType"].lower()
    high_risk = (bp["interactionMode"] == "execute" and approved_target) or client_facing
    required_unmapped = [item["source"] for item in trace["unmapped"] if _required_marked(bp[item["source"]])]
    if high_risk and not bp["intentAnchors"]:
        required_unmapped.append("intentAnchors")
        trace["conflicts"].append({"source": "intentAnchors", "reason": "high-risk blueprint requires intent anchors"})
    if high_risk and not bp["acceptanceCases"]:
        required_unmapped.append("acceptanceCases")
        trace["conflicts"].append({"source": "acceptanceCases", "reason": "high-risk blueprint requires acceptance cases"})
    if bp["interactionMode"] == "execute" and approved_target and "writePolicy" not in contract:
        required_unmapped.append("writePolicy")
        trace["conflicts"].append({"source": "writePolicy", "reason": "execute approved-target requires writePolicy"})
    for gate_name in ("sampleGate", "userApprovalGate"):
        gate = contract[gate_name]
        if gate.get("required"):
            for lane in gate.get("blocks", []):
                if lane not in lane_names:
                    required_unmapped.append(f"approvals.{gate_name}.blocks.{lane}")
                    trace["conflicts"].append({"source": f"approvals.{gate_name}", "reason": f"unknown lane: {lane}"})

    required_unmapped = sorted(set(required_unmapped))
    digest_input = {"blueprint": bp, "laneDefinitions": lanes, "contractSpec": contract}
    return {
        "blueprintDigest": _canonical_digest(digest_input),
        "contractSpec": contract,
        "traceability": trace,
        "requiredUnmapped": required_unmapped,
        "compiledExecutable": not required_unmapped,
    }
