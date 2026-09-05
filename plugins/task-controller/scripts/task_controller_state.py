#!/usr/bin/env python3
"""Local schema-v2 state helper for KY-TASK controller checkpoints."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# The helper is invoked by MCP from arbitrary working directories. Keep imports
# anchored to this checked-in plugin root rather than the caller's cwd.
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from control_plane.blueprint import compile_blueprint, validate_blueprint
from control_plane.capability_router import shadow_route
from control_plane.decision_governance import (
    AUTHORITIES,
    apply_scenario_policy,
    classify_feedback,
    derive_decision_governance,
)
from control_plane.orchestration import (
    CONTRIBUTION_ROLES,
    HANDOFF_MODES,
    HANDOFF_RISKS,
    ORCHESTRATION_POLICIES,
    SEMANTIC_AUTHORITIES,
    VERIFY_SCOPES,
    compile_orchestration_plan,
    declared_orchestration_fields,
)
from control_plane.solution_graph import build_solution_graph, projection_to_lane_definitions, validate_solution_graph
from control_plane.worker_packet import compile_worker_packets, render_worker_prompt, validate_worker_packet
from registry.loader import load_registry
from operation_adapters import LarkCliAdapter, MemoryTestAdapter
from runtime.dispatch_admission import (
    AdmissionError,
    active_workers,
    capacity,
    lane_attempts,
    registration_claim,
    require_admission,
    release_dispatch,
    reserve_dispatch,
    reserved_claims,
)
from runtime.operation_dispatcher import (
    Dispatcher,
    PermitError,
    claim_permit,
    issue_permit,
    reconcile_claimed_permit,
    revoke_permit,
    validate_permit,
)
from runtime.worker_runtime import (
    RUNTIME_REGISTRY,
    approved_runtime_ids,
    profile_satisfies,
    requirement_for_lane,
    select_runtime,
)
from verification.acceptance import (
    ATTESTATION_STRENGTH,
    aggregate_verification,
    validate_acceptance_case,
    validate_verification_result,
)


SCHEMA_VERSION = 2
DEFAULT_LANES = ["evidence", "object-model", "product-experience", "implementation", "review"]
TRUE_WORKER_RUNTIMES = RUNTIME_REGISTRY.independent_runtime_ids()
LANE_RUNTIMES = TRUE_WORKER_RUNTIMES | {"single_thread_section", "thread_create_unavailable"}
SPLIT_REQUIREMENTS = {"mandatory", "recommended", "none"}
EXECUTION_MODES = {"distributed", "multi_session", "sequential_lanes", "direct"}
LEGACY_DISTRIBUTED_MODE = "multi_session"
WORKER_LIFECYCLES = {"ephemeral", "persistent"}
CONTEXT_POLICIES = {"packet_only", "checkpoint_delta"}
RUNTIME_PREFERENCES = {"auto"} | TRUE_WORKER_RUNTIMES
RUNTIME_SELECTION_POLICIES = {"lane_lifecycle", "native_session_required"}
PROJECT_AFFINITY_POLICIES = {"inherit_or_resolve_required", "allow_projectless"}
PROJECT_RESOLUTION_SOURCES = {
    "controller_project",
    "workspace_path_match",
    "material_path_match",
    "user_selected",
}
PROJECT_ENVIRONMENTS = {"local", "worktree"}
DEFAULT_ORCHESTRATION_POLICY = "strict"
DEFAULT_MAX_PARALLEL_WORKERS = 4
MAX_PARALLEL_WORKERS = 10
MAX_WAIT_TARGETS_PER_CALL = 8
ENFORCEMENT_MODES = {"workflow_only", "semantic_strict"}
INTERACTION_MODES = {"discuss_only", "plan_only", "execute"}
WRITE_BOUNDARIES = {"read-only", "draft-file", "approved-target", "review-only"}
DECISION_REVIEW_KINDS = {"decision-review"}
ACTIVE_WORKER_STATUSES = {"pending", "running", "done", "needs-work", "blocked"}
PASS_CALLBACK_MODES = {
    "active_message_required": {"active_message"},
    "active_message_preferred": {"active_message", "controller_poll_recovery"},
    "controller_poll_allowed": {"active_message", "controller_poll_recovery"},
    "managed_result_collected": {"managed_result_collected"},
}
SEMANTIC_COLLECTIONS = ("canonicalSources", "preserve", "allowedChanges", "forbidden", "acceptance")
CORRECTION_STATUSES = {"open", "consumed"}
DECISION_STATUSES = {"binding", "advisory", "superseded"}
ARTIFACT_ROLES = {"entrypoint", "appendix", "source"}
DESTRUCTIVE_ACTIONS = {"delete", "drop", "remove", "replace", "truncate", "overwrite", "purge"}
MUTATING_COMMANDS = {
    "init",
    "complete-lane",
    "insert-lane",
    "add-note",
    "register-worker",
    "claim-dispatch",
    "release-dispatch",
    "update-worker",
    "ingest-feedback",
    "record-correction",
    "record-approval",
    "record-callback",
    "issue-operation-permit",
    "dispatch-operation",
    "reconcile-operation",
    "revoke-operation-permit",
    "record-verification-result",
    "revise-contract",
    "finalize",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fail(message: str) -> None:
    raise SystemExit(message)


def require_nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{name} must be a non-empty string.")
    return value.strip()


def parse_csv(value: str | None) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in (value or "").split(",") if item.strip()))


def normalize_string_list(value: Any, name: str, *, allow_empty: bool = False) -> list[str]:
    if isinstance(value, str):
        values = [require_nonempty(value, name)]
    elif isinstance(value, list):
        values = [require_nonempty(item, f"{name} item") for item in value]
    else:
        fail(f"{name} must be a non-empty string or array of non-empty strings.")
    values = list(dict.fromkeys(values))
    if not values and not allow_empty:
        fail(f"{name} must not be empty.")
    return values


def load_json_value(value: str) -> Any:
    raw = require_nonempty(value, "JSON value")
    if raw.startswith("@"):
        raw = Path(raw[1:]).expanduser().read_text(encoding="utf-8")
    return json.loads(raw)


def canonical_json(value: Any) -> str:
    """Return the UTF-8 JSON representation used by all semantic hashes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def interaction_mode(state: dict[str, Any]) -> str:
    spec = state.get("contractSpec")
    if not isinstance(spec, dict):
        return "execute"
    mode = spec.get("interactionMode", "execute")
    return mode if mode in INTERACTION_MODES else "execute"


def business_contract_v2(value: dict[str, Any]) -> bool:
    spec = value.get("contractSpec") if "contractSpec" in value else value
    if not isinstance(spec, dict):
        return False
    version = spec.get("specVersion")
    if isinstance(version, int):
        return version >= 2
    if isinstance(version, str):
        try:
            return int(version.strip().split(".", 1)[0]) >= 2
        except ValueError:
            return False
    return False


def effective_enforcement_mode(state: dict[str, Any]) -> str:
    mode = state.get("enforcementMode")
    if mode is None and state.get("schemaVersion", 1) == SCHEMA_VERSION:
        return "workflow_only"
    if mode not in ENFORCEMENT_MODES:
        fail(f"Unsupported enforcementMode in state: {mode}")
    return mode


def has_semantic_risk(state: dict[str, Any], lanes: list[dict[str, Any]] | None = None) -> bool:
    active_lanes = state.get("lanes", []) if lanes is None else lanes
    policy = state.get("executionPolicy", {})
    if not isinstance(policy, dict):
        policy = {}
    return any(lane.get("writeBoundary") == "approved-target" for lane in active_lanes) or bool(
        policy.get("independentReviewRequired", False)
    )


def require_continuation_state(state: dict[str, Any]) -> None:
    require_v2(state)
    if state.get("enforcementMode") is None and has_semantic_risk(state):
        fail(
            "semantic_migration_required: legacy schemaVersion 2 risk state has no enforcementMode; "
            "upgrade or migrate it before any mutation, worker registration, gate, completion, or revision."
        )


def require_risk_enforcement(
    state: dict[str, Any],
    lanes: list[dict[str, Any]] | None = None,
    *,
    additional_risk: bool = False,
) -> None:
    if not (has_semantic_risk(state, lanes) or additional_risk) or is_semantic_strict(state):
        return
    reason = state.get("semanticDowngradeReason", "")
    if not isinstance(reason, str) or not reason.strip():
        fail(
            "semantic_upgrade_required: risk lanes require semantic_strict, or workflow_only with a "
            "non-empty semanticDowngradeReason."
        )


def is_semantic_strict(state: dict[str, Any]) -> bool:
    return effective_enforcement_mode(state) == "semantic_strict"


def normalize_semantic_item(item: Any, collection: str) -> dict[str, Any]:
    if isinstance(item, str):
        normalized = {"id": require_nonempty(item, f"{collection} id")}
    elif isinstance(item, dict):
        normalized = dict(item)
        normalized["id"] = require_nonempty(normalized.get("id"), f"{collection} item id")
    else:
        fail(f"Each {collection} item must be a string id or object.")
    if collection == "canonicalSources":
        normalized["required"] = bool(normalized.get("required", True))
        if "priority" in normalized:
            priority = normalized["priority"]
            if isinstance(priority, bool) or not isinstance(priority, int):
                fail("canonicalSources priority must be an integer.")
        if "role" in normalized:
            normalized["role"] = require_nonempty(normalized.get("role"), "canonicalSources role")
        if "appliesTo" in normalized:
            normalized["appliesTo"] = normalize_string_list(
                normalized.get("appliesTo"), "canonicalSources appliesTo"
            )
    return normalized


def item_lane_names(item: dict[str, Any]) -> list[str]:
    names: list[str] = []
    if "lane" in item:
        names.append(require_nonempty(item.get("lane"), "lane reference"))
    if "lanes" in item:
        raw = item.get("lanes")
        if not isinstance(raw, list):
            fail("lanes reference must be an array.")
        names.extend(require_nonempty(name, "lane reference") for name in raw)
    return list(dict.fromkeys(names))


def validate_contract_spec(raw: Any, lanes: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        fail("semantic_strict requires contractSpec to be an object.")
    spec = dict(raw)
    spec_version = spec.get("specVersion")
    if not ((isinstance(spec_version, str) and spec_version.strip()) or (isinstance(spec_version, int) and spec_version > 0)):
        fail("contractSpec.specVersion must be a non-empty string or positive integer.")
    next_business_contract = business_contract_v2(spec)
    interaction = spec.get("interactionMode", "execute" if not next_business_contract else None)
    if interaction not in INTERACTION_MODES:
        fail(
            "contractSpec.interactionMode is required in semantic_strict and must be one of: "
            + ", ".join(sorted(INTERACTION_MODES))
        )
    spec["interactionMode"] = interaction
    deliverable = spec.get("deliverable")
    if not isinstance(deliverable, dict):
        fail("contractSpec.deliverable must be an object.")
    deliverable = dict(deliverable)
    for field in ("id", "kind", "target", "format"):
        deliverable[field] = require_nonempty(deliverable.get(field), f"contractSpec.deliverable.{field}")
    if next_business_contract:
        deliverable["audience"] = normalize_string_list(
            deliverable.get("audience"), "contractSpec.deliverable.audience"
        )
        deliverable["useMode"] = require_nonempty(
            deliverable.get("useMode"), "contractSpec.deliverable.useMode"
        )
        if not isinstance(deliverable.get("standalone"), bool):
            fail("contractSpec.deliverable.standalone must be a boolean.")
        deliverable["artifactClass"] = require_nonempty(
            deliverable.get("artifactClass"), "contractSpec.deliverable.artifactClass"
        )
    raw_units = deliverable.get("units", [])
    if not isinstance(raw_units, list):
        fail("contractSpec.deliverable.units must be an array when provided.")
    units: list[dict[str, Any]] = []
    unit_ids: set[str] = set()
    for raw_unit in raw_units:
        if not isinstance(raw_unit, dict):
            fail("Each contractSpec.deliverable.units item must be an object.")
        unit = dict(raw_unit)
        unit["id"] = require_nonempty(unit.get("id"), "contractSpec.deliverable.units item id")
        if unit["id"] in unit_ids:
            fail(f"contractSpec.deliverable.units IDs must be unique: {unit['id']}")
        unit_ids.add(unit["id"])
        units.append(unit)
    deliverable["units"] = units
    raw_package = deliverable.get("deliveryPackage")
    if raw_package is not None:
        if not isinstance(raw_package, dict):
            fail("contractSpec.deliverable.deliveryPackage must be an object when provided.")
        delivery_package = dict(raw_package)
        if "entrypoint" in delivery_package:
            delivery_package["entrypoint"] = require_nonempty(
                delivery_package.get("entrypoint"), "contractSpec.deliverable.deliveryPackage.entrypoint"
            )
        if "selfContained" in delivery_package and not isinstance(delivery_package.get("selfContained"), bool):
            fail("contractSpec.deliverable.deliveryPackage.selfContained must be a boolean.")
        delivery_package["selfContained"] = bool(delivery_package.get("selfContained", False))
        if "maxRequiredOpens" in delivery_package:
            max_opens = delivery_package.get("maxRequiredOpens")
            if isinstance(max_opens, bool) or not isinstance(max_opens, int) or max_opens < 1:
                fail("contractSpec.deliverable.deliveryPackage.maxRequiredOpens must be a positive integer.")
        deliverable["deliveryPackage"] = delivery_package
    lane_names = {lane["name"] for lane in lanes}
    for lane_name in item_lane_names(deliverable):
        if lane_name not in lane_names:
            fail(f"contractSpec deliverable references missing lane: {lane_name}")
    spec["deliverable"] = deliverable
    computed_fingerprint = sha256_json(deliverable)
    supplied_fingerprint = spec.get("deliverableFingerprint", "")
    if supplied_fingerprint and supplied_fingerprint != computed_fingerprint:
        fail("contractSpec.deliverableFingerprint does not match the canonical deliverable SHA256.")
    spec["deliverableFingerprint"] = computed_fingerprint

    seen_ids = {deliverable["id"]}
    seen_ids.update(unit_ids)
    for collection in SEMANTIC_COLLECTIONS:
        raw_items = spec.get(collection)
        if not isinstance(raw_items, list):
            fail(f"contractSpec.{collection} must be an array.")
        if collection == "canonicalSources" and not raw_items:
            fail("contractSpec.canonicalSources must be non-empty.")
        items = [normalize_semantic_item(item, collection) for item in raw_items]
        for item in items:
            item_id = item["id"]
            if item_id in seen_ids:
                fail(f"contractSpec IDs must be globally unique: {item_id}")
            seen_ids.add(item_id)
            for lane_name in item_lane_names(item):
                if lane_name not in lane_names:
                    fail(f"contractSpec {collection} references missing lane: {lane_name}")
        spec[collection] = items

    raw_anchors = spec.get("intentAnchors", [])
    if not isinstance(raw_anchors, list):
        fail("contractSpec.intentAnchors must be an array when provided.")
    intent_anchors = [normalize_semantic_item(item, "intentAnchors") for item in raw_anchors]
    for item in intent_anchors:
        if item["id"] in seen_ids:
            fail(f"contractSpec IDs must be globally unique: {item['id']}")
        seen_ids.add(item["id"])
        for lane_name in item_lane_names(item):
            if lane_name not in lane_names:
                fail(f"contractSpec intentAnchors references missing lane: {lane_name}")
    spec["intentAnchors"] = intent_anchors

    raw_ledger = spec.get("decisionLedger", [])
    if not isinstance(raw_ledger, list):
        fail("contractSpec.decisionLedger must be an array when provided.")
    decision_ledger: list[dict[str, Any]] = []
    for raw_decision in raw_ledger:
        if not isinstance(raw_decision, dict):
            fail("Each contractSpec.decisionLedger item must be an object.")
        decision = dict(raw_decision)
        decision["id"] = require_nonempty(decision.get("id"), "contractSpec.decisionLedger item id")
        decision["statement"] = require_nonempty(
            decision.get("statement"), "contractSpec.decisionLedger statement"
        )
        status = require_nonempty(decision.get("status"), "contractSpec.decisionLedger status")
        if status not in DECISION_STATUSES:
            fail("contractSpec.decisionLedger status must be binding, advisory, or superseded.")
        decision["status"] = status
        if decision["id"] in seen_ids:
            fail(f"contractSpec IDs must be globally unique: {decision['id']}")
        seen_ids.add(decision["id"])
        for lane_name in item_lane_names(decision):
            if lane_name not in lane_names:
                fail(f"contractSpec decisionLedger references missing lane: {lane_name}")
        decision_ledger.append(decision)
    spec["decisionLedger"] = decision_ledger

    derived_governance = derive_decision_governance(
        {
            "taskType": str(spec.get("taskType", "")),
            "deliverable": deliverable,
            "domains": spec.get("domains", []),
            "changePolicy": {
                "preserve": spec["preserve"],
                "allowed": spec["allowedChanges"],
                "forbidden": spec["forbidden"],
            },
            "approvals": {"userApprovalGate": spec.get("userApprovalGate", {})},
        },
        lanes,
    )
    raw_governance = spec.get("decisionGovernance", derived_governance)
    if not isinstance(raw_governance, dict):
        fail("contractSpec.decisionGovernance must be an object when provided.")
    decision_governance = dict(raw_governance)
    decision_governance["policyVersion"] = require_nonempty(
        decision_governance.get("policyVersion"), "contractSpec.decisionGovernance.policyVersion"
    )
    if decision_governance.get("riskLevel") not in {"low", "high"}:
        fail("contractSpec.decisionGovernance.riskLevel must be low or high.")
    if not isinstance(decision_governance.get("confirmationRequired"), bool):
        fail("contractSpec.decisionGovernance.confirmationRequired must be a boolean.")
    raw_items = decision_governance.get("items")
    if not isinstance(raw_items, list):
        fail("contractSpec.decisionGovernance.items must be an array.")
    governance_items: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            fail("contractSpec.decisionGovernance items must be objects.")
        item = dict(raw_item)
        item["id"] = require_nonempty(item.get("id"), "contractSpec.decisionGovernance item id")
        item["category"] = require_nonempty(
            item.get("category"), "contractSpec.decisionGovernance item category"
        )
        item["authority"] = require_nonempty(
            item.get("authority"), "contractSpec.decisionGovernance item authority"
        )
        if item["authority"] not in AUTHORITIES:
            fail("contractSpec.decisionGovernance item authority is invalid.")
        item["source"] = require_nonempty(
            item.get("source"), "contractSpec.decisionGovernance item source"
        )
        governance_items.append(item)
    if len({item["id"] for item in governance_items}) != len(governance_items):
        fail("contractSpec.decisionGovernance item IDs must be unique.")
    governed_by_id = {item["id"]: item for item in governance_items}
    derived_by_id = {item["id"]: item for item in derived_governance["items"]}
    if set(governed_by_id) != set(derived_by_id):
        fail("contractSpec.decisionGovernance items must cover every change-policy item exactly once.")
    for item_id, derived_item in derived_by_id.items():
        actual = governed_by_id[item_id]
        if derived_item["authority"] in {"locked", "propose_then_confirm"} and actual["authority"] != derived_item["authority"]:
            fail(
                "contractSpec.decisionGovernance cannot weaken derived authority for item: "
                + item_id
            )
    confirmation_ids = sorted(
        item["id"] for item in governance_items if item["authority"] == "propose_then_confirm"
    )
    declared_confirmation_ids = decision_governance.get("confirmationItemIds", confirmation_ids)
    if not isinstance(declared_confirmation_ids, list) or sorted(declared_confirmation_ids) != confirmation_ids:
        fail("contractSpec.decisionGovernance.confirmationItemIds must match propose_then_confirm items.")
    if decision_governance["confirmationRequired"] != bool(confirmation_ids):
        fail("contractSpec.decisionGovernance.confirmationRequired does not match its authority items.")
    decision_governance["items"] = governance_items
    decision_governance["confirmationItemIds"] = confirmation_ids
    decision_governance["triggers"] = normalize_string_list(
        decision_governance.get("triggers", []),
        "contractSpec.decisionGovernance.triggers",
        allow_empty=True,
    )
    spec["decisionGovernance"] = decision_governance

    raw_write_policy = spec.get("writePolicy")
    approved_target_lanes = [lane for lane in lanes if lane.get("writeBoundary") == "approved-target"]
    if raw_write_policy is not None:
        if not isinstance(raw_write_policy, dict):
            fail("contractSpec.writePolicy must be an object when provided.")
        write_policy = dict(raw_write_policy)
        raw_targets = write_policy.get("targets")
        if not isinstance(raw_targets, list) or not raw_targets:
            fail("contractSpec.writePolicy.targets must be a non-empty array.")
        targets: list[dict[str, Any]] = []
        target_ids: set[str] = set()
        for raw_target in raw_targets:
            if not isinstance(raw_target, dict):
                fail("Each contractSpec.writePolicy.targets item must be an object.")
            target = dict(raw_target)
            target["id"] = require_nonempty(target.get("id"), "contractSpec.writePolicy target id")
            target["locator"] = require_nonempty(
                target.get("locator"), "contractSpec.writePolicy target locator"
            )
            if target["id"] in target_ids:
                fail(f"contractSpec.writePolicy target IDs must be unique: {target['id']}")
            target_ids.add(target["id"])
            if "environment" in target:
                target["environment"] = require_nonempty(
                    target.get("environment"), "contractSpec.writePolicy target environment"
                )
            targets.append(target)
        write_policy["targets"] = targets
        write_policy["allowedActions"] = normalize_string_list(
            write_policy.get("allowedActions"), "contractSpec.writePolicy.allowedActions"
        )
        if not isinstance(write_policy.get("destructiveActionsRequireApproval"), bool):
            fail("contractSpec.writePolicy.destructiveActionsRequireApproval must be a boolean.")
        spec["writePolicy"] = write_policy
    if next_business_contract and interaction == "execute" and approved_target_lanes:
        if not isinstance(spec.get("writePolicy"), dict):
            fail("execute + approved-target requires contractSpec.writePolicy.")
        targets = spec["writePolicy"]["targets"]
        if not any(
            deliverable["target"] in {target["id"], target["locator"]} for target in targets
        ):
            fail("execute approved-target deliverable.target must match a writePolicy target id or locator.")

    sample_gate = spec.get("sampleGate", {"required": False})
    if not isinstance(sample_gate, dict):
        fail("contractSpec.sampleGate must be an object when provided.")
    sample_gate = dict(sample_gate)
    sample_gate["required"] = bool(sample_gate.get("required", False))
    if sample_gate["required"]:
        sample_lane = require_nonempty(sample_gate.get("lane"), "contractSpec.sampleGate.lane")
        if sample_lane not in lane_names:
            fail(f"contractSpec.sampleGate references missing lane: {sample_lane}")
        blocks = sample_gate.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            fail("required sampleGate.blocks must be a non-empty array.")
        blocks = list(dict.fromkeys(require_nonempty(name, "sampleGate block lane") for name in blocks))
        missing_blocks = [name for name in blocks if name not in lane_names]
        if missing_blocks:
            fail(f"contractSpec.sampleGate blocks missing lanes: {', '.join(missing_blocks)}")
        if sample_lane in blocks:
            fail("contractSpec.sampleGate cannot block its own sample lane.")
        acceptance_ids = sample_gate.get("acceptanceIds")
        if not isinstance(acceptance_ids, list) or not acceptance_ids:
            fail("required sampleGate.acceptanceIds must be a non-empty array.")
        acceptance_ids = list(
            dict.fromkeys(require_nonempty(item, "sampleGate acceptance id") for item in acceptance_ids)
        )
        known_acceptance = {item["id"] for item in spec["acceptance"]}
        unknown = sorted(set(acceptance_ids) - known_acceptance)
        if unknown:
            fail(f"contractSpec.sampleGate references unknown acceptance IDs: {', '.join(unknown)}")
        sample_gate.update({"lane": sample_lane, "blocks": blocks, "acceptanceIds": acceptance_ids})
    spec["sampleGate"] = sample_gate
    user_gate = spec.get("userApprovalGate", {"required": False})
    if not isinstance(user_gate, dict):
        fail("contractSpec.userApprovalGate must be an object when provided.")
    user_gate = dict(user_gate)
    user_gate["required"] = bool(user_gate.get("required", False))
    if user_gate["required"]:
        blocks = user_gate.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            fail("required userApprovalGate.blocks must be a non-empty array.")
        blocks = list(dict.fromkeys(require_nonempty(name, "userApprovalGate block lane") for name in blocks))
        missing_blocks = sorted(set(blocks) - lane_names)
        if missing_blocks:
            fail(f"contractSpec.userApprovalGate blocks missing lanes: {', '.join(missing_blocks)}")
        artifact_id = require_nonempty(
            user_gate.get("artifactId"), "contractSpec.userApprovalGate.artifactId"
        )
        user_gate.update({"blocks": blocks, "artifactId": artifact_id})
    spec["userApprovalGate"] = user_gate
    return spec


def require_decision_confirmation_gate(contract_spec: dict[str, Any]) -> None:
    governance = contract_spec.get("decisionGovernance", {})
    gate = contract_spec.get("userApprovalGate", {})
    if (
        contract_spec.get("interactionMode") == "execute"
        and isinstance(governance, dict)
        and governance.get("confirmationRequired") is True
        and not (isinstance(gate, dict) and gate.get("required") is True)
    ):
        fail(
            "decision_confirmation_gate_required: propose_then_confirm commercial decisions "
            "require a fingerprint-bound userApprovalGate before execution."
        )


def compute_contract_digest(contract_spec: dict[str, Any], revision: int) -> str:
    return sha256_json({"contractRevision": revision, "contractSpec": contract_spec})


def compile_task_blueprint(raw_blueprint: Any, lane_definitions: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile a validated blueprint and normalize its schema-v2 projection."""
    blueprint = validate_blueprint(raw_blueprint)
    compiled = compile_blueprint(blueprint, lane_definitions)
    compiled["contractSpec"] = validate_contract_spec(compiled["contractSpec"], lane_definitions)
    return blueprint, compiled


def require_executable_blueprint(
    compiled: dict[str, Any],
    *,
    enforcement_mode: str,
    risky: bool,
) -> None:
    if (
        enforcement_mode == "semantic_strict"
        and risky
        and compiled["contractSpec"].get("interactionMode") == "execute"
        and not compiled["compiledExecutable"]
    ):
        details = ", ".join(compiled.get("requiredUnmapped", [])) or "unknown compiler blocker"
        fail(
            "semantic_strict risk execution requires a compiledExecutable TaskBlueprint; "
            f"requiredUnmapped: {details}"
        )


def require_matching_contract_spec(
    supplied: dict[str, Any],
    compiled: dict[str, Any],
) -> None:
    if canonical_json(supplied) != canonical_json(compiled["contractSpec"]):
        fail(
            "contractSpec does not semantically match the TaskBlueprint compiled contractSpec. "
            "TaskBlueprint is canonical for blueprint-based state."
        )


def compile_blueprint_command(args: argparse.Namespace) -> None:
    lane_definitions = load_json_value(args.lane_definitions)
    if not isinstance(lane_definitions, list):
        fail("laneDefinitions must be a JSON array.")
    _, compiled = compile_task_blueprint(load_json_value(args.task_blueprint), lane_definitions)
    print(json.dumps(compiled, ensure_ascii=False, indent=2))


def route_capabilities(args: argparse.Namespace) -> None:
    blueprint = validate_blueprint(load_json_value(args.task_blueprint))
    active_ids = parse_csv(args.active_capability_ids)
    runtime_availability = load_json_value(args.runtime_availability)
    if not isinstance(runtime_availability, dict):
        fail("runtime availability must be a JSON object.")
    if not all(isinstance(value, bool) for value in runtime_availability.values()):
        fail("runtime availability values must be booleans.")
    route = shadow_route(
        blueprint,
        active_capability_ids=active_ids if args.active_capability_ids.strip() else None,
        runtime_availability=runtime_availability,
    )
    print(json.dumps(route, ensure_ascii=False, indent=2))


def available_capability_catalog(value: str) -> list[dict[str, Any]]:
    raw = load_json_value(value) if value else []
    if not isinstance(raw, list) or any(
        not isinstance(item, (str, dict)) for item in raw
    ):
        fail("availableCapabilities must be a JSON array of IDs or capability objects.")
    result: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            if not item.strip():
                fail("availableCapabilities IDs must be non-empty strings.")
            result.append({"id": item.strip()})
            continue
        capability_id = item.get("id", item.get("capabilityId"))
        if not isinstance(capability_id, str) or not capability_id.strip():
            fail("availableCapabilities objects require a non-empty id.")
        result.append(item)
    return result


def plan_orchestration_command(args: argparse.Namespace) -> None:
    lanes = load_json_value(args.lane_definitions)
    runtime_availability = load_json_value(args.runtime_availability)
    if not isinstance(runtime_availability, dict) or not all(
        isinstance(value, bool) for value in runtime_availability.values()
    ):
        fail("runtime availability must be a JSON object with boolean values.")
    try:
        plan = compile_orchestration_plan(
            lanes,
            policy=args.orchestration_policy,
            active_capability_ids=parse_csv(args.active_capability_ids) or None,
            runtime_availability=runtime_availability,
            available_capabilities=available_capability_catalog(args.available_capabilities),
        )
    except ValueError as error:
        fail(str(error))
    print(json.dumps(plan, ensure_ascii=False, indent=2))


def controller_lane_projection(projection: dict[str, Any]) -> dict[str, Any]:
    """Translate SolutionGraph's read-only ``none`` boundary for state lanes."""
    result = json.loads(json.dumps(projection))
    for lane in result.get("laneDefinitions", []):
        if lane.get("writeBoundary") == "none":
            lane["writeBoundary"] = "read-only"
    return result


def packet_index(packets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {packet["nodeId"]: packet for packet in packets}


def plan_blueprint_data(
    raw_blueprint: Any,
    *,
    runtime_availability: dict[str, Any] | None = None,
    active_capability_ids: list[str] | None = None,
    available_capabilities: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    """Build a read-only graph plan and return its internal compiler projection."""
    blueprint = validate_blueprint(raw_blueprint)
    routing = shadow_route(
        blueprint,
        active_capability_ids=active_capability_ids,
        runtime_availability=runtime_availability,
    )
    blockers: list[dict[str, Any]] = []
    for item in routing.get("missing", []):
        blockers.append({"stage": "routing", **item})
    solution_graph: dict[str, Any] | None = None
    lane_projection: dict[str, Any] = {"laneDefinitions": [], "mapping": []}
    packets: list[dict[str, Any]] = []
    orchestration_plan: dict[str, Any] | None = None
    compiled: dict[str, Any] | None = None
    policy_applications: list[dict[str, Any]] = []
    scenario = routing.get("scenarioPack")
    if not isinstance(scenario, dict) or not scenario.get("id"):
        blockers.append({"stage": "routing", "reason": "No scenario pack matched the TaskBlueprint."})
    else:
        pack = load_registry().scenario_load(
            scenario["id"],
            scenario.get("version") or None,
            task_blueprint_version=blueprint.get("blueprintVersion"),
        ).data
        try:
            blueprint, policy_applications = apply_scenario_policy(blueprint, pack)
            blueprint = validate_blueprint(blueprint)
        except ValueError as error:
            blockers.append({"stage": "policy", "reason": str(error)})
        try:
            solution_graph = build_solution_graph(blueprint, routing, pack)
        except ValueError:
            # A missing verifier can make the constructor reject an unbound
            # verifier node before it can report the normal non-executable plan.
            # Build the formal shape from the unrestricted shadow route, then
            # validate it against the requested availability to retain blockers.
            complete_route = shadow_route(blueprint)
            solution_graph = build_solution_graph(blueprint, complete_route, pack)
            route_digest_input = json.loads(json.dumps(routing))
            for field in ("selected", "missing", "fallback", "rejected", "reasons"):
                if isinstance(route_digest_input.get(field), list):
                    route_digest_input[field] = sorted(route_digest_input[field], key=canonical_json)
            solution_graph["routingDigest"] = sha256_json(route_digest_input)
            solution_graph["graphDigest"] = ""
            solution_graph = validate_solution_graph(solution_graph, routing)
            solution_graph["graphDigest"] = sha256_json(
                {key: value for key, value in solution_graph.items() if key != "graphDigest"}
            )
        graph_for_projection = solution_graph
        if not solution_graph.get("graphExecutable"):
            graph_for_projection = json.loads(json.dumps(solution_graph))
            graph_for_projection["blockers"] = []
            graph_for_projection["graphExecutable"] = True
            graph_for_projection["graphDigest"] = ""
        lane_projection = controller_lane_projection(projection_to_lane_definitions(graph_for_projection))
        orchestration_plan = compile_orchestration_plan(
            lane_projection["laneDefinitions"],
            policy="strict",
            trusted=True,
            active_capability_ids=active_capability_ids,
            runtime_availability=runtime_availability,
            available_capabilities=available_capabilities,
        )
        for blocker in orchestration_plan.get("blockers", []):
            blockers.append({"stage": "orchestration", **blocker})
        _, compiled = compile_task_blueprint(blueprint, lane_projection["laneDefinitions"])
        for required in compiled.get("requiredUnmapped", []):
            blockers.append({"stage": "compile", "id": required, "reason": "required blueprint content is unmapped"})
        for blocker in solution_graph.get("blockers", []):
            blockers.append({"stage": "graph", **blocker})
        if solution_graph.get("graphExecutable") and compiled.get("compiledExecutable"):
            packets = compile_worker_packets(blueprint, compiled, solution_graph, routing)
    plan_executable = bool(
        solution_graph
        and solution_graph.get("graphExecutable")
        and compiled
        and compiled.get("compiledExecutable")
        and orchestration_plan
        and orchestration_plan.get("orchestrationExecutable")
        and not blockers
    )
    plan = {
        "routingDecision": routing,
        "solutionGraph": solution_graph,
        "laneProjection": lane_projection,
        "orchestrationPlan": orchestration_plan,
        "workerPackets": packets,
        "policyApplications": policy_applications,
        "planDigest": "",
        "planExecutable": plan_executable,
        "blockers": blockers,
    }
    plan["planDigest"] = sha256_json({key: value for key, value in plan.items() if key != "planDigest"})
    return plan, blueprint, compiled


def plan_blueprint_command(args: argparse.Namespace) -> None:
    runtime_availability = load_json_value(args.runtime_availability)
    if not isinstance(runtime_availability, dict) or not all(
        isinstance(value, bool) for value in runtime_availability.values()
    ):
        fail("runtime availability must be a JSON object with boolean values.")
    plan, _, _ = plan_blueprint_data(
        load_json_value(args.task_blueprint),
        runtime_availability=runtime_availability,
        active_capability_ids=parse_csv(args.active_capability_ids) or None,
        available_capabilities=available_capability_catalog(args.available_capabilities),
    )
    print(json.dumps(plan, ensure_ascii=False, indent=2))


def semantic_universe(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    spec = state.get("contractSpec", {})
    collections = (*SEMANTIC_COLLECTIONS, "intentAnchors", "decisionLedger")
    return {item["id"]: item for collection in collections for item in spec.get(collection, [])}


def required_check_ids(state: dict[str, Any], lane: dict[str, Any]) -> set[str]:
    spec = state["contractSpec"]
    required = {item["id"] for item in spec["canonicalSources"] if item.get("required", True)}
    required.update(item["id"] for item in spec.get("decisionLedger", []) if item.get("status") == "binding")
    lane_name = lane["name"]
    sample_gate = spec.get("sampleGate", {})
    if sample_gate.get("required") and lane_name == sample_gate.get("lane"):
        required.update(sample_gate.get("acceptanceIds", []))
    for collection in ("preserve", "allowedChanges", "forbidden", "acceptance"):
        for item in spec[collection]:
            refs = item_lane_names(item)
            if lane_name in refs or (not refs and lane.get("writeBoundary") in {"approved-target", "review-only"}):
                required.add(item["id"])
    for item in spec.get("intentAnchors", []):
        refs = item_lane_names(item)
        if item.get("required", True) and (lane_name in refs or not refs):
            required.add(item["id"])
    if lane.get("kind") == "review":
        required.update(item["id"] for collection in ("preserve", "allowedChanges", "forbidden", "acceptance") for item in spec[collection])
    return required


def normalize_manifest(state: dict[str, Any], raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        fail("semantic_strict pass requires a non-empty artifactManifest array.")
    manifest = [normalize_semantic_item(item, "artifactManifest") for item in raw]
    ids = [item["id"] for item in manifest]
    if len(ids) != len(set(ids)):
        fail("artifactManifest contains duplicate IDs.")
    deliverable_id = state["contractSpec"]["deliverable"]["id"]
    deliverable = state["contractSpec"]["deliverable"]
    unit_ids = {unit["id"] for unit in deliverable.get("units", [])}
    for item in manifest:
        item["deliverableId"] = require_nonempty(item.get("deliverableId"), "artifactManifest deliverableId")
        if item["deliverableId"] != deliverable_id:
            fail(f"artifactManifest deliverableId must match contractSpec.deliverable.id: {deliverable_id}")
        if "role" in item:
            role = require_nonempty(item.get("role"), "artifactManifest role")
            if role not in ARTIFACT_ROLES:
                fail("artifactManifest role must be entrypoint, appendix, or source.")
            item["role"] = role
        if "unitId" in item:
            item["unitId"] = require_nonempty(item.get("unitId"), "artifactManifest unitId")
            if item["unitId"] not in unit_ids:
                fail(f"artifactManifest references unknown unitId: {item['unitId']}")
        if structured_verification_enforced(state):
            fingerprint = require_nonempty(
                item.get("artifactFingerprint"), "artifactManifest artifactFingerprint"
            )
            if len(fingerprint) != 64 or any(char not in "0123456789abcdef" for char in fingerprint):
                fail("artifactManifest artifactFingerprint must be a lowercase SHA-256 digest.")
            item["artifactFingerprint"] = fingerprint
    covered_units = {item.get("unitId") for item in manifest if item.get("unitId")}
    missing_units = sorted(unit_ids - covered_units)
    if missing_units:
        fail(f"artifactManifest missing deliverable unitIds: {', '.join(missing_units)}")
    delivery_package = deliverable.get("deliveryPackage", {})
    if delivery_package.get("selfContained"):
        entrypoints = [item for item in manifest if item.get("role") == "entrypoint"]
        if not entrypoints:
            fail("selfContained deliveryPackage requires an artifactManifest entrypoint.")
        configured_entrypoint = delivery_package.get("entrypoint")
        if configured_entrypoint and not any(item["id"] == configured_entrypoint for item in entrypoints):
            fail("artifactManifest entrypoint must match deliveryPackage.entrypoint.")
    user_gate = state["contractSpec"].get("userApprovalGate", {})
    if user_gate.get("required"):
        approval_artifact = next((item for item in manifest if item["id"] == user_gate.get("artifactId")), None)
        if approval_artifact is not None:
            approval_artifact["artifactFingerprint"] = require_nonempty(
                approval_artifact.get("artifactFingerprint"),
                "userApprovalGate artifactManifest artifactFingerprint",
            )
    return manifest


def validate_check_results(state: dict[str, Any], lane: dict[str, Any], raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        fail("semantic_strict pass requires checkResults to be an array.")
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    universe = semantic_universe(state)
    for result in raw:
        if not isinstance(result, dict):
            fail("Each checkResults item must be an object.")
        item = dict(result)
        check_id = require_nonempty(item.get("id"), "checkResults id")
        if check_id in seen:
            fail(f"checkResults contains duplicate ID: {check_id}")
        if check_id not in universe:
            fail(f"checkResults contains unknown ID: {check_id}")
        seen.add(check_id)
        if item.get("status") != "pass":
            fail(f"checkResults must pass: {check_id}")
        item["evidence"] = require_nonempty(item.get("evidence"), f"checkResults evidence for {check_id}")
        results.append(item)
    missing = sorted(required_check_ids(state, lane) - seen)
    if missing:
        fail(f"checkResults missing required IDs: {', '.join(missing)}")
    return results


def open_correction_events(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [event for event in state.get("correctionEvents", []) if event.get("status") == "open"]


def invalidate_finalization(state: dict[str, Any], reason: str) -> None:
    finalization = state.setdefault("finalization", {"status": "open"})
    if finalization.get("status") == "finalized":
        finalization.update({"status": "open", "invalidated_at": now(), "invalidationReason": reason})


def stale_current_approvals(state: dict[str, Any], reason: str) -> None:
    revision = state.get("contractRevision")
    for approval in state.get("approvalRecords", []):
        if approval.get("contractRevision") == revision and approval.get("status") == "active":
            approval.update({"status": "stale", "staleReason": reason, "stale_at": now()})
    invalidate_finalization(state, reason)


def normalize_correction_events(raw: Any, state: dict[str, Any], lane_name: str) -> list[dict[str, Any]]:
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        fail("correctionEvents must be an array.")
    lane_names = {lane["name"] for lane in state.get("lanes", [])}
    existing_ids = {event.get("id") for event in state.get("correctionEvents", [])}
    events: list[dict[str, Any]] = []
    for raw_event in raw:
        if not isinstance(raw_event, dict):
            fail("Each correctionEvents item must be an object.")
        event = dict(raw_event)
        event["reason"] = require_nonempty(event.get("reason"), "correction event reason")
        recommended = require_nonempty(
            event.get("recommendedInvalidFromLane"), "correction recommendedInvalidFromLane"
        )
        if recommended not in lane_names:
            fail(f"Correction event references missing lane: {recommended}")
        event_id = event.get("id") or sha256_json(
            {"contractRevision": state["contractRevision"], "fromLane": lane_name, "event": event}
        )[:24]
        event_id = require_nonempty(event_id, "correction event id")
        if event_id in existing_ids or any(item["id"] == event_id for item in events):
            fail(f"Correction event ID already exists: {event_id}")
        event.update(
            {
                "id": event_id,
                "status": "open",
                "fromLane": lane_name,
                "recommendedInvalidFromLane": recommended,
                "contractRevision": state["contractRevision"],
                "created_at": now(),
            }
        )
        events.append(event)
    return events


def semantic_identity_blockers(state: dict[str, Any], worker: dict[str, Any]) -> list[str]:
    if not is_semantic_strict(state):
        return []
    blockers: list[str] = []
    if worker.get("contractDigest") != state.get("contractDigest"):
        blockers.append(f"Worker contractDigest is not current: {worker.get('workerId', '')}")
    if worker.get("deliverableFingerprint") != state.get("contractSpec", {}).get("deliverableFingerprint"):
        blockers.append(f"Worker deliverableFingerprint is not current: {worker.get('workerId', '')}")
    return blockers


def sample_gate_blockers(state: dict[str, Any], target_lane: str) -> list[str]:
    if not is_semantic_strict(state):
        return []
    sample_gate = state["contractSpec"].get("sampleGate", {})
    if not sample_gate.get("required") or target_lane not in sample_gate.get("blocks", []):
        return []
    sample_lane = find_lane(state, sample_gate["lane"])
    revision = state["contractRevision"]
    blockers: list[str] = []
    if sample_lane.get("validForRevision") != revision or sample_lane.get("status") != "done" or sample_lane.get("decision") != "pass":
        blockers.append(f"Sample gate lane has not passed current revision: {sample_lane['name']}")
        return blockers
    passed_ids: set[str] = set()
    for worker in state.get("workers", []):
        if worker_is_current(worker, revision) and worker.get("lane") == sample_lane["name"] and worker.get("decision") == "pass":
            passed_ids.update(result.get("id") for result in worker.get("checkResults", []))
    missing = sorted(set(sample_gate.get("acceptanceIds", [])) - passed_ids)
    if missing:
        blockers.append(f"Sample gate acceptance IDs have not passed: {', '.join(missing)}")
    return blockers


def current_manifest_artifacts(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    revision = state["contractRevision"]
    artifacts: dict[str, dict[str, Any]] = {}
    for worker in state.get("workers", []):
        if not worker_is_current(worker, revision) or worker.get("decision") != "pass":
            continue
        for item in worker.get("artifactManifest", []):
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                artifacts[item["id"]] = item
    return artifacts


def active_approval_for_artifact(
    state: dict[str, Any], artifact_id: str, artifact_fingerprint: str
) -> dict[str, Any] | None:
    revision = state["contractRevision"]
    return next(
        (
            approval
            for approval in reversed(state.get("approvalRecords", []))
            if approval.get("status") == "active"
            and approval.get("contractRevision") == revision
            and approval.get("artifactId") == artifact_id
            and approval.get("artifactFingerprint") == artifact_fingerprint
        ),
        None,
    )


def user_approval_gate_blockers(state: dict[str, Any], target_lane: str) -> list[str]:
    if not is_semantic_strict(state):
        return []
    gate = state["contractSpec"].get("userApprovalGate", {})
    if not gate.get("required") or target_lane not in gate.get("blocks", []):
        return []
    return user_approval_record_blockers(state)


def user_approval_record_blockers(state: dict[str, Any]) -> list[str]:
    gate = state["contractSpec"].get("userApprovalGate", {})
    if not gate.get("required"):
        return []
    artifact_id = gate["artifactId"]
    artifact = current_manifest_artifacts(state).get(artifact_id)
    if artifact is None:
        return [f"User approval artifact is not available for current revision: {artifact_id}"]
    fingerprint = str(artifact.get("artifactFingerprint", "")).strip()
    if not fingerprint:
        return [f"User approval artifact fingerprint is missing: {artifact_id}"]
    if active_approval_for_artifact(state, artifact_id, fingerprint) is None:
        return [f"User approval is required for current artifact fingerprint: {artifact_id}"]
    return []


def require_approved_target_authorization(state: dict[str, Any], lane: dict[str, Any]) -> None:
    if lane.get("writeBoundary") != "approved-target":
        return
    mode = interaction_mode(state)
    if mode != "execute":
        fail(f"interactionMode={mode} prohibits approved-target lane operations: {lane.get('name', '')}")
    if (
        is_semantic_strict(state)
        and business_contract_v2(state)
        and not isinstance(state["contractSpec"].get("writePolicy"), dict)
    ):
        fail("execute + approved-target requires contractSpec.writePolicy.")


def is_destructive_action(action: str) -> bool:
    normalized = action.strip().lower().replace("_", "-")
    return normalized in DESTRUCTIVE_ACTIONS or any(
        normalized.startswith(prefix + "-") for prefix in DESTRUCTIVE_ACTIONS
    )


def normalize_write_receipt(state: dict[str, Any], raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        fail("approved-target pass requires writeReceipt to be an object.")
    receipt = dict(raw)
    for field in (
        "targetId",
        "targetLocator",
        "action",
        "afterVersion",
        "readbackEvidence",
        "idempotencyKey",
    ):
        receipt[field] = require_nonempty(receipt.get(field), f"writeReceipt.{field}")
    before_version = receipt.get("beforeVersion", "")
    if before_version is None:
        before_version = ""
    if not isinstance(before_version, str):
        fail("writeReceipt.beforeVersion must be a string or empty.")
    receipt["beforeVersion"] = before_version.strip()
    policy = state.get("contractSpec", {}).get("writePolicy")
    if not isinstance(policy, dict):
        fail("approved-target writeReceipt requires contractSpec.writePolicy.")
    target = next(
        (
            item
            for item in policy.get("targets", [])
            if item.get("id") == receipt["targetId"]
            and item.get("locator") == receipt["targetLocator"]
        ),
        None,
    )
    if target is None:
        fail("writeReceipt targetId/targetLocator must exactly match one writePolicy target.")
    if receipt["action"] not in policy.get("allowedActions", []):
        fail(f"writeReceipt action is not allowed by writePolicy: {receipt['action']}")
    destructive = is_destructive_action(receipt["action"])
    if destructive and not receipt["beforeVersion"]:
        fail("Destructive writeReceipt actions require beforeVersion.")
    if destructive and policy.get("destructiveActionsRequireApproval"):
        active = [
            item
            for item in state.get("approvalRecords", [])
            if item.get("status") == "active"
            and item.get("contractRevision") == state["contractRevision"]
        ]
        if not active:
            fail("Destructive writeReceipt action requires a current-revision user approval.")
    return receipt


def structured_verification_enforced(state: dict[str, Any]) -> bool:
    """New graph states use ledger-backed permits and verification results.

    The marker is deliberately opt-in so pre-existing manual and non-graph
    checkpoints retain their documented callback compatibility.
    """
    # ``structuredVerificationEnforced`` was emitted by an unreleased preview
    # of this protocol. Read it for checkpoint compatibility, but only new
    # state uses the explicit, versioned marker.
    return bool(
        state.get("verificationEnforcement") == "structured-v1"
        or state.get("structuredVerificationEnforced")
    ) and is_graph_state(state)


def artifact_manifest_fingerprint(manifest: list[dict[str, Any]]) -> str:
    return sha256_json(manifest)


def operation_ledgers(state: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    permits = state.setdefault("operationPermits", [])
    receipts = state.setdefault("operationReceipts", [])
    results = state.setdefault("verificationResults", [])
    if not all(isinstance(value, list) and all(isinstance(item, dict) for item in value) for value in (permits, receipts, results)):
        fail("Structured operation ledgers must be arrays of objects.")
    return permits, receipts, results


def ledger_entry(entries: list[dict[str, Any]], key: str, value: str) -> dict[str, Any] | None:
    return next((entry for entry in entries if entry.get(key) == value), None)


def replace_ledger_entry(entries: list[dict[str, Any]], key: str, value: str, entry: dict[str, Any]) -> None:
    for index, existing in enumerate(entries):
        if existing.get(key) == value:
            entries[index] = entry
            return
    entries.append(entry)


def operation_identity(state: dict[str, Any], worker: dict[str, Any], packet: dict[str, Any]) -> dict[str, dict[str, str]]:
    graph = state.get("solutionGraph", {})
    blueprint = state.get("taskBlueprint", {})
    return {
        "planIdentity": {"id": state.get("planDigest", ""), "digest": state.get("planDigest", "")},
        "graphIdentity": {"id": graph.get("id", ""), "digest": state.get("solutionGraphDigest", "")},
        "packetIdentity": {"id": packet.get("packetId", ""), "digest": packet.get("packetDigest", "")},
        "blueprintIdentity": {"id": blueprint.get("id", ""), "digest": state.get("blueprintDigest", "")},
        "contractIdentity": {"id": str(state.get("contractRevision", "")), "digest": state.get("contractDigest", "")},
    }


def require_current_operation_permit(
    state: dict[str, Any], permit: dict[str, Any], *, worker: dict[str, Any] | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not structured_verification_enforced(state):
        fail("Operation permits are required only for structured graph state.")
    permit = validate_permit(permit, allow_expired=True)
    permit_worker = next(
        (item for item in state.get("workers", []) if item.get("workerId") == permit.get("workerId")), None
    )
    if permit_worker is None or permit_worker.get("contractRevision") != state["contractRevision"]:
        fail("Operation permit worker is not current for this contract revision.")
    if worker is not None and permit_worker.get("workerId") != worker.get("workerId"):
        fail("Operation permit does not belong to the callback worker.")
    if permit_worker.get("runtimeHandle") != permit.get("runtimeHandle"):
        fail("Operation permit runtime identity does not match the registered worker.")
    packet = current_packet(state, permit_worker.get("packetId", ""), permit_worker.get("packetDigest", ""))
    expected = operation_identity(state, permit_worker, packet)
    for field, value in expected.items():
        if permit.get(field) != value:
            fail(f"Operation permit {field} is stale or does not match the current graph identity.")
    lane = find_lane(state, permit_worker.get("lane", ""))
    if lane.get("writeBoundary") != "approved-target":
        fail("Operation permits may only authorize approved-target workers.")
    policy = packet.get("writePolicySlice", {})
    target = next(
        (
            item for item in policy.get("targets", [])
            if item.get("id") == permit.get("targetId") and item.get("locator") == permit.get("targetLocator")
        ),
        None,
    )
    if target is None or permit.get("action") not in policy.get("allowedActions", []):
        fail("Operation permit target or action is outside the current WorkerPacket allowlist.")
    capability_ids = {
        item.get("capabilityId") for item in packet.get("capabilityBindings", []) if isinstance(item, dict)
    }
    if permit.get("capabilityId") not in capability_ids:
        fail("Operation permit capability is not bound by the current WorkerPacket.")
    return permit_worker, packet


def restricted_operation_adapter(
    adapter_id: str,
    options: dict[str, Any],
    *,
    operation_id: str = "",
    action: str = "",
    target_locator: str = "",
) -> Any:
    adapter_id = require_nonempty(adapter_id, "adapterId")
    if adapter_id == "memory-test":
        if os.environ.get("KY_TASK_TEST_MODE") != "1":
            fail("memory-test adapter is available only when KY_TASK_TEST_MODE=1.")
        allowed = {"failExecute", "readbackMode"}
        if set(options) - allowed:
            fail("memory-test adapter options are restricted.")
        return MemoryTestAdapter(
            fail_execute=bool(options.get("failExecute", False)),
            readback_mode=str(options.get("readbackMode", "match")),
        )
    if adapter_id == "lark-cli":
        if options:
            fail("lark-cli adapter options are not accepted by the controller.")
        return LarkCliAdapter(
            operation_id=require_nonempty(operation_id, "operationId"),
            action=require_nonempty(action, "action"),
            target_locator=require_nonempty(target_locator, "targetLocator"),
        )
    fail("Operation adapter is not allowlisted.")


def packet_acceptance_cases(packet: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for raw in packet.get("acceptanceCases", []):
        try:
            # WorkerPacket uses ``verification`` as routing metadata for review
            # nodes and Blueprint keeps descriptive copy; neither is part of
            # the immutable AcceptanceCase contract.
            case = dict(raw)
            case.pop("verification", None)
            case.pop("description", None)
            case.pop("statement", None)
            cases.append(validate_acceptance_case(case))
        except ValueError as error:
            fail(f"WorkerPacket contains an invalid AcceptanceCase: {error}")
    return cases


def parse_operation_receipt_ids(value: str) -> list[str]:
    raw = require_nonempty(value, "operationReceiptIds")
    parsed = load_json_value(raw) if raw.startswith("[") or raw.startswith("@") else parse_csv(raw)
    if not isinstance(parsed, list) or not parsed:
        fail("operationReceiptIds must be a non-empty JSON array or CSV list.")
    return normalize_string_list(parsed, "operationReceiptIds")


def structured_results_for(
    state: dict[str, Any], worker: dict[str, Any], packet: dict[str, Any], manifest_fingerprint: str
) -> list[dict[str, Any]]:
    _, _, ledger_results = operation_ledgers(state)
    return [
        entry["result"]
        for entry in ledger_results
        if entry.get("contractRevision") == state["contractRevision"]
        and entry.get("workerId") == worker.get("workerId")
        and entry.get("packetId") == packet["packetId"]
        and entry.get("packetDigest") == packet["packetDigest"]
        and entry.get("artifactManifestFingerprint") == manifest_fingerprint
        and isinstance(entry.get("result"), dict)
    ]


def validate_structured_result_provenance(
    state: dict[str, Any], worker: dict[str, Any], packet: dict[str, Any], case: dict[str, Any], result: dict[str, Any],
    artifact_manifest: list[dict[str, Any]],
) -> None:
    """Bind externally judged results to the current registered review worker."""
    if case["method"] not in {"business", "semantic"}:
        return
    if result.get("workerId") != worker.get("workerId"):
        fail("semantic/business VerificationResult.workerId must match the registered worker.")
    if result["evaluator"]["runtimeHandle"] != worker.get("runtimeHandle"):
        fail("semantic/business VerificationResult evaluator.runtimeHandle must match the registered worker.")
    capability_ids = {
        item.get("capabilityId") for item in packet.get("capabilityBindings", []) if isinstance(item, dict)
    }
    if result["evaluator"]["capabilityId"] not in capability_ids:
        fail("semantic/business VerificationResult evaluator capability is not bound by the registered WorkerPacket.")
    lane = find_lane(state, worker.get("lane", ""))
    if lane.get("kind") != "review" and lane.get("kind") not in DECISION_REVIEW_KINDS:
        fail("semantic/business VerificationResult requires a review or decision-review lane worker.")
    if ATTESTATION_STRENGTH[result["attestationType"]] < ATTESTATION_STRENGTH["independent_reviewed"]:
        fail("semantic/business VerificationResult requires independent_reviewed or human_approved attestation.")
    writers = review_subject_workers(state, lane["name"])
    writer_ids = {item.get("workerId") for item in writers}
    reviewed_ids = set(result.get("reviewedWorkerIds", []))
    missing = sorted(writer_id for writer_id in writer_ids - reviewed_ids if isinstance(writer_id, str))
    if missing:
        fail("semantic/business VerificationResult.reviewedWorkerIds must cover the current review subjects: " + ", ".join(missing))
    writer_runtimes = {item.get("runtimeHandle") for item in writers}
    if worker.get("workerId") in writer_ids or worker.get("runtimeHandle") in writer_runtimes:
        fail("semantic/business VerificationResult reviewer must be independent from its review subjects.")
    review_items_by_receipt = {
        item.get("operationReceiptId"): item
        for item in artifact_manifest
        if isinstance(item, dict) and item.get("operationReceiptId")
    }
    identity_fields = (
        "id", "deliverableId", "path", "artifactFingerprint", "unitId", "role",
        "operationReceiptId", "operationArtifactFingerprint", "targetVersion",
    )
    for writer in writers:
        writer_manifest = writer.get("artifactManifest")
        if not isinstance(writer_manifest, list) or not writer_manifest:
            fail("semantic/business review requires each covered writer to have a current artifactManifest.")
        for writer_item in writer_manifest:
            if not isinstance(writer_item, dict):
                continue
            receipt_id = writer_item.get("operationReceiptId")
            reviewed_item = review_items_by_receipt.get(receipt_id) if receipt_id else next(
                (
                    item for item in artifact_manifest
                    if isinstance(item, dict)
                    and item.get("id") == writer_item.get("id")
                    and item.get("artifactFingerprint") == writer_item.get("artifactFingerprint")
                ),
                None,
            )
            if reviewed_item is None:
                fail("semantic/business review artifactManifest must include every review-subject artifact.")
            if any(reviewed_item.get(field) != writer_item.get(field) for field in identity_fields):
                fail("semantic/business review artifactManifest does not match the covered writer artifact identity.")


def persist_verification_results(
    state: dict[str, Any], worker: dict[str, Any], packet: dict[str, Any], manifest_fingerprint: str,
    raw_results: Any, artifact_manifest: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(raw_results, list):
        fail("verificationResults must be a JSON array.")
    cases = {case["id"]: case for case in packet_acceptance_cases(packet)}
    _, _, results = operation_ledgers(state)
    persisted: list[dict[str, Any]] = []
    for raw_result in raw_results:
        if not isinstance(raw_result, dict):
            fail("verificationResults items must be objects.")
        case = cases.get(raw_result.get("caseId"))
        if case is None:
            fail("Verification result caseId is not in the current WorkerPacket.")
        try:
            result = validate_verification_result(raw_result, case, {"artifactFingerprint": manifest_fingerprint})
        except ValueError as error:
            fail(f"Verification result rejected: {error}")
        validate_structured_result_provenance(state, worker, packet, case, result, artifact_manifest)
        if result.get("workerId") and result["workerId"] != worker["workerId"]:
            fail("Verification result workerId must match the registered worker.")
        entry = {
            "result": result, "contractRevision": state["contractRevision"], "workerId": worker["workerId"],
            "runtimeHandle": worker.get("runtimeHandle", ""), "packetId": packet["packetId"],
            "packetDigest": packet["packetDigest"], "artifactManifestFingerprint": manifest_fingerprint,
            "recorded_at": now(),
        }
        existing = ledger_entry(results, "resultId", result["resultId"])
        if existing is not None and canonical_json(existing.get("result")) != canonical_json(result):
            fail("Verification result ID is already bound to different content.")
        replace_ledger_entry(results, "resultId", result["resultId"], entry)
        persisted.append(entry)
    return persisted


def structured_verification_summary(
    state: dict[str, Any], worker: dict[str, Any], packet: dict[str, Any], manifest_fingerprint: str
) -> dict[str, Any]:
    writers = [
        {"workerId": item.get("workerId", ""), "runtimeHandle": item.get("runtimeHandle", "")}
        for item in review_subject_workers(state, worker["lane"])
    ]
    try:
        return aggregate_verification(
            packet_acceptance_cases(packet), structured_results_for(state, worker, packet, manifest_fingerprint),
            {"artifactFingerprint": manifest_fingerprint}, {"writers": writers},
        )
    except ValueError as error:
        fail(f"Structured verification aggregation failed: {error}")


def current_receipt_for_callback(state: dict[str, Any], receipt_id: str, worker: dict[str, Any]) -> dict[str, Any]:
    _, receipts, _ = operation_ledgers(state)
    receipt = ledger_entry(receipts, "receiptId", require_nonempty(receipt_id, "operationReceiptId"))
    if not isinstance(receipt, dict):
        fail("operationReceiptId is not present in the state ledger.")
    permits, _, _ = operation_ledgers(state)
    permit = ledger_entry(permits, "permitId", str(receipt.get("permitId", "")))
    if not isinstance(permit, dict):
        fail("Operation receipt has no corresponding permit ledger entry.")
    permit_worker, _ = require_current_operation_permit(state, permit, worker=worker)
    if receipt.get("contractRevision") != state.get("contractRevision"):
        fail("Operation receipt is stale for the current contract revision.")
    if receipt.get("status") != "consumed" or permit.get("status") != "consumed":
        fail("Operation receipt must be consumed with successful readback; reconcile receipts cannot pass callbacks.")
    if receipt.get("workerId") != permit_worker.get("workerId") or receipt.get("runtimeHandle") != permit_worker.get("runtimeHandle"):
        fail("Operation receipt identity does not match the current worker.")
    for field in ("permitId", "targetId", "targetLocator", "action", "payloadFingerprint", "idempotencyKey"):
        if receipt.get(field) != permit.get(field):
            fail(f"Operation receipt {field} does not match its permit.")
    if not isinstance(receipt.get("readbackDigest"), str) or not receipt["readbackDigest"]:
        fail("Operation receipt is missing readback evidence.")
    return receipt


def require_receipt_manifest_binding(receipt: dict[str, Any], manifest: list[dict[str, Any]]) -> None:
    match = next(
        (item for item in manifest if item.get("operationReceiptId") == receipt.get("receiptId")),
        None,
    )
    if match is None:
        fail("artifactManifest must reference every operationReceiptId.")
    if match.get("path") != receipt.get("targetLocator"):
        fail("artifactManifest operation path must match the dispatched targetLocator.")
    if match.get("operationArtifactFingerprint") != receipt.get("artifactFingerprint"):
        fail("artifactManifest operationArtifactFingerprint must match dispatcher readback evidence.")
    expected_version = "" if receipt.get("afterVersion") is None else str(receipt.get("afterVersion"))
    if str(match.get("targetVersion", "")) != expected_version:
        fail("artifactManifest targetVersion must match the dispatcher afterVersion.")


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"State file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now()
    payload = (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


@contextmanager
def state_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def require_v2(state: dict[str, Any]) -> None:
    if state.get("schemaVersion", 1) != SCHEMA_VERSION:
        fail("migration_required: continuing operations require schemaVersion 2; re-initialize or migrate this state.")


def infer_lane_kind(name: str) -> str:
    value = name.lower().replace("_", "-")
    if any(token in value for token in ("review", "acceptance", "audit", "验收", "复核", "审查")):
        return "review"
    if any(token in value for token in ("implement", "writer", "write", "build", "repair", "实现", "写入", "修复")):
        return "implementation"
    if any(token in value for token in ("evidence", "source", "research", "证据", "来源", "调研")):
        return "evidence"
    if any(token in value for token in ("metric", "chart", "指标", "图表")):
        return "metric"
    if any(token in value for token in ("object", "model", "schema", "对象", "模型")):
        return "model"
    if any(token in value for token in ("product", "experience", "ux", "产品", "体验")):
        return "product_experience"
    return "support"


def infer_write_boundary(kind: str) -> str:
    if kind == "implementation":
        return "approved-target"
    if kind == "review":
        return "review-only"
    return "read-only"


def is_distributed_mode(mode: str) -> bool:
    """Treat the historical multi_session value as a wire-compatible alias."""
    return mode in {"distributed", LEGACY_DISTRIBUTED_MODE}


def load_runtime_defaults() -> dict[str, Any]:
    """Load the user's auditable plugin-level runtime preference."""
    path = PLUGIN_ROOT / "config" / "runtime-policy.json"
    fallback = {
        "runtimeSelectionPolicy": "lane_lifecycle",
        "orchestrationPolicy": DEFAULT_ORCHESTRATION_POLICY,
        "nativeThreadUserApproved": False,
        "maxParallelWorkers": DEFAULT_MAX_PARALLEL_WORKERS,
        "projectAffinityPolicy": "allow_projectless",
        "projectlessUserApproved": False,
    }
    if not path.exists():
        return fallback
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Invalid runtime policy config: {exc}")
    if not isinstance(raw, dict):
        fail("Runtime policy config must be a JSON object.")
    return {**fallback, **raw}


def make_lane(
    name: str,
    revision: int,
    *,
    kind: str = "",
    worker_required: bool = False,
    write_boundary: str = "",
    worker_lifecycle: str = "ephemeral",
    context_policy: str = "",
    runtime_preference: str = "auto",
    depends_on: Any = None,
    purpose: str = "",
    contribution_role: str = "",
    semantic_authority: str = "",
    semantic_owner: bool = False,
    dependency_reasons: Any = None,
    input_contracts: Any = None,
    output_contracts: Any = None,
    external_inputs: Any = None,
    write_targets: Any = None,
    handoff_risk: str = "",
    handoff_mode: str = "",
    handoff_contract: Any = None,
    verification_scope: str = "",
    capability_requirements: Any = None,
    capability_needs: Any = None,
    estimated_effort: Any = 1,
    continuity_required: bool = False,
    orchestration_declared: Any = None,
    status: str = "pending",
    artifact: str = "",
    decision: str = "",
    notes: str = "",
) -> dict[str, Any]:
    lane_name = require_nonempty(name, "lane name")
    lane_kind = kind.strip() if isinstance(kind, str) and kind.strip() else infer_lane_kind(lane_name)
    boundary = write_boundary.strip() if isinstance(write_boundary, str) and write_boundary.strip() else infer_write_boundary(lane_kind)
    if boundary not in WRITE_BOUNDARIES:
        fail(f"Unsupported writeBoundary: {boundary}")
    lifecycle = worker_lifecycle.strip() if isinstance(worker_lifecycle, str) else ""
    if lifecycle not in WORKER_LIFECYCLES:
        fail(f"Unsupported workerLifecycle: {lifecycle}")
    context = context_policy.strip() if isinstance(context_policy, str) and context_policy.strip() else (
        "checkpoint_delta" if lifecycle == "persistent" else "packet_only"
    )
    if context not in CONTEXT_POLICIES:
        fail(f"Unsupported contextPolicy: {context}")
    if lifecycle == "persistent" and context != "checkpoint_delta":
        fail("persistent workerLifecycle requires contextPolicy=checkpoint_delta.")
    preference = runtime_preference.strip() if isinstance(runtime_preference, str) else ""
    if preference not in RUNTIME_PREFERENCES:
        fail(f"Unsupported runtimePreference: {preference}")
    preferred_profile = RUNTIME_REGISTRY.get(preference)
    if lifecycle == "persistent" and preferred_profile and not preferred_profile.supports_persistent:
        fail(
            f"persistent workerLifecycle cannot prefer {preference}: its runtime "
            "profile does not support persistent workers."
        )
    lane = {
        "name": lane_name,
        "kind": lane_kind,
        "workerRequired": bool(worker_required) or lifecycle == "persistent",
        "writeBoundary": boundary,
        "workerLifecycle": lifecycle,
        "contextPolicy": context,
        "runtimePreference": preference,
        "purpose": purpose.strip() if isinstance(purpose, str) else "",
        "contributionRole": contribution_role.strip() if isinstance(contribution_role, str) else "",
        "semanticAuthority": semantic_authority.strip() if isinstance(semantic_authority, str) else "",
        "semanticOwner": bool(semantic_owner),
        "dependencyReasons": dependency_reasons if isinstance(dependency_reasons, (dict, list)) else {},
        "inputContracts": input_contracts if isinstance(input_contracts, list) else [],
        "outputContracts": output_contracts if isinstance(output_contracts, list) else [],
        "externalInputs": external_inputs if isinstance(external_inputs, list) else [],
        "writeTargets": write_targets if isinstance(write_targets, list) else [],
        "handoffRisk": handoff_risk.strip() if isinstance(handoff_risk, str) else "",
        "handoffMode": handoff_mode.strip() if isinstance(handoff_mode, str) else "",
        "handoffContract": handoff_contract if isinstance(handoff_contract, (dict, list)) else {},
        "verificationScope": verification_scope.strip() if isinstance(verification_scope, str) else "",
        "capabilityRequirements": capability_requirements if isinstance(capability_requirements, list) else [],
        "capabilityNeeds": capability_needs if isinstance(capability_needs, (list, dict, str)) else [],
        "estimatedEffort": estimated_effort,
        "continuityRequired": bool(continuity_required),
        "orchestrationDeclared": orchestration_declared if isinstance(orchestration_declared, list) else [],
        "recommendedRuntime": "",
        "validForRevision": revision,
        "status": status,
        "artifact": artifact,
        "decision": decision,
        "notes": notes,
        "completed_at": now() if status == "done" else "",
    }
    if depends_on is not None:
        if not isinstance(depends_on, list) or any(
            not isinstance(item, str) or not item.strip() for item in depends_on
        ):
            fail("dependsOn must be an array of lane names.")
        normalized_dependencies = list(dict.fromkeys(item.strip() for item in depends_on))
        if lane_name in normalized_dependencies:
            fail(f"Lane {lane_name} cannot depend on itself.")
        lane["dependsOn"] = normalized_dependencies
    return lane


def distributed_worker_required(mode: str, lane: dict[str, Any]) -> bool:
    return is_distributed_mode(mode) and (
        lane.get("kind") == "implementation" or lane.get("writeBoundary") == "approved-target"
    )


def native_thread_approved(policy: dict[str, Any]) -> bool:
    """New states require approval; missing means a legacy state may continue."""
    if "nativeThreadUserApproved" not in policy:
        return True
    return bool(policy.get("nativeThreadUserApproved"))


def recommended_runtime(
    lane: dict[str, Any], eligible: list[str], *, native_approved: bool,
    selection_policy: str = "lane_lifecycle",
) -> str:
    approved = approved_runtime_ids(
        {"nativeThreadUserApproved": native_approved}
    )
    return select_runtime(
        lane,
        eligible,
        approved_runtime_ids=approved,
        selection_policy=selection_policy,
    )


def normalize_lane_definitions(
    lane_names: list[str], lane_definitions: list[dict[str, Any]] | None, revision: int
) -> list[dict[str, Any]]:
    lanes: list[dict[str, Any]] = []
    if lane_definitions:
        for definition in lane_definitions:
            if not isinstance(definition, dict):
                fail("Each laneDefinitions item must be an object.")
            metadata = definition.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            depends_on = (
                definition.get("dependsOn")
                if "dependsOn" in definition
                else metadata.get("dependsOn")
                if "dependsOn" in metadata
                else None
            )
            orchestration_declared = declared_orchestration_fields(definition)
            def lane_value(field: str, default: Any = None) -> Any:
                return definition[field] if field in definition else metadata.get(field, default)
            lanes.append(
                make_lane(
                    definition.get("name", ""),
                    revision,
                    kind=definition.get("kind", ""),
                    worker_required=bool(
                        definition.get("workerRequired", metadata.get("workerRequired", False))
                    ),
                    write_boundary=definition.get("writeBoundary", ""),
                    worker_lifecycle=definition.get("workerLifecycle", "ephemeral"),
                    context_policy=definition.get("contextPolicy", ""),
                    runtime_preference=definition.get("runtimePreference", "auto"),
                    depends_on=depends_on,
                    purpose=lane_value("purpose", ""),
                    contribution_role=lane_value("contributionRole", ""),
                    semantic_authority=lane_value("semanticAuthority", ""),
                    semantic_owner=bool(lane_value("semanticOwner", False)),
                    dependency_reasons=lane_value("dependencyReasons", {}),
                    input_contracts=lane_value("inputContracts", []),
                    output_contracts=lane_value("outputContracts", []),
                    external_inputs=lane_value("externalInputs", []),
                    write_targets=lane_value("writeTargets", []),
                    handoff_risk=lane_value("handoffRisk", ""),
                    handoff_mode=lane_value("handoffMode", ""),
                    handoff_contract=lane_value("handoffContract", {}),
                    verification_scope=lane_value("verificationScope", ""),
                    capability_requirements=lane_value("capabilityRequirements", []),
                    capability_needs=lane_value("capabilityNeeds", []),
                    estimated_effort=lane_value("estimatedEffort", 1),
                    continuity_required=bool(lane_value("continuityRequired", False)),
                    orchestration_declared=orchestration_declared,
                    notes=definition.get("notes", ""),
                )
            )
    else:
        lanes = [make_lane(name, revision) for name in lane_names]
    names = [lane["name"] for lane in lanes]
    if len(names) != len(set(names)):
        fail("Lane names must be unique.")
    all_names = set(names)
    for lane in lanes:
        if "dependsOn" in lane:
            missing = [name for name in lane["dependsOn"] if name not in all_names]
            if missing:
                fail(f"Lane {lane['name']} dependsOn missing lanes: {', '.join(missing)}")
    return lanes


def normalize_execution_policy(raw: dict[str, Any], lanes: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        fail("executionPolicy must be an object.")
    split_requirement = raw.get("splitRequirement", "none")
    mode = raw.get("mode", "direct")
    if split_requirement not in SPLIT_REQUIREMENTS:
        fail(f"Unsupported splitRequirement: {split_requirement}")
    if mode not in EXECUTION_MODES:
        fail(f"Unsupported execution mode: {mode}")
    eligible = raw.get("eligibleRuntimes", [])
    if not isinstance(eligible, list) or any(item not in TRUE_WORKER_RUNTIMES for item in eligible):
        fail(
            "eligibleRuntimes may contain only registered independent worker runtimes: "
            + ", ".join(sorted(TRUE_WORKER_RUNTIMES))
            + "."
        )
    eligible = list(dict.fromkeys(eligible))
    downgrade_reason = raw.get("downgradeReason", "")
    if not isinstance(downgrade_reason, str):
        fail("downgradeReason must be a string.")
    required_lanes = raw.get("requiredWorkerLanes", [])
    if not isinstance(required_lanes, list) or any(not isinstance(item, str) or not item.strip() for item in required_lanes):
        fail("requiredWorkerLanes must be an array of lane names.")
    required_lanes = list(dict.fromkeys(item.strip() for item in required_lanes))
    lane_names = {lane["name"] for lane in lanes}
    missing = [name for name in required_lanes if name not in lane_names]
    if missing:
        fail(f"requiredWorkerLanes reference missing lanes: {', '.join(missing)}")
    defaults = load_runtime_defaults()
    independent_review = bool(raw.get("independentReviewRequired", False))
    native_approved = bool(
        raw.get("nativeThreadUserApproved", defaults.get("nativeThreadUserApproved", False))
    )
    selection_policy = raw.get(
        "runtimeSelectionPolicy", defaults.get("runtimeSelectionPolicy", "lane_lifecycle")
    )
    if selection_policy not in RUNTIME_SELECTION_POLICIES:
        fail(f"Unsupported runtimeSelectionPolicy: {selection_policy}")
    orchestration_policy = raw.get(
        "orchestrationPolicy", defaults.get("orchestrationPolicy", DEFAULT_ORCHESTRATION_POLICY)
    )
    if orchestration_policy not in ORCHESTRATION_POLICIES:
        fail(f"Unsupported orchestrationPolicy: {orchestration_policy}")
    max_parallel_workers = raw.get(
        "maxParallelWorkers", defaults.get("maxParallelWorkers", DEFAULT_MAX_PARALLEL_WORKERS)
    )
    if (
        not isinstance(max_parallel_workers, int)
        or isinstance(max_parallel_workers, bool)
        or max_parallel_workers < 1
        or max_parallel_workers > MAX_PARALLEL_WORKERS
    ):
        fail(f"maxParallelWorkers must be an integer from 1 to {MAX_PARALLEL_WORKERS}.")
    project_affinity_policy = raw.get(
        "projectAffinityPolicy",
        defaults.get("projectAffinityPolicy", "allow_projectless"),
    )
    if project_affinity_policy not in PROJECT_AFFINITY_POLICIES:
        fail(f"Unsupported projectAffinityPolicy: {project_affinity_policy}")
    projectless_user_approved = raw.get(
        "projectlessUserApproved",
        defaults.get("projectlessUserApproved", False),
    )
    if not isinstance(projectless_user_approved, bool):
        fail("projectlessUserApproved must be a boolean.")
    target_project_id = raw.get("targetProjectId", "")
    target_project_path = raw.get("targetProjectPath", "")
    project_resolution_source = raw.get("projectResolutionSource", "")
    for value, name in (
        (target_project_id, "targetProjectId"),
        (target_project_path, "targetProjectPath"),
        (project_resolution_source, "projectResolutionSource"),
    ):
        if not isinstance(value, str):
            fail(f"{name} must be a string.")
    target_project_id = target_project_id.strip()
    target_project_path = target_project_path.strip()
    project_resolution_source = project_resolution_source.strip()
    if project_resolution_source and project_resolution_source not in PROJECT_RESOLUTION_SOURCES:
        fail(f"Unsupported projectResolutionSource: {project_resolution_source}")
    if target_project_id and not project_resolution_source:
        fail("targetProjectId requires a non-empty projectResolutionSource.")
    approved_runtimes = approved_runtime_ids(
        {"nativeThreadUserApproved": native_approved}
    )
    project_scoped_runtime_ids = {
        profile.runtime_id
        for profile in RUNTIME_REGISTRY.profiles
        if profile.runtime_id in eligible
        and profile.user_visible
        and profile.supports_scope("project")
        and (
            not profile.requires_explicit_approval
            or profile.runtime_id in approved_runtimes
        )
    }
    project_binding_needed = (
        is_distributed_mode(mode)
        and bool(project_scoped_runtime_ids)
        and (
            selection_policy == "native_session_required"
            or any(
                lane.get("workerLifecycle") == "persistent"
                or lane.get("runtimePreference") in project_scoped_runtime_ids
                for lane in lanes
            )
        )
    )
    if (
        project_binding_needed
        and project_affinity_policy == "inherit_or_resolve_required"
        and not target_project_id
    ):
        fail(
            "project_affinity_required: resolve a saved Codex project with list_projects "
            "and set targetProjectId plus projectResolutionSource before distributed Session dispatch."
        )
    if (
        project_binding_needed
        and project_affinity_policy == "allow_projectless"
        and not target_project_id
        and not projectless_user_approved
    ):
        fail(
            "Projectless Session dispatch requires explicit projectlessUserApproved=true."
        )
    implementation_lanes = [lane["name"] for lane in lanes if lane["kind"] == "implementation"
                            or lane.get("writeBoundary") == "approved-target"
                            or lane.get("semanticAuthority") in {"implement", "define-and-implement"}]
    review_lanes = [lane["name"] for lane in lanes if is_artifact_review_lane(lane)]
    if independent_review:
        if not implementation_lanes or not review_lanes:
            fail("independentReviewRequired needs implementation and review lanes.")
        required_lanes = list(dict.fromkeys(required_lanes + implementation_lanes + review_lanes))
    if is_distributed_mode(mode) and not eligible:
        fail("distributed execution requires at least one eligible worker runtime.")
    if is_distributed_mode(mode) and not required_lanes:
        required_lanes = [lane["name"] for lane in lanes if lane.get("workerRequired")]
    if is_distributed_mode(mode):
        required_lanes = list(
            dict.fromkeys(
                required_lanes
                + [lane["name"] for lane in lanes if distributed_worker_required(mode, lane)]
                + [lane["name"] for lane in lanes if lane.get("workerLifecycle") == "persistent"]
            )
        )
    if split_requirement == "mandatory":
        if eligible and not is_distributed_mode(mode):
            fail(
                "mandatory split with an eligible worker runtime requires "
                "mode=distributed (legacy alias: multi_session)."
            )
        if not eligible and is_distributed_mode(mode):
            fail("mandatory distributed execution has no eligible worker runtime.")
        if not eligible and not is_distributed_mode(mode) and not downgrade_reason.strip():
            fail("mandatory split may downgrade only with a non-empty downgradeReason and no eligible runtime.")
    policy = {
        "splitRequirement": split_requirement,
        "mode": mode,
        "eligibleRuntimes": eligible,
        "downgradeReason": downgrade_reason.strip(),
        "requiredWorkerLanes": required_lanes,
        "independentReviewRequired": independent_review,
        "runtimeSelectionPolicy": selection_policy,
        "orchestrationPolicy": orchestration_policy,
        "nativeThreadUserApproved": native_approved,
        "maxParallelWorkers": max_parallel_workers,
        "projectAffinityPolicy": project_affinity_policy,
        "projectlessUserApproved": projectless_user_approved,
        "targetProjectId": target_project_id,
        "targetProjectPath": target_project_path,
        "projectResolutionSource": project_resolution_source,
    }
    required_set = set(required_lanes)
    for lane in lanes:
        lane["workerRequired"] = lane["workerRequired"] or lane["name"] in required_set
        if lane["workerRequired"] and lane["name"] not in required_set:
            policy["requiredWorkerLanes"].append(lane["name"])
    return policy


def apply_runtime_selection(policy: dict[str, Any], lanes: list[dict[str, Any]]) -> None:
    """Choose worker runtimes only after the work orchestration gate passes."""
    eligible = policy["eligibleRuntimes"]
    native_approved = policy["nativeThreadUserApproved"]
    selection_policy = policy["runtimeSelectionPolicy"]
    mode = policy["mode"]
    for lane in lanes:
        lane["recommendedRuntime"] = recommended_runtime(
            lane,
            eligible,
            native_approved=native_approved,
            selection_policy=selection_policy,
        )
        if lane["workerLifecycle"] == "persistent" and not is_distributed_mode(mode):
            fail(
                f"Lane {lane['name']} is persistent and requires mode=distributed "
                "(legacy alias: multi_session)."
            )
        if (
            is_distributed_mode(mode)
            and lane["workerRequired"]
            and not lane["recommendedRuntime"]
        ):
            if lane["workerLifecycle"] == "persistent":
                fail(
                    f"Lane {lane['name']} is persistent and requires an eligible, "
                    "approved runtime profile with supportsPersistent=true; the current "
                    "profile is native_thread_lane with nativeThreadUserApproved=true."
                )
            if selection_policy == "native_session_required":
                fail(
                    f"Lane {lane['name']} requires an approved, user-visible, "
                    "project-capable runtime under "
                    "runtimeSelectionPolicy=native_session_required."
                )
            fail(
                f"Lane {lane['name']} requires an independent worker, but its "
                "runtimePreference cannot be satisfied by the eligible runtimes."
            )


def apply_orchestration_projection(lanes: list[dict[str, Any]], plan: dict[str, Any]) -> None:
    """Persist semantic orchestration fields without changing legacy dependency semantics."""
    planned = {lane["name"]: lane for lane in plan.get("lanes", []) if isinstance(lane, dict)}
    routes = {route["lane"]: route for route in plan.get("capabilityRoutes", []) if isinstance(route, dict)}
    wave_by_lane = {
        lane_name: wave.get("wave", 0)
        for wave in plan.get("waves", []) if isinstance(wave, dict)
        for lane_name in wave.get("lanes", []) if isinstance(lane_name, str)
    }
    parallel_by_lane = {
        lane_name: list(group)
        for group in plan.get("parallelGroups", []) if isinstance(group, list)
        for lane_name in group if isinstance(lane_name, str)
    }
    projection_fields = (
        "purpose", "contributionRole", "semanticAuthority", "semanticOwner",
        "dependencyReasons", "inputContracts", "outputContracts", "externalInputs",
        "writeTargets", "handoffRisk", "handoffMode", "handoffContract",
        "verificationScope", "capabilityRequirements", "capabilityNeeds",
        "estimatedEffort", "continuityRequired", "orchestrationDeclared",
    )
    for lane in lanes:
        source = planned.get(lane["name"])
        if not source:
            continue
        for field in projection_fields:
            lane[field] = deepcopy(source.get(field))
        lane["effectiveDependsOn"] = list(source.get("dependsOn", []))
        lane["orchestrationWave"] = wave_by_lane.get(lane["name"], 0)
        lane["parallelGroup"] = parallel_by_lane.get(lane["name"], [])
        route = routes.get(lane["name"], {})
        lane["capabilityBindings"] = [
            item.get("id") for item in route.get("selected", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        lane["capabilityRouteStatus"] = route.get("status", "unbound")
        lane["capabilityRuntimeReady"] = route.get("runtimeReady", False)
        if "verificationSubjects" in source and plan.get("policy") != "legacy":
            lane["verificationSubjects"] = list(source["verificationSubjects"])


def find_lane(state: dict[str, Any], lane_name: str) -> dict[str, Any]:
    lane = next((item for item in state.get("lanes", []) if item.get("name") == lane_name), None)
    if lane is None:
        fail(f"Lane not found: {lane_name}")
    return lane


def lane_dependencies(state: dict[str, Any], lane_name: str) -> list[str]:
    """Return explicit DAG dependencies, or the legacy ordered-lane prefix."""
    lanes = state.get("lanes", [])
    lane = find_lane(state, lane_name)
    if "dependsOn" in lane:
        dependencies = lane.get("dependsOn", [])
        if not isinstance(dependencies, list):
            fail(f"Lane {lane_name} has invalid dependsOn state.")
        return list(dependencies)
    lane_index = lanes.index(lane)
    return [item.get("name", "") for item in lanes[:lane_index]]


def lane_dependency_closure(state: dict[str, Any], lane_name: str) -> list[str]:
    """Return transitive dependencies in stable lane order."""
    lanes = state.get("lanes", [])
    lane_names = {lane.get("name") for lane in lanes}
    required: set[str] = set()
    pending = list(lane_dependencies(state, lane_name))
    while pending:
        dependency = pending.pop()
        if dependency not in lane_names:
            fail(f"Lane {lane_name} dependsOn missing lane: {dependency}")
        if dependency == lane_name:
            fail(f"Lane {lane_name} cannot depend on itself.")
        if dependency in required:
            continue
        required.add(dependency)
        pending.extend(lane_dependencies(state, dependency))
    return [lane["name"] for lane in lanes if lane.get("name") in required]


def worker_is_current(worker: dict[str, Any], revision: int) -> bool:
    return worker.get("contractRevision") == revision and worker.get("status") in ACTIVE_WORKER_STATUSES


def callback_mode_error(worker: dict[str, Any], observed: str | None = None) -> str:
    expected = worker.get("callbackModeExpected", "")
    observed_mode = str(observed or worker.get("callbackModeObserved") or "unspecified")
    allowed = PASS_CALLBACK_MODES.get(expected)
    if allowed is None or observed_mode in allowed:
        return ""
    allowed_modes = " or ".join(sorted(allowed))
    return (
        f"Worker callback mode mismatch: {worker.get('workerId', '')} -> "
        f"expected {allowed_modes}, got {observed_mode}"
    )


def callback_mode_warning(worker: dict[str, Any], observed: str | None = None) -> str:
    observed_mode = str(observed or worker.get("callbackModeObserved") or "unspecified")
    if worker.get("callbackModeExpected") == "active_message_preferred" and observed_mode == "controller_poll_recovery":
        return f"Worker callback degraded to controller poll recovery: {worker.get('workerId', '')}"
    return ""


def worker_callback_blockers(worker: dict[str, Any], state: dict[str, Any] | None = None) -> list[str]:
    blockers: list[str] = []
    worker_id = worker.get("workerId", "")
    if worker.get("status") != "done":
        blockers.append(f"Worker not done: {worker_id} ({worker.get('lane', '')})")
    if worker.get("decision") != "pass":
        blockers.append(f"Worker decision is not pass: {worker_id} -> {worker.get('decision', '')}")
    if not str(worker.get("artifact", "")).strip():
        blockers.append(f"Worker pass artifact missing: {worker_id}")
    if worker.get("callbackExpected") and not worker.get("callbackReceived"):
        blockers.append(f"Worker callback missing: {worker_id}")
    if worker.get("callbackExpected") and worker.get("callbackReceived"):
        mode_error = callback_mode_error(worker)
        if mode_error:
            blockers.append(mode_error)
    if state is not None and is_semantic_strict(state) and worker.get("decision") == "pass":
        lane = find_lane(state, worker.get("lane", ""))
        manifest = worker.get("artifactManifest")
        if not manifest:
            blockers.append(f"Worker semantic artifactManifest missing: {worker_id}")
        else:
            deliverable_id = state["contractSpec"]["deliverable"]["id"]
            invalid_manifest = [
                item.get("id", "<unknown>") if isinstance(item, dict) else "<non-object>"
                for item in manifest
                if not isinstance(item, dict) or item.get("deliverableId") != deliverable_id
            ]
            if invalid_manifest:
                blockers.append(
                    f"Worker artifactManifest does not cover deliverable {deliverable_id}: "
                    + ", ".join(str(item) for item in invalid_manifest)
                )
        if structured_verification_enforced(state):
            packet = current_packet(state, worker.get("packetId", ""), worker.get("packetDigest", ""))
            try:
                manifest_fingerprint = artifact_manifest_fingerprint(manifest)
                summary = structured_verification_summary(state, worker, packet, manifest_fingerprint)
            except SystemExit as error:
                blockers.append(f"Worker structured verification invalid: {worker_id} -> {error}")
                return blockers
            if summary.get("allowed") is not True:
                blockers.append(f"Worker structured verification is missing or blocked: {worker_id}")
            if lane.get("writeBoundary") == "approved-target":
                try:
                    receipt_ids = worker.get("operationReceiptIds", [])
                    if not isinstance(receipt_ids, list) or not receipt_ids:
                        fail("operationReceiptIds is missing.")
                    for receipt_id in receipt_ids:
                        receipt = current_receipt_for_callback(state, receipt_id, worker)
                        require_receipt_manifest_binding(receipt, manifest)
                except SystemExit as error:
                    blockers.append(f"Worker operation receipt invalid: {worker_id} -> {error}")
            return blockers
        results = worker.get("checkResults", [])
        result_ids = [result.get("id") for result in results if isinstance(result, dict)]
        if len(result_ids) != len(set(result_ids)):
            blockers.append(f"Worker semantic checkResults contain duplicates: {worker_id}")
        missing = sorted(required_check_ids(state, lane) - set(result_ids))
        if missing:
            blockers.append(f"Worker semantic checkResults missing: {worker_id} -> {', '.join(missing)}")
        universe = semantic_universe(state)
        invalid = []
        for result in results:
            if not isinstance(result, dict):
                invalid.append("<non-object>")
            elif (
                result.get("id") not in universe
                or result.get("status") != "pass"
                or not str(result.get("evidence", "")).strip()
            ):
                invalid.append(result.get("id", ""))
        if invalid:
            blockers.append(f"Worker semantic checkResults invalid: {worker_id} -> {', '.join(str(item) for item in invalid)}")
        if lane.get("writeBoundary") == "approved-target" and business_contract_v2(state):
            try:
                normalize_write_receipt(state, worker.get("writeReceipt"))
            except SystemExit as error:
                blockers.append(f"Worker writeReceipt invalid: {worker_id} -> {error}")
    return blockers


def approved_target_writers_before_lane(state: dict[str, Any], lane_name: str) -> list[dict[str, Any]]:
    revision = state["contractRevision"]
    lanes = state.get("lanes", [])
    lane_index = next((idx for idx, lane in enumerate(lanes) if lane.get("name") == lane_name), -1)
    if lane_index < 0:
        fail(f"Lane not found: {lane_name}")
    writer_lanes = {
        lane.get("name")
        for lane in lanes[:lane_index]
        if lane.get("writeBoundary") == "approved-target"
    }
    return [
        worker
        for worker in state.get("workers", [])
        if worker_is_current(worker, revision)
        and worker.get("lane") in writer_lanes
    ]


def review_subject_workers(state: dict[str, Any], lane_name: str) -> list[dict[str, Any]]:
    """Return the artifacts a review is required to judge.

    Final review keeps its historical approved-target scope.  A pre-production
    decision review instead covers workers in its direct dependency lanes, so a
    commercial-model reviewer can be proven independent before any final write.
    """
    lane = find_lane(state, lane_name)
    if "verificationSubjects" in lane:
        subjects = set(lane["verificationSubjects"])
        return [
            worker for worker in state.get("workers", [])
            if worker_is_current(worker, state["contractRevision"]) and worker.get("lane") in subjects
        ]
    if lane.get("kind") == "review":
        return approved_target_writers_before_lane(state, lane_name)
    if lane.get("kind") not in DECISION_REVIEW_KINDS:
        return []
    dependency_lanes = set(lane.get("dependsOn", []))
    revision = state["contractRevision"]
    return [
        worker
        for worker in state.get("workers", [])
        if worker_is_current(worker, revision)
        and worker.get("lane") in dependency_lanes
        and worker.get("status") == "done"
        and worker.get("decision") == "pass"
    ]


def is_artifact_review_lane(lane: dict[str, Any]) -> bool:
    return lane.get("kind") == "review" or (
        lane.get("semanticAuthority") == "verify"
        and lane.get("verificationScope") != "upstream-decision"
    )


def review_coverage_blockers(
    state: dict[str, Any], review_lane: str, review_workers: list[dict[str, Any]]
) -> list[str]:
    writer_workers = review_subject_workers(state, review_lane)
    blockers: list[str] = []
    if not writer_workers:
        blockers.append("Independent review has no preceding current-revision approved-target writer to review.")
        return blockers
    writer_ids = {worker["workerId"] for worker in writer_workers}
    covered: set[str] = set()
    identities = {worker.get("runtimeHandle", "") for worker in writer_workers}
    for reviewer in review_workers:
        covered.update(reviewer.get("reviewsWorkerIds", []))
        if reviewer.get("runtimeHandle", "") in identities:
            blockers.append(f"Review worker is not runtime-independent: {reviewer.get('workerId', '')}")
        blockers.extend(semantic_identity_blockers(state, reviewer))
        if is_semantic_strict(state) and reviewer.get("decision") == "pass":
            result_ids = {result.get("id") for result in reviewer.get("checkResults", [])}
            review_ids = {
                item["id"]
                for collection in ("preserve", "allowedChanges", "forbidden", "acceptance")
                for item in state["contractSpec"][collection]
            }
            missing_checks = sorted(review_ids - result_ids)
            if missing_checks:
                blockers.append(
                    f"Review worker lacks semantic item coverage: {reviewer.get('workerId', '')} -> {', '.join(missing_checks)}"
                )
    missing = sorted(writer_ids - covered)
    if missing:
        blockers.append(f"Review workers do not cover preceding current approved-target writers: {', '.join(missing)}")
    return blockers


def final_review_coverage_blockers(state: dict[str, Any]) -> list[str]:
    revision = state["contractRevision"]
    lanes = state.get("lanes", [])
    current_workers = [worker for worker in state.get("workers", []) if worker_is_current(worker, revision)]
    writer_ids = {
        worker["workerId"]
        for worker in current_workers
        if find_lane(state, worker.get("lane", "")).get("writeBoundary") == "approved-target"
    }
    legitimately_covered: set[str] = set()
    for lane in lanes:
        if not is_artifact_review_lane(lane):
            continue
        preceding_ids = {
            worker["workerId"] for worker in review_subject_workers(state, lane["name"])
        }
        for reviewer in current_workers:
            if reviewer.get("lane") == lane.get("name"):
                legitimately_covered.update(set(reviewer.get("reviewsWorkerIds", [])) & preceding_ids)
    missing = sorted(writer_ids - legitimately_covered)
    if missing:
        return [f"Final review coverage does not cover current approved-target writers: {', '.join(missing)}"]
    return []


def evaluate_gate(
    state: dict[str, Any],
    target_lane: str = "",
    include_target_workers: bool = False,
    require_target_worker: bool = True,
) -> dict[str, Any]:
    require_continuation_state(state)
    lanes = state.get("lanes", [])
    revision = state["contractRevision"]
    if target_lane:
        target_index = next((idx for idx, lane in enumerate(lanes) if lane.get("name") == target_lane), -1)
        if target_index < 0:
            fail(f"Target lane not found: {target_lane}")
    else:
        first_pending = next((lane for lane in lanes if lane.get("status") != "done"), None)
        if first_pending:
            target_lane = first_pending["name"]
            target_index = lanes.index(first_pending)
        else:
            target_index = len(lanes)
    if target_index < len(lanes):
        dependency_names = lane_dependency_closure(state, target_lane)
        dependency_set = set(dependency_names)
        prerequisite_lanes = [lane for lane in lanes if lane.get("name") in dependency_set]
        worker_scope_lanes = [
            lane
            for lane in lanes
            if lane.get("name") in dependency_set
            or (include_target_workers and lane.get("name") == target_lane)
        ]
    else:
        prerequisite_lanes = list(lanes)
        worker_scope_lanes = list(lanes)
    blockers: list[str] = []
    warnings: list[str] = []
    if state.get("enforcementMode") is None:
        warnings.append("Legacy schemaVersion 2 state has no enforcementMode; treating it as workflow_only without rewriting it.")
    open_events = open_correction_events(state)
    if open_events:
        blockers.append("Open correctionEvents require revise-contract before registration, gate, or completion: " + ", ".join(event["id"] for event in open_events))
    gate_targets = [target_lane] if target_index < len(lanes) else [lane["name"] for lane in lanes]
    for gate_target in gate_targets:
        target = find_lane(state, gate_target)
        if target.get("writeBoundary") == "approved-target" and interaction_mode(state) != "execute":
            blockers.append(
                f"interactionMode={interaction_mode(state)} prohibits approved-target gate: {gate_target}"
            )
    if is_semantic_strict(state):
        if not state.get("contractSpec") or not state.get("contractDigest"):
            blockers.append("semantic_strict state is missing contractSpec or contractDigest.")
        for gate_target in gate_targets:
            blockers.extend(sample_gate_blockers(state, gate_target))
            blockers.extend(user_approval_gate_blockers(state, gate_target))
    for lane in prerequisite_lanes:
        if lane.get("validForRevision") != revision:
            blockers.append(f"Lane is not valid for contract revision {revision}: {lane.get('name')}")
        if lane.get("status") != "done":
            blockers.append(f"Lane not complete: {lane.get('name')}")
        if lane.get("decision") != "pass":
            blockers.append(f"Lane decision is not pass: {lane.get('name')} -> {lane.get('decision', '')}")
        if not str(lane.get("artifact", "")).strip():
            blockers.append(f"Lane pass artifact missing: {lane.get('name')}")
    current_workers = [worker for worker in state.get("workers", []) if worker_is_current(worker, revision)]
    for lane in worker_scope_lanes:
        lane_workers = [worker for worker in current_workers if worker.get("lane") == lane.get("name")]
        carried = lane.get("carriedForwardAtRevision") == revision
        if is_semantic_strict(state) and lane.get("workerRequired") and not lane_workers and not carried:
            blockers.append(f"Strict semantic worker callback missing for lane: {lane.get('name')}")
        if lane.get("workerRequired"):
            real_workers = [worker for worker in lane_workers if worker.get("laneRuntime") in TRUE_WORKER_RUNTIMES]
            if not real_workers and not carried:
                blockers.append(f"Required worker missing for lane: {lane.get('name')}")
            lane_workers = real_workers
        for worker in lane_workers:
            blockers.extend(worker_callback_blockers(worker, state))
            blockers.extend(semantic_identity_blockers(state, worker))
            mode_warning = callback_mode_warning(worker)
            if mode_warning:
                warnings.append(mode_warning)
        if is_artifact_review_lane(lane) and state["executionPolicy"].get("independentReviewRequired"):
            blockers.extend(review_coverage_blockers(state, lane["name"], lane_workers))
    if require_target_worker and not include_target_workers and target_index < len(lanes):
        target = lanes[target_index]
        target_workers = [
            worker
            for worker in current_workers
            if worker.get("lane") == target.get("name") and worker.get("laneRuntime") in TRUE_WORKER_RUNTIMES
        ]
        if (target.get("workerRequired") or is_semantic_strict(state)) and not target_workers:
            blockers.append(f"Required worker missing for lane: {target.get('name')}")
        if is_artifact_review_lane(target) and state["executionPolicy"].get("independentReviewRequired"):
            blockers.extend(review_coverage_blockers(state, target["name"], target_workers))
    if target_index == len(lanes) and state["executionPolicy"].get("independentReviewRequired"):
        blockers.extend(final_review_coverage_blockers(state))
    stale_workers = [
        worker.get("workerId", "")
        for worker in state.get("workers", [])
        if worker.get("contractRevision") != revision and worker.get("status") not in {"superseded", "stale", "resolved"}
    ]
    if stale_workers:
        warnings.append(f"Old-revision workers ignored: {', '.join(stale_workers)}")
    return {
        "allowed": not blockers,
        "targetLane": target_lane,
        "contractRevision": revision,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": warnings,
        "previousLanes": prerequisite_lanes,
    }


def init(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    if path.exists() and not args.force:
        fail(f"State file already exists. Use --force to replace: {path}")
    lane_definitions = load_json_value(args.lane_definitions) if args.lane_definitions else None
    if lane_definitions is not None and not isinstance(lane_definitions, list):
        fail("laneDefinitions must be a JSON array.")
    if args.auto_plan and not args.task_blueprint:
        fail("--auto-plan requires --task-blueprint.")
    plan: dict[str, Any] | None = None
    task_blueprint: dict[str, Any] | None = None
    blueprint_compiled: dict[str, Any] | None = None
    if args.auto_plan:
        runtime_availability = load_json_value(args.runtime_availability)
        if not isinstance(runtime_availability, dict) or not all(
            isinstance(value, bool) for value in runtime_availability.values()
        ):
            fail("runtime availability must be a JSON object with boolean values.")
        plan, task_blueprint, blueprint_compiled = plan_blueprint_data(
            load_json_value(args.task_blueprint),
            runtime_availability=runtime_availability,
            active_capability_ids=parse_csv(args.active_capability_ids) or None,
            available_capabilities=available_capability_catalog(args.available_capabilities),
        )
        projected = plan["laneProjection"]["laneDefinitions"]
        if lane_definitions is not None:
            def lane_plan_identity(item: dict[str, Any]) -> tuple[str, str, str, str, str, tuple[str, ...]]:
                lifecycle = item.get("workerLifecycle", "ephemeral")
                metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
                dependencies = (
                    item.get("dependsOn")
                    if "dependsOn" in item
                    else metadata.get("dependsOn", [])
                )
                return (
                    item.get("name", ""),
                    item.get("writeBoundary") or infer_write_boundary(item.get("kind", "")),
                    lifecycle,
                    item.get("contextPolicy")
                    or ("checkpoint_delta" if lifecycle == "persistent" else "packet_only"),
                    item.get("runtimePreference", "auto"),
                    tuple(dependencies) if isinstance(dependencies, list) else (),
                )

            supplied = [
                lane_plan_identity(item)
                for item in lane_definitions
                if isinstance(item, dict)
            ]
            expected = [lane_plan_identity(item) for item in projected]
            if len(supplied) != len(lane_definitions) or supplied != expected:
                fail(
                    "auto-plan laneDefinitions must match the laneProjection order, "
                    "names, write boundaries, lifecycle, context, and runtime preference."
                )
        else:
            lane_definitions = projected
    lane_names = parse_csv(args.lanes) or DEFAULT_LANES
    lanes = normalize_lane_definitions(lane_names, lane_definitions, 1)
    policy_raw = (
        load_json_value(args.execution_policy)
        if args.execution_policy
        else dict(
            {
                "splitRequirement": args.split_requirement,
                "mode": args.mode,
                "eligibleRuntimes": parse_csv(args.eligible_runtimes),
                "downgradeReason": args.downgrade_reason,
                "requiredWorkerLanes": parse_csv(args.required_worker_lanes),
                "independentReviewRequired": args.independent_review_required,
            },
            **(
                {"runtimeSelectionPolicy": args.runtime_selection_policy}
                if args.runtime_selection_policy
                else {}
            ),
            **(
                {"orchestrationPolicy": args.orchestration_policy}
                if args.orchestration_policy
                else {}
            ),
            **(
                {"nativeThreadUserApproved": args.native_thread_user_approved}
                if args.native_thread_user_approved is not None
                else {}
            ),
            **(
                {"maxParallelWorkers": args.max_parallel_workers}
                if args.max_parallel_workers
                else {}
            ),
            **(
                {"projectAffinityPolicy": args.project_affinity_policy}
                if args.project_affinity_policy
                else {}
            ),
            **(
                {"projectlessUserApproved": args.projectless_user_approved}
                if args.projectless_user_approved is not None
                else {}
            ),
            **(
                {"targetProjectId": args.target_project_id}
                if args.target_project_id
                else {}
            ),
            **(
                {"targetProjectPath": args.target_project_path}
                if args.target_project_path
                else {}
            ),
            **(
                {"projectResolutionSource": args.project_resolution_source}
                if args.project_resolution_source
                else {}
            ),
        )
    )
    policy = normalize_execution_policy(policy_raw, lanes)
    # New states use the declared/default policy. Compatibility is an explicit
    # opt-in for new imports, never inferred from an incomplete new plan.
    if policy["orchestrationPolicy"] != "strict":
        known: set[str] = set()
        for lane in lanes:
            future = [name for name in lane.get("dependsOn", []) if name not in known]
            if future:
                fail(f"Lane {lane['name']} dependencies must appear earlier in lane order: " + ", ".join(future))
            known.add(lane["name"])
    runtime_availability = load_json_value(args.runtime_availability)
    if not isinstance(runtime_availability, dict) or not all(
        isinstance(value, bool) for value in runtime_availability.values()
    ):
        fail("runtime availability must be a JSON object with boolean values.")
    orchestration_plan = plan.get("orchestrationPlan") if plan else None
    if orchestration_plan is None:
        try:
            orchestration_plan = compile_orchestration_plan(
                lanes,
                policy=policy["orchestrationPolicy"],
                active_capability_ids=parse_csv(args.active_capability_ids) or None,
                runtime_availability=runtime_availability,
                available_capabilities=available_capability_catalog(args.available_capabilities),
            )
        except ValueError as error:
            fail(str(error))
    apply_orchestration_projection(lanes, orchestration_plan)
    if (
        plan is None
        and policy["orchestrationPolicy"] == "strict"
        and not orchestration_plan["orchestrationExecutable"]
    ):
        fail(
            "orchestration_invalid: "
            + json.dumps(orchestration_plan["blockers"], ensure_ascii=False)
        )
    if policy["orchestrationPolicy"] == "strict" and orchestration_plan["orchestrationExecutable"]:
        order = {name: index for index, name in enumerate(orchestration_plan["topologicalOrder"])}
        lanes.sort(key=lambda lane: order[lane["name"]])
    risky = any(lane.get("writeBoundary") == "approved-target" for lane in lanes) or policy.get(
        "independentReviewRequired", False
    )
    explicit_mode = (args.enforcement_mode or "").strip()
    enforcement_mode = explicit_mode or ("semantic_strict" if risky else "workflow_only")
    semantic_downgrade_reason = (args.semantic_downgrade_reason or "").strip()
    if enforcement_mode not in ENFORCEMENT_MODES:
        fail(f"Unsupported enforcementMode: {enforcement_mode}")
    if risky and explicit_mode == "workflow_only" and not semantic_downgrade_reason:
        fail("Risk tasks explicitly downgraded to workflow_only require semanticDowngradeReason.")

    if args.task_blueprint and not args.auto_plan:
        task_blueprint, blueprint_compiled = compile_task_blueprint(
            load_json_value(args.task_blueprint), lanes
        )
        require_executable_blueprint(
            blueprint_compiled, enforcement_mode=enforcement_mode, risky=risky
        )
    if plan is not None and enforcement_mode == "semantic_strict" and risky and not plan["planExecutable"]:
        fail("semantic_strict risk init requires an executable SolutionGraph plan: " + json.dumps(plan["blockers"], ensure_ascii=False))
    if orchestration_plan["orchestrationExecutable"] or policy["orchestrationPolicy"] != "strict":
        apply_runtime_selection(policy, lanes)

    contract_spec: dict[str, Any] | None = None
    contract_digest = ""
    if enforcement_mode == "semantic_strict":
        if blueprint_compiled is not None:
            if args.contract_spec:
                supplied_contract_spec = validate_contract_spec(load_json_value(args.contract_spec), lanes)
                require_matching_contract_spec(supplied_contract_spec, blueprint_compiled)
            contract_spec = blueprint_compiled["contractSpec"]
        else:
            raw_contract_spec = load_json_value(args.contract_spec) if args.contract_spec else None
            contract_spec = validate_contract_spec(raw_contract_spec, lanes)
        require_decision_confirmation_gate(contract_spec)
        contract_digest = compute_contract_digest(contract_spec, 1)
    elif blueprint_compiled is not None:
        if args.contract_spec:
            supplied_contract_spec = validate_contract_spec(load_json_value(args.contract_spec), lanes)
            require_matching_contract_spec(supplied_contract_spec, blueprint_compiled)
        contract_spec = blueprint_compiled["contractSpec"]
    state = {
        "schemaVersion": SCHEMA_VERSION,
        "contractRevision": 1,
        "enforcementMode": enforcement_mode,
        "semanticDowngradeReason": semantic_downgrade_reason,
        "contractSpec": contract_spec,
        "contractDigest": contract_digest,
        "taskBlueprint": task_blueprint,
        "blueprintDigest": (
            plan["solutionGraph"]["blueprintDigest"]
            if plan and plan["solutionGraph"]
            else blueprint_compiled["blueprintDigest"] if blueprint_compiled else ""
        ),
        "blueprintTraceability": blueprint_compiled["traceability"] if blueprint_compiled else None,
        "blueprintCompiledExecutable": blueprint_compiled["compiledExecutable"] if blueprint_compiled else None,
        "routingDecision": plan["routingDecision"] if plan else None,
        "solutionGraph": plan["solutionGraph"] if plan else None,
        "solutionGraphDigest": plan["solutionGraph"].get("graphDigest", "") if plan and plan["solutionGraph"] else "",
        "workerPackets": packet_index(plan["workerPackets"]) if plan else {},
        "planDigest": plan["planDigest"] if plan else "",
        "planExecutable": plan["planExecutable"] if plan else None,
        "planBlockers": plan["blockers"] if plan else [],
        "planRuntimeAvailability": load_json_value(args.runtime_availability) if plan else None,
        "planActiveCapabilityIds": parse_csv(args.active_capability_ids) if plan else [],
        "orchestrationPlan": orchestration_plan,
        "orchestrationPlanDigest": orchestration_plan["orchestrationDigest"],
        "orchestrationExecutable": orchestration_plan["orchestrationExecutable"],
        "orchestrationBlockers": orchestration_plan["blockers"],
        "orchestrationWarnings": orchestration_plan["warnings"],
        "availableCapabilities": available_capability_catalog(args.available_capabilities),
        "orchestrationRuntimeAvailability": runtime_availability,
        "orchestrationActiveCapabilityIds": parse_csv(args.active_capability_ids),
        # Only newly initialized SolutionGraph states opt into the durable
        # permit/receipt/result protocol. Older manual checkpoints remain
        # readable and retain their legacy callback contract.
        "correctionEvents": [],
        "approvalRecords": [],
        "goal": require_nonempty(args.goal, "goal"),
        "contract": args.contract or "",
        "executionPolicy": policy,
        "created_at": now(),
        "updated_at": now(),
        "lanes": lanes,
        "workers": [],
        "dispatchAdmission": "claims-v1" if policy["orchestrationPolicy"] == "strict" else "legacy-registration",
        "dispatchClaims": [],
        "finalization": {"status": "open"},
        "revisions": [{"revision": 1, "created_at": now(), "reason": "initial contract"}],
    }
    if plan:
        state.update(
            {
                "verificationEnforcement": "structured-v1",
                "operationPermits": [],
                "operationReceipts": [],
                "verificationResults": [],
            }
        )
    save_state(path, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))


def status(args: argparse.Namespace) -> None:
    state = load_state(Path(args.state).expanduser())
    output = dict(state)
    if state.get("schemaVersion", 1) == SCHEMA_VERSION and "enforcementMode" not in state:
        warning = "Legacy schemaVersion 2 state has no enforcementMode; read without rewriting the state file."
        if has_semantic_risk(state):
            warning += " Semantic migration/upgrade is required before continued operations."
        else:
            warning += " Low-risk state is read as workflow_only."
        output["compatibilityWarnings"] = [warning]
    print(json.dumps(output, ensure_ascii=False, indent=2))


def finalization_gate(state: dict[str, Any]) -> dict[str, Any]:
    """The same terminal check is used by scheduling and actual finalization."""
    incomplete = [lane["name"] for lane in state.get("lanes", []) if lane.get("status") != "done"]
    blockers = ["finalize requires all lanes done: " + ", ".join(incomplete)] if incomplete else []
    if reserved_claims(state):
        blockers.append("Unreconciled dispatch claims remain; bind or reconcile host creation before finalization.")
    if active_workers(state):
        blockers.append("Active worker attempts remain.")
    if not incomplete:
        blockers.extend(evaluate_gate(state)["blockers"])
    return {"allowed": not blockers, "blockers": blockers}


def dispatch_frontier(state: dict[str, Any]) -> dict[str, Any]:
    """Classify every unfinished lane; no empty-queue inference of completion."""
    require_continuation_state(state)
    policy = state.get("executionPolicy", {})
    slots = capacity(state)
    available_slots = slots["availableSlots"]
    active = active_workers(state)
    claims = reserved_claims(state)
    occupied_lanes = {worker.get("lane") for worker in active} | {claim.get("lane") for claim in claims}
    ready: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for lane in state.get("lanes", []):
        if lane.get("status") == "done" or lane["name"] in occupied_lanes:
            continue
        if lane.get("status") not in {"pending", "stale"}:
            attempts = lane_attempts(state, lane["name"])
            action = "complete-lane" if attempts and all(worker.get("status") == "done" for worker in attempts) else "resolve-or-revise"
            blocked.append({"lane": lane["name"], "status": lane.get("status"), "action": action,
                            "blockers": [f"Lane requires {action}: {lane['name']} ({lane.get('status')})"]})
            continue
        if lane_attempts(state, lane["name"]):
            blocked.append({"lane": lane["name"], "action": "complete-or-supersede-worker", "blockers": ["Current worker attempt already exists."]})
            continue
        guard = evaluate_gate(state, lane["name"], require_target_worker=False)
        if guard["allowed"]:
            ready.append(lane)
        else:
            blocked.append({"lane": lane["name"], "blockers": guard["blockers"]})
    selected = ready[:available_slots]
    coordination_lanes = list(dict.fromkeys([worker.get("lane", "") for worker in active] + [lane["name"] for lane in selected]))
    wait_lane_batches = [
        coordination_lanes[index : index + MAX_WAIT_TARGETS_PER_CALL]
        for index in range(0, len(coordination_lanes), MAX_WAIT_TARGETS_PER_CALL)
    ]
    guard = finalization_gate(state)
    finalization = state.get("finalization", {})
    finalized = (
        finalization.get("status") == "finalized"
        and finalization.get("contractRevision") == state["contractRevision"]
        and guard["allowed"]
    )
    status_value = (
        "finalized" if finalized else "ready" if selected
        else "waiting" if active or claims else "finalizable" if guard["allowed"] else "blocked"
    )
    return {
        "status": status_value,
        **slots,
        "readyLanes": selected,
        "deferredReadyLanes": ready[available_slots:],
        "blockedLanes": blocked,
        "pendingDispatchClaims": claims,
        "stoppingWorkers": [
            {"workerId": worker["workerId"], "lane": worker["lane"],
             "runtimeHandle": worker.get("runtimeHandle", ""), "action": "confirm-host-stop"}
            for worker in active if worker.get("runtimeStopPending") is True
        ],
        "finalizationBlockers": guard["blockers"],
        "waitCoordination": {
            "maxTargetsPerCall": MAX_WAIT_TARGETS_PER_CALL,
            "requiresBatching": len(coordination_lanes) > MAX_WAIT_TARGETS_PER_CALL,
            "laneBatches": wait_lane_batches,
            "policy": "stable-rotation-after-completion-or-timeout",
        },
        "orchestration": {
            "policy": policy.get("orchestrationPolicy", "legacy"),
            "semanticOwnerLane": state.get("orchestrationPlan", {}).get("semanticOwnerLane", ""),
            "activeWave": min((lane.get("orchestrationWave", 0) for lane in selected), default=0),
            "parallelFrontier": [lane.get("name", "") for lane in selected],
            "serialEdges": state.get("orchestrationPlan", {}).get("serialEdges", []),
        },
    }


def next_lane(args: argparse.Namespace) -> None:
    state = load_state(Path(args.state).expanduser())
    frontier = dispatch_frontier(state)
    if frontier["readyLanes"]:
        output = {**frontier["readyLanes"][0], "schedulingStatus": "ready"}
    else:
        output = frontier
    print(json.dumps(output, ensure_ascii=False, indent=2))


def ready_lanes(args: argparse.Namespace) -> None:
    """Read the shared scheduling result; actual dispatch still needs admission."""
    state = load_state(Path(args.state).expanduser())
    print(json.dumps(dispatch_frontier(state), ensure_ascii=False, indent=2))


def complete_lane(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    open_events = open_correction_events(state)
    if open_events:
        fail(
            "Open correctionEvents require revise-contract before registration, gate, or completion: "
            + ", ".join(event["id"] for event in open_events)
        )
    lane = find_lane(state, args.lane)
    require_approved_target_authorization(state, lane)
    artifact = (args.artifact or lane.get("artifact", "")).strip()
    if args.decision == "pass":
        if not artifact:
            fail("pass requires a non-empty artifact.")
        if lane.get("kind") in {"user-approval", "approval"}:
            approval_blockers = user_approval_record_blockers(state)
            if approval_blockers:
                fail("user_approval_blocked: " + "; ".join(approval_blockers))
        guard = evaluate_gate(state, lane["name"], include_target_workers=True)
        if not guard["allowed"]:
            fail("gate_blocked: " + "; ".join(guard["blockers"]))
        lane["status"] = "done"
        lane["completed_at"] = now()
    else:
        lane["status"] = args.decision
        lane["completed_at"] = ""
    lane["artifact"] = artifact
    lane["decision"] = args.decision
    lane["notes"] = args.notes or lane.get("notes", "")
    lane["validForRevision"] = state["contractRevision"]
    invalidate_finalization(state, f"lane updated: {lane['name']}")
    save_state(path, state)
    print(json.dumps(lane, ensure_ascii=False, indent=2))


def insert_lane(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    lanes = state.setdefault("lanes", [])
    lane_name = require_nonempty(args.lane, "lane")
    if any(lane.get("name") == lane_name for lane in lanes):
        fail(f"Lane already exists: {lane_name}")
    if args.before and args.after:
        fail("Use only one of --before or --after.")
    if args.status != "pending" or args.artifact or args.decision:
        fail("insert-lane only accepts a pending lane with empty artifact and decision.")
    if args.before:
        index = next((idx for idx, lane in enumerate(lanes) if lane.get("name") == args.before), -1)
        if index < 0:
            fail(f"Before lane not found: {args.before}")
    elif args.after:
        index = next((idx for idx, lane in enumerate(lanes) if lane.get("name") == args.after), -1)
        if index < 0:
            fail(f"After lane not found: {args.after}")
        index += 1
    else:
        index = len(lanes)
    lane = make_lane(
        lane_name,
        state["contractRevision"],
        kind=args.kind,
        worker_required=args.worker_required,
        write_boundary=args.write_boundary,
        worker_lifecycle=args.worker_lifecycle,
        context_policy=args.context_policy,
        runtime_preference=args.runtime_preference,
        depends_on=(
            []
            if args.independent
            else parse_csv(args.depends_on)
            if args.depends_on is not None
            else None
        ),
        purpose=args.purpose,
        contribution_role=args.contribution_role,
        semantic_authority=args.semantic_authority,
        semantic_owner=args.semantic_owner,
        dependency_reasons=load_json_value(args.dependency_reasons) if args.dependency_reasons else {},
        input_contracts=load_json_value(args.input_contracts) if args.input_contracts else [],
        output_contracts=load_json_value(args.output_contracts) if args.output_contracts else [],
        external_inputs=load_json_value(args.external_inputs) if args.external_inputs else [],
        write_targets=load_json_value(args.write_targets) if args.write_targets else [],
        handoff_risk=args.handoff_risk,
        handoff_mode=args.handoff_mode,
        handoff_contract=load_json_value(args.handoff_contract) if args.handoff_contract else {},
        verification_scope=args.verification_scope,
        capability_requirements=parse_csv(args.capability_requirements),
        capability_needs=load_json_value(args.capability_needs) if args.capability_needs else [],
        estimated_effort=args.estimated_effort,
        continuity_required=args.continuity_required,
        orchestration_declared=[
            field for field, declared in (
                ("dependsOn", args.independent or args.depends_on is not None),
                ("purpose", bool(args.purpose)),
                ("contributionRole", bool(args.contribution_role)),
                ("semanticAuthority", bool(args.semantic_authority)),
                ("semanticOwner", args.semantic_owner),
                ("dependencyReasons", bool(args.dependency_reasons)),
                ("inputContracts", bool(args.input_contracts)),
                ("outputContracts", bool(args.output_contracts)),
                ("externalInputs", bool(args.external_inputs)),
                ("writeTargets", bool(args.write_targets)),
                ("handoffRisk", bool(args.handoff_risk)),
                ("handoffMode", bool(args.handoff_mode)),
                ("handoffContract", bool(args.handoff_contract)),
                ("verificationScope", bool(args.verification_scope)),
                ("capabilityRequirements", bool(args.capability_requirements)),
                ("capabilityNeeds", bool(args.capability_needs)),
                ("estimatedEffort", args.estimated_effort != 1),
                ("continuityRequired", args.continuity_required),
            ) if declared
        ],
        status=args.status,
        artifact=args.artifact,
        decision=args.decision,
        notes=args.notes,
    )
    inserted_review_risk = lane.get("kind") == "review" or lane.get("writeBoundary") == "review-only"
    require_risk_enforcement(state, [*lanes, lane], additional_risk=inserted_review_risk)
    if "dependsOn" in lane:
        known_before = {item.get("name") for item in lanes[:index]}
        missing_or_future = [name for name in lane["dependsOn"] if name not in known_before]
        if missing_or_future:
            fail(
                f"Lane {lane_name} dependencies must exist before its insertion point: "
                + ", ".join(missing_or_future)
            )
    if distributed_worker_required(state["executionPolicy"].get("mode", ""), lane):
        lane["workerRequired"] = True
    lanes.insert(index, lane)
    invalidate_finalization(state, f"lane inserted: {lane_name}")
    if lane["workerRequired"]:
        required = state["executionPolicy"]["requiredWorkerLanes"]
        if lane_name not in required:
            required.append(lane_name)
    try:
        orchestration_plan = compile_orchestration_plan(
            lanes,
            policy=state["executionPolicy"].get("orchestrationPolicy", "legacy"),
            active_capability_ids=state.get("orchestrationActiveCapabilityIds") or None,
            runtime_availability=state.get("orchestrationRuntimeAvailability") or {},
            available_capabilities=state.get("availableCapabilities") or [],
        )
    except ValueError as error:
        fail(str(error))
    if (
        state["executionPolicy"].get("orchestrationPolicy") == "strict"
        and not orchestration_plan["orchestrationExecutable"]
    ):
        fail("orchestration_invalid: " + json.dumps(orchestration_plan["blockers"], ensure_ascii=False))
    apply_orchestration_projection(lanes, orchestration_plan)
    state["orchestrationPlan"] = orchestration_plan
    state["orchestrationPlanDigest"] = orchestration_plan["orchestrationDigest"]
    state["orchestrationExecutable"] = orchestration_plan["orchestrationExecutable"]
    state["orchestrationBlockers"] = orchestration_plan["blockers"]
    state["orchestrationWarnings"] = orchestration_plan["warnings"]
    apply_runtime_selection(state["executionPolicy"], lanes)
    save_state(path, state)
    print(json.dumps({"inserted": lane, "lanes": lanes}, ensure_ascii=False, indent=2))


def add_note(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    lane = find_lane(state, args.lane)
    lane["notes"] = args.notes
    save_state(path, state)
    print(json.dumps(lane, ensure_ascii=False, indent=2))


def is_graph_state(state: dict[str, Any]) -> bool:
    return bool(state.get("planDigest"))


def current_packet(state: dict[str, Any], packet_id: str, packet_digest: str) -> dict[str, Any]:
    if not is_graph_state(state):
        fail("Packet identity is only valid for graph-based state.")
    if not state.get("planExecutable"):
        fail("Graph plan is not executable; packet registration and callbacks are blocked.")
    requested_id = require_nonempty(packet_id, "packetId")
    requested_digest = require_nonempty(packet_digest, "packetDigest")
    packets = state.get("workerPackets")
    if not isinstance(packets, dict):
        fail("Graph state is missing indexed workerPackets.")
    packet = next((item for item in packets.values() if item.get("packetId") == requested_id), None)
    if packet is None:
        fail("packetId is not part of the current SolutionGraph plan.")
    graph = state.get("solutionGraph")
    if not isinstance(graph, dict) or graph.get("graphDigest") != state.get("solutionGraphDigest"):
        fail("Graph state has an inconsistent current SolutionGraph digest.")
    if packet.get("graphDigest") != state.get("solutionGraphDigest"):
        fail("WorkerPacket graphDigest does not match the current SolutionGraph.")
    if packet.get("blueprintDigest") != state.get("blueprintDigest"):
        fail("WorkerPacket blueprintDigest does not match the current TaskBlueprint.")
    contract = state.get("contractSpec")
    if not isinstance(contract, dict) or packet.get("contractSpecDigest") != sha256_json(contract):
        fail("WorkerPacket contractSpecDigest does not match the current contract.")
    node_ids = {node.get("id") for node in graph.get("nodes", []) if isinstance(node, dict)}
    if packet.get("nodeId") not in node_ids or packet.get("laneName") != packet.get("nodeId"):
        fail("WorkerPacket node/lane is not part of the current SolutionGraph.")
    try:
        blueprint, compiled = compile_task_blueprint(state.get("taskBlueprint"), state.get("lanes", []))
        if canonical_json(compiled["contractSpec"]) != canonical_json(contract):
            raise ValueError("contractSpec does not match the current TaskBlueprint compilation")
        routing = state.get("routingDecision")
        normalized_graph = validate_solution_graph(graph, routing)
        if normalized_graph.get("graphDigest") != state.get("solutionGraphDigest"):
            raise ValueError("solutionGraphDigest does not match the current SolutionGraph")
        validate_worker_packet(packet, blueprint, compiled["contractSpec"], normalized_graph)
        expected_packets = {
            item["packetId"]: item
            for item in compile_worker_packets(blueprint, compiled, normalized_graph, routing)
        }
        if canonical_json(packet) != canonical_json(expected_packets.get(requested_id)):
            raise ValueError("packet does not match the current compiled WorkerPacket")
        if packet.get("packetDigest") != requested_digest:
            raise ValueError("packetDigest does not match the registration request")
    except (SystemExit, ValueError, KeyError, TypeError):
        fail("packet_integrity_error")
    return packet


def packet_lane_boundary(packet: dict[str, Any]) -> str:
    boundary = packet.get("writePolicySlice", {}).get("writeBoundary", "")
    return "read-only" if boundary == "none" else boundary


def claim_dispatch(args: argparse.Namespace) -> None:
    """Reserve capacity before calling a host's non-idempotent task creation tool."""
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    lane = find_lane(state, args.lane)
    request_id = require_nonempty(args.request_id, "requestId")
    existing = any(item.get("requestId") == request_id for item in state.get("dispatchClaims", []))
    evidence = load_json_value(args.capability_evidence)
    if not isinstance(evidence, dict) or any(not isinstance(key, str) or not isinstance(value, str) or not value.strip() for key, value in evidence.items()):
        fail("capabilityEvidence must map capability IDs to non-empty host-discovery evidence.")
    if not existing:
        require_approved_target_authorization(state, lane)
        if lane.get("status") not in {"pending", "stale"}:
            fail("lane_not_dispatchable: complete or explicitly supersede/revise the current attempt")
        guard = evaluate_gate(state, lane["name"], require_target_worker=False)
        if not guard["allowed"]:
            fail("upstream_gate_blocked: " + "; ".join(guard["blockers"]))
        if state.get("executionPolicy", {}).get("orchestrationPolicy") == "strict":
            if lane.get("capabilityRouteStatus") != "bound" or not lane.get("capabilityBindings"):
                fail("capability_unbound: choose exact lane capabilities before dispatch")
            route = next((item for item in state.get("orchestrationPlan", {}).get("capabilityRoutes", []) if item.get("lane") == lane["name"]), {})
            unverified = {item["id"] for item in route.get("selected", []) if item.get("availability") != "confirmed"}
            missing = sorted(unverified - set(evidence))
            if missing:
                fail("capability_runtime_unverified: provide host-discovery evidence for " + ", ".join(missing))
    try:
        claim = reserve_dispatch(state, lane["name"], request_id, evidence, now())
    except AdmissionError as error:
        fail(str(error))
    if not existing:
        save_state(path, state)
    action = "create" if not existing else "already-registered" if claim["status"] == "bound" else "reconcile-existing-creation"
    print(json.dumps({**claim, "creationAction": action, "capacity": capacity(state)}, ensure_ascii=False, indent=2))


def release_dispatch_command(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    try:
        claim = release_dispatch(state, args.claim_id, args.outcome, require_nonempty(args.evidence, "evidence"), now())
    except AdmissionError as error:
        fail(str(error))
    save_state(path, state)
    print(json.dumps(claim, ensure_ascii=False, indent=2))


def register_worker(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    revision = state["contractRevision"]
    requested_revision = args.contract_revision or revision
    if requested_revision != revision:
        fail(f"Worker contractRevision must equal current revision {revision}.")
    lane = find_lane(state, args.lane)
    packet: dict[str, Any] | None = None
    if is_graph_state(state):
        if (args.task or "").strip() or (args.prompt or "").strip():
            fail("packet_task_override_forbidden")
        packet = current_packet(state, args.packet_id, args.packet_digest)
        if packet["laneName"] != lane["name"]:
            fail("packetId must belong to the registered lane.")
        if packet_lane_boundary(packet) != lane["writeBoundary"]:
            fail("WorkerPacket write boundary does not match the registered lane.")
    require_approved_target_authorization(state, lane)
    if lane.get("status") == "done":
        fail(f"Cannot register a worker for completed lane: {lane['name']}")
    upstream_guard = evaluate_gate(state, lane["name"], require_target_worker=False)
    if not upstream_guard["allowed"]:
        fail("upstream_gate_blocked: " + "; ".join(upstream_guard["blockers"]))
    workers = state.setdefault("workers", [])
    worker_id = require_nonempty(args.worker_id, "workerId")
    if any(worker.get("workerId") == worker_id for worker in workers):
        fail(f"Worker already exists: {worker_id}")
    runtime = args.lane_runtime
    if runtime not in LANE_RUNTIMES:
        fail(f"Unsupported laneRuntime: {runtime}")
    runtime_profile = RUNTIME_REGISTRY.get(runtime)
    is_independent_runtime = bool(runtime_profile and runtime_profile.independent)
    request_id = (args.request_id or "").strip()
    if is_independent_runtime and not request_id:
        fail("requestId is required for independent workers.")
    if request_id and any(worker.get("requestId") == request_id for worker in workers):
        fail(f"requestId already exists: {request_id}")
    thread_id = (args.thread_id or "").strip()
    runtime_handle = (args.runtime_handle or "").strip()
    if runtime_profile and runtime_profile.identity_binding == "thread_id_equals_runtime_handle":
        if not thread_id:
            fail(f"{runtime} requires a non-empty threadId.")
        if not runtime_handle:
            fail(f"{runtime} requires runtimeHandle equal to threadId.")
        if thread_id != runtime_handle:
            fail(f"{runtime} runtimeHandle must equal threadId.")
    if is_independent_runtime and not runtime_handle:
        fail("runtimeHandle is required for independent workers.")
    if runtime_handle and any(
        worker.get("runtimeHandle") == runtime_handle
        and worker.get("contractRevision") == revision
        and worker.get("status") in ACTIVE_WORKER_STATUSES
        for worker in workers
    ):
        fail(f"runtimeHandle already has a current worker identity: {runtime_handle}")
    if lane.get("workerRequired") and not is_independent_runtime:
        fail(f"Lane {lane['name']} requires a real independent worker runtime.")
    policy = state["executionPolicy"]
    if is_independent_runtime and runtime not in policy.get("eligibleRuntimes", []):
        fail(f"laneRuntime is not eligible under executionPolicy: {runtime}")
    if (
        is_distributed_mode(policy.get("mode", ""))
        and policy.get("runtimeSelectionPolicy") == "native_session_required"
        and (
            runtime_profile is None
            or not profile_satisfies(
                runtime_profile,
                requirement_for_lane(lane, "native_session_required"),
            )
        )
    ):
        fail(
            "runtimeSelectionPolicy=native_session_required requires an independent, "
            "user-visible, project-capable runtime profile."
        )
    preference = lane.get("runtimePreference", "auto")
    lifecycle = lane.get("workerLifecycle", "ephemeral")
    if preference in TRUE_WORKER_RUNTIMES and runtime != preference:
        fail(
            f"Lane {lane['name']} requires runtimePreference={preference}; got {runtime}."
        )
    if lifecycle == "persistent" and (
        runtime_profile is None or not runtime_profile.supports_persistent
    ):
        fail(
            f"Lane {lane['name']} is persistent and requires native_thread_lane today; "
            "the capability gate is supportsPersistent=true."
        )
    if (
        runtime_profile
        and runtime_profile.requires_explicit_approval
        and runtime not in approved_runtime_ids(policy)
    ):
        fail(
            f"{runtime} requires explicit runtime approval through "
            f"executionPolicy.{runtime_profile.approval_policy_field}=true."
        )
    project_id = (args.project_id or "").strip()
    project_environment = (args.project_environment or "").strip()
    project_target_type = (args.project_target_type or "").strip() or (
        "project" if project_id else "projectless"
    )
    if runtime_profile and not runtime_profile.supports_scope(project_target_type):
        fail(
            f"projectTargetType={project_target_type} is not supported by the "
            f"{runtime} runtime profile."
        )
    target_project_id = str(policy.get("targetProjectId", "") or "").strip()
    project_affinity_policy = policy.get("projectAffinityPolicy", "legacy_best_effort")
    project_affinity_runtime = bool(
        runtime_profile
        and runtime_profile.user_visible
        and runtime_profile.supports_scope("project")
    )
    if project_affinity_runtime:
        if project_affinity_policy == "inherit_or_resolve_required":
            if not target_project_id:
                fail(
                    "project_affinity_required: executionPolicy is missing targetProjectId."
                )
            if not project_id:
                fail(
                    f"project_affinity_required: {runtime} requires the created "
                    "Session projectId."
                )
            if project_target_type != "project":
                fail(
                    f"project_affinity_required: {runtime} requires "
                    "projectTargetType=project."
                )
            if project_id != target_project_id:
                fail(
                    "project_affinity_mismatch: worker projectId must equal "
                    f"executionPolicy.targetProjectId ({target_project_id})."
                )
            if project_environment not in PROJECT_ENVIRONMENTS:
                fail(
                    f"project_affinity_required: {runtime} requires "
                    "projectEnvironment=local or worktree."
                )
        elif target_project_id and project_target_type != "project":
            fail("A locked targetProjectId requires projectTargetType=project.")
        elif target_project_id and project_id != target_project_id:
            fail(
                "project_affinity_mismatch: worker projectId must equal "
                f"executionPolicy.targetProjectId ({target_project_id})."
            )
        elif project_target_type == "project":
            if not project_id:
                fail("projectTargetType=project requires a non-empty projectId.")
            if project_environment not in PROJECT_ENVIRONMENTS:
                fail("projectEnvironment must be local or worktree for a project target.")
        elif project_target_type == "projectless" and (project_id or project_environment):
            fail("projectTargetType=projectless cannot include projectId or projectEnvironment.")
        elif (
            project_target_type == "projectless"
            and project_affinity_policy == "allow_projectless"
            and not policy.get("projectlessUserApproved", False)
        ):
            fail("Projectless Session worker requires projectlessUserApproved=true.")
    callback_expected = not args.no_callback_expected
    if is_independent_runtime and not callback_expected:
        fail("Independent workers must require a callback.")
    callback_mode = args.callback_mode_expected or (
        runtime_profile.default_callback_mode
        if runtime_profile
        else "controller_poll_allowed"
    )
    if runtime_profile and callback_mode not in runtime_profile.callback_modes:
        fail(
            f"callbackModeExpected={callback_mode} is not supported by the "
            f"{runtime} runtime profile."
        )
    thread_tool_check = (args.thread_tool_check or "").strip()
    if is_independent_runtime and not thread_tool_check:
        fail("Independent workers require a non-empty threadToolCheck.")
    controller_thread_id = (args.controller_thread_id or "").strip()
    reply_to_thread_id = (args.reply_to_thread_id or "").strip()
    if runtime_profile and runtime_profile.requires_thread_routing and callback_mode == "active_message_required":
        if not controller_thread_id or not reply_to_thread_id:
            fail("Thread-routed active_message_required workers require controllerThreadId and replyToThreadId.")
    write_boundary = (args.write_boundary or lane["writeBoundary"]).strip()
    if write_boundary != lane["writeBoundary"]:
        fail(f"Worker writeBoundary must match lane boundary {lane['writeBoundary']}.")
    tool_profile = (args.tool_profile or "").strip()
    credential_policy = (args.credential_policy or "").strip()
    if write_boundary == "approved-target" and (not tool_profile or not credential_policy):
        fail("approved-target workers require non-empty toolProfile and credentialPolicy.")
    reviews_worker_ids = parse_csv(args.reviews_worker_ids)
    if is_artifact_review_lane(lane):
        writer_workers = review_subject_workers(state, lane["name"])
        known_ids = {worker["workerId"] for worker in writer_workers}
        unknown = sorted(set(reviews_worker_ids) - known_ids)
        if unknown:
            fail(f"reviewsWorkerIds reference non-current or non-preceding approved-target writers: {', '.join(unknown)}")
        if policy.get("independentReviewRequired"):
            missing = sorted(known_ids - set(reviews_worker_ids))
            if not known_ids:
                fail("Independent review requires a preceding current-revision approved-target writer.")
            if missing:
                fail(f"Review worker must cover preceding current approved-target writers: {', '.join(missing)}")
            writer_handles = {worker.get("runtimeHandle") for worker in writer_workers}
            if runtime_handle in writer_handles:
                fail("Review worker must use an independent runtime identity.")
    elif lane.get("kind") in DECISION_REVIEW_KINDS:
        subject_workers = review_subject_workers(state, lane["name"])
        known_ids = {worker["workerId"] for worker in subject_workers}
        unknown = sorted(set(reviews_worker_ids) - known_ids)
        missing = sorted(known_ids - set(reviews_worker_ids))
        if not known_ids:
            fail("Decision review requires a completed current-revision dependency worker.")
        if unknown:
            fail(f"reviewsWorkerIds reference non-current decision-review subjects: {', '.join(unknown)}")
        if missing:
            fail(f"Decision review worker must cover dependency workers: {', '.join(missing)}")
        subject_handles = {worker.get("runtimeHandle") for worker in subject_workers}
        if runtime_handle in subject_handles:
            fail("Decision review worker must use an independent runtime identity.")
    contract_digest = (args.contract_digest or "").strip()
    deliverable_fingerprint = (args.deliverable_fingerprint or "").strip()
    if is_semantic_strict(state):
        if contract_digest != state.get("contractDigest"):
            fail("Worker contractDigest must match the current semantic contract digest.")
        if deliverable_fingerprint != state["contractSpec"]["deliverableFingerprint"]:
            fail("Worker deliverableFingerprint must match the current semantic deliverable fingerprint.")
    if packet is not None:
        task = canonical_json(packet)
        prompt = render_worker_prompt(packet)
    else:
        task = (args.task or "").strip()
        prompt = (args.prompt or "").strip()
        task = require_nonempty(task, "task")
    runtime_envelope = (
        "Runtime envelope:\n"
        f"- workerLifecycle: {lifecycle}\n"
        f"- contextPolicy: {lane.get('contextPolicy', 'packet_only')}\n"
        f"- runtimePreference: {preference}\n"
        f"- projectTargetType: {project_target_type}\n"
        f"- projectId: {project_id or 'projectless'}\n"
        f"- projectEnvironment: {project_environment or 'projectless'}\n"
        "- Context rule: use only the assigned task/packet and declared upstream "
        "artifacts; do not hydrate unrelated controller history."
    )
    prompt = f"{prompt}\n{runtime_envelope}".strip()
    worker = {
        "workerId": worker_id,
        "threadId": thread_id,
        "runtimeHandle": runtime_handle,
        "requestId": request_id,
        "dispatchClaimId": (args.claim_id or "").strip(),
        "contractRevision": revision,
        "contractDigest": contract_digest,
        "deliverableFingerprint": deliverable_fingerprint,
        "validForRevision": revision,
        "controllerThreadId": controller_thread_id,
        "replyToThreadId": reply_to_thread_id,
        "projectTargetType": project_target_type,
        "projectId": project_id,
        "projectEnvironment": project_environment,
        "lane": lane["name"],
        "laneRuntime": runtime,
        "runtimeRegistryVersion": RUNTIME_REGISTRY.registry_version if runtime_profile else "",
        "runtimeProfileVersion": runtime_profile.profile_version if runtime_profile else "",
        "runtimeProfileFingerprint": runtime_profile.fingerprint if runtime_profile else "",
        "workerLifecycle": lifecycle,
        "contextPolicy": lane.get("contextPolicy", "packet_only"),
        "runtimePreference": preference,
        "task": task,
        "prompt": prompt,
        "packetId": packet["packetId"] if packet else "",
        "packetDigest": packet["packetDigest"] if packet else "",
        "packetNodeId": packet["nodeId"] if packet else "",
        "toolProfile": tool_profile,
        "credentialPolicy": credential_policy,
        "threadToolCheck": thread_tool_check,
        "writeBoundary": write_boundary,
        "reviewsWorkerIds": reviews_worker_ids,
        "callbackExpected": callback_expected,
        "callbackModeExpected": callback_mode,
        "callbackModeObserved": "",
        "callbackReceived": False,
        "callbackMessage": "",
        "status": "pending",
        "artifact": "",
        "artifactManifest": [],
        "checkResults": [],
        "writeReceipt": None,
        "operationReceiptId": "",
        "operationReceiptIds": [],
        "verificationSummary": None,
        "decision": "",
        "notes": "",
        "created_at": now(),
        "updated_at": now(),
    }
    claim_id = (args.claim_id or "").strip()
    if lane.get("status") not in {"pending", "stale", "running"}:
        fail("lane_not_dispatchable: explicitly supersede/revise before retrying a failed or blocked lane")
    if is_independent_runtime and state.get("dispatchAdmission") == "claims-v1" and not claim_id:
        fail("dispatch_claim_required: reserve capacity before creating the worker task")
    try:
        claim = registration_claim(state, lane["name"], request_id, claim_id)
    except AdmissionError as error:
        fail(str(error))
    workers.append(worker)
    if claim is not None:
        claim.update(status="bound", workerId=worker_id, runtimeHandle=runtime_handle, updated_at=now())
    lane["status"] = "running"
    lane["completed_at"] = ""
    save_state(path, state)
    print(json.dumps(worker, ensure_ascii=False, indent=2))


def update_worker(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    worker = next((item for item in state.get("workers", []) if item.get("workerId") == args.worker_id), None)
    if worker is None:
        fail(f"Worker not found: {args.worker_id}")
    if worker.get("contractRevision") != state["contractRevision"] and args.status not in {"superseded", "stale", "resolved"}:
        fail("Old-revision workers cannot be updated as active workers.")
    if args.status == "done" or args.decision == "pass":
        fail("Use record-callback to set a worker done/pass.")
    stop_evidence = (args.runtime_stop_evidence or "").strip()
    if stop_evidence and args.status not in {"superseded", "stale", "resolved"}:
        fail("runtimeStopEvidence is only accepted when retiring a worker.")
    if args.status in {"pending", "running"} and worker.get("status") not in {"pending", "running"}:
        if find_lane(state, worker["lane"]).get("status") == "done":
            fail("Cannot reactivate a worker for a completed lane; revise the contract first.")
        try:
            require_admission({**state, "workers": [item for item in state.get("workers", []) if item is not worker]}, worker["lane"])
        except AdmissionError as error:
            fail(str(error))
    if args.status in {"superseded", "stale", "resolved"}:
        if stop_evidence:
            worker["runtimeStopPending"] = False
            worker["runtimeStopEvidence"] = stop_evidence
        elif worker.get("status") in {"pending", "running"}:
            worker["runtimeStopPending"] = True
    worker["status"] = args.status
    if args.artifact:
        worker["artifact"] = args.artifact
    if args.status in {"superseded", "stale"}:
        worker["decision"] = ""
    elif args.decision:
        worker["decision"] = args.decision
    if args.notes:
        worker["notes"] = args.notes
    worker["updated_at"] = now()
    if args.status in {"superseded", "stale", "resolved"} and worker.get("contractRevision") == state["contractRevision"]:
        lane = find_lane(state, worker["lane"])
        if lane.get("status") != "done" and not lane_attempts(state, lane["name"]):
            # This is an explicit lifecycle action, not an automatic retry of
            # blocked/needs-work callbacks. Contract corrections use revision.
            lane["status"] = "pending"
            lane["decision"] = ""
            lane["completed_at"] = ""
    invalidate_finalization(state, f"worker updated: {worker['workerId']}")
    save_state(path, state)
    print(json.dumps(worker, ensure_ascii=False, indent=2))


def list_workers(args: argparse.Namespace) -> None:
    state = load_state(Path(args.state).expanduser())
    if state.get("schemaVersion", 1) == SCHEMA_VERSION and "enforcementMode" not in state:
        warning = "warning: legacy schemaVersion 2 state has no enforcementMode; workers are read without rewriting state."
        if has_semantic_risk(state):
            warning += " Semantic migration/upgrade is required before continued operations."
        else:
            warning += " Low-risk state is treated as workflow_only."
        print(warning, file=sys.stderr)
    print(json.dumps(state.get("workers", []), ensure_ascii=False, indent=2))


def feedback_classification_for_state(state: dict[str, Any] | None, feedback: str) -> dict[str, Any]:
    lane_names = [lane.get("name", "") for lane in (state or {}).get("lanes", [])]
    contract_spec = (state or {}).get("contractSpec")
    governance = contract_spec.get("decisionGovernance", {}) if isinstance(contract_spec, dict) else {}
    if not isinstance(governance, dict):
        governance = {}
    try:
        return classify_feedback(
            feedback,
            lane_names=lane_names,
            governance=governance,
        )
    except ValueError as error:
        fail(str(error))


def classify_feedback_command(args: argparse.Namespace) -> None:
    state = load_state(Path(args.state).expanduser()) if args.state else None
    print(
        json.dumps(
            feedback_classification_for_state(state, args.feedback),
            ensure_ascii=False,
            indent=2,
        )
    )


def ingest_feedback(args: argparse.Namespace) -> None:
    """Classify feedback and atomically open a correction when required."""
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    feedback = require_nonempty(args.feedback, "feedback")
    classification = feedback_classification_for_state(state, feedback)
    if not classification["requiresContractRevision"]:
        print(
            json.dumps(
                {"classification": classification, "correctionEvent": None},
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    recommended = require_nonempty(
        classification.get("suggestedInvalidFromLane"), "suggestedInvalidFromLane"
    )
    find_lane(state, recommended)
    feedback_digest = hashlib.sha256(feedback.encode("utf-8")).hexdigest()
    existing = next(
        (
            event for event in state.get("correctionEvents", [])
            if event.get("contractRevision") == state["contractRevision"]
            and event.get("feedbackDigest") == feedback_digest
            and event.get("status") == "open"
        ),
        None,
    )
    if existing is not None:
        print(
            json.dumps(
                {"classification": classification, "correctionEvent": existing, "idempotentReplay": True},
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    event_id = (args.event_id or f"feedback-{sha256_json({'revision': state['contractRevision'], 'feedbackDigest': feedback_digest})[:20]}").strip()
    if any(event.get("id") == event_id for event in state.get("correctionEvents", [])):
        fail(f"Correction event ID already exists: {event_id}")
    categories = classification.get("impactedCategories", [])
    event = {
        "id": require_nonempty(event_id, "eventId"),
        "status": "open",
        "source": "user_feedback",
        "fromLane": "controller",
        "summary": feedback,
        "feedbackDigest": feedback_digest,
        "category": categories[0] if categories else "contract_correction",
        "requirementIds": classification["impactedRequirementIds"],
        "recommendedInvalidFromLane": recommended,
        "preserveUnmentioned": classification["preserveUnmentioned"],
        "matchedTriggers": classification["matchedTriggers"],
        "contractRevision": state["contractRevision"],
        "created_at": now(),
    }
    state.setdefault("correctionEvents", []).append(event)
    stale_current_approvals(state, f"user feedback correction opened: {event_id}")
    invalidate_finalization(state, f"user feedback correction opened: {event_id}")
    save_state(path, state)
    print(
        json.dumps(
            {"classification": classification, "correctionEvent": event},
            ensure_ascii=False,
            indent=2,
        )
    )


def record_correction(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    event_id = require_nonempty(args.event_id, "eventId")
    if any(event.get("id") == event_id for event in state.get("correctionEvents", [])):
        fail(f"Correction event ID already exists: {event_id}")
    recommended = require_nonempty(args.recommended_invalid_from_lane, "recommendedInvalidFromLane")
    find_lane(state, recommended)
    requirement_ids = parse_csv(args.requirement_ids)
    if not requirement_ids:
        fail("requirementIds must contain at least one requirement ID.")
    event = {
        "id": event_id,
        "status": "open",
        "source": "controller",
        "fromLane": "controller",
        "summary": require_nonempty(args.summary, "summary"),
        "category": require_nonempty(args.category, "category"),
        "requirementIds": requirement_ids,
        "recommendedInvalidFromLane": recommended,
        "contractRevision": state["contractRevision"],
        "created_at": now(),
    }
    state.setdefault("correctionEvents", []).append(event)
    stale_current_approvals(state, f"correction opened: {event_id}")
    invalidate_finalization(state, f"correction opened: {event_id}")
    save_state(path, state)
    print(json.dumps(event, ensure_ascii=False, indent=2))


def record_approval(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    if not is_semantic_strict(state):
        fail("record-approval requires semantic_strict contract state.")
    if open_correction_events(state):
        fail("Open correctionEvents block user approval recording.")
    artifact_id = require_nonempty(args.artifact_id, "artifactId")
    artifact_fingerprint = require_nonempty(args.artifact_fingerprint, "artifactFingerprint")
    artifact = current_manifest_artifacts(state).get(artifact_id)
    if artifact is None:
        fail(f"Approval artifact is not available from a current-revision pass callback: {artifact_id}")
    if artifact.get("artifactFingerprint") != artifact_fingerprint:
        fail("artifactFingerprint must match the current artifactManifest fingerprint.")
    revision = state["contractRevision"]
    for approval in state.get("approvalRecords", []):
        if (
            approval.get("status") == "active"
            and approval.get("contractRevision") == revision
            and approval.get("artifactId") == artifact_id
        ):
            approval.update({"status": "stale", "staleReason": "superseded by newer approval", "stale_at": now()})
    approval = {
        "id": (args.approval_id or sha256_json(
            {
                "contractRevision": revision,
                "artifactId": artifact_id,
                "artifactFingerprint": artifact_fingerprint,
                "approver": args.approver,
                "timestamp": args.timestamp or now(),
            }
        )[:24]),
        "status": "active",
        "contractRevision": revision,
        "artifactId": artifact_id,
        "artifactFingerprint": artifact_fingerprint,
        "approver": require_nonempty(args.approver, "approver"),
        "timestamp": require_nonempty(args.timestamp or now(), "timestamp"),
        "recorded_at": now(),
    }
    approval["id"] = require_nonempty(approval["id"], "approvalId")
    if any(item.get("id") == approval["id"] for item in state.get("approvalRecords", [])):
        fail(f"Approval record ID already exists: {approval['id']}")
    state.setdefault("approvalRecords", []).append(approval)
    invalidate_finalization(state, f"approval recorded: {approval['id']}")
    save_state(path, state)
    print(json.dumps(approval, ensure_ascii=False, indent=2))


def issue_operation_permit_command(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    if not structured_verification_enforced(state):
        fail("issue-operation-permit requires a new structured graph state.")
    worker = next((item for item in state.get("workers", []) if item.get("workerId") == args.worker_id), None)
    if worker is None or worker.get("contractRevision") != state["contractRevision"] or worker.get("status") not in {"pending", "running"}:
        fail("Operation permit requires an active current-revision worker.")
    if worker.get("laneRuntime") not in TRUE_WORKER_RUNTIMES or not str(worker.get("runtimeHandle", "")).strip():
        fail("Operation permit requires an active worker runtime handle.")
    lane = find_lane(state, worker.get("lane", ""))
    require_approved_target_authorization(state, lane)
    packet = current_packet(state, worker.get("packetId", ""), worker.get("packetDigest", ""))
    if lane.get("writeBoundary") != "approved-target":
        fail("Only approved-target workers may receive operation permits.")
    payload = load_json_value(args.payload)
    if not isinstance(payload, dict):
        fail("Operation permit payload must be a JSON object.")
    readback_spec = load_json_value(args.readback_spec)
    if not isinstance(readback_spec, dict):
        fail("Operation permit readbackSpec must be a JSON object.")
    target_id = require_nonempty(args.target_id, "targetId")
    target_locator = require_nonempty(args.target_locator, "targetLocator")
    action = require_nonempty(args.action, "action")
    operation_id = require_nonempty(args.operation_id, "operationId")
    options = load_json_value(args.adapter_options) if args.adapter_options else {}
    if not isinstance(options, dict):
        fail("adapterOptions must be a JSON object.")
    adapter = restricted_operation_adapter(
        args.adapter_id,
        options,
        operation_id=operation_id,
        action=action,
        target_locator=target_locator,
    )
    if adapter.adapter_id != args.adapter_id:
        fail("Operation adapter identity is inconsistent.")
    if args.adapter_id == "lark-cli":
        try:
            adapter.validate_execute_descriptor(payload)
            adapter.validate_readback_descriptor(readback_spec)
        except (TypeError, ValueError, RuntimeError) as error:
            fail(f"Operation descriptor rejected: {error}")
    policy = packet.get("writePolicySlice", {})
    allowed_target = any(
        item.get("id") == target_id and item.get("locator") == target_locator
        for item in policy.get("targets", [])
    )
    if not allowed_target or action not in policy.get("allowedActions", []):
        fail("Operation target/action must match the current WorkerPacket allowlist.")
    capability_id = require_nonempty(args.capability_id, "capabilityId")
    capability_ids = {
        item.get("capabilityId") for item in packet.get("capabilityBindings", []) if isinstance(item, dict)
    }
    if capability_id not in capability_ids:
        fail("Operation capabilityId is not bound by the current WorkerPacket.")
    approval_refs = parse_csv(args.approval_refs)
    current_approvals = {
        item.get("id") for item in state.get("approvalRecords", [])
        if item.get("status") == "active" and item.get("contractRevision") == state["contractRevision"]
    }
    if any(reference not in current_approvals for reference in approval_refs):
        fail("Operation approvalRefs must name active current-revision approvals.")
    requires_approval = (
        is_destructive_action(action)
        and bool(policy.get("destructiveActionsRequireApproval"))
    ) or bool(packet.get("userApprovalRequired")) or bool(next(
        (item.get("userApprovalRequired", False) for item in policy.get("targets", [])
         if item.get("id") == target_id and item.get("locator") == target_locator), False
    ))
    if requires_approval and (not approval_refs or not current_approvals):
        fail("Operation requires an active user approval reference.")
    permit_id = require_nonempty(args.permit_id, "permitId")
    permits, _, _ = operation_ledgers(state)
    if ledger_entry(permits, "permitId", permit_id) is not None:
        fail("Operation permit ID already exists.")
    identities = operation_identity(state, worker, packet)
    try:
        permit = issue_permit(
            permitId=permit_id,
            **identities,
            workerId=worker["workerId"], runtimeHandle=require_nonempty(worker.get("runtimeHandle"), "worker.runtimeHandle"),
            capabilityId=capability_id, operationId=operation_id,
            targetId=target_id, targetLocator=target_locator, action=action, payload=payload,
            restrictedFields=parse_csv(args.restricted_fields), approvalRefs=approval_refs,
            idempotencyKey=require_nonempty(args.idempotency_key, "idempotencyKey"), adapterId=args.adapter_id,
            readbackSpec=readback_spec, expiresAt=require_nonempty(args.expires_at, "expiresAt"),
        )
    except PermitError as error:
        fail(f"Operation permit rejected: {error}")
    permit.update({"contractRevision": state["contractRevision"], "lane": lane["name"], "adapterOptions": options, "issuedBy": "task-controller"})
    permits.append(permit)
    invalidate_finalization(state, f"operation permit issued: {permit_id}")
    save_state(path, state)
    print(json.dumps(permit, ensure_ascii=False, indent=2))


def dispatch_operation_command(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    if not structured_verification_enforced(state):
        fail("dispatch-operation requires a new structured graph state.")
    permits, receipts, _ = operation_ledgers(state)
    permit_id = require_nonempty(args.permit_id, "permitId")
    permit = ledger_entry(permits, "permitId", permit_id)
    if not isinstance(permit, dict):
        fail("Operation permit is not present in the state ledger.")
    worker, _ = require_current_operation_permit(state, permit)
    existing = next(
        (receipt for receipt in receipts if receipt.get("permitId") == permit_id),
        None,
    )
    if existing is not None:
        print(json.dumps(existing, ensure_ascii=False, indent=2))
        return
    claim_id = (args.claim_id or f"dispatch:{permit_id}").strip()
    if permit.get("status") == "claimed":
        fail("operation_requires_reconciliation: a prior dispatch may have reached the provider; do not execute it again.")
    if permit.get("status") != "issued":
        fail(f"Operation permit cannot be dispatched in status {permit.get('status', '')}.")
    try:
        claimed = claim_permit(permit, claim_id)
    except PermitError as error:
        fail(f"Operation dispatch claim rejected: {error}")
    claimed.update({key: value for key, value in permit.items() if key not in claimed})
    replace_ledger_entry(permits, "permitId", permit_id, claimed)
    # Persist the claim before touching the external provider. If this process
    # dies after the provider call, a retry is forced into readback-only
    # reconciliation instead of executing the write again.
    save_state(path, state)
    try:
        adapter = restricted_operation_adapter(
            permit["adapterId"],
            permit.get("adapterOptions", {}),
            operation_id=permit["operationId"],
            action=permit["action"],
            target_locator=permit["targetLocator"],
        )
        dispatcher = Dispatcher({adapter.adapter_id: adapter})
        dispatcher.issue(claimed)
        receipt = dispatcher.dispatch(claimed, claim_id=claim_id)
        replace_ledger_entry(permits, "permitId", permit_id, dispatcher.permits.get(permit_id))
    except PermitError as error:
        fail(f"Operation dispatch rejected: {error}")
    receipt.update({
        "contractRevision": state["contractRevision"], "workerId": worker["workerId"],
        "runtimeHandle": worker["runtimeHandle"], "lane": worker["lane"],
        "packetId": worker["packetId"], "packetDigest": worker["packetDigest"],
    })
    replace_ledger_entry(receipts, "receiptId", receipt["receiptId"], receipt)
    invalidate_finalization(state, f"operation dispatched: {permit_id}")
    save_state(path, state)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def reconcile_operation_command(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    if not structured_verification_enforced(state):
        fail("reconcile-operation requires a new structured graph state.")
    permits, receipts, _ = operation_ledgers(state)
    permit_id = require_nonempty(args.permit_id, "permitId")
    permit = ledger_entry(permits, "permitId", permit_id)
    if not isinstance(permit, dict):
        fail("Operation permit is not present in the state ledger.")
    worker, _ = require_current_operation_permit(state, permit)
    if permit.get("status") != "claimed" or not permit.get("claimId"):
        fail("reconcile-operation requires an interrupted claimed permit.")
    if any(receipt.get("permitId") == permit_id for receipt in receipts):
        fail("Operation already has a dispatcher receipt; use that receipt or investigate reconcile_required status.")
    adapter = restricted_operation_adapter(
        permit["adapterId"], permit.get("adapterOptions", {}),
        operation_id=permit["operationId"], action=permit["action"],
        target_locator=permit["targetLocator"],
    )
    try:
        updated, receipt = reconcile_claimed_permit(
            permit, adapter, claim_id=permit["claimId"]
        )
    except PermitError as error:
        fail(f"Operation reconciliation rejected: {error}")
    updated.update({key: value for key, value in permit.items() if key not in updated})
    replace_ledger_entry(permits, "permitId", permit_id, updated)
    receipt.update({
        "contractRevision": state["contractRevision"], "workerId": worker["workerId"],
        "runtimeHandle": worker["runtimeHandle"], "lane": worker["lane"],
        "packetId": worker["packetId"], "packetDigest": worker["packetDigest"],
    })
    replace_ledger_entry(receipts, "receiptId", receipt["receiptId"], receipt)
    invalidate_finalization(state, f"operation reconciled: {permit_id}")
    save_state(path, state)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def revoke_operation_permit_command(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    if not structured_verification_enforced(state):
        fail("revoke-operation-permit requires a new structured graph state.")
    permits, _, _ = operation_ledgers(state)
    permit_id = require_nonempty(args.permit_id, "permitId")
    permit = ledger_entry(permits, "permitId", permit_id)
    if not isinstance(permit, dict):
        fail("Operation permit is not present in the state ledger.")
    try:
        replace_ledger_entry(permits, "permitId", permit_id, revoke_permit(permit))
    except PermitError as error:
        fail(f"Operation permit cannot be revoked: {error}")
    updated = ledger_entry(permits, "permitId", permit_id)
    assert updated is not None
    updated["revokedReason"] = (args.reason or "controller revoked").strip()
    save_state(path, state)
    print(json.dumps(updated, ensure_ascii=False, indent=2))


def record_verification_result_command(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    if not structured_verification_enforced(state):
        fail("record-verification-result requires a new structured graph state.")
    worker = next((item for item in state.get("workers", []) if item.get("workerId") == args.worker_id), None)
    if worker is None or worker.get("contractRevision") != state["contractRevision"] or worker.get("status") not in ACTIVE_WORKER_STATUSES:
        fail("Verification result requires an active current-revision worker.")
    packet = current_packet(state, args.packet_id, args.packet_digest)
    if worker.get("packetId") != packet["packetId"] or worker.get("packetDigest") != packet["packetDigest"]:
        fail("Verification result packet identity must match the registered worker packet.")
    manifest = normalize_manifest(state, load_json_value(args.artifact_manifest))
    manifest_fingerprint = artifact_manifest_fingerprint(manifest)
    raw_result = load_json_value(args.verification_result)
    if not isinstance(raw_result, dict):
        fail("verificationResult must be a JSON object.")
    if raw_result.get("caseId") != require_nonempty(args.case_id, "caseId"):
        fail("Verification result caseId must match --case-id.")
    entry = persist_verification_results(
        state, worker, packet, manifest_fingerprint, [raw_result], manifest
    )[0]
    invalidate_finalization(state, f"verification result recorded: {entry['result']['resultId']}")
    save_state(path, state)
    print(json.dumps(entry, ensure_ascii=False, indent=2))


def record_callback(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    worker_id = (args.worker_id or "").strip()
    request_id = (args.request_id or "").strip()
    if not worker_id and not request_id:
        fail("Provide --worker-id or --request-id.")
    by_worker = next((item for item in state.get("workers", []) if worker_id and item.get("workerId") == worker_id), None)
    by_request = next((item for item in state.get("workers", []) if request_id and item.get("requestId") == request_id), None)
    if worker_id and request_id and (by_worker is None or by_request is None or by_worker is not by_request):
        fail("workerId and requestId must identify the same worker.")
    worker = by_worker or by_request
    if worker is None:
        fail("Worker not found. Provide --worker-id or --request-id.")
    revision = state["contractRevision"]
    if worker.get("contractRevision") != revision or worker.get("status") not in ACTIVE_WORKER_STATUSES:
        fail("Old, superseded, stale, or resolved worker callbacks cannot satisfy the current revision.")
    if args.contract_revision and args.contract_revision != revision:
        fail(f"Callback contractRevision must equal current revision {revision}.")
    if worker.get("callbackReceived"):
        fail(f"Callback already recorded for worker: {worker.get('workerId', '')}")
    from_lane = require_nonempty(args.from_lane, "fromLane")
    if from_lane != worker.get("lane"):
        fail(f"fromLane must match registered worker lane {worker.get('lane')}.")
    if is_graph_state(state):
        packet = current_packet(state, args.packet_id, args.packet_digest)
        if packet["laneName"] != from_lane:
            fail("Callback packetId must belong to fromLane.")
        if worker.get("packetId") != packet["packetId"] or worker.get("packetDigest") != packet["packetDigest"]:
            fail("Callback packet identity must match the registered worker packet.")
    lane = find_lane(state, from_lane)
    require_approved_target_authorization(state, lane)
    if lane.get("status") != "running":
        fail(f"Worker callback requires lane running: {from_lane} (status={lane.get('status', '')})")
    upstream_guard = evaluate_gate(state, from_lane, require_target_worker=False)
    if not upstream_guard["allowed"]:
        fail("upstream_gate_blocked: " + "; ".join(upstream_guard["blockers"]))
    artifact = (args.artifact or worker.get("artifact", "")).strip()
    if args.gate_decision == "pass" and not artifact:
        fail("Worker pass callback requires a non-empty artifact.")
    artifact_manifest: list[dict[str, Any]] = []
    check_results: list[dict[str, Any]] = []
    write_receipt: dict[str, Any] | None = None
    operation_receipt_id = ""
    operation_receipt_ids: list[str] = []
    verification_summary: dict[str, Any] | None = None
    callback_contract_digest = (args.contract_digest or "").strip()
    callback_fingerprint = (args.deliverable_fingerprint or "").strip()
    correction_events = normalize_correction_events(
        load_json_value(args.correction_events) if args.correction_events else [], state, from_lane
    )
    if structured_verification_enforced(state) and args.write_receipt:
        fail("Structured graph callbacks accept operationReceiptId, never a free-form writeReceipt.")
    if is_semantic_strict(state):
        if callback_contract_digest != state.get("contractDigest"):
            fail("Callback contractDigest must match the current semantic contract digest.")
        if callback_fingerprint != state["contractSpec"]["deliverableFingerprint"]:
            fail("Callback deliverableFingerprint must match the current semantic deliverable fingerprint.")
        if args.gate_decision == "pass" and not correction_events:
            artifact_manifest = normalize_manifest(
                state, load_json_value(args.artifact_manifest) if args.artifact_manifest else None
            )
            if structured_verification_enforced(state):
                manifest_fingerprint = artifact_manifest_fingerprint(artifact_manifest)
                receipt_ids = parse_operation_receipt_ids(args.operation_receipt_ids) if args.operation_receipt_ids else []
                if lane.get("writeBoundary") == "approved-target":
                    if args.operation_receipt_id:
                        fail("Structured graph callbacks require --operation-receipt-ids, not --operation-receipt-id.")
                    if not receipt_ids:
                        fail("approved-target structured callback requires operationReceiptIds.")
                    for receipt_id in receipt_ids:
                        receipt = current_receipt_for_callback(state, receipt_id, worker)
                        require_receipt_manifest_binding(receipt, artifact_manifest)
                    operation_receipt_id = receipt_ids[0]
                    operation_receipt_ids = receipt_ids
                packet = current_packet(state, worker.get("packetId", ""), worker.get("packetDigest", ""))
                if args.verification_results:
                    persist_verification_results(
                        state, worker, packet, manifest_fingerprint,
                        load_json_value(args.verification_results), artifact_manifest,
                    )
                verification_summary = structured_verification_summary(
                    state, worker, packet, manifest_fingerprint
                )
                if not verification_summary["allowed"]:
                    fail("verification_gate_blocked: " + json.dumps(verification_summary["blockers"], ensure_ascii=False))
            else:
                check_results = validate_check_results(
                    state, lane, load_json_value(args.check_results) if args.check_results else None
                )
                if lane.get("writeBoundary") == "approved-target" and business_contract_v2(state):
                    write_receipt = normalize_write_receipt(
                        state, load_json_value(args.write_receipt) if args.write_receipt else None
                    )
    observed_mode = args.callback_mode_observed or (
        "managed_result_collected"
        if worker.get("callbackModeExpected") == "managed_result_collected"
        else "unspecified"
    )
    if args.gate_decision == "pass":
        mode_error = callback_mode_error(worker, observed_mode)
        if mode_error:
            fail(mode_error)
    mode_warning = callback_mode_warning(worker, observed_mode)
    if correction_events:
        state.setdefault("correctionEvents", []).extend(correction_events)
        stale_current_approvals(
            state, "correction opened from callback: " + ", ".join(event["id"] for event in correction_events)
        )
        worker["status"] = "needs-work"
        worker["artifact"] = artifact
        worker["decision"] = "needs-work"
        worker["callbackReceived"] = True
        worker["callbackModeObserved"] = observed_mode
        worker["callbackMessage"] = json.dumps(
            {
                "messageType": args.message_type,
                "requestId": worker.get("requestId", ""),
                "contractRevision": revision,
                "contractDigest": callback_contract_digest,
                "deliverableFingerprint": callback_fingerprint,
                "fromLane": from_lane,
                "packetId": worker.get("packetId", ""),
                "packetDigest": worker.get("packetDigest", ""),
                "correctionEventIds": [event["id"] for event in correction_events],
            },
            ensure_ascii=False,
        )
        worker["notes"] = "open correctionEvents: " + ", ".join(event["id"] for event in correction_events)
        worker["updated_at"] = now()
        save_state(path, state)
        fail("correction_opened: callback cannot pass; revise-contract must consume all open correctionEvents.")
    worker["status"] = "blocked" if args.message_type == "blocker" else ("done" if args.gate_decision == "pass" else args.gate_decision)
    worker["artifact"] = artifact
    worker["decision"] = args.gate_decision
    worker["callbackReceived"] = True
    worker["artifactManifest"] = artifact_manifest
    worker["checkResults"] = check_results
    worker["writeReceipt"] = write_receipt
    worker["operationReceiptId"] = operation_receipt_id
    worker["operationReceiptIds"] = operation_receipt_ids
    worker["verificationSummary"] = verification_summary
    worker["callbackModeObserved"] = observed_mode
    worker["callbackMessage"] = json.dumps(
        {
            "messageType": args.message_type,
            "requestId": worker.get("requestId", ""),
            "contractRevision": revision,
            "contractDigest": callback_contract_digest,
            "deliverableFingerprint": callback_fingerprint,
            "fromLane": from_lane,
            "packetId": worker.get("packetId", ""),
            "packetDigest": worker.get("packetDigest", ""),
            "callbackModeObserved": observed_mode,
            "keyFindings": args.key_findings,
            "evidence": args.evidence,
            "risks": args.risks,
            "nextRecommendation": args.next_recommendation,
        },
        ensure_ascii=False,
    )
    worker["notes"] = "\n".join(
        part
        for part in [
            f"findings: {args.key_findings}" if args.key_findings else "",
            f"risks: {args.risks}" if args.risks else "",
            f"next: {args.next_recommendation}" if args.next_recommendation else "",
            f"warning: {mode_warning}" if mode_warning else "",
        ]
        if part
    )
    worker["updated_at"] = now()
    invalidate_finalization(state, f"worker callback recorded: {worker.get('workerId', '')}")
    save_state(path, state)
    print(json.dumps(worker, ensure_ascii=False, indent=2))


def gate_check(args: argparse.Namespace) -> None:
    state = load_state(Path(args.state).expanduser())
    result = evaluate_gate(state, args.target_lane)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def finalize(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    guard = finalization_gate(state)
    if not guard["allowed"]:
        fail("final_gate_blocked: " + "; ".join(guard["blockers"]))
    finalization = {
        "status": "finalized",
        "contractRevision": state["contractRevision"],
        "contractDigest": state.get("contractDigest", ""),
        "finalized_at": now(),
    }
    state["finalization"] = finalization
    save_state(path, state)
    print(json.dumps(finalization, ensure_ascii=False, indent=2))


def revise_contract(args: argparse.Namespace) -> None:
    path = Path(args.state).expanduser()
    state = load_state(path)
    require_continuation_state(state)
    lanes = state.get("lanes", [])
    invalid_index = next((idx for idx, lane in enumerate(lanes) if lane.get("name") == args.invalid_from_lane), -1)
    if invalid_index < 0:
        fail(f"invalidFromLane not found: {args.invalid_from_lane}")
    old_revision = state["contractRevision"]
    new_revision = old_revision + 1
    reason = (args.reason or f"contract revised from lane {args.invalid_from_lane}").strip()
    open_events = open_correction_events(state)
    consumed_ids = parse_csv(args.consume_correction_event_ids)
    open_ids = {event["id"] for event in open_events}
    if open_ids and set(consumed_ids) != open_ids:
        missing = sorted(open_ids - set(consumed_ids))
        unknown = sorted(set(consumed_ids) - open_ids)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown/non-open " + ", ".join(unknown))
        fail("revise-contract must consume all and only open correctionEvents: " + "; ".join(details))
    if not open_ids and consumed_ids:
        fail("consumeCorrectionEventIds were provided but there are no open correctionEvents.")
    if open_events:
        lane_indexes = {lane["name"]: index for index, lane in enumerate(lanes)}
        earliest_recommended = min(lane_indexes[event["recommendedInvalidFromLane"]] for event in open_events)
        if invalid_index > earliest_recommended:
            fail(
                "invalidFromLane is later than the earliest correction recommendation: "
                + lanes[earliest_recommended]["name"]
            )
    graph_based = is_graph_state(state)
    new_plan: dict[str, Any] | None = None
    old_packet_digests = {
        packet.get("packetDigest", "")
        for packet in state.get("workerPackets", {}).values()
        if isinstance(packet, dict)
    }
    new_task_blueprint: dict[str, Any] | None = None
    new_blueprint_compiled: dict[str, Any] | None = None
    if graph_based and not args.task_blueprint:
        fail("graph-based revise-contract requires --task-blueprint.")
    if args.task_blueprint:
        if graph_based:
            runtime_availability = state.get("planRuntimeAvailability") or {}
            active_ids = state.get("planActiveCapabilityIds") or []
            new_plan, new_task_blueprint, new_blueprint_compiled = plan_blueprint_data(
                load_json_value(args.task_blueprint),
                runtime_availability=runtime_availability,
                active_capability_ids=active_ids or None,
                available_capabilities=state.get("availableCapabilities") or [],
            )
            old_graph = state.get("solutionGraph")
            new_graph = new_plan.get("solutionGraph")
            if not isinstance(old_graph, dict) or not isinstance(new_graph, dict) or (
                old_graph.get("topologicalOrder") != new_graph.get("topologicalOrder")
            ):
                fail("replan_requires_new_state: SolutionGraph node IDs or topological order changed.")
            old_projection = [(lane["name"], lane["writeBoundary"]) for lane in state.get("lanes", [])]
            new_projection = [
                (lane["name"], lane["writeBoundary"])
                for lane in new_plan["laneProjection"]["laneDefinitions"]
            ]
            if old_projection != new_projection:
                fail("replan_requires_new_state: projected lane boundaries changed.")
        else:
            new_task_blueprint, new_blueprint_compiled = compile_task_blueprint(
                load_json_value(args.task_blueprint), lanes
            )
        require_executable_blueprint(
            new_blueprint_compiled,
            enforcement_mode=effective_enforcement_mode(state),
            risky=has_semantic_risk(state),
        )
        if (
            new_plan is not None
            and effective_enforcement_mode(state) == "semantic_strict"
            and has_semantic_risk(state)
            and not new_plan["planExecutable"]
        ):
            fail("semantic_strict graph revision requires an executable SolutionGraph plan.")
    elif is_semantic_strict(state) and state.get("taskBlueprint") is not None:
        fail(
            "blueprint-based semantic_strict revise-contract requires --task-blueprint; "
            "TaskBlueprint lineage is canonical and cannot be replaced by a hand-authored contractSpec."
        )

    new_contract_spec: dict[str, Any] | None = None
    new_contract_digest = ""
    if is_semantic_strict(state):
        if new_blueprint_compiled is not None:
            if args.contract_spec:
                supplied_contract_spec = validate_contract_spec(load_json_value(args.contract_spec), lanes)
                require_matching_contract_spec(supplied_contract_spec, new_blueprint_compiled)
            new_contract_spec = new_blueprint_compiled["contractSpec"]
        elif not args.contract_spec:
            fail("semantic_strict revise-contract requires a complete contractSpec.")
        else:
            new_contract_spec = validate_contract_spec(load_json_value(args.contract_spec), lanes)
        require_decision_confirmation_gate(new_contract_spec)
        new_contract_digest = compute_contract_digest(new_contract_spec, new_revision)
    elif new_blueprint_compiled is not None:
        if args.contract_spec:
            supplied_contract_spec = validate_contract_spec(load_json_value(args.contract_spec), lanes)
            require_matching_contract_spec(supplied_contract_spec, new_blueprint_compiled)
        new_contract_spec = new_blueprint_compiled["contractSpec"]
    if args.contract:
        state["contract"] = args.contract
    # Permits are authorization for exactly one contract revision. Preserve the
    # ledger for audit, but revoke any authorization that has not been consumed
    # before changing the revision. Receipts and verification results keep their
    # old revision markers and are therefore never current evidence afterwards.
    revoked_permit_ids: list[str] = []
    if structured_verification_enforced(state):
        permits, _, _ = operation_ledgers(state)
        for permit in permits:
            permit_id = permit.get("permitId", "")
            if permit.get("contractRevision") != old_revision:
                continue
            if permit.get("status") in {"issued", "claimed"}:
                try:
                    revoked = revoke_permit(permit)
                except PermitError:
                    continue
                revoked.update({"contractRevision": old_revision, "invalidatedAtRevision": new_revision, "revokedReason": "contract revision"})
                replace_ledger_entry(permits, "permitId", permit_id, revoked)
                revoked_permit_ids.append(permit_id)
    stale_current_approvals(state, f"contract revised to revision {new_revision}")
    state["contractRevision"] = new_revision
    if new_contract_spec is not None:
        state["contractSpec"] = new_contract_spec
        state["contractDigest"] = new_contract_digest
    if new_task_blueprint is not None and new_blueprint_compiled is not None:
        state["taskBlueprint"] = new_task_blueprint
        state["blueprintDigest"] = (
            new_plan["solutionGraph"]["blueprintDigest"]
            if new_plan is not None and new_plan["solutionGraph"]
            else new_blueprint_compiled["blueprintDigest"]
        )
        state["blueprintTraceability"] = new_blueprint_compiled["traceability"]
        state["blueprintCompiledExecutable"] = new_blueprint_compiled["compiledExecutable"]
    if new_plan is not None:
        state["routingDecision"] = new_plan["routingDecision"]
        state["solutionGraph"] = new_plan["solutionGraph"]
        state["solutionGraphDigest"] = new_plan["solutionGraph"].get("graphDigest", "") if new_plan["solutionGraph"] else ""
        state["workerPackets"] = packet_index(new_plan["workerPackets"])
        state["planDigest"] = new_plan["planDigest"]
        state["planExecutable"] = new_plan["planExecutable"]
        state["planBlockers"] = new_plan["blockers"]
        state["orchestrationPlan"] = new_plan["orchestrationPlan"]
        state["orchestrationPlanDigest"] = new_plan["orchestrationPlan"]["orchestrationDigest"]
        state["orchestrationExecutable"] = new_plan["orchestrationPlan"]["orchestrationExecutable"]
        state["orchestrationBlockers"] = new_plan["orchestrationPlan"]["blockers"]
        state["orchestrationWarnings"] = new_plan["orchestrationPlan"]["warnings"]
        apply_orchestration_projection(lanes, new_plan["orchestrationPlan"])
    for event in state.get("correctionEvents", []):
        if event.get("id") in consumed_ids:
            event["status"] = "consumed"
            event["consumedAtRevision"] = new_revision
            event["consumed_at"] = now()
    for index, lane in enumerate(lanes):
        lane["validForRevision"] = new_revision
        if index >= invalid_index:
            lane.pop("carriedForwardAtRevision", None)
            had_output = lane.get("status") == "done" or bool(lane.get("artifact") or lane.get("decision"))
            if had_output:
                lane.setdefault("invalidatedOutputs", []).append(
                    {
                        "contractRevision": old_revision,
                        "invalidatedAtRevision": new_revision,
                        "status": lane.get("status", ""),
                        "artifact": lane.get("artifact", ""),
                        "decision": lane.get("decision", ""),
                    }
                )
            lane["status"] = "stale" if had_output else "pending"
            lane["artifact"] = ""
            lane["decision"] = ""
            lane["completed_at"] = ""
            revision_note = f"revision {new_revision}: invalidated from {args.invalid_from_lane}: {reason}"
            lane["notes"] = "\n".join(part for part in [lane.get("notes", ""), revision_note] if part)
        else:
            lane["carriedForwardAtRevision"] = new_revision
    for worker in state.get("workers", []):
        if worker.get("status") in ACTIVE_WORKER_STATUSES:
            worker_lane_index = next(
                (index for index, lane in enumerate(lanes) if lane.get("name") == worker.get("lane")), invalid_index
            )
            if worker_lane_index >= invalid_index:
                if worker.get("status") in {"pending", "running"}:
                    worker["runtimeStopPending"] = True
                worker["status"] = "superseded"
                worker["decision"] = ""
                worker["supersededAtRevision"] = new_revision
                worker["notes"] = "\n".join(
                    part for part in [worker.get("notes", ""), f"superseded by contract revision {new_revision}: {reason}"] if part
                )
            else:
                worker["carriedForwardFromRevision"] = old_revision
                worker["contractRevision"] = new_revision
                worker["validForRevision"] = new_revision
                if is_semantic_strict(state):
                    worker["contractDigest"] = state["contractDigest"]
                    worker["deliverableFingerprint"] = state["contractSpec"]["deliverableFingerprint"]
            worker["updated_at"] = now()
    if new_plan is not None:
        for worker in state.get("workers", []):
            if worker.get("packetDigest") in old_packet_digests:
                if worker.get("status") in {"pending", "running"}:
                    worker["runtimeStopPending"] = True
                worker["status"] = "superseded"
                worker["decision"] = ""
                worker["supersededAtRevision"] = new_revision
                worker["notes"] = "\n".join(
                    part for part in [worker.get("notes", ""), f"superseded by WorkerPacket revision {new_revision}: {reason}"] if part
                )
                worker["updated_at"] = now()
    state.setdefault("revisions", []).append(
        {
            "revision": new_revision,
            "previousRevision": old_revision,
            "invalidFromLane": args.invalid_from_lane,
            "reason": reason,
            "contractDigest": state.get("contractDigest", ""),
            "blueprintDigest": state.get("blueprintDigest", ""),
            "planDigest": state.get("planDigest", ""),
            "invalidatedPacketDigests": sorted(old_packet_digests) if new_plan is not None else [],
            "revokedOperationPermitIds": revoked_permit_ids,
            "consumedCorrectionEventIds": consumed_ids,
            "created_at": now(),
        }
    )
    state["finalization"] = {
        "status": "open",
        "invalidatedAtRevision": new_revision,
        "invalidationReason": reason,
    }
    save_state(path, state)
    print(
        json.dumps(
            {"contractRevision": new_revision, "invalidFromLane": args.invalid_from_lane, "state": state},
            ensure_ascii=False,
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KY-TASK schema-v2 controller state helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("compile-blueprint")
    p.add_argument("--task-blueprint", required=True, help="JSON object or @path")
    p.add_argument("--lane-definitions", required=True, help="JSON array or @path")
    p.set_defaults(func=compile_blueprint_command)

    p = sub.add_parser("route-capabilities")
    p.add_argument("--task-blueprint", required=True, help="JSON object or @path")
    p.add_argument("--active-capability-ids", default="")
    p.add_argument("--runtime-availability", default="{}", help="JSON object or @path")
    p.set_defaults(func=route_capabilities)

    p = sub.add_parser("plan-orchestration")
    p.add_argument("--lane-definitions", required=True, help="JSON array or @path")
    p.add_argument("--orchestration-policy", choices=sorted(ORCHESTRATION_POLICIES), default=DEFAULT_ORCHESTRATION_POLICY)
    p.add_argument("--active-capability-ids", default="")
    p.add_argument("--available-capabilities", default="[]", help="JSON array or @path")
    p.add_argument("--runtime-availability", default="{}", help="JSON object or @path")
    p.set_defaults(func=plan_orchestration_command)

    p = sub.add_parser("plan-blueprint")
    p.add_argument("--task-blueprint", required=True, help="JSON object or @path")
    p.add_argument("--active-capability-ids", default="")
    p.add_argument("--available-capabilities", default="[]", help="JSON array or @path")
    p.add_argument("--runtime-availability", default="{}", help="JSON object or @path")
    p.set_defaults(func=plan_blueprint_command)

    p = sub.add_parser("init")
    p.add_argument("--state", required=True)
    p.add_argument("--goal", required=True)
    p.add_argument("--contract", default="")
    p.add_argument("--enforcement-mode", choices=sorted(ENFORCEMENT_MODES), default="")
    p.add_argument("--semantic-downgrade-reason", default="")
    p.add_argument("--contract-spec", default="", help="JSON object or @path")
    p.add_argument("--task-blueprint", default="", help="JSON object or @path")
    p.add_argument("--auto-plan", action="store_true")
    p.add_argument("--runtime-availability", default="{}", help="JSON object or @path")
    p.add_argument("--active-capability-ids", default="")
    p.add_argument("--available-capabilities", default="[]", help="JSON array or @path")
    p.add_argument("--lanes", default="")
    p.add_argument("--lane-definitions", default="", help="JSON array or @path")
    p.add_argument("--execution-policy", default="", help="JSON object or @path")
    p.add_argument("--split-requirement", choices=sorted(SPLIT_REQUIREMENTS), default="none")
    p.add_argument("--mode", choices=sorted(EXECUTION_MODES), default="direct")
    p.add_argument("--eligible-runtimes", default="")
    p.add_argument("--downgrade-reason", default="")
    p.add_argument("--required-worker-lanes", default="")
    p.add_argument("--independent-review-required", action="store_true")
    p.add_argument("--runtime-selection-policy", choices=sorted(RUNTIME_SELECTION_POLICIES), default="")
    p.add_argument("--orchestration-policy", choices=["", *sorted(ORCHESTRATION_POLICIES)], default="")
    p.add_argument("--native-thread-user-approved", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--max-parallel-workers", type=int, default=0)
    p.add_argument("--project-affinity-policy", choices=sorted(PROJECT_AFFINITY_POLICIES), default="")
    p.add_argument("--projectless-user-approved", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--target-project-id", default="")
    p.add_argument("--target-project-path", default="")
    p.add_argument("--project-resolution-source", choices=["", *sorted(PROJECT_RESOLUTION_SOURCES)], default="")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=init)

    p = sub.add_parser("status")
    p.add_argument("--state", required=True)
    p.set_defaults(func=status)

    p = sub.add_parser("next-lane")
    p.add_argument("--state", required=True)
    p.set_defaults(func=next_lane)

    p = sub.add_parser("ready-lanes")
    p.add_argument("--state", required=True)
    p.set_defaults(func=ready_lanes)

    p = sub.add_parser("complete-lane")
    p.add_argument("--state", required=True)
    p.add_argument("--lane", required=True)
    p.add_argument("--artifact", default="")
    p.add_argument("--decision", choices=["pass", "needs-work", "blocked"], default="pass")
    p.add_argument("--notes", default="")
    p.set_defaults(func=complete_lane)

    p = sub.add_parser("insert-lane")
    p.add_argument("--state", required=True)
    p.add_argument("--lane", required=True)
    p.add_argument("--before", default="")
    p.add_argument("--after", default="")
    p.add_argument("--kind", default="")
    p.add_argument("--worker-required", action="store_true")
    p.add_argument("--write-boundary", choices=sorted(WRITE_BOUNDARIES), default="")
    p.add_argument("--worker-lifecycle", choices=sorted(WORKER_LIFECYCLES), default="ephemeral")
    p.add_argument("--context-policy", choices=["", *sorted(CONTEXT_POLICIES)], default="")
    p.add_argument("--runtime-preference", choices=sorted(RUNTIME_PREFERENCES), default="auto")
    p.add_argument("--depends-on", default=None)
    p.add_argument("--independent", action="store_true")
    p.add_argument("--purpose", default="")
    p.add_argument("--contribution-role", choices=["", *sorted(CONTRIBUTION_ROLES)], default="")
    p.add_argument("--semantic-authority", choices=["", *sorted(SEMANTIC_AUTHORITIES)], default="")
    p.add_argument("--semantic-owner", action="store_true")
    p.add_argument("--dependency-reasons", default="", help="JSON object or @path")
    p.add_argument("--input-contracts", default="", help="JSON array or @path")
    p.add_argument("--output-contracts", default="", help="JSON array or @path")
    p.add_argument("--external-inputs", default="", help="JSON array or @path")
    p.add_argument("--write-targets", default="", help="JSON array or @path")
    p.add_argument("--handoff-risk", choices=["", *sorted(HANDOFF_RISKS)], default="")
    p.add_argument("--handoff-mode", choices=["", *sorted(mode for mode in HANDOFF_MODES if mode)], default="")
    p.add_argument("--handoff-contract", default="", help="JSON object/array or @path")
    p.add_argument("--verification-scope", choices=["", *sorted(VERIFY_SCOPES)], default="")
    p.add_argument("--capability-requirements", default="")
    p.add_argument("--capability-needs", default="", help="JSON value or @path")
    p.add_argument("--estimated-effort", type=float, default=1)
    p.add_argument("--continuity-required", action="store_true")
    p.add_argument("--status", choices=["pending", "running", "done", "needs-work", "blocked", "stale"], default="pending")
    p.add_argument("--artifact", default="")
    p.add_argument("--decision", choices=["", "pass", "needs-work", "blocked"], default="")
    p.add_argument("--notes", default="")
    p.set_defaults(func=insert_lane)

    p = sub.add_parser("add-note")
    p.add_argument("--state", required=True)
    p.add_argument("--lane", required=True)
    p.add_argument("--notes", required=True)
    p.set_defaults(func=add_note)

    p = sub.add_parser("register-worker")
    p.add_argument("--state", required=True)
    p.add_argument("--worker-id", required=True)
    p.add_argument("--thread-id", default="")
    p.add_argument("--runtime-handle", default="")
    p.add_argument("--request-id", default="")
    p.add_argument("--claim-id", default="")
    p.add_argument("--contract-revision", type=int, default=0)
    p.add_argument("--contract-digest", default="")
    p.add_argument("--deliverable-fingerprint", default="")
    p.add_argument("--controller-thread-id", default="")
    p.add_argument("--reply-to-thread-id", default="")
    p.add_argument("--project-target-type", choices=["", "project", "projectless"], default="")
    p.add_argument("--project-id", default="")
    p.add_argument("--project-environment", choices=["", *sorted(PROJECT_ENVIRONMENTS)], default="")
    p.add_argument("--lane", required=True)
    p.add_argument("--lane-runtime", choices=sorted(LANE_RUNTIMES), default="single_thread_section")
    p.add_argument("--task", default="")
    p.add_argument("--prompt", default="")
    p.add_argument("--packet-id", default="")
    p.add_argument("--packet-digest", default="")
    p.add_argument("--tool-profile", default="")
    p.add_argument("--credential-policy", default="")
    p.add_argument("--thread-tool-check", default="")
    p.add_argument("--write-boundary", choices=sorted(WRITE_BOUNDARIES), default="")
    p.add_argument("--reviews-worker-ids", default="")
    p.add_argument("--no-callback-expected", action="store_true")
    p.add_argument(
        "--callback-mode-expected",
        choices=["", "active_message_required", "active_message_preferred", "controller_poll_allowed", "managed_result_collected"],
        default="",
    )
    p.set_defaults(func=register_worker)

    p = sub.add_parser("claim-dispatch")
    p.add_argument("--state", required=True)
    p.add_argument("--lane", required=True)
    p.add_argument("--request-id", required=True)
    p.add_argument("--capability-evidence", default="{}", help="Capability ID to host-discovery evidence JSON object")
    p.set_defaults(func=claim_dispatch)

    p = sub.add_parser("release-dispatch")
    p.add_argument("--state", required=True)
    p.add_argument("--claim-id", required=True)
    p.add_argument("--outcome", required=True, choices=["not-created", "stopped"])
    p.add_argument("--evidence", required=True)
    p.set_defaults(func=release_dispatch_command)

    p = sub.add_parser("update-worker")
    p.add_argument("--state", required=True)
    p.add_argument("--worker-id", required=True)
    p.add_argument("--status", choices=["pending", "running", "needs-work", "blocked", "superseded", "stale", "resolved"], default="running")
    p.add_argument("--artifact", default="")
    p.add_argument("--decision", choices=["", "needs-work", "blocked"], default="")
    p.add_argument("--notes", default="")
    p.add_argument("--runtime-stop-evidence", default="", help="Host evidence that a retired worker is no longer running")
    p.set_defaults(func=update_worker)

    p = sub.add_parser("list-workers")
    p.add_argument("--state", required=True)
    p.set_defaults(func=list_workers)

    p = sub.add_parser("classify-feedback")
    p.add_argument("--state", default="")
    p.add_argument("--feedback", required=True)
    p.set_defaults(func=classify_feedback_command)

    p = sub.add_parser("ingest-feedback")
    p.add_argument("--state", required=True)
    p.add_argument("--feedback", required=True)
    p.add_argument("--event-id", default="")
    p.set_defaults(func=ingest_feedback)

    p = sub.add_parser("record-correction")
    p.add_argument("--state", required=True)
    p.add_argument("--event-id", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--category", required=True)
    p.add_argument("--requirement-ids", required=True)
    p.add_argument("--recommended-invalid-from-lane", required=True)
    p.set_defaults(func=record_correction)

    p = sub.add_parser("record-approval")
    p.add_argument("--state", required=True)
    p.add_argument("--approval-id", default="")
    p.add_argument("--artifact-id", required=True)
    p.add_argument("--artifact-fingerprint", required=True)
    p.add_argument("--approver", required=True)
    p.add_argument("--timestamp", default="")
    p.set_defaults(func=record_approval)

    p = sub.add_parser("record-callback")
    p.add_argument("--state", required=True)
    p.add_argument("--worker-id", default="")
    p.add_argument("--request-id", default="")
    p.add_argument("--contract-revision", type=int, default=0)
    p.add_argument("--contract-digest", default="")
    p.add_argument("--deliverable-fingerprint", default="")
    p.add_argument("--packet-id", default="")
    p.add_argument("--packet-digest", default="")
    p.add_argument("--message-type", choices=["completion", "blocker", "review_request", "fix_request", "approved"], default="completion")
    p.add_argument("--from-lane", required=True)
    p.add_argument("--artifact", default="")
    p.add_argument("--key-findings", default="")
    p.add_argument("--evidence", default="")
    p.add_argument("--risks", default="")
    p.add_argument("--gate-decision", choices=["pass", "needs-work", "blocked"], default="pass")
    p.add_argument("--next-recommendation", default="")
    p.add_argument(
        "--callback-mode-observed",
        choices=["", "active_message", "controller_poll_recovery", "managed_result_collected", "unavailable", "unspecified"],
        default="",
    )
    p.add_argument("--artifact-manifest", default="", help="JSON array or @path")
    p.add_argument("--check-results", default="", help="JSON array or @path")
    p.add_argument("--write-receipt", default="", help="JSON object or @path")
    p.add_argument("--operation-receipt-id", default="")
    p.add_argument("--operation-receipt-ids", default="", help="JSON array, CSV list, or @path")
    p.add_argument("--verification-results", default="", help="JSON array or @path")
    p.add_argument("--correction-events", default="", help="JSON array or @path")
    p.set_defaults(func=record_callback)

    p = sub.add_parser("issue-operation-permit")
    p.add_argument("--state", required=True)
    p.add_argument("--permit-id", required=True)
    p.add_argument("--worker-id", required=True)
    p.add_argument("--capability-id", required=True)
    p.add_argument("--operation-id", required=True)
    p.add_argument("--target-id", required=True)
    p.add_argument("--target-locator", required=True)
    p.add_argument("--action", required=True)
    p.add_argument("--payload", required=True, help="JSON object or @path")
    p.add_argument("--restricted-fields", default="")
    p.add_argument("--approval-refs", default="")
    p.add_argument("--idempotency-key", required=True)
    p.add_argument("--adapter-id", required=True, choices=["memory-test", "lark-cli"])
    p.add_argument("--adapter-options", default="", help="JSON object or @path")
    p.add_argument("--readback-spec", required=True, help="JSON object or @path")
    p.add_argument("--expires-at", required=True)
    p.set_defaults(func=issue_operation_permit_command)

    p = sub.add_parser("dispatch-operation")
    p.add_argument("--state", required=True)
    p.add_argument("--permit-id", required=True)
    p.add_argument("--claim-id", default="")
    p.set_defaults(func=dispatch_operation_command)

    p = sub.add_parser("reconcile-operation")
    p.add_argument("--state", required=True)
    p.add_argument("--permit-id", required=True)
    p.set_defaults(func=reconcile_operation_command)

    p = sub.add_parser("revoke-operation-permit")
    p.add_argument("--state", required=True)
    p.add_argument("--permit-id", required=True)
    p.add_argument("--reason", default="")
    p.set_defaults(func=revoke_operation_permit_command)

    p = sub.add_parser("record-verification-result")
    p.add_argument("--state", required=True)
    p.add_argument("--worker-id", required=True)
    p.add_argument("--packet-id", required=True)
    p.add_argument("--packet-digest", required=True)
    p.add_argument("--case-id", required=True)
    p.add_argument("--artifact-manifest", required=True, help="JSON array or @path")
    p.add_argument("--verification-result", required=True, help="JSON object or @path")
    p.set_defaults(func=record_verification_result_command)

    p = sub.add_parser("gate-check")
    p.add_argument("--state", required=True)
    p.add_argument("--target-lane", default="")
    p.set_defaults(func=gate_check)

    p = sub.add_parser("revise-contract")
    p.add_argument("--state", required=True)
    p.add_argument("--invalid-from-lane", required=True)
    p.add_argument("--contract", default="")
    p.add_argument("--contract-spec", default="", help="JSON object or @path")
    p.add_argument("--task-blueprint", default="", help="JSON object or @path")
    p.add_argument("--consume-correction-event-ids", default="")
    p.add_argument("--reason", default="")
    p.set_defaults(func=revise_contract)

    p = sub.add_parser("finalize")
    p.add_argument("--state", required=True)
    p.set_defaults(func=finalize)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd in MUTATING_COMMANDS:
        with state_lock(Path(args.state).expanduser()):
            args.func(args)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
