"""Fail-closed worker runtime profiles and capability-based selection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "worker-runtime-profiles.json"
)
IDENTITY_BINDINGS = {
    "thread_id_equals_runtime_handle",
    "opaque_runtime_handle",
}
SCOPE_KINDS = {"project", "projectless"}
CALLBACK_MODES = {
    "active_message_required",
    "active_message_preferred",
    "controller_poll_allowed",
    "managed_result_collected",
}
PROFILE_KEYS = {
    "runtimeId",
    "profileVersion",
    "independent",
    "userVisible",
    "supportsPersistent",
    "requiresExplicitApproval",
    "approvalPolicyField",
    "identityBinding",
    "scopeKinds",
    "defaultScopeKind",
    "callbackModes",
    "defaultCallbackMode",
    "requiresThreadRouting",
    "selectionPriority",
}


class RuntimeProfileError(ValueError):
    """Raised when the checked-in runtime registry is missing or invalid."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeProfileError(f"{field} must be a non-empty string")
    return value.strip()


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise RuntimeProfileError(f"{field} must be a boolean")
    return value


def _string_list(value: Any, field: str, allowed: set[str]) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or item not in allowed for item in value)
    ):
        raise RuntimeProfileError(
            f"{field} must be a non-empty array containing only {sorted(allowed)}"
        )
    if len(value) != len(set(value)):
        raise RuntimeProfileError(f"{field} must not contain duplicates")
    return tuple(value)


@dataclass(frozen=True)
class WorkerRuntimeProfile:
    runtime_id: str
    profile_version: str
    independent: bool
    user_visible: bool
    supports_persistent: bool
    requires_explicit_approval: bool
    approval_policy_field: str
    identity_binding: str
    scope_kinds: tuple[str, ...]
    default_scope_kind: str
    callback_modes: tuple[str, ...]
    default_callback_mode: str
    requires_thread_routing: bool
    selection_priority: int
    fingerprint: str

    def supports_scope(self, scope_kind: str) -> bool:
        return scope_kind in self.scope_kinds

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtimeId": self.runtime_id,
            "profileVersion": self.profile_version,
            "independent": self.independent,
            "userVisible": self.user_visible,
            "supportsPersistent": self.supports_persistent,
            "requiresExplicitApproval": self.requires_explicit_approval,
            "approvalPolicyField": self.approval_policy_field,
            "identityBinding": self.identity_binding,
            "scopeKinds": list(self.scope_kinds),
            "defaultScopeKind": self.default_scope_kind,
            "callbackModes": list(self.callback_modes),
            "defaultCallbackMode": self.default_callback_mode,
            "requiresThreadRouting": self.requires_thread_routing,
            "selectionPriority": self.selection_priority,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class RuntimeRequirement:
    independent: bool = True
    user_visible: bool = False
    persistent: bool = False
    scope_kind: str = ""


@dataclass(frozen=True)
class WorkerRuntimeRegistry:
    registry_version: str
    profiles: tuple[WorkerRuntimeProfile, ...]
    fingerprint: str

    @property
    def by_id(self) -> dict[str, WorkerRuntimeProfile]:
        return {profile.runtime_id: profile for profile in self.profiles}

    def get(self, runtime_id: str) -> WorkerRuntimeProfile | None:
        return self.by_id.get(runtime_id)

    def require(self, runtime_id: str) -> WorkerRuntimeProfile:
        profile = self.get(runtime_id)
        if profile is None:
            raise RuntimeProfileError(f"Unknown worker runtime profile: {runtime_id}")
        return profile

    def independent_runtime_ids(self) -> set[str]:
        return {profile.runtime_id for profile in self.profiles if profile.independent}

    def to_dict(self) -> dict[str, Any]:
        return {
            "registryVersion": self.registry_version,
            "registryFingerprint": self.fingerprint,
            "profiles": [profile.to_dict() for profile in self.profiles],
        }


def _parse_profile(raw: Any, index: int) -> WorkerRuntimeProfile:
    if not isinstance(raw, dict):
        raise RuntimeProfileError(f"profiles[{index}] must be an object")
    unknown = set(raw) - PROFILE_KEYS
    missing = PROFILE_KEYS - set(raw)
    if unknown or missing:
        details = []
        if missing:
            details.append(f"missing={sorted(missing)}")
        if unknown:
            details.append(f"unknown={sorted(unknown)}")
        raise RuntimeProfileError(f"profiles[{index}] has invalid fields: {', '.join(details)}")

    runtime_id = _nonempty(raw["runtimeId"], f"profiles[{index}].runtimeId")
    profile_version = _nonempty(
        raw["profileVersion"], f"profiles[{index}].profileVersion"
    )
    identity_binding = _nonempty(
        raw["identityBinding"], f"profiles[{index}].identityBinding"
    )
    if identity_binding not in IDENTITY_BINDINGS:
        raise RuntimeProfileError(
            f"profiles[{index}].identityBinding must be one of {sorted(IDENTITY_BINDINGS)}"
        )
    scope_kinds = _string_list(
        raw["scopeKinds"], f"profiles[{index}].scopeKinds", SCOPE_KINDS
    )
    default_scope_kind = _nonempty(
        raw["defaultScopeKind"], f"profiles[{index}].defaultScopeKind"
    )
    if default_scope_kind not in scope_kinds:
        raise RuntimeProfileError(
            f"profiles[{index}].defaultScopeKind must appear in scopeKinds"
        )
    callback_modes = _string_list(
        raw["callbackModes"], f"profiles[{index}].callbackModes", CALLBACK_MODES
    )
    default_callback_mode = _nonempty(
        raw["defaultCallbackMode"], f"profiles[{index}].defaultCallbackMode"
    )
    if default_callback_mode not in callback_modes:
        raise RuntimeProfileError(
            f"profiles[{index}].defaultCallbackMode must appear in callbackModes"
        )
    priority = raw["selectionPriority"]
    if not isinstance(priority, int) or isinstance(priority, bool) or priority < 0:
        raise RuntimeProfileError(
            f"profiles[{index}].selectionPriority must be a non-negative integer"
        )
    requires_explicit_approval = _boolean(
        raw["requiresExplicitApproval"],
        f"profiles[{index}].requiresExplicitApproval",
    )
    approval_policy_field = raw["approvalPolicyField"]
    if not isinstance(approval_policy_field, str):
        raise RuntimeProfileError(
            f"profiles[{index}].approvalPolicyField must be a string"
        )
    approval_policy_field = approval_policy_field.strip()
    if requires_explicit_approval != bool(approval_policy_field):
        raise RuntimeProfileError(
            f"profiles[{index}].approvalPolicyField must be non-empty exactly when "
            "requiresExplicitApproval is true"
        )

    return WorkerRuntimeProfile(
        runtime_id=runtime_id,
        profile_version=profile_version,
        independent=_boolean(raw["independent"], f"profiles[{index}].independent"),
        user_visible=_boolean(raw["userVisible"], f"profiles[{index}].userVisible"),
        supports_persistent=_boolean(
            raw["supportsPersistent"], f"profiles[{index}].supportsPersistent"
        ),
        requires_explicit_approval=requires_explicit_approval,
        approval_policy_field=approval_policy_field,
        identity_binding=identity_binding,
        scope_kinds=scope_kinds,
        default_scope_kind=default_scope_kind,
        callback_modes=callback_modes,
        default_callback_mode=default_callback_mode,
        requires_thread_routing=_boolean(
            raw["requiresThreadRouting"], f"profiles[{index}].requiresThreadRouting"
        ),
        selection_priority=priority,
        fingerprint=_fingerprint(raw),
    )


def load_runtime_profiles(path: str | Path | None = None) -> WorkerRuntimeRegistry:
    registry_path = Path(path) if path is not None else DEFAULT_REGISTRY_PATH
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeProfileError(f"Cannot read runtime profile registry: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeProfileError(f"Invalid runtime profile registry JSON: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {"registryVersion", "profiles"}:
        raise RuntimeProfileError(
            "Runtime profile registry requires exactly registryVersion and profiles"
        )
    registry_version = _nonempty(raw["registryVersion"], "registryVersion")
    profiles_raw = raw["profiles"]
    if not isinstance(profiles_raw, list) or not profiles_raw:
        raise RuntimeProfileError("profiles must be a non-empty array")
    profiles = tuple(_parse_profile(item, index) for index, item in enumerate(profiles_raw))
    runtime_ids = [profile.runtime_id for profile in profiles]
    if len(runtime_ids) != len(set(runtime_ids)):
        raise RuntimeProfileError("runtimeId values must be unique")
    priorities = [profile.selection_priority for profile in profiles]
    if len(priorities) != len(set(priorities)):
        raise RuntimeProfileError("selectionPriority values must be unique")
    if not any(profile.independent for profile in profiles):
        raise RuntimeProfileError("At least one independent runtime profile is required")
    return WorkerRuntimeRegistry(
        registry_version=registry_version,
        profiles=profiles,
        fingerprint=_fingerprint(raw),
    )


def requirement_for_lane(
    lane: Mapping[str, Any], selection_policy: str = "lane_lifecycle"
) -> RuntimeRequirement:
    session_required = selection_policy == "native_session_required"
    return RuntimeRequirement(
        independent=True,
        user_visible=session_required,
        persistent=lane.get("workerLifecycle", "ephemeral") == "persistent",
        scope_kind="project" if session_required else "",
    )


def profile_satisfies(
    profile: WorkerRuntimeProfile, requirement: RuntimeRequirement
) -> bool:
    if requirement.independent and not profile.independent:
        return False
    if requirement.user_visible and not profile.user_visible:
        return False
    if requirement.persistent and not profile.supports_persistent:
        return False
    if requirement.scope_kind and not profile.supports_scope(requirement.scope_kind):
        return False
    return True


def approved_runtime_ids(
    approval_policy: Mapping[str, Any],
    registry: WorkerRuntimeRegistry | None = None,
) -> set[str]:
    active_registry = registry or RUNTIME_REGISTRY
    return {
        profile.runtime_id
        for profile in active_registry.profiles
        if not profile.requires_explicit_approval
        or approval_policy.get(profile.approval_policy_field) is True
    }


def select_runtime(
    lane: Mapping[str, Any],
    eligible_runtime_ids: Iterable[str],
    *,
    approved_runtime_ids: Iterable[str] = (),
    selection_policy: str = "lane_lifecycle",
    registry: WorkerRuntimeRegistry | None = None,
) -> str:
    active_registry = registry or RUNTIME_REGISTRY
    eligible = set(eligible_runtime_ids)
    approved = set(approved_runtime_ids)
    requirement = requirement_for_lane(lane, selection_policy)
    candidates = [
        profile
        for profile in active_registry.profiles
        if profile.runtime_id in eligible
        and profile_satisfies(profile, requirement)
        and (not profile.requires_explicit_approval or profile.runtime_id in approved)
    ]
    preference = lane.get("runtimePreference", "auto")
    if preference != "auto":
        return preference if any(profile.runtime_id == preference for profile in candidates) else ""
    candidates.sort(key=lambda profile: (profile.selection_priority, profile.runtime_id))
    return candidates[0].runtime_id if candidates else ""


RUNTIME_REGISTRY = load_runtime_profiles()
