"""Compile lane definitions into an explicit, capability-aware work plan.

``dependsOn`` is necessary for scheduling, but it is not sufficient for good
decomposition.  This module validates the professional meaning of a lane map
before runtime selection: who owns the result, which work only constrains it,
which handoffs are intentionally serial, and which lanes are genuinely safe to
run in parallel.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re
from typing import Any, Iterable

from registry.loader import load_registry


ORCHESTRATION_VERSION = "1.0"
ORCHESTRATION_POLICIES = {"strict", "advisory", "legacy"}
CONTRIBUTION_ROLES = {"primary", "prerequisite", "supporting", "verification"}
SEMANTIC_AUTHORITIES = {"define", "constrain", "implement", "define-and-implement", "verify"}
HANDOFF_RISKS = {"low", "medium", "high"}
HANDOFF_MODES = {"", "same-lane", "artifact-contract", "independent"}
VERIFY_SCOPES = {"final-artifact", "intermediate-artifact", "upstream-decision"}
ORDER_ONLY_REASONS = {"order", "list-order", "keep-order", "sequential-by-default", "default-order"}
ORCHESTRATION_FIELDS = (
    "dependsOn", "purpose", "contributionRole", "semanticAuthority", "semanticOwner",
    "dependencyReasons", "inputContracts", "outputContracts", "externalInputs",
    "handoffRisk", "handoffMode", "handoffContract", "verificationScope",
    "capabilityRequirements", "capabilityNeeds", "estimatedEffort", "writeTargets",
    "continuityRequired",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any, default: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(item.strip() for item in value if isinstance(item, str) and item.strip()))


def _contract_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
            result.append(item["id"].strip())
    return list(dict.fromkeys(result))


def _field(definition: dict[str, Any], metadata: dict[str, Any], key: str, default: Any = None) -> Any:
    if key in definition:
        return definition[key]
    if key in metadata:
        return metadata[key]
    return default


def declared_orchestration_fields(definition: dict[str, Any]) -> list[str]:
    """Preserve input provenance across normalization; inferred defaults are not declarations."""
    metadata = definition.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    declared = (
        set(_strings(definition["orchestrationDeclared"]))
        if "orchestrationDeclared" in definition
        else {key for key in ORCHESTRATION_FIELDS if key in definition or key in metadata}
    )
    # A caller cannot make an absent/blank required field explicit just by
    # listing its name in provenance. Empty dependency arrays remain valid.
    for key in ("purpose", "contributionRole", "semanticAuthority", "handoffRisk", "handoffMode"):
        if not _text(_field(definition, metadata, key)):
            declared.discard(key)
    if not isinstance(_field(definition, metadata, "dependsOn"), list):
        declared.discard("dependsOn")
    return sorted(declared)


def _semantic_text(name: str, kind: str, purpose: str) -> str:
    return f"{name} {kind} {purpose}".lower().replace("_", "-")


def infer_contribution_role(name: str, kind: str, purpose: str = "") -> str:
    exact = kind.lower().replace("_", "-")
    if exact in {"decision-review", "user-approval", "approval"}:
        return "prerequisite"
    if exact in {"review", "verifier", "readback", "qa", "quality-assurance"}:
        return "verification"
    if exact in {"evidence", "source", "research", "audit"}:
        return "prerequisite"
    if exact in {"strategy", "design", "planning", "analysis", "model", "modeling", "product", "product-experience", "sample", "implementation", "production", "writer"}:
        return "primary"
    value = _semantic_text(name, kind, purpose)
    if any(token in value for token in ("final-review", "review", "verifier", "readback", " qa", "qa-", "-qa", "验收", "复核", "质检")):
        return "verification"
    if any(token in value for token in ("evidence", "source", "research", "audit", "证据", "来源", "调研", "审计")):
        return "prerequisite"
    if any(token in value for token in ("strategy", "design", "planning", "analysis", "model", "product", "experience", "sample", "implement", "production", "writer", "build", "策略", "设计", "模型", "分析", "实现", "制作")):
        return "primary"
    return "supporting"


def infer_semantic_authority(name: str, kind: str, purpose: str = "") -> str:
    exact = kind.lower().replace("_", "-")
    if exact in {"decision-review", "user-approval", "approval"}:
        return "constrain"
    if exact in {"review", "verifier", "readback", "qa", "quality-assurance"}:
        return "verify"
    if exact in {"implementation", "production", "writer"}:
        return "implement"
    if exact in {"strategy", "design", "planning", "analysis", "model", "modeling", "product", "product-experience", "sample"}:
        return "define"
    if exact in {"evidence", "source", "research", "audit", "support"}:
        return "constrain"
    value = _semantic_text(name, kind, purpose)
    if any(token in value for token in ("final-review", "review", "verifier", "readback", " qa", "qa-", "-qa", "验收", "复核", "质检")):
        return "verify"
    if any(token in value for token in ("implement", "production", "writer", "write", "build", "repair", "revise", "实现", "写入", "制作", "修复")):
        return "implement"
    if any(token in value for token in ("strategy", "design", "planning", "analysis", "model", "product", "experience", "sample", "策略", "设计", "规划", "分析", "模型", "体验", "样稿")):
        return "define"
    return "constrain"


def _normalize_dependencies(value: Any) -> list[str]:
    return _strings(value)


def _dependency_reasons(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {
            str(key).strip(): str(reason).strip()
            for key, reason in value.items()
            if str(key).strip() and isinstance(reason, str) and reason.strip()
        }
    if isinstance(value, list):
        result: dict[str, str] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            source = _text(item.get("from", item.get("lane")))
            reason = _text(item.get("reason"))
            if source and reason:
                result[source] = reason
        return result
    return {}


def _normalize_lane(definition: dict[str, Any], previous: str | None, policy: str) -> dict[str, Any]:
    metadata = definition.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    name = _text(definition.get("name", definition.get("id")))
    if not name:
        raise ValueError("OrchestrationPlan: every lane requires a non-empty name")
    kind = _text(_field(definition, metadata, "kind"), "support")
    purpose = _text(_field(definition, metadata, "purpose"), _text(definition.get("notes"), f"Complete {name}"))
    declared = set(declared_orchestration_fields(definition))
    dependency_declared = "dependsOn" in declared
    dependencies = _normalize_dependencies(_field(definition, metadata, "dependsOn", []))
    if not dependency_declared and previous:
        dependencies = [previous]
    role = _text(_field(definition, metadata, "contributionRole")) or infer_contribution_role(name, kind, purpose)
    authority = _text(_field(definition, metadata, "semanticAuthority")) or infer_semantic_authority(name, kind, purpose)
    handoff_contract = _field(definition, metadata, "handoffContract", {})
    if not isinstance(handoff_contract, (dict, list)):
        handoff_contract = {}
    effort = _field(definition, metadata, "estimatedEffort", 1)
    if not isinstance(effort, (int, float)) or isinstance(effort, bool) or effort <= 0:
        effort = 1
    return {
        "name": name,
        "kind": kind,
        "purpose": purpose,
        "contributionRole": role,
        "semanticAuthority": authority,
        "semanticOwner": bool(_field(definition, metadata, "semanticOwner", False)),
        "dependsOn": dependencies,
        "dependencySource": "explicit" if dependency_declared else "legacy-order",
        "dependencyReasons": _dependency_reasons(_field(definition, metadata, "dependencyReasons", {})),
        "inputContracts": _contract_ids(_field(definition, metadata, "inputContracts", [])),
        "outputContracts": _contract_ids(_field(definition, metadata, "outputContracts", [])),
        "externalInputs": _contract_ids(_field(definition, metadata, "externalInputs", [])),
        "writeBoundary": _text(_field(definition, metadata, "writeBoundary"), "read-only"),
        "writeTargets": _contract_ids(_field(definition, metadata, "writeTargets", [])),
        "workerRequired": bool(_field(definition, metadata, "workerRequired", False)),
        "workerLifecycle": _text(_field(definition, metadata, "workerLifecycle"), "ephemeral"),
        "continuityRequired": bool(_field(definition, metadata, "continuityRequired", False)),
        "handoffRisk": _text(_field(definition, metadata, "handoffRisk"), "medium"),
        "handoffMode": _text(_field(definition, metadata, "handoffMode")),
        "handoffContract": deepcopy(handoff_contract),
        "verificationScope": _text(_field(definition, metadata, "verificationScope"), "final-artifact"),
        "capabilityRequirements": _strings(_field(definition, metadata, "capabilityRequirements", [])),
        "capabilityNeeds": deepcopy(_field(definition, metadata, "capabilityNeeds", [])),
        "estimatedEffort": effort,
        "orchestrationDeclared": sorted(declared),
        "policy": policy,
    }


def _topology(lanes: list[dict[str, Any]]) -> tuple[list[str], list[list[str]], list[dict[str, Any]]]:
    names = [lane["name"] for lane in lanes]
    index = {name: position for position, name in enumerate(names)}
    name_set = set(names)
    blockers: list[dict[str, Any]] = []
    remaining: dict[str, set[str]] = {}
    for lane in lanes:
        missing = sorted(set(lane["dependsOn"]) - name_set)
        if missing:
            blockers.append({"code": "missing_dependency", "lane": lane["name"], "dependencies": missing})
        if lane["name"] in lane["dependsOn"]:
            blockers.append({"code": "self_dependency", "lane": lane["name"]})
        remaining[lane["name"]] = (set(lane["dependsOn"]) & name_set) - {lane["name"]}
    order: list[str] = []
    waves: list[list[str]] = []
    while len(order) < len(names):
        completed = set(order)
        ready = sorted(
            (name for name in names if name not in completed and remaining[name] <= completed),
            key=index.get,
        )
        if not ready:
            blockers.append({"code": "dependency_cycle", "lanes": sorted(name_set - completed)})
            break
        waves.append(ready)
        order.extend(ready)
    return order, waves, blockers


def _ancestor_map(lanes: list[dict[str, Any]], order: list[str]) -> dict[str, set[str]]:
    dependencies = {lane["name"]: set(lane["dependsOn"]) for lane in lanes}
    result: dict[str, set[str]] = {name: set() for name in order}
    for name in order:
        for dependency in dependencies[name]:
            if dependency in result:
                result[name].add(dependency)
                result[name].update(result[dependency])
    return result


def _runtime_available(capability: dict[str, Any], runtime: dict[str, Any] | None) -> tuple[bool, str]:
    if not runtime:
        return True, ""
    capability_id = capability["id"]
    if runtime.get(capability_id) is False:
        return False, f"capability runtime '{capability_id}' is unavailable"
    dependencies = capability.get("dependencies", {})
    providers = dependencies.get("runtimes", []) if isinstance(dependencies, dict) else []
    for provider in providers if isinstance(providers, list) else []:
        if runtime.get(provider) is False:
            return False, f"provider runtime '{provider}' is unavailable"
    return True, ""


def _availability_status(capability: dict[str, Any], runtime: dict[str, Any] | None) -> str:
    """Unknown host availability is not evidence that a capability can run."""
    runtime = runtime or {}
    available, _ = _runtime_available(capability, runtime)
    if not available:
        return "unavailable"
    dependencies = capability.get("dependencies", {})
    providers = dependencies.get("runtimes", []) if isinstance(dependencies, dict) else []
    if runtime.get(capability["id"]) is True or (providers and all(runtime.get(item) is True for item in providers)):
        return "confirmed"
    return "unverified"


def _capability_catalog(
    active_ids: Iterable[str] | None,
    available_capabilities: Any,
) -> dict[str, dict[str, Any]]:
    active = set(active_ids) if active_ids is not None else None
    catalog: dict[str, dict[str, Any]] = {}
    registry = load_registry()
    for capability in registry.capabilities.values():
        value = deepcopy(capability.data)
        if active is None or capability.id in active:
            catalog[capability.id] = value
    if isinstance(available_capabilities, dict):
        available_capabilities = list(available_capabilities.values())
    if isinstance(available_capabilities, list):
        for raw in available_capabilities:
            if isinstance(raw, str):
                raw = {"id": raw}
            if not isinstance(raw, dict):
                continue
            capability_id = _text(raw.get("id", raw.get("capabilityId")))
            if not capability_id or (active is not None and capability_id not in active):
                continue
            catalog[capability_id] = {
                "id": capability_id,
                "name": _text(raw.get("name"), capability_id),
                "status": _text(raw.get("status"), "active"),
                "capabilityType": _text(raw.get("capabilityType"), "workflow"),
                "domains": _strings(raw.get("domains", [])),
                "triggers": _strings(raw.get("triggers", [])),
                "inputs": _strings(raw.get("inputs", [])),
                "outputs": _strings(raw.get("outputs", [])),
                "resourcePatterns": _strings(raw.get("resourcePatterns", [])),
                "dependencies": raw.get("dependencies", {}) if isinstance(raw.get("dependencies", {}), dict) else {},
                "routing": raw.get("routing", {}) if isinstance(raw.get("routing", {}), dict) else {},
            }
    if active is not None:
        for capability_id in active:
            catalog.setdefault(capability_id, {
                "id": capability_id,
                "name": capability_id,
                "status": "active",
                "capabilityType": "workflow",
                "domains": [], "triggers": [], "inputs": [], "outputs": [], "resourcePatterns": [],
                "dependencies": {}, "routing": {},
            })
    return catalog


def _tokens(value: Any) -> set[str]:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    text = str(value or "").lower()
    return {token for token in re.findall(r"[a-z0-9][a-z0-9-]*|[\u4e00-\u9fff]{2,}", text) if len(token) > 1}


def _capability_score(lane: dict[str, Any], capability: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    lane_tokens = _tokens([
        lane["capabilityNeeds"] or lane["purpose"], lane["inputContracts"], lane["outputContracts"],
    ])
    cap_type = _text(capability.get("capabilityType"), "workflow")
    for field, weight in (("domains", 30), ("triggers", 18), ("inputs", 20), ("outputs", 20)):
        overlap = lane_tokens & _tokens(capability.get(field, []))
        if overlap:
            score += weight * len(overlap)
            reasons.append(f"{field}: {', '.join(sorted(overlap))}")
    if not reasons:
        return 0, []
    # Role and catalog priority may rank relevant candidates, never create a
    # match on their own (notably for unknown-domain verifier requests).
    if lane["semanticAuthority"] == "verify":
        if cap_type == "verifier":
            score += 60
            reasons.append("verifier role fit")
        else:
            score -= 30
    priority = capability.get("routing", {}).get("priority", 0) if isinstance(capability.get("routing"), dict) else 0
    if isinstance(priority, int):
        score += min(max(priority, 0), 100) // 20
    return score, reasons


def route_lane_capabilities(
    lanes: list[dict[str, Any]],
    *,
    active_capability_ids: Iterable[str] | None = None,
    runtime_availability: dict[str, Any] | None = None,
    available_capabilities: Any = None,
) -> list[dict[str, Any]]:
    """Resolve exact requirements and suggest candidates from lane-local contracts."""
    catalog = _capability_catalog(active_capability_ids, available_capabilities)
    routes: list[dict[str, Any]] = []
    for lane in lanes:
        selected: list[dict[str, Any]] = []
        missing: list[dict[str, str]] = []
        suggestions: list[dict[str, Any]] = []
        for requirement in lane["capabilityRequirements"]:
            capability = catalog.get(requirement)
            if capability is None:
                missing.append({"id": requirement, "reason": "required capability is not available"})
                continue
            available, reason = _runtime_available(capability, runtime_availability)
            if capability.get("status", "active") != "active" or not available:
                missing.append({"id": requirement, "reason": reason or f"capability status is {capability.get('status')}"})
                continue
            selected.append({
                "id": requirement,
                "reason": "exact lane capability requirement",
                "availability": _availability_status(capability, runtime_availability),
            })
        if not lane["capabilityRequirements"] and lane["capabilityNeeds"]:
            candidates: list[tuple[int, str, list[str]]] = []
            for capability_id, capability in catalog.items():
                available, _ = _runtime_available(capability, runtime_availability)
                if capability.get("status", "active") != "active" or not available:
                    continue
                score, reasons = _capability_score(lane, capability)
                if score > 10:
                    candidates.append((score, capability_id, reasons))
            for score, capability_id, reasons in sorted(candidates, key=lambda item: (-item[0], item[1]))[:3]:
                suggestions.append({"id": capability_id, "score": score, "reasons": reasons})
        status = "bound" if selected and not missing else "blocked" if missing else "suggested" if suggestions else "unbound"
        routes.append({
            "lane": lane["name"],
            "job": lane["purpose"],
            "inputs": lane["inputContracts"],
            "outputs": lane["outputContracts"],
            "acceptanceRole": lane["semanticAuthority"],
            "selected": selected,
            "suggestions": suggestions,
            "missing": missing,
            "status": status,
            "runtimeReady": status == "bound" and all(item["availability"] == "confirmed" for item in selected),
        })
    return routes


def compile_orchestration_plan(
    raw_lanes: Any,
    *,
    policy: str = "strict",
    trusted: bool = False,
    active_capability_ids: Iterable[str] | None = None,
    runtime_availability: dict[str, Any] | None = None,
    available_capabilities: Any = None,
) -> dict[str, Any]:
    """Compile and validate a lane map before runtime dispatch."""
    if policy not in ORCHESTRATION_POLICIES:
        raise ValueError(f"OrchestrationPlan: unsupported policy {policy}")
    if not isinstance(raw_lanes, list) or not raw_lanes or not all(isinstance(item, dict) for item in raw_lanes):
        raise ValueError("OrchestrationPlan: laneDefinitions must be a non-empty object array")
    lanes: list[dict[str, Any]] = []
    previous: str | None = None
    for definition in raw_lanes:
        lane = _normalize_lane(definition, previous, policy)
        lanes.append(lane)
        previous = lane["name"]
    names = [lane["name"] for lane in lanes]
    if len(names) != len(set(names)):
        raise ValueError("OrchestrationPlan: lane names must be unique")

    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    order, wave_names, topology_blockers = _topology(lanes)
    blockers.extend(topology_blockers)
    by_name = {lane["name"]: lane for lane in lanes}
    ancestors = _ancestor_map(lanes, order) if len(order) == len(lanes) else {name: set() for name in names}
    complex_plan = len(lanes) > 1

    if policy == "strict" and complex_plan and not trusted:
        for lane in lanes:
            for field in ("dependsOn", "purpose", "contributionRole", "semanticAuthority"):
                if field not in lane["orchestrationDeclared"]:
                    blockers.append({"code": "orchestration_field_required", "lane": lane["name"], "field": field})
            if lane["dependsOn"] and "dependencyReasons" not in lane["orchestrationDeclared"]:
                blockers.append({"code": "dependency_reason_required", "lane": lane["name"]})
            if lane["workerRequired"] and not (lane["capabilityRequirements"] or lane["capabilityNeeds"]):
                blockers.append({"code": "lane_capability_required", "lane": lane["name"]})
    elif complex_plan:
        for lane in lanes:
            if lane["dependencySource"] == "legacy-order":
                warnings.append({"code": "legacy_order_dependency", "lane": lane["name"], "reason": "parallelism was not explicitly planned"})

    for lane in lanes:
        if lane["contributionRole"] not in CONTRIBUTION_ROLES:
            blockers.append({"code": "invalid_contribution_role", "lane": lane["name"], "value": lane["contributionRole"]})
        if lane["semanticAuthority"] not in SEMANTIC_AUTHORITIES:
            blockers.append({"code": "invalid_semantic_authority", "lane": lane["name"], "value": lane["semanticAuthority"]})
        if lane["handoffRisk"] not in HANDOFF_RISKS:
            blockers.append({"code": "invalid_handoff_risk", "lane": lane["name"], "value": lane["handoffRisk"]})
        if lane["handoffMode"] not in HANDOFF_MODES:
            blockers.append({"code": "invalid_handoff_mode", "lane": lane["name"], "value": lane["handoffMode"]})
        if lane["verificationScope"] not in VERIFY_SCOPES:
            blockers.append({"code": "invalid_verification_scope", "lane": lane["name"], "value": lane["verificationScope"]})
        extra_reasons = sorted(set(lane["dependencyReasons"]) - set(lane["dependsOn"]))
        if extra_reasons:
            blockers.append({"code": "orphan_dependency_reason", "lane": lane["name"], "dependencies": extra_reasons})
        for dependency in lane["dependsOn"]:
            reason = lane["dependencyReasons"].get(dependency, "")
            if policy == "strict" and complex_plan and not trusted and not reason:
                blockers.append({"code": "dependency_reason_required", "lane": lane["name"], "dependency": dependency})
            if reason.lower().strip() in ORDER_ONLY_REASONS:
                blockers.append({"code": "order_only_dependency", "lane": lane["name"], "dependency": dependency})

    explicit_owners = [lane for lane in lanes if lane["semanticOwner"]]
    if not explicit_owners and (trusted or policy != "strict" or not complex_plan):
        candidates = [lane for lane in lanes if lane["semanticAuthority"] in {"define", "define-and-implement"}]
        if candidates:
            candidates[0]["semanticOwner"] = True
            explicit_owners = [candidates[0]]
            warnings.append({"code": "semantic_owner_inferred", "lane": candidates[0]["name"]})
    if complex_plan and not explicit_owners:
        blockers.append({"code": "semantic_owner_required", "reason": "one primary lane must own the result meaning"})
    if len(explicit_owners) > 1:
        blockers.append({"code": "multiple_semantic_owners", "lanes": [lane["name"] for lane in explicit_owners]})
    owner = explicit_owners[0] if len(explicit_owners) == 1 else None
    if owner and (owner["contributionRole"] != "primary" or owner["semanticAuthority"] not in {"define", "define-and-implement"}):
        blockers.append({"code": "invalid_semantic_owner", "lane": owner["name"]})

    output_producers: dict[str, list[str]] = {}
    for lane in lanes:
        for contract in lane["outputContracts"]:
            output_producers.setdefault(contract, []).append(lane["name"])
    for contract, producers in output_producers.items():
        if len(producers) > 1:
            ordered = all(
                left in ancestors.get(right, set()) or right in ancestors.get(left, set())
                for index, left in enumerate(producers)
                for right in producers[index + 1:]
            )
            item = {"code": "versioned_output_contract" if ordered else "ambiguous_output_producer", "contract": contract, "lanes": producers}
            (warnings if ordered else blockers).append(item)
    for lane in lanes:
        for contract in lane["inputContracts"]:
            producers = output_producers.get(contract, [])
            if not producers and contract not in lane["externalInputs"]:
                item = {"code": "undeclared_external_input", "lane": lane["name"], "contract": contract}
                (blockers if policy == "strict" and not trusted else warnings).append(item)
            elif producers:
                valid = [
                    producer for producer in producers
                    if producer != lane["name"] and producer in ancestors.get(lane["name"], set())
                ]
                if not valid:
                    blockers.append({"code": "missing_artifact_dependency", "lane": lane["name"], "contract": contract, "producer": producers[0]})

    writers = [lane for lane in lanes if lane["writeBoundary"] == "approved-target" or lane["semanticAuthority"] in {"implement", "define-and-implement"}]
    for index, left in enumerate(writers):
        left_targets = set(left["writeTargets"])
        for right in writers[index + 1:]:
            if left_targets & set(right["writeTargets"]) and left["name"] not in ancestors.get(right["name"], set()) and right["name"] not in ancestors.get(left["name"], set()):
                blockers.append({"code": "parallel_shared_writer", "lanes": [left["name"], right["name"]], "targets": sorted(left_targets & set(right["writeTargets"]))})

    primary_implementers = [lane for lane in lanes if lane["contributionRole"] == "primary" and lane["semanticAuthority"] in {"implement", "define-and-implement"}]
    if owner:
        for lane in primary_implementers:
            if lane["name"] != owner["name"] and owner["name"] not in ancestors.get(lane["name"], set()):
                blockers.append({"code": "implementation_before_semantic_owner", "lane": lane["name"], "owner": owner["name"]})
            if lane["name"] != owner["name"]:
                if policy == "strict" and not trusted:
                    for field in ("handoffRisk", "handoffMode"):
                        if field not in lane["orchestrationDeclared"]:
                            blockers.append({"code": "handoff_field_required", "lane": lane["name"], "field": field})
                if lane["handoffMode"] == "same-lane":
                    blockers.append({"code": "invalid_separate_handoff", "lane": lane["name"], "owner": owner["name"]})
                if lane["handoffRisk"] == "high" and (lane["handoffMode"] != "artifact-contract" or not lane["handoffContract"]):
                    blockers.append({"code": "lossy_handoff", "lane": lane["name"], "owner": owner["name"], "reason": "high-risk design/production split requires a concrete artifact contract or one combined lane"})

    final_writers = [lane for lane in writers if lane["writeBoundary"] == "approved-target"] or writers
    for lane in lanes:
        if lane["semanticAuthority"] != "verify" or lane["verificationScope"] == "upstream-decision":
            continue
        if lane["verificationScope"] == "intermediate-artifact":
            subjects: set[str] = set()
            for contract in lane["inputContracts"]:
                upstream = set(output_producers.get(contract, [])) & ancestors.get(lane["name"], set())
                # For a versioned contract, judge the latest consumed version,
                # not a future producer of the same contract ID.
                subjects.update(name for name in upstream if not any(name in ancestors.get(other, set()) for other in upstream))
            if not subjects:
                blockers.append({"code": "verification_subject_required", "lane": lane["name"], "reason": "intermediate review must name a produced input artifact"})
        else:
            subjects = {writer["name"] for writer in final_writers if writer["name"] != lane["name"]}
        lane["verificationSubjects"] = [name for name in names if name in subjects]
        for subject in lane["verificationSubjects"]:
            if subject not in ancestors.get(lane["name"], set()):
                blockers.append({"code": "premature_verification", "lane": lane["name"], "writer": subject, "reason": "verification must consume the artifact it judges"})

    capability_routes = route_lane_capabilities(
        lanes,
        active_capability_ids=active_capability_ids,
        runtime_availability=runtime_availability,
        available_capabilities=available_capabilities,
    )
    for route in capability_routes:
        if route["missing"]:
            item = {"code": "capability_unavailable", "lane": route["lane"], "missing": route["missing"]}
            (blockers if policy == "strict" else warnings).append(item)
        elif route["status"] in {"unbound", "suggested"} and by_name[route["lane"]]["workerRequired"]:
            item = {"code": "capability_unbound", "lane": route["lane"]}
            (blockers if policy == "strict" else warnings).append(item)

    primary_effort = sum(lane["estimatedEffort"] for lane in lanes if lane["contributionRole"] == "primary")
    supporting_effort = sum(lane["estimatedEffort"] for lane in lanes if lane["contributionRole"] == "supporting")
    if primary_effort and supporting_effort > primary_effort:
        warnings.append({"code": "support_dominance", "primaryEffort": primary_effort, "supportingEffort": supporting_effort})

    serial_edges: list[dict[str, str]] = []
    for lane in lanes:
        for dependency in lane["dependsOn"]:
            serial_edges.append({
                "from": dependency,
                "to": lane["name"],
                "reason": lane["dependencyReasons"].get(dependency, "legacy ordered-lane dependency" if lane["dependencySource"] == "legacy-order" else "dependency declared without reason"),
            })
    waves = [{"wave": index + 1, "lanes": wave, "parallel": len(wave) > 1} for index, wave in enumerate(wave_names)]
    join_points = [{"lane": lane["name"], "waitsFor": lane["dependsOn"]} for lane in lanes if len(lane["dependsOn"]) > 1]
    primary_path = [name for name in order if by_name[name]["contributionRole"] in {"primary", "verification"}]
    plan = {
        "orchestrationVersion": ORCHESTRATION_VERSION,
        "policy": policy,
        "source": "trusted-solution-graph" if trusted else "lane-definitions",
        "lanes": lanes,
        "topologicalOrder": order,
        "waves": waves,
        "parallelGroups": [wave["lanes"] for wave in waves if wave["parallel"]],
        "serialEdges": sorted(serial_edges, key=_canonical),
        "joinPoints": join_points,
        "semanticOwnerLane": owner["name"] if owner else "",
        "primaryPath": primary_path,
        "capabilityRoutes": capability_routes,
        "runtimeSelectionStage": "after-orchestration",
        "orchestrationExecutable": not blockers,
        "runtimeReady": not blockers and all(route["runtimeReady"] for route in capability_routes if by_name[route["lane"]]["workerRequired"]),
        "blockers": sorted(blockers, key=_canonical),
        "warnings": sorted(warnings, key=_canonical),
        "orchestrationDigest": "",
    }
    plan["orchestrationDigest"] = _digest({key: value for key, value in plan.items() if key != "orchestrationDigest"})
    return plan
