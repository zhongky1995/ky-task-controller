"""Runtime primitives for permit-governed external operations."""

from .operation_dispatcher import (
    AdapterProtocol,
    DispatchError,
    Dispatcher,
    OperationPermitStore,
    PermitStateError,
    PermitValidationError,
    claim_permit,
    consume_permit,
    expire_permit,
    issue_permit,
    normalize_payload,
    payload_fingerprint,
    reconcile_claimed_permit,
    revoke_permit,
    transition_permit,
    validate_permit,
)

__all__ = [
    "AdapterProtocol",
    "DispatchError",
    "Dispatcher",
    "OperationPermitStore",
    "PermitStateError",
    "PermitValidationError",
    "claim_permit",
    "consume_permit",
    "expire_permit",
    "issue_permit",
    "normalize_payload",
    "payload_fingerprint",
    "reconcile_claimed_permit",
    "revoke_permit",
    "transition_permit",
    "validate_permit",
]
