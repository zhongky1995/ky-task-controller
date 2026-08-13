"""Explainable, read-only capability suggestions for the controller shadow path."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from registry.loader import CapabilityRegistry, load_registry


def _values(blueprint: dict[str, Any], key: str) -> set[str]:
    value = blueprint.get(key, [])
    if isinstance(value, str):
        return {value}
    return {item for item in value if isinstance(item, str)} if isinstance(value, list) else set()


def _available(capability: Any, active_ids: set[str] | None, runtime: dict[str, Any] | set[str] | None) -> tuple[bool, str | None]:
    capability_id = capability.id
    if active_ids is not None and capability_id not in active_ids:
        return False, "not active in the supplied capability set"
    runtimes = capability.data["dependencies"].get("runtimes", [])
    if isinstance(runtime, dict):
        if runtime.get(capability_id) is False:
            return False, f"capability runtime '{capability_id}' is unavailable"
        for provider in runtimes:
            if runtime.get(provider) is False:
                return False, f"provider runtime '{provider}' is unavailable"
    elif isinstance(runtime, set):
        if runtimes:
            if capability_id not in runtime and not any(provider in runtime for provider in runtimes):
                return False, "required provider runtime is unavailable"
        elif capability_id not in runtime:
            return False, "capability runtime is unavailable"
    return True, None


def _pack_score(pack: dict[str, Any], blueprint: dict[str, Any]) -> tuple[int, str] | None:
    domains = _values(blueprint, "domains") | _values(blueprint, "domain")
    artifacts = _values(blueprint, "artifactClasses") | _values(blueprint, "artifactClass")
    match = pack["match"]
    excludes = set(match.get("exclusions", []))
    if excludes & (domains | artifacts):
        return None
    domain_hits = domains & set(match.get("domains", []))
    artifact_hits = artifacts & set(match.get("artifactClasses", []))
    task_type = str(blueprint.get("taskType", "")).lower()
    task_hits = {
        value for value in match.get("taskTypes", [])
        if isinstance(value, str) and value.lower() in task_type
    }
    task_type_bypass_domains = set(match.get("taskTypeBypassDomains", []))
    if (
        match.get("requireTaskType") is True
        and not task_hits
        and not (domain_hits & task_type_bypass_domains)
    ):
        return None
    if match.get("requireDomain") is True and not domain_hits:
        return None
    if not domain_hits and not artifact_hits:
        return None
    matched = domain_hits | artifact_hits | task_hits
    return (
        len(domain_hits) * 10 + len(artifact_hits) * 20 + len(task_hits) * 30,
        "matched " + ", ".join(sorted(matched)),
    )


def shadow_route(
    blueprint: dict[str, Any],
    active_capability_ids: Iterable[str] | None = None,
    runtime_availability: dict[str, Any] | Iterable[str] | None = None,
    *,
    registry_root: Path | str | None = None,
) -> dict[str, Any]:
    """Return a suggestion only. This function never executes or mutates task state."""
    registry: CapabilityRegistry = load_registry(registry_root)
    active = set(active_capability_ids) if active_capability_ids is not None else None
    runtime = set(runtime_availability) if runtime_availability is not None and not isinstance(runtime_availability, dict) else runtime_availability
    blueprint_version = blueprint.get("blueprintVersion") if isinstance(blueprint.get("blueprintVersion"), str) else None
    packs = []
    for pack_id in {pack.id for pack in registry.scenario_packs}:
        try:
            packs.append(registry.scenario_load(pack_id, task_blueprint_version=blueprint_version))
        except ValueError:
            continue
    scored = [(score, pack) for pack in packs if (score := _pack_score(pack.data, blueprint))]
    scored.sort(key=lambda item: (-item[0][0], item[1].id))
    rejected: list[dict[str, str]] = []
    if not scored:
        return {"mode": "shadow", "selected": [], "rejected": rejected, "missing": [], "fallback": [], "reasons": ["No scenario pack matched the blueprint."]}
    _, pack = scored[0]
    for _, other in scored[1:]:
        rejected.append({"id": other.id, "reason": f"Less specific than selected scenario pack {pack.id}."})
    requirements = list(
        dict.fromkeys(pack.data["capabilityRequirements"] + list(_values(blueprint, "requiredCapabilities")))
    )
    selected: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    fallback: list[dict[str, str]] = []
    for capability_id in requirements:
        try:
            capability = registry.capability_load(capability_id)
        except ValueError:
            missing.append({"id": capability_id, "reason": "Required capability is not registered."})
            continue
        available, reason = _available(capability, active, runtime)
        if capability.data["status"] != "active":
            available, reason = False, f"Capability status is {capability.data['status']}."
        if available:
            selected.append({"id": capability_id, "reason": f"Required by scenario pack {pack.id}."})
            continue
        missing.append({"id": capability_id, "reason": reason or "Unavailable."})
        for alternative in capability.data["routing"].get("fallback", []):
            try:
                alt = registry.capability_load(alternative)
            except ValueError:
                alt = None
            alt_available, _ = _available(alt, active, runtime) if alt else (False, None)
            if alt and alt.data["status"] == "active" and alt_available:
                fallback.append({"for": capability_id, "id": alternative, "reason": "Registered equivalent-fallback candidate."})
                break
    verifier_missing = []
    for capability_id in pack.data["verifierRequirements"]:
        try:
            capability = registry.capability_load(capability_id)
        except ValueError:
            capability = None
        available, reason = _available(capability, active, runtime) if capability else (False, None)
        if capability is None or capability.data["status"] != "active" or not available:
            verifier_missing.append({"id": capability_id, "role": "verifier", "reason": reason or "Required verifier is unavailable."})
        else:
            selected.append({"id": capability_id, "role": "verifier", "reason": f"Required verifier for scenario pack {pack.id}."})
    missing.extend(verifier_missing)
    reasons = [f"Selected scenario pack {pack.id} {pack.version}: {scored[0][0][1]}."]
    reasons.append("Routing is shadow-only; no provider has been invoked.")
    if missing:
        reasons.append("Missing required capabilities block an executable route.")
    return {"mode": "shadow", "scenarioPack": {"id": pack.id, "version": pack.version}, "selected": selected, "rejected": rejected, "missing": missing, "fallback": fallback, "reasons": reasons}


class CapabilityRouter:
    """Small object wrapper for callers that retain a router instance."""

    def route(self, blueprint: dict[str, Any], active_capability_ids: Iterable[str] | None = None, runtime_availability: dict[str, Any] | Iterable[str] | None = None) -> dict[str, Any]:
        return shadow_route(blueprint, active_capability_ids, runtime_availability)
