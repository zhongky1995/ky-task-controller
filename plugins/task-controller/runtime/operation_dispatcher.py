"""Permit-governed operation dispatch with deterministic evidence receipts.

The state-transition helpers are pure functions.  ``OperationPermitStore`` adds
the small in-process lock needed when several workers attempt to claim a permit.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from threading import RLock
from typing import Any, Mapping, Protocol, runtime_checkable


PERMIT_VERSION = "1.0"
PERMIT_STATUSES = {
    "issued", "claimed", "consumed", "revoked", "expired", "reconcile_required",
}
_IDENTITY_FIELDS = (
    "planIdentity", "graphIdentity", "packetIdentity", "blueprintIdentity", "contractIdentity",
)
_REQUIRED_FIELDS = (
    "permitVersion", "permitId", *_IDENTITY_FIELDS, "workerId", "runtimeHandle",
    "capabilityId", "operationId", "targetId", "targetLocator", "action", "payload",
    "payloadFingerprint", "restrictedFields", "approvalRefs", "idempotencyKey", "adapterId",
    "readbackSpec", "issuedAt", "expiresAt", "status",
)
_TERMINAL_STATUSES = {"consumed", "revoked", "expired", "reconcile_required"}


class PermitError(ValueError):
    """Base class for permit failures."""


class PermitValidationError(PermitError):
    """A permit is malformed or does not bind the requested operation."""


class PermitStateError(PermitError):
    """A requested transition is not allowed from the current state."""


class DispatchError(PermitError):
    """Dispatch cannot begin because its adapter or permit is unsafe."""


@runtime_checkable
class AdapterProtocol(Protocol):
    """External operation adapter.  Readback is mandatory for every dispatch."""

    adapter_id: str

    def execute(self, payload: Mapping[str, Any]) -> Any: ...

    def readback(self, spec: Mapping[str, Any], result: Any) -> Any: ...


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _timestamp(value: str | datetime | None = None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise PermitValidationError("timestamps must include a timezone")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if not isinstance(value, str):
        raise PermitValidationError("timestamp must be an ISO-8601 string")
    _parse_timestamp(value)
    return value


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise PermitValidationError("timestamp must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PermitValidationError("timestamp must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise PermitValidationError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PermitValidationError(f"{field} must be a non-empty string")
    return value.strip()


def normalize_payload(payload: Any) -> Any:
    """Return a JSON-only, order-stable deep copy of a payload.

    Object key order never affects the payload fingerprint; array order remains
    meaningful and is preserved.
    """
    if payload is None or isinstance(payload, (str, bool, int)):
        return payload
    if isinstance(payload, float):
        if payload != payload or payload in (float("inf"), float("-inf")):
            raise PermitValidationError("payload must not contain non-finite numbers")
        return payload
    if isinstance(payload, list):
        return [normalize_payload(item) for item in payload]
    if isinstance(payload, dict):
        result: dict[str, Any] = {}
        for key in sorted(payload):
            if not isinstance(key, str):
                raise PermitValidationError("payload object keys must be strings")
            result[key] = normalize_payload(payload[key])
        return result
    raise PermitValidationError("payload must be JSON-compatible")


def payload_fingerprint(payload: Any) -> str:
    return _digest(normalize_payload(payload))


def _identity(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise PermitValidationError(f"{field} must be a non-empty object")
    normalized = normalize_payload(value)
    if not any(key in normalized for key in ("id", "digest", "fingerprint", "version")):
        raise PermitValidationError(f"{field} must include an id, digest, fingerprint, or version")
    return normalized


def _normalise_identities(data: dict[str, Any]) -> None:
    # Accept explicit flat forms at the API boundary while retaining one stable
    # schema representation inside every issued permit.
    for name in _IDENTITY_FIELDS:
        if name in data:
            continue
        prefix = name.removesuffix("Identity")
        identity = {
            key[len(prefix):].lstrip("_").lower(): data[key]
            for key in list(data)
            if key.startswith(prefix) and key not in _IDENTITY_FIELDS
        }
        if identity:
            data[name] = identity


def issue_permit(permit: Mapping[str, Any] | None = None, /, *, now: str | datetime | None = None, **fields: Any) -> dict[str, Any]:
    """Issue a validated permit and bind it to the canonical payload hash."""
    data = deepcopy(dict(permit or {}))
    data.update(deepcopy(fields))
    _normalise_identities(data)
    data.setdefault("permitVersion", PERMIT_VERSION)
    data.setdefault("status", "issued")
    data.setdefault("issuedAt", _timestamp(now))
    if "expiresAt" not in data:
        raise PermitValidationError("expiresAt is required")
    data["payload"] = normalize_payload(data.get("payload"))
    data["payloadFingerprint"] = payload_fingerprint(data["payload"])
    data.setdefault("restrictedFields", [])
    data.setdefault("approvalRefs", [])
    data.setdefault("readbackSpec", {})
    return validate_permit(data)


def validate_permit(permit: Mapping[str, Any], *, now: str | datetime | None = None, allow_expired: bool = False) -> dict[str, Any]:
    """Validate a permit without changing it and return a normalized copy."""
    if not isinstance(permit, Mapping):
        raise PermitValidationError("permit must be an object")
    result = deepcopy(dict(permit))
    missing = [field for field in _REQUIRED_FIELDS if field not in result]
    if missing:
        raise PermitValidationError("missing required fields: " + ", ".join(missing))
    if result["permitVersion"] != PERMIT_VERSION:
        raise PermitValidationError(f"permitVersion must be {PERMIT_VERSION}")
    for field in (
        "permitId", "workerId", "runtimeHandle", "capabilityId", "operationId", "targetId",
        "targetLocator", "action", "idempotencyKey", "adapterId",
    ):
        result[field] = _nonempty(result[field], field)
    for field in _IDENTITY_FIELDS:
        result[field] = _identity(result[field], field)
    result["payload"] = normalize_payload(result["payload"])
    if result["payloadFingerprint"] != payload_fingerprint(result["payload"]):
        raise PermitValidationError("payloadFingerprint does not match payload")
    for field in ("restrictedFields", "approvalRefs"):
        if not isinstance(result[field], list) or not all(isinstance(item, str) and item for item in result[field]):
            raise PermitValidationError(f"{field} must be a string array")
    if not isinstance(result["readbackSpec"], dict):
        raise PermitValidationError("readbackSpec must be an object")
    if result["status"] not in PERMIT_STATUSES:
        raise PermitValidationError("status is invalid")
    issued_at = _parse_timestamp(result["issuedAt"])
    expires_at = _parse_timestamp(result["expiresAt"])
    if expires_at <= issued_at:
        raise PermitValidationError("expiresAt must be after issuedAt")
    for field in ("claimId", "claimedAt", "consumedAt"):
        if field in result and result[field] is not None:
            if field.endswith("At"):
                _parse_timestamp(result[field])
            else:
                result[field] = _nonempty(result[field], field)
    if result["status"] == "claimed" and (not result.get("claimId") or not result.get("claimedAt")):
        raise PermitValidationError("claimed permits require claimId and claimedAt")
    if result["status"] in {"consumed", "reconcile_required"} and not result.get("consumedAt"):
        raise PermitValidationError("completed permits require consumedAt")
    if not allow_expired and result["status"] not in _TERMINAL_STATUSES and now is not None:
        if _parse_timestamp(_timestamp(now)) >= expires_at:
            raise PermitStateError("permit is expired")
    return result


def transition_permit(permit: Mapping[str, Any], event: str, /, *, now: str | datetime | None = None, claim_id: str | None = None) -> dict[str, Any]:
    """Apply exactly one legal state transition without mutating ``permit``."""
    result = validate_permit(permit, now=now, allow_expired=True)
    moment = _timestamp(now)
    expired = _parse_timestamp(moment) >= _parse_timestamp(result["expiresAt"])
    if event == "expire":
        if result["status"] in _TERMINAL_STATUSES:
            raise PermitStateError(f"cannot expire permit in {result['status']}")
        result["status"] = "expired"
        return result
    if expired and result["status"] not in _TERMINAL_STATUSES:
        result["status"] = "expired"
        raise PermitStateError("permit is expired")
    if event == "claim":
        claim = _nonempty(claim_id, "claimId")
        if result["status"] != "issued":
            raise PermitStateError(f"cannot claim permit in {result['status']}")
        result.update({"status": "claimed", "claimId": claim, "claimedAt": moment})
    elif event in {"consume", "reconcile"}:
        if result["status"] != "claimed":
            raise PermitStateError(f"cannot {event} permit in {result['status']}")
        if claim_id is not None and result.get("claimId") != claim_id:
            raise PermitStateError("claimId does not own this permit")
        result.update({"status": "consumed" if event == "consume" else "reconcile_required", "consumedAt": moment})
    elif event == "revoke":
        if result["status"] not in {"issued", "claimed"}:
            raise PermitStateError(f"cannot revoke permit in {result['status']}")
        result["status"] = "revoked"
    else:
        raise PermitStateError(f"unknown permit event: {event}")
    return validate_permit(result, allow_expired=True)


def claim_permit(permit: Mapping[str, Any], claim_id: str, *, now: str | datetime | None = None) -> dict[str, Any]:
    return transition_permit(permit, "claim", now=now, claim_id=claim_id)


def consume_permit(permit: Mapping[str, Any], claim_id: str | None = None, *, now: str | datetime | None = None) -> dict[str, Any]:
    return transition_permit(permit, "consume", now=now, claim_id=claim_id)


def revoke_permit(permit: Mapping[str, Any], *, now: str | datetime | None = None) -> dict[str, Any]:
    return transition_permit(permit, "revoke", now=now)


def expire_permit(permit: Mapping[str, Any], *, now: str | datetime | None = None) -> dict[str, Any]:
    return transition_permit(permit, "expire", now=now)


def reconcile_claimed_permit(
    permit: Mapping[str, Any],
    adapter: AdapterProtocol,
    *,
    claim_id: str,
    now: str | datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve an interrupted dispatch by readback only; never execute again."""
    requested = validate_permit(permit, now=now, allow_expired=True)
    if requested["status"] != "claimed" or requested.get("claimId") != claim_id:
        raise PermitStateError("reconciliation requires the existing claimed permit owner")
    if getattr(adapter, "adapter_id", None) != requested["adapterId"]:
        raise DispatchError("registered adapter ID does not match permit adapterId")
    readback = getattr(adapter, "readback", None)
    if not callable(readback):
        raise DispatchError("adapter must provide readback(spec, result)")
    started = _timestamp(now)
    observation: Any = None
    failure: str | None = None
    try:
        observation = readback(deepcopy(requested["readbackSpec"]), None)
        if not _observation_is_consistent(requested["readbackSpec"], observation):
            raise DispatchError("reconciliation readback is missing or inconsistent")
        status = "consumed"
    except Exception as error:
        status = "reconcile_required"
        failure = f"{type(error).__name__}: {error}"
    completed = _timestamp(now)
    before_version, after_version = _versions(None, observation)
    receipt = {
        "receiptVersion": "1.0",
        "receiptId": _digest({"permitId": requested["permitId"], "idempotencyKey": requested["idempotencyKey"], "payloadFingerprint": requested["payloadFingerprint"]}),
        "permitId": requested["permitId"],
        "targetId": requested["targetId"], "targetLocator": requested["targetLocator"],
        "action": requested["action"], "payloadFingerprint": requested["payloadFingerprint"],
        "providerResultDigest": _digest(None), "readbackDigest": _digest(observation),
        "beforeVersion": before_version, "afterVersion": after_version,
        "artifactFingerprint": _digest({"targetId": requested["targetId"], "targetLocator": requested["targetLocator"], "afterVersion": after_version, "observation": observation}),
        "idempotencyKey": requested["idempotencyKey"], "adapterFingerprint": _adapter_fingerprint(adapter),
        "startedAt": started, "completedAt": completed, "status": status,
        "reconciled": True,
    }
    if failure:
        receipt["reconcileReason"] = failure
    updated = transition_permit(
        requested, "consume" if status == "consumed" else "reconcile",
        now=now, claim_id=claim_id,
    )
    return updated, receipt


class OperationPermitStore:
    """Thread-safe, in-memory permit ledger with atomic compare-and-transition."""

    def __init__(self) -> None:
        self._permits: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def issue(self, permit: Mapping[str, Any]) -> dict[str, Any]:
        issued = validate_permit(permit, allow_expired=True)
        with self._lock:
            existing = self._permits.get(issued["permitId"])
            if existing is not None and existing != issued:
                raise PermitStateError("permitId is already registered with different content")
            self._permits.setdefault(issued["permitId"], issued)
            return deepcopy(self._permits[issued["permitId"]])

    def get(self, permit_id: str) -> dict[str, Any]:
        with self._lock:
            if permit_id not in self._permits:
                raise PermitStateError("unknown permitId")
            return deepcopy(self._permits[permit_id])

    def transition(self, permit_id: str, event: str, *, now: str | datetime | None = None, claim_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            current = self.get(permit_id)
            updated = transition_permit(current, event, now=now, claim_id=claim_id)
            self._permits[permit_id] = updated
            return deepcopy(updated)


def _adapter_fingerprint(adapter: Any) -> str:
    value = getattr(adapter, "fingerprint", None)
    if isinstance(value, str) and value:
        return value
    return _digest({"adapterId": getattr(adapter, "adapter_id", ""), "type": f"{type(adapter).__module__}.{type(adapter).__qualname__}"})


def _observation_is_consistent(spec: Mapping[str, Any], observation: Any) -> bool:
    if observation is None:
        return False
    if isinstance(observation, Mapping) and observation.get("consistent") is False:
        return False
    expected = spec.get("expected")
    if expected is None:
        return True
    if not isinstance(expected, Mapping) or not isinstance(observation, Mapping):
        return False
    return all(observation.get(key) == value for key, value in expected.items())


def _versions(result: Any, observation: Any) -> tuple[Any, Any]:
    combined: dict[str, Any] = {}
    if isinstance(result, Mapping):
        combined.update(result)
    if isinstance(observation, Mapping):
        combined.update(observation)
    return combined.get("beforeVersion"), combined.get("afterVersion")


class Dispatcher:
    """Execute an adapter once per idempotency key and retain its evidence receipt."""

    def __init__(self, adapters: Mapping[str, AdapterProtocol], *, permit_store: OperationPermitStore | None = None) -> None:
        self.adapters = dict(adapters)
        self.permits = permit_store or OperationPermitStore()
        self._receipts: dict[str, dict[str, Any]] = {}
        self._receipt_lock = RLock()
        # A receipt key cannot be reserved durably by this in-memory runtime, so
        # serialize dispatches to guarantee at-most-once adapter execution.
        self._dispatch_lock = RLock()

    def issue(self, permit: Mapping[str, Any] | None = None, /, *, now: str | datetime | None = None, **fields: Any) -> dict[str, Any]:
        return self.permits.issue(issue_permit(permit, now=now, **fields))

    def claim(self, permit_id: str, claim_id: str, *, now: str | datetime | None = None) -> dict[str, Any]:
        return self.permits.transition(permit_id, "claim", now=now, claim_id=claim_id)

    def receipt_for(self, idempotency_key: str) -> dict[str, Any] | None:
        with self._receipt_lock:
            receipt = self._receipts.get(idempotency_key)
            return deepcopy(receipt) if receipt else None

    def dispatch(self, permit: Mapping[str, Any], payload: Any | None = None, *, claim_id: str | None = None, now: str | datetime | None = None) -> dict[str, Any]:
        with self._dispatch_lock:
            return self._dispatch(permit, payload, claim_id=claim_id, now=now)

    def _dispatch(self, permit: Mapping[str, Any], payload: Any | None = None, *, claim_id: str | None = None, now: str | datetime | None = None) -> dict[str, Any]:
        """Claim, execute, independently read back, and evidence one operation."""
        requested = validate_permit(permit, now=now, allow_expired=True)
        actual_payload = requested["payload"] if payload is None else normalize_payload(payload)
        actual_hash = payload_fingerprint(actual_payload)
        if actual_hash != requested["payloadFingerprint"]:
            raise PermitValidationError("dispatch payload does not match permit payloadFingerprint")
        with self._receipt_lock:
            previous = self._receipts.get(requested["idempotencyKey"])
            if previous is not None:
                if previous["permitId"] != requested["permitId"] or previous["payloadFingerprint"] != actual_hash:
                    raise PermitValidationError("idempotencyKey is already bound to another operation")
                return deepcopy(previous)

        self.permits.issue(requested)
        owner = claim_id or f"dispatch:{requested['permitId']}"
        current = self.permits.get(requested["permitId"])
        if _parse_timestamp(_timestamp(now)) >= _parse_timestamp(current["expiresAt"]):
            self.permits.transition(requested["permitId"], "expire", now=now)
            raise PermitStateError("permit is expired")
        if current["status"] == "issued":
            current = self.permits.transition(requested["permitId"], "claim", now=now, claim_id=owner)
        elif current["status"] != "claimed" or current.get("claimId") != owner:
            raise PermitStateError("permit must be claimed by this dispatch")
        adapter = self.adapters.get(requested["adapterId"])
        if adapter is None or not callable(getattr(adapter, "execute", None)):
            raise DispatchError("registered adapter with execute(payload) is required")
        if getattr(adapter, "adapter_id", None) != requested["adapterId"]:
            raise DispatchError("registered adapter ID does not match permit adapterId")

        started = _timestamp(now)
        result: Any = None
        observation: Any = None
        failure: str | None = None
        try:
            result = adapter.execute(deepcopy(actual_payload))
            readback = getattr(adapter, "readback", None)
            if not callable(readback):
                raise DispatchError("adapter must provide readback(spec, result)")
            observation = readback(deepcopy(requested["readbackSpec"]), deepcopy(result))
            if not _observation_is_consistent(requested["readbackSpec"], observation):
                raise DispatchError("readback is missing or inconsistent")
            status = "consumed"
        except Exception as error:  # External providers are untrusted; retain evidence and reconcile.
            status = "reconcile_required"
            failure = f"{type(error).__name__}: {error}"
        completed = _timestamp(now)
        before_version, after_version = _versions(result, observation)
        receipt = {
            "receiptVersion": "1.0",
            "receiptId": _digest({"permitId": requested["permitId"], "idempotencyKey": requested["idempotencyKey"], "payloadFingerprint": actual_hash}),
            "permitId": requested["permitId"],
            "targetId": requested["targetId"], "targetLocator": requested["targetLocator"],
            "action": requested["action"], "payloadFingerprint": actual_hash,
            "providerResultDigest": _digest(result), "readbackDigest": _digest(observation),
            "beforeVersion": before_version, "afterVersion": after_version,
            "artifactFingerprint": _digest({"targetId": requested["targetId"], "targetLocator": requested["targetLocator"], "afterVersion": after_version, "observation": observation}),
            "idempotencyKey": requested["idempotencyKey"], "adapterFingerprint": _adapter_fingerprint(adapter),
            "startedAt": started, "completedAt": completed, "status": status,
        }
        if failure:
            receipt["reconcileReason"] = failure
        self.permits.transition(requested["permitId"], "consume" if status == "consumed" else "reconcile", now=now, claim_id=owner)
        with self._receipt_lock:
            existing = self._receipts.setdefault(requested["idempotencyKey"], receipt)
            return deepcopy(existing)
