"""Deterministic acceptance cases, verification results, and built-in checks.

The module only evaluates mechanically observable facts.  Semantic and
business cases are intentionally accepted only as results from an explicitly
declared external verifier; this module never makes that judgment itself.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
from typing import Any


CASE_VERSION = "1.0"
RESULT_VERSION = "1.0"
BUILTIN_METHODS = frozenset({"structural", "hash", "readback"})
ATTESTATION_STRENGTH = {
    "self_attested": 0,
    "tool_verified": 1,
    "independent_reviewed": 2,
    "human_approved": 3,
}
_DIGEST_LENGTH = 64


def _fail(message: str) -> None:
    raise ValueError(f"Verification: {message}")


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        _fail(f"value must be JSON-serializable: {error}")


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} must be a non-empty string")
    return value.strip()


def _digest_string(value: Any, label: str) -> str:
    value = _nonempty(value, label)
    if len(value) != _DIGEST_LENGTH or any(character not in "0123456789abcdef" for character in value):
        _fail(f"{label} must be a lowercase SHA-256 digest")
    return value


def _finite_probability(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        _fail(f"{label} must be a finite number from 0 through 1")
    value = float(value)
    if not 0 <= value <= 1:
        _fail(f"{label} must be from 0 through 1")
    return value


def _json_value(value: Any, label: str) -> Any:
    _canonical(value)
    return deepcopy(value)


def _string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        _fail(f"{label} must be an array of strings")
    values = [_nonempty(item, f"{label} item") for item in value]
    if len(set(values)) != len(values):
        _fail(f"{label} must contain unique strings")
    return sorted(values)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    return deepcopy(value)


def _external_verifiers(procedure: dict[str, Any]) -> set[str]:
    declared: set[str] = set()
    for field in ("externalVerifier", "verifierCapabilityId"):
        value = procedure.get(field)
        if isinstance(value, str) and value.strip():
            declared.add(value.strip())
    value = procedure.get("verifierCapabilities")
    if isinstance(value, list):
        declared.update(_string_list(value, "procedure.verifierCapabilities"))
    return declared


def normalize_acceptance_case(case: Any) -> dict[str, Any]:
    """Validate and canonicalize an AcceptanceCase without its fingerprint."""
    raw = _object(case, "AcceptanceCase")
    unknown = set(raw) - {
        "id", "version", "method", "procedure", "expected", "threshold",
        "evidenceSchema", "appliesTo", "required", "minimumAttestation", "fingerprint",
    }
    if unknown:
        _fail(f"AcceptanceCase has unknown fields: {', '.join(sorted(unknown))}")
    procedure = _object(raw.get("procedure"), "AcceptanceCase.procedure")
    method = _nonempty(raw.get("method"), "AcceptanceCase.method")
    if method in {"semantic", "business"} and not _external_verifiers(procedure):
        _fail(f"AcceptanceCase {method} method requires procedure.externalVerifier or verifierCapabilityId")
    result = {
        "id": _nonempty(raw.get("id"), "AcceptanceCase.id"),
        "version": _nonempty(raw.get("version", CASE_VERSION), "AcceptanceCase.version"),
        "method": method,
        "procedure": procedure,
        "expected": _json_value(raw.get("expected"), "AcceptanceCase.expected"),
        "threshold": _finite_probability(raw.get("threshold", 1), "AcceptanceCase.threshold"),
        "evidenceSchema": _object(raw.get("evidenceSchema", {}), "AcceptanceCase.evidenceSchema"),
        "appliesTo": _string_list(raw.get("appliesTo", []), "AcceptanceCase.appliesTo"),
        "required": raw.get("required", True),
        "minimumAttestation": _nonempty(raw.get("minimumAttestation", "tool_verified"), "AcceptanceCase.minimumAttestation"),
    }
    if not isinstance(result["required"], bool):
        _fail("AcceptanceCase.required must be boolean")
    if result["minimumAttestation"] not in ATTESTATION_STRENGTH:
        _fail("AcceptanceCase.minimumAttestation is not a recognized attestation type")
    declared_fingerprint = raw.get("fingerprint")
    if declared_fingerprint is not None and _digest_string(declared_fingerprint, "AcceptanceCase.fingerprint") != acceptance_case_fingerprint(result):
        _fail("AcceptanceCase.fingerprint does not match case content")
    return result


def acceptance_case_fingerprint(case: Any) -> str:
    """Fingerprint all normalized case content, never a supplied fingerprint."""
    raw = _object(case, "AcceptanceCase")
    raw.pop("fingerprint", None)
    normalized = normalize_acceptance_case(raw)
    return _digest(normalized)


def validate_acceptance_case(case: Any) -> dict[str, Any]:
    normalized = normalize_acceptance_case(case)
    normalized["fingerprint"] = acceptance_case_fingerprint(normalized)
    return normalized


def procedure_fingerprint(case: Any) -> str:
    return _digest(validate_acceptance_case(case)["procedure"])


def _artifact_fingerprint(manifest: Any) -> str:
    if isinstance(manifest, str):
        return _digest_string(manifest, "artifact manifest fingerprint")
    if not isinstance(manifest, dict):
        _fail("artifact manifest must be an object or fingerprint string")
    for field in ("artifactFingerprint", "fingerprint", "manifestFingerprint"):
        if field in manifest:
            return _digest_string(manifest[field], f"artifact manifest.{field}")
    _fail("artifact manifest must declare artifactFingerprint, fingerprint, or manifestFingerprint")


def _evidence_refs(value: Any) -> list[Any]:
    if not isinstance(value, list):
        _fail("VerificationResult.evidenceRefs must be an array")
    return sorted((_json_value(item, "VerificationResult.evidenceRefs item") for item in value), key=_canonical)


def _validate_evidence_schema(schema: dict[str, Any], refs: list[Any]) -> None:
    """A compact deterministic evidence contract, without a JSON Schema dependency."""
    required_keys = schema.get("requiredKeys", [])
    if required_keys:
        keys = _string_list(required_keys, "AcceptanceCase.evidenceSchema.requiredKeys")
        present = {key for ref in refs if isinstance(ref, dict) for key in ref}
        missing = sorted(set(keys) - present)
        if missing:
            _fail(f"VerificationResult.evidenceRefs missing evidence keys: {', '.join(missing)}")
    minimum_refs = schema.get("minItems")
    if minimum_refs is not None:
        if not isinstance(minimum_refs, int) or isinstance(minimum_refs, bool) or minimum_refs < 0:
            _fail("AcceptanceCase.evidenceSchema.minItems must be a non-negative integer")
        if len(refs) < minimum_refs:
            _fail("VerificationResult.evidenceRefs does not meet evidenceSchema.minItems")


def normalize_verification_result(result: Any) -> dict[str, Any]:
    """Validate result shape and normalize its unordered evidence/review fields."""
    raw = _object(result, "VerificationResult")
    allowed = {
        "resultVersion", "resultId", "caseId", "caseVersion", "caseFingerprint", "artifactFingerprint",
        "evaluator", "procedureFingerprint", "method", "normalizedInputDigest", "expected", "actual",
        "status", "evidenceRefs", "evidenceDigest", "confidence", "executedAt", "attestationType",
        "workerId", "reviewedWorkerIds",
    }
    unknown = set(raw) - allowed
    if unknown:
        _fail(f"VerificationResult has unknown fields: {', '.join(sorted(unknown))}")
    evaluator = _object(raw.get("evaluator"), "VerificationResult.evaluator")
    if set(evaluator) != {"capabilityId", "version", "runtimeHandle"}:
        _fail("VerificationResult.evaluator requires exactly capabilityId, version, runtimeHandle")
    result = {
        "resultVersion": _nonempty(raw.get("resultVersion", RESULT_VERSION), "VerificationResult.resultVersion"),
        "resultId": _nonempty(raw.get("resultId"), "VerificationResult.resultId"),
        "caseId": _nonempty(raw.get("caseId"), "VerificationResult.caseId"),
        "caseVersion": _nonempty(raw.get("caseVersion"), "VerificationResult.caseVersion"),
        "caseFingerprint": _digest_string(raw.get("caseFingerprint"), "VerificationResult.caseFingerprint"),
        "artifactFingerprint": _digest_string(raw.get("artifactFingerprint"), "VerificationResult.artifactFingerprint"),
        "evaluator": {key: _nonempty(evaluator[key], f"VerificationResult.evaluator.{key}") for key in sorted(evaluator)},
        "procedureFingerprint": _digest_string(raw.get("procedureFingerprint"), "VerificationResult.procedureFingerprint"),
        "method": _nonempty(raw.get("method"), "VerificationResult.method"),
        "normalizedInputDigest": _digest_string(raw.get("normalizedInputDigest"), "VerificationResult.normalizedInputDigest"),
        "expected": _json_value(raw.get("expected"), "VerificationResult.expected"),
        "actual": _json_value(raw.get("actual"), "VerificationResult.actual"),
        "status": _nonempty(raw.get("status"), "VerificationResult.status"),
        "evidenceRefs": _evidence_refs(raw.get("evidenceRefs")),
        "evidenceDigest": _digest_string(raw.get("evidenceDigest"), "VerificationResult.evidenceDigest"),
        "confidence": _finite_probability(raw.get("confidence"), "VerificationResult.confidence"),
        "executedAt": _nonempty(raw.get("executedAt"), "VerificationResult.executedAt"),
        "attestationType": _nonempty(raw.get("attestationType"), "VerificationResult.attestationType"),
    }
    if result["status"] not in {"pass", "fail", "error", "skipped"}:
        _fail("VerificationResult.status must be pass, fail, error, or skipped")
    if result["attestationType"] not in ATTESTATION_STRENGTH:
        _fail("VerificationResult.attestationType is not a recognized attestation type")
    if "workerId" in raw:
        result["workerId"] = _nonempty(raw["workerId"], "VerificationResult.workerId")
    if "reviewedWorkerIds" in raw:
        result["reviewedWorkerIds"] = _string_list(raw["reviewedWorkerIds"], "VerificationResult.reviewedWorkerIds")
    return result


def validate_verification_result(result: Any, case: Any, artifact_manifest: Any) -> dict[str, Any]:
    """Validate a result's immutable links to its case, artifact, procedure, and evidence."""
    normalized_case = validate_acceptance_case(case)
    normalized_result = normalize_verification_result(result)
    bindings = {
        "caseId": normalized_case["id"],
        "caseVersion": normalized_case["version"],
        "caseFingerprint": normalized_case["fingerprint"],
        "artifactFingerprint": _artifact_fingerprint(artifact_manifest),
        "procedureFingerprint": _digest(normalized_case["procedure"]),
        "method": normalized_case["method"],
        "expected": normalized_case["expected"],
    }
    for field, expected in bindings.items():
        if normalized_result[field] != expected:
            _fail(f"VerificationResult.{field} is not bound to the current AcceptanceCase or artifact")
    if normalized_result["evidenceDigest"] != _digest(normalized_result["evidenceRefs"]):
        _fail("VerificationResult.evidenceDigest does not match evidenceRefs")
    _validate_evidence_schema(normalized_case["evidenceSchema"], normalized_result["evidenceRefs"])
    if normalized_case["method"] in {"semantic", "business"}:
        declared = _external_verifiers(normalized_case["procedure"])
        if normalized_result["evaluator"]["capabilityId"] not in declared:
            _fail("semantic/business VerificationResult evaluator is not the declared external verifier")
        if normalized_result["attestationType"] == "self_attested":
            _fail("semantic/business VerificationResult cannot be self-attested")
    return normalized_result


def _builtin_result(case: Any, artifact_manifest: Any, input_value: Any, actual: Any, passed: bool, evidence: list[Any], capability_id: str, runtime_handle: str, executed_at: str | None) -> dict[str, Any]:
    normalized_case = validate_acceptance_case(case)
    artifact_fingerprint = _artifact_fingerprint(artifact_manifest)
    normalized_input = _json_value(input_value, "built-in evaluator input")
    evidence_refs = _evidence_refs(evidence)
    result_seed = {
        "caseFingerprint": normalized_case["fingerprint"], "artifactFingerprint": artifact_fingerprint,
        "normalizedInputDigest": _digest(normalized_input), "actual": actual, "evidenceRefs": evidence_refs,
        "capabilityId": capability_id, "runtimeHandle": runtime_handle,
    }
    result = {
        "resultVersion": RESULT_VERSION,
        "resultId": f"builtin:{_digest(result_seed)}",
        "caseId": normalized_case["id"], "caseVersion": normalized_case["version"],
        "caseFingerprint": normalized_case["fingerprint"], "artifactFingerprint": artifact_fingerprint,
        "evaluator": {"capabilityId": capability_id, "version": "1.0", "runtimeHandle": runtime_handle},
        "procedureFingerprint": _digest(normalized_case["procedure"]), "method": normalized_case["method"],
        "normalizedInputDigest": _digest(normalized_input), "expected": normalized_case["expected"],
        "actual": actual, "status": "pass" if passed else "fail", "evidenceRefs": evidence_refs,
        "evidenceDigest": _digest(evidence_refs), "confidence": 1.0,
        "executedAt": executed_at or "1970-01-01T00:00:00Z", "attestationType": "tool_verified",
    }
    return validate_verification_result(result, normalized_case, artifact_manifest)


def _structural_actual(input_value: Any, procedure: dict[str, Any], expected: Any, threshold: float) -> tuple[dict[str, Any], bool]:
    if not isinstance(input_value, dict):
        _fail("structural evaluator input must be an object")
    expected_spec = expected if isinstance(expected, dict) else {}
    required_keys = _string_list(procedure.get("requiredKeys", expected_spec.get("requiredKeys", expected_spec.get("keys", []))), "procedure.requiredKeys")
    expected_units = _string_list(procedure.get("requiredUnits", expected_spec.get("requiredUnits", expected_spec.get("units", []))), "procedure.requiredUnits")
    unit_field = _nonempty(procedure.get("unitField", "units"), "procedure.unitField")
    missing_keys = sorted(key for key in required_keys if key not in input_value)
    raw_units = input_value.get(unit_field, [])
    if not isinstance(raw_units, list):
        _fail(f"structural evaluator input.{unit_field} must be an array")
    actual_units = {item if isinstance(item, str) else item.get("id") for item in raw_units if isinstance(item, (str, dict))}
    missing_units = sorted(unit for unit in expected_units if unit not in actual_units)
    total = len(required_keys) + len(expected_units)
    matched = total - len(missing_keys) - len(missing_units)
    coverage = 1.0 if total == 0 else matched / total
    actual = {"missingKeys": missing_keys, "missingUnits": missing_units, "keysPresent": sorted(input_value), "unitsPresent": sorted(unit for unit in actual_units if isinstance(unit, str)), "coverage": coverage}
    return actual, coverage >= threshold


def _readback_actual(input_value: Any, expected: Any, procedure: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    mode = _nonempty(procedure.get("mode", procedure.get("operator", "equality")), "procedure.mode")
    if mode == "equality":
        return {"mode": mode, "observed": input_value, "matched": input_value == expected}, input_value == expected
    if mode == "contains":
        if isinstance(input_value, dict) and isinstance(expected, dict):
            passed = all(key in input_value and input_value[key] == value for key, value in expected.items())
        elif isinstance(input_value, (str, list, tuple, set)):
            values = expected if isinstance(expected, list) else [expected]
            passed = all(value in input_value for value in values)
        else:
            _fail("readback contains input must be a string, collection, or object")
        return {"mode": mode, "observed": input_value, "matched": passed}, passed
    _fail("procedure.mode must be equality or contains")


def evaluate_builtin(case: Any, artifact_manifest: Any, input_value: Any, *, capability_id: str = "verification.builtin", runtime_handle: str = "local", executed_at: str | None = None) -> dict[str, Any]:
    """Run a deterministic structural, hash, or readback evaluator.

    The supplied input is normalized into the result digest.  No semantic or
    business method is implemented here.
    """
    normalized_case = validate_acceptance_case(case)
    if normalized_case["method"] not in BUILTIN_METHODS:
        _fail(f"built-in evaluator does not support {normalized_case['method']} cases")
    if normalized_case["method"] == "structural":
        actual, passed = _structural_actual(input_value, normalized_case["procedure"], normalized_case["expected"], normalized_case["threshold"])
    elif normalized_case["method"] == "hash":
        actual = _digest(input_value)
        expected = normalized_case["expected"]
        if isinstance(expected, dict):
            expected = expected.get("sha256", expected.get("digest"))
        passed = actual == expected
    else:
        actual, passed = _readback_actual(input_value, normalized_case["expected"], normalized_case["procedure"])
    evidence = [{"method": normalized_case["method"], "input": _json_value(input_value, "built-in evaluator input"), "inputDigest": _digest(input_value), "actual": actual}]
    return _builtin_result(normalized_case, artifact_manifest, input_value, actual, passed, evidence, capability_id, runtime_handle, executed_at)


def evaluate_structural(case: Any, artifact_manifest: Any, input_value: Any, **kwargs: Any) -> dict[str, Any]:
    """Run the built-in structural keys/units evaluator."""
    if validate_acceptance_case(case)["method"] != "structural":
        _fail("evaluate_structural requires a structural AcceptanceCase")
    return evaluate_builtin(case, artifact_manifest, input_value, **kwargs)


def evaluate_hash_match(case: Any, artifact_manifest: Any, input_value: Any, **kwargs: Any) -> dict[str, Any]:
    """Run the built-in SHA-256 equality evaluator."""
    if validate_acceptance_case(case)["method"] != "hash":
        _fail("evaluate_hash_match requires a hash AcceptanceCase")
    return evaluate_builtin(case, artifact_manifest, input_value, **kwargs)


def evaluate_readback(case: Any, artifact_manifest: Any, input_value: Any, **kwargs: Any) -> dict[str, Any]:
    """Run the built-in readback equality or contains evaluator."""
    if validate_acceptance_case(case)["method"] != "readback":
        _fail("evaluate_readback requires a readback AcceptanceCase")
    return evaluate_builtin(case, artifact_manifest, input_value, **kwargs)


def _writer_records(context: dict[str, Any]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for field in ("coveredWriters", "artifactWriters", "writers"):
        raw = context.get(field, [])
        if isinstance(raw, list):
            for value in raw:
                if isinstance(value, dict):
                    records.append({key: value[key] for key in ("workerId", "runtimeHandle") if isinstance(value.get(key), str) and value[key].strip()})
    for worker_id in _string_list(context.get("coveredWriterIds", context.get("writerWorkerIds", [])), "context.writerWorkerIds"):
        records.append({"workerId": worker_id})
    for runtime_handle in _string_list(context.get("coveredRuntimeHandles", context.get("writerRuntimeHandles", [])), "context.writerRuntimeHandles"):
        records.append({"runtimeHandle": runtime_handle})
    return records


def _requires_independence(case: dict[str, Any], context: dict[str, Any]) -> bool:
    if case["id"] in set(_string_list(context.get("highRiskCaseIds", []), "context.highRiskCaseIds")):
        return True
    procedure = case["procedure"]
    return case["method"] == "review" or procedure.get("reviewRequired") is True or procedure.get("risk") == "high"


def _is_independent(result: dict[str, Any], writers: list[dict[str, str]]) -> bool:
    worker_ids = {item["workerId"] for item in writers if "workerId" in item}
    runtimes = {item["runtimeHandle"] for item in writers if "runtimeHandle" in item}
    worker = result.get("workerId")
    runtime = result["evaluator"]["runtimeHandle"]
    # reviewedWorkerIds identifies the writers being reviewed.  Its coverage is
    # a controller provenance concern, not evidence that the evaluator shares
    # an identity with a writer.
    return not ((worker and worker in worker_ids) or runtime in runtimes)


def aggregate_verification(cases: Any, results: Any, artifact_manifest: Any, context: Any = None) -> dict[str, Any]:
    """Apply current-result, attestation, and reviewer-independence final gates."""
    if not isinstance(cases, list) or not isinstance(results, list):
        _fail("aggregate_verification cases and results must be arrays")
    normalized_cases = [validate_acceptance_case(case) for case in cases]
    case_ids = [case["id"] for case in normalized_cases]
    if len(set(case_ids)) != len(case_ids):
        _fail("aggregate_verification cases must have unique IDs")
    if not isinstance(context, (dict, type(None))):
        _fail("aggregate_verification context must be an object")
    normalized_context = context or {}
    artifact_fingerprint = _artifact_fingerprint(artifact_manifest)
    blockers: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    writers = _writer_records(normalized_context)

    for case in normalized_cases:
        current: list[dict[str, Any]] = []
        for raw_result in results:
            if not isinstance(raw_result, dict) or raw_result.get("caseId") != case["id"]:
                continue
            try:
                candidate = validate_verification_result(raw_result, case, artifact_manifest)
            except ValueError:
                continue
            if candidate["artifactFingerprint"] == artifact_fingerprint:
                current.append(candidate)
        entry: dict[str, Any] = {"caseId": case["id"], "required": case["required"], "currentResultCount": len(current), "satisfied": False}
        if not case["required"]:
            entry["satisfied"] = bool(len(current) == 1 and current[0]["status"] == "pass")
            coverage.append(entry)
            continue
        if not current:
            blockers.append({"code": "missing_current_result", "caseId": case["id"]})
        elif len(current) > 1:
            blockers.append({"code": "duplicate_current_result", "caseId": case["id"], "resultIds": sorted(item["resultId"] for item in current)})
        else:
            result = current[0]
            entry["resultId"] = result["resultId"]
            if result["status"] != "pass":
                blockers.append({"code": "result_not_pass", "caseId": case["id"], "status": result["status"]})
            elif ATTESTATION_STRENGTH[result["attestationType"]] < ATTESTATION_STRENGTH[case["minimumAttestation"]]:
                blockers.append({"code": "insufficient_attestation", "caseId": case["id"], "actual": result["attestationType"], "minimum": case["minimumAttestation"]})
            elif _requires_independence(case, normalized_context) and result["attestationType"] in {"self_attested", "independent_reviewed"} and not _is_independent(result, writers):
                blockers.append({"code": "reviewer_not_independent", "caseId": case["id"]})
            else:
                entry["satisfied"] = True
        coverage.append(entry)
    return {"allowed": not blockers, "blockers": blockers, "coverage": coverage}


# Short aliases keep the contract vocabulary usable by controller adapters.
normalize_case = normalize_acceptance_case
validate_case = validate_acceptance_case
fingerprint_case = acceptance_case_fingerprint
normalize_result = normalize_verification_result
validate_result = validate_verification_result
