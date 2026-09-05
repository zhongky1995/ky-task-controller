"""Durable worker admission; caller holds the controller's state lock.

No host tasks are created here. A reserved claim consumes capacity until it is
bound to a worker or explicitly reconciled. Timeouts never imply non-creation.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4


RUNNING_STATUSES = {"pending", "running"}
CURRENT_ATTEMPT_STATUSES = RUNNING_STATUSES | {"done", "needs-work", "blocked"}


class AdmissionError(ValueError):
    pass


def active_workers(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [worker for worker in state.get("workers", [])
            if worker.get("status") in RUNNING_STATUSES or worker.get("runtimeStopPending") is True]


def reserved_claims(state: dict[str, Any]) -> list[dict[str, Any]]:
    # Include old revisions: an uncertain host creation must be reconciled,
    # not silently forgotten when the contract changes.
    return [claim for claim in state.get("dispatchClaims", []) if claim.get("status") == "reserved"]


def capacity(state: dict[str, Any]) -> dict[str, int]:
    maximum = state.get("executionPolicy", {}).get("maxParallelWorkers", 1)
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
        maximum = 1
    active = len(active_workers(state))
    reserved = len(reserved_claims(state))
    return {
        "maxParallelWorkers": maximum,
        "activeWorkers": active,
        "reservedDispatches": reserved,
        "availableSlots": max(0, maximum - active - reserved),
    }


def lane_attempts(state: dict[str, Any], lane: str) -> list[dict[str, Any]]:
    return [worker for worker in state.get("workers", [])
            if worker.get("lane") == lane
            and worker.get("contractRevision") == state["contractRevision"]
            and worker.get("status") in CURRENT_ATTEMPT_STATUSES]


def require_admission(state: dict[str, Any], lane: str, claim_id: str = "") -> None:
    if lane_attempts(state, lane):
        raise AdmissionError(f"lane_attempt_exists: {lane}; complete or explicitly supersede its current attempt")
    if any(worker.get("lane") == lane for worker in active_workers(state)):
        raise AdmissionError(f"lane_runtime_not_stopped: {lane}; confirm the retired runtime has stopped before replacement")
    other_claims = [claim for claim in reserved_claims(state) if claim.get("claimId") != claim_id]
    if any(claim.get("lane") == lane for claim in other_claims):
        raise AdmissionError(f"lane_dispatch_reserved: {lane}; reconcile the existing claim before creating another task")
    occupied = len(active_workers(state)) + len(other_claims)
    if occupied >= capacity(state)["maxParallelWorkers"]:
        raise AdmissionError("worker_capacity_exceeded: no dispatch slot available")


def reserve_dispatch(
    state: dict[str, Any], lane: str, request_id: str, evidence: dict[str, str], timestamp: str,
) -> dict[str, Any]:
    claims = state.setdefault("dispatchClaims", [])
    existing = next((item for item in claims if item.get("requestId") == request_id), None)
    if existing:
        if (existing.get("lane") != lane or existing.get("contractRevision") != state["contractRevision"]
                or existing.get("orchestrationPlanDigest", "") != state.get("orchestrationPlanDigest", "")):
            raise AdmissionError("dispatch_request_conflict: requestId belongs to another lane or plan revision")
        if existing.get("status") == "released":
            raise AdmissionError("dispatch_request_closed: use a new requestId after reconciliation")
        return existing
    if any(worker.get("requestId") == request_id for worker in state.get("workers", [])):
        raise AdmissionError("dispatch_request_conflict: requestId already belongs to a worker")
    require_admission(state, lane)
    claim = {
        "claimId": "dispatch-" + uuid4().hex,
        "requestId": request_id,
        "lane": lane,
        "contractRevision": state["contractRevision"],
        "orchestrationPlanDigest": state.get("orchestrationPlanDigest", ""),
        "capabilityEvidence": evidence,
        "status": "reserved",
        "created_at": timestamp,
        "updated_at": timestamp,
        "workerId": "",
    }
    claims.append(claim)
    return claim


def registration_claim(state: dict[str, Any], lane: str, request_id: str, claim_id: str) -> dict[str, Any] | None:
    claim = next((item for item in state.get("dispatchClaims", []) if item.get("claimId") == claim_id), None) if claim_id else None
    if claim_id and claim is None:
        raise AdmissionError("dispatch_claim_not_found")
    if claim:
        if (claim.get("status") != "reserved" or claim.get("lane") != lane
                or claim.get("requestId") != request_id
                or claim.get("contractRevision") != state["contractRevision"]
                or claim.get("orchestrationPlanDigest", "") != state.get("orchestrationPlanDigest", "")):
            raise AdmissionError("dispatch_claim_mismatch: reconcile stale creation; do not bind it to a new plan")
    require_admission(state, lane, claim_id)
    return claim


def release_dispatch(state: dict[str, Any], claim_id: str, outcome: str, evidence: str, timestamp: str) -> dict[str, Any]:
    claim = next((item for item in state.get("dispatchClaims", []) if item.get("claimId") == claim_id), None)
    if claim is None:
        raise AdmissionError("dispatch_claim_not_found")
    if outcome not in {"not-created", "stopped"} or not evidence.strip():
        raise AdmissionError("dispatch_reconciliation_required: confirm not-created or stopped with evidence")
    if claim.get("status") == "released":
        if claim.get("outcome") != outcome or claim.get("reconciliationEvidence") != evidence:
            raise AdmissionError("dispatch_reconciliation_conflict")
        return claim
    if claim.get("status") != "reserved":
        raise AdmissionError("dispatch_claim_bound: use the registered worker lifecycle")
    claim.update(status="released", outcome=outcome, reconciliationEvidence=evidence, updated_at=timestamp)
    return claim
