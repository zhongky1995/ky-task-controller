from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from verification.acceptance import (  # noqa: E402
    acceptance_case_fingerprint,
    aggregate_verification,
    evaluate_builtin,
    validate_acceptance_case,
    validate_verification_result,
)


MANIFEST = {"artifactFingerprint": "a" * 64}


def case(method: str = "readback", **overrides: object) -> dict:
    result = {
        "id": "case-main", "version": "1.0", "method": method,
        "procedure": {"mode": "equality"} if method == "readback" else {},
        "expected": {"complete": True} if method == "readback" else "expected",
        "threshold": 1, "evidenceSchema": {"minItems": 1}, "appliesTo": ["artifact-main"],
        "required": True, "minimumAttestation": "tool_verified",
    }
    result.update(overrides)
    return result


class VerificationFrameworkTests(unittest.TestCase):
    def test_case_fingerprint_is_deterministic_and_excludes_itself(self) -> None:
        first = validate_acceptance_case(case())
        reordered = deepcopy(first)
        reordered["appliesTo"].reverse()
        self.assertEqual(first["fingerprint"], acceptance_case_fingerprint(reordered))
        self.assertEqual(first, validate_acceptance_case(first))

    def test_case_change_invalidates_result_binding(self) -> None:
        original = validate_acceptance_case(case())
        result = evaluate_builtin(original, MANIFEST, {"complete": True})
        changed = case(expected={"complete": False})
        with self.assertRaisesRegex(ValueError, "caseFingerprint"):
            validate_verification_result(result, changed, MANIFEST)

    def test_artifact_and_evidence_binding_reject_tampering(self) -> None:
        accepted = validate_acceptance_case(case())
        result = evaluate_builtin(accepted, MANIFEST, {"complete": True})
        with self.assertRaisesRegex(ValueError, "artifactFingerprint"):
            validate_verification_result(result, accepted, {"fingerprint": "b" * 64})
        tampered = deepcopy(result)
        tampered["evidenceDigest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "evidenceDigest"):
            validate_verification_result(tampered, accepted, MANIFEST)

    def test_attestation_strength_and_only_pass_results_cover_required_case(self) -> None:
        accepted = validate_acceptance_case(case(minimumAttestation="independent_reviewed"))
        result = evaluate_builtin(accepted, MANIFEST, {"complete": True})
        aggregate = aggregate_verification([accepted], [result], MANIFEST)
        self.assertFalse(aggregate["allowed"])
        self.assertEqual("insufficient_attestation", aggregate["blockers"][0]["code"])
        result["attestationType"] = "independent_reviewed"
        self.assertTrue(aggregate_verification([accepted], [result], MANIFEST)["allowed"])
        result["status"] = "fail"
        self.assertEqual("result_not_pass", aggregate_verification([accepted], [result], MANIFEST)["blockers"][0]["code"])

    def test_review_independence_rejects_writer_runtime_disguise(self) -> None:
        accepted = validate_acceptance_case(case(procedure={"mode": "equality", "risk": "high"}, minimumAttestation="independent_reviewed"))
        result = evaluate_builtin(accepted, MANIFEST, {"complete": True}, runtime_handle="writer-runtime")
        result["attestationType"] = "independent_reviewed"
        result["workerId"] = "writer-1"
        aggregate = aggregate_verification([accepted], [result], MANIFEST, {"writers": [{"workerId": "writer-1", "runtimeHandle": "writer-runtime"}]})
        self.assertEqual("reviewer_not_independent", aggregate["blockers"][0]["code"])

    def test_missing_and_duplicate_current_results_block(self) -> None:
        accepted = validate_acceptance_case(case())
        self.assertEqual("missing_current_result", aggregate_verification([accepted], [], MANIFEST)["blockers"][0]["code"])
        result = evaluate_builtin(accepted, MANIFEST, {"complete": True})
        duplicate = deepcopy(result)
        duplicate["resultId"] = "duplicate"
        self.assertEqual("duplicate_current_result", aggregate_verification([accepted], [result, duplicate], MANIFEST)["blockers"][0]["code"])

    def test_builtin_structural_hash_and_readback_are_deterministic(self) -> None:
        structural = case("structural", procedure={}, expected={"keys": ["title"], "units": ["u1"]})
        structural_result = evaluate_builtin(structural, MANIFEST, {"title": "ok", "units": [{"id": "u1"}]})
        self.assertEqual("pass", structural_result["status"])
        hash_case = case("hash", expected="", procedure={})
        input_value = {"a": 1}
        expected_digest = evaluate_builtin(hash_case, MANIFEST, input_value)["actual"]
        hash_case["expected"] = expected_digest
        self.assertEqual("pass", evaluate_builtin(hash_case, MANIFEST, input_value)["status"])
        readback = evaluate_builtin(case("readback", procedure={"mode": "contains"}, expected={"complete": True}), MANIFEST, {"complete": True, "other": 1})
        self.assertEqual("pass", readback["status"])
        self.assertEqual(readback, evaluate_builtin(case("readback", procedure={"mode": "contains"}, expected={"complete": True}), MANIFEST, {"other": 1, "complete": True}))

    def test_semantic_cases_require_an_external_declared_verifier(self) -> None:
        with self.assertRaisesRegex(ValueError, "externalVerifier"):
            validate_acceptance_case(case("semantic"))
        semantic = validate_acceptance_case(case("semantic", procedure={"externalVerifier": "expert-review"}))
        result = evaluate_builtin(case(), MANIFEST, {"complete": True})
        result.update({"caseId": semantic["id"], "caseVersion": semantic["version"], "caseFingerprint": semantic["fingerprint"], "procedureFingerprint": __import__("hashlib").sha256(b'{"externalVerifier":"expert-review"}').hexdigest(), "method": "semantic", "expected": semantic["expected"], "attestationType": "independent_reviewed"})
        result["evaluator"]["capabilityId"] = "expert-review"
        validate_verification_result(result, semantic, MANIFEST)


if __name__ == "__main__":
    unittest.main()
