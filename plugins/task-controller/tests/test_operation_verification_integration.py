from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from verification.acceptance import validate_acceptance_case  # noqa: E402


HELPER = ROOT / "scripts" / "task_controller_state.py"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def blueprint() -> dict[str, Any]:
    return {
        "blueprintVersion": "1.0", "id": "operation-integration", "taskType": "operations", "interactionMode": "execute",
        "domains": ["client-deck"], "artifactClass": "presentation",
        "outcome": {"businessGoal": "Deliver", "supportedDecision": "Approve"},
        "deliverable": {"id": "delivery", "kind": "presentation", "target": "deck", "format": "json", "audience": "client", "useMode": "handoff", "standalone": True, "artifactClass": "presentation"},
        "sources": [{"id": "source", "required": True}],
        "intentAnchors": [{"id": "anchor", "statement": "Remain in scope"}],
        "decisions": [{"id": "decision", "statement": "Use approved content", "status": "binding"}],
        "changePolicy": {"preserve": [{"id": "preserve"}], "allowed": [{"id": "allowed"}], "forbidden": [{"id": "forbidden"}]},
        "acceptanceCases": [
            {"id": "business", "description": "Independent business approval", "version": "1.0", "method": "business", "procedure": {"externalVerifier": "deck-verifier", "verifierCapabilities": ["alternate-verifier"]}, "expected": {"approved": True}, "evidenceSchema": {"minItems": 1}, "minimumAttestation": "independent_reviewed"},
            {"id": "structure", "description": "Deck contains required structure", "version": "1.0", "method": "structural", "procedure": {}, "expected": {"keys": ["pages"]}, "evidenceSchema": {"minItems": 1}, "minimumAttestation": "tool_verified"},
        ],
        "approvals": {}, "writePolicy": {"targets": [{"id": "deck", "locator": "/approved/deck"}], "allowedActions": ["update"], "destructiveActionsRequireApproval": True},
        "standards": [], "assumptions": [], "nonGoals": [], "capacity": {}, "changeTriggers": [],
    }


class OperationVerificationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "state.json"
        self.env = {**os.environ, "KY_TASK_TEST_MODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        self.command("init", "--state", str(self.state), "--goal", "operations", "--task-blueprint", json.dumps(blueprint()), "--auto-plan")
        self.prepare_writer()

    def command(self, command: str, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run([sys.executable, str(HELPER), command, *args], cwd=ROOT, text=True, capture_output=True, env=self.env)
        if ok and result.returncode:
            self.fail(result.stderr or result.stdout)
        if not ok and not result.returncode:
            self.fail(f"command unexpectedly passed: {result.stdout}")
        return result

    def output(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        return json.loads(result.stdout)

    def data(self) -> dict[str, Any]:
        return json.loads(self.state.read_text())

    def write(self, value: dict[str, Any]) -> None:
        self.state.write_text(json.dumps(value), encoding="utf-8")

    def prepare_writer(self) -> None:
        state = self.data()
        for lane in state["lanes"]:
            if lane["name"] == "production":
                lane["status"] = "running"
                continue
            if state["lanes"].index(lane) < next(i for i, item in enumerate(state["lanes"]) if item["name"] == "production"):
                lane.update({"status": "done", "decision": "pass", "artifact": lane["name"] + ".json", "carriedForwardAtRevision": 1})
        packet = state["workerPackets"]["production"]
        state["workers"] = [{
            "workerId": "writer", "contractRevision": 1, "status": "running", "decision": "", "artifact": "", "lane": "production",
            "runtimeHandle": "writer-runtime", "laneRuntime": "managed_agent_worker", "packetId": packet["packetId"], "packetDigest": packet["packetDigest"],
            "contractDigest": state["contractDigest"], "deliverableFingerprint": state["contractSpec"]["deliverableFingerprint"],
            "writeBoundary": "approved-target", "callbackExpected": False, "callbackReceived": False,
        }]
        self.write(state)

    def permit_args(self, permit_id: str = "permit-good", **changes: str) -> list[str]:
        values = {
            "permit_id": permit_id, "worker_id": "writer", "capability_id": "deck-script", "operation_id": "update-deck",
            "target_id": "deck", "target_locator": "/approved/deck", "action": "update", "payload": '{"pages": 3}',
            "idempotency_key": "deck-write", "adapter_id": "memory-test", "readback_spec": "{}", "expires_at": "2030-01-01T00:00:00Z",
        }
        values.update(changes)
        args: list[str] = []
        for name, value in values.items():
            args.extend(("--" + name.replace("_", "-"), value))
        return args

    def issue_and_dispatch(self, permit_id: str = "permit-good", **changes: str) -> dict[str, Any]:
        self.command("issue-operation-permit", "--state", str(self.state), *self.permit_args(permit_id, **changes))
        return self.output(self.command("dispatch-operation", "--state", str(self.state), "--permit-id", permit_id))

    def manifest(self) -> list[dict[str, Any]]:
        receipts = self.data().get("operationReceipts", [])
        receipt = next((item for item in receipts if item.get("status") == "consumed"), None)
        item: dict[str, Any] = {"id": "delivery-artifact", "deliverableId": "delivery", "path": "/approved/deck", "artifactFingerprint": "a" * 64}
        if receipt:
            item.update({
                "operationReceiptId": receipt["receiptId"],
                "operationArtifactFingerprint": receipt["artifactFingerprint"],
                "targetVersion": receipt.get("afterVersion") if receipt.get("afterVersion") is not None else "",
            })
        return [item]

    def verification_result(self, case: dict[str, Any], fingerprint: str, *, attestation: str, result_id: str, worker_id: str = "writer", runtime_handle: str = "review-runtime", capability_id: str = "deck-verifier", reviewed_worker_ids: list[str] | None = None) -> dict[str, Any]:
        evidence = [{"proof": case["id"]}]
        return {
            "resultVersion": "1.0", "resultId": result_id, "caseId": case["id"], "caseVersion": case["version"],
            "caseFingerprint": validate_acceptance_case({key: value for key, value in case.items() if key not in {"fingerprint", "description", "statement", "verification"}})["fingerprint"], "artifactFingerprint": fingerprint,
            "evaluator": {"capabilityId": capability_id, "version": "1.0", "runtimeHandle": runtime_handle},
            "procedureFingerprint": digest(case["procedure"]), "method": case["method"], "normalizedInputDigest": digest({}),
            "expected": case["expected"], "actual": case["expected"], "status": "pass", "evidenceRefs": evidence,
            "evidenceDigest": digest(evidence), "confidence": 1, "executedAt": "2026-07-13T00:00:00Z", "attestationType": attestation, "workerId": worker_id,
            "reviewedWorkerIds": reviewed_worker_ids or [],
        }

    def callback_args(self, receipt_ids: str, results: list[dict[str, Any]], *, worker_id: str = "writer", lane: str = "production") -> list[str]:
        state = self.data()
        packet = state["workerPackets"][lane]
        args = [
            "--state", str(self.state), "--worker-id", worker_id, "--from-lane", lane, "--artifact", "deck.json",
            "--packet-id", packet["packetId"], "--packet-digest", packet["packetDigest"],
            "--contract-digest", state["contractDigest"], "--deliverable-fingerprint", state["contractSpec"]["deliverableFingerprint"],
            "--callback-mode-observed", "managed_result_collected", "--artifact-manifest", json.dumps(self.manifest()),
            "--verification-results", json.dumps(results),
        ]
        if receipt_ids:
            args.extend(("--operation-receipt-ids", receipt_ids))
        return args

    def test_permit_rejects_unbound_target_action_payload_worker_adapter_and_approval(self) -> None:
        cases = [
            ({"target_id": "wrong"}, "target/action"), ({"action": "delete"}, "target/action"),
            ({"payload": "[]"}, "payload"), ({"worker_id": "wrong"}, "worker"),
            ({"adapter_id": "invalid"}, "invalid choice"), ({"approval_refs": "forged"}, "approvalRefs"),
        ]
        for changes, message in cases:
            with self.subTest(changes=changes):
                result = self.command("issue-operation-permit", "--state", str(self.state), *self.permit_args("reject-" + next(iter(changes)), **changes), ok=False)
                self.assertIn(message, result.stderr)

    def test_memory_dispatch_is_persistent_and_idempotent(self) -> None:
        receipt = self.issue_and_dispatch()
        replay = self.output(self.command("dispatch-operation", "--state", str(self.state), "--permit-id", "permit-good"))
        state = self.data()
        self.assertEqual("consumed", receipt["status"])
        self.assertEqual(receipt, replay)
        self.assertEqual("structured-v1", state["verificationEnforcement"])
        self.assertEqual(1, len(state["operationPermits"]))
        self.assertEqual(1, len(state["operationReceipts"]))

    def test_revoke_and_interrupted_dispatch_reconciliation(self) -> None:
        self.command("issue-operation-permit", "--state", str(self.state), *self.permit_args("permit-revoke", idempotency_key="revoke-write"))
        revoked = self.output(self.command("revoke-operation-permit", "--state", str(self.state), "--permit-id", "permit-revoke"))
        self.assertEqual("revoked", revoked["status"])
        self.assertIn("cannot be dispatched", self.command("dispatch-operation", "--state", str(self.state), "--permit-id", "permit-revoke", ok=False).stderr)
        self.command("issue-operation-permit", "--state", str(self.state), *self.permit_args("permit-crash", idempotency_key="crash-write"))
        state = self.data()
        permit = next(item for item in state["operationPermits"] if item["permitId"] == "permit-crash")
        permit.update({"status": "claimed", "claimId": "dispatch:permit-crash", "claimedAt": "2026-07-13T00:00:00Z"})
        self.write(state)
        self.assertIn("requires_reconciliation", self.command("dispatch-operation", "--state", str(self.state), "--permit-id", "permit-crash", ok=False).stderr)
        reconciled = self.output(self.command("reconcile-operation", "--state", str(self.state), "--permit-id", "permit-crash"))
        self.assertTrue(reconciled["reconciled"])
        self.assertEqual("consumed", reconciled["status"])

    def add_reviewer(self) -> None:
        state = self.data()
        next(lane for lane in state["lanes"] if lane["name"] == "production").update({"status": "done", "decision": "pass", "artifact": "deck.json"})
        next(lane for lane in state["lanes"] if lane["name"] == "review")["status"] = "running"
        review_packet = state["workerPackets"]["review"]
        state["workers"].append({
            "workerId": "reviewer", "contractRevision": 1, "status": "running", "decision": "", "artifact": "", "lane": "review",
            "runtimeHandle": "review-runtime", "laneRuntime": "managed_agent_worker", "packetId": review_packet["packetId"], "packetDigest": review_packet["packetDigest"],
            "contractDigest": state["contractDigest"], "deliverableFingerprint": state["contractSpec"]["deliverableFingerprint"],
            "writeBoundary": "review-only", "callbackExpected": False, "callbackReceived": False, "reviewsWorkerIds": ["writer"],
        })
        self.write(state)

    def record_result_args(self, result: dict[str, Any], *, worker_id: str = "reviewer", lane: str = "review") -> list[str]:
        state = self.data()
        packet = state["workerPackets"][lane]
        return [
            "--state", str(self.state), "--worker-id", worker_id, "--packet-id", packet["packetId"], "--packet-digest", packet["packetDigest"],
            "--case-id", result["caseId"], "--artifact-manifest", json.dumps(self.manifest()), "--verification-result", json.dumps(result),
        ]

    def test_callback_requires_current_receipt_and_independent_review_verification(self) -> None:
        receipt = self.issue_and_dispatch()
        manifest_fingerprint = digest(self.manifest())
        missing = self.command("record-callback", *self.callback_args("forged", []), ok=False)
        self.assertIn("not present", missing.stderr)
        self.write({**self.data(), "workers": [{**self.data()["workers"][0], "callbackReceived": False}]})
        worker = self.output(self.command("record-callback", *self.callback_args(json.dumps([receipt["receiptId"]]), [])))
        self.assertTrue(worker["verificationSummary"]["allowed"])
        self.assertEqual([receipt["receiptId"]], worker["operationReceiptIds"])

        state = self.data()
        state["workers"][0].update({"callbackReceived": False, "status": "running", "decision": ""})
        self.write(state)
        wrong_manifest = self.manifest()
        wrong_manifest[0]["path"] = "/not/the/dispatched/target"
        args = self.callback_args(json.dumps([receipt["receiptId"]]), [])
        index = args.index("--artifact-manifest") + 1
        args[index] = json.dumps(wrong_manifest)
        self.assertIn("targetLocator", self.command("record-callback", *args, ok=False).stderr)
        state = self.data()
        state["workers"][0].update({"callbackReceived": True, "status": "done", "decision": "pass"})
        self.write(state)
        self.add_reviewer()
        business = next(case for case in self.data()["workerPackets"]["review"]["acceptanceCases"] if case["id"] == "business")
        wrong_review_manifest = json.loads(json.dumps(self.manifest()))
        wrong_review_manifest[0]["artifactFingerprint"] = "b" * 64
        wrong_review_result = self.verification_result(
            business, digest(wrong_review_manifest), attestation="independent_reviewed",
            result_id="wrong-artifact", worker_id="reviewer", reviewed_worker_ids=["writer"],
        )
        state = self.data()
        review_packet = state["workerPackets"]["review"]
        wrong_args = [
            "--state", str(self.state), "--worker-id", "reviewer",
            "--packet-id", review_packet["packetId"], "--packet-digest", review_packet["packetDigest"],
            "--case-id", business["id"], "--artifact-manifest", json.dumps(wrong_review_manifest),
            "--verification-result", json.dumps(wrong_review_result),
        ]
        self.assertIn("covered writer artifact", self.command("record-verification-result", *wrong_args, ok=False).stderr)
        writer_result = self.verification_result(business, manifest_fingerprint, attestation="independent_reviewed", result_id="writer-business", worker_id="writer", runtime_handle="writer-runtime", reviewed_worker_ids=["writer"])
        self.assertIn("workerId", self.command("record-verification-result", *self.record_result_args(writer_result), ok=False).stderr)
        bad_runtime = self.verification_result(business, manifest_fingerprint, attestation="independent_reviewed", result_id="bad-runtime", worker_id="reviewer", runtime_handle="unregistered-runtime", reviewed_worker_ids=["writer"])
        self.assertIn("runtimeHandle", self.command("record-verification-result", *self.record_result_args(bad_runtime), ok=False).stderr)
        bad_capability = self.verification_result(business, manifest_fingerprint, attestation="independent_reviewed", result_id="bad-capability", worker_id="reviewer", capability_id="alternate-verifier", reviewed_worker_ids=["writer"])
        self.assertIn("not bound", self.command("record-verification-result", *self.record_result_args(bad_capability), ok=False).stderr)
        uncovered = self.verification_result(business, manifest_fingerprint, attestation="independent_reviewed", result_id="uncovered", worker_id="reviewer")
        self.assertIn("reviewedWorkerIds", self.command("record-callback", *self.callback_args("", [uncovered], worker_id="reviewer", lane="review"), ok=False).stderr)
        valid = self.verification_result(business, manifest_fingerprint, attestation="independent_reviewed", result_id="review-business", worker_id="reviewer", reviewed_worker_ids=["writer"])
        persisted = self.output(self.command("record-verification-result", *self.record_result_args(valid)))
        self.assertEqual("review-business", persisted["result"]["resultId"])
        review = self.output(self.command("record-callback", *self.callback_args("", [], worker_id="reviewer", lane="review")))
        self.assertTrue(review["verificationSummary"]["allowed"])

    def test_reconcile_receipt_and_prior_revision_evidence_do_not_pass(self) -> None:
        bad = self.issue_and_dispatch("permit-bad", adapter_options='{"readbackMode":"missing"}', idempotency_key="bad-write")
        self.assertEqual("reconcile_required", bad["status"])
        state = self.data()
        fingerprint = digest(self.manifest())
        self.assertIn("reconcile", self.command("record-callback", *self.callback_args(bad["receiptId"], []), ok=False).stderr)
        old = self.issue_and_dispatch("permit-old", idempotency_key="old-write")
        revised = blueprint()
        revised["outcome"]["businessGoal"] = "Revised delivery"
        self.command("revise-contract", "--state", str(self.state), "--invalid-from-lane", "production", "--task-blueprint", json.dumps(revised))
        self.assertIn("not current", self.command("dispatch-operation", "--state", str(self.state), "--permit-id", "permit-old", ok=False).stderr)
        self.assertTrue(old["receiptId"])

    def test_manual_state_keeps_legacy_callback_contract(self) -> None:
        legacy = Path(self.temp.name) / "legacy.json"
        state = self.output(self.command("init", "--state", str(legacy), "--goal", "legacy", "--lane-definitions", '[{"name":"research","kind":"research"}]', "--enforcement-mode", "workflow_only"))
        self.assertNotIn("verificationEnforcement", state)
        self.assertNotIn("operationReceipts", state)


if __name__ == "__main__":
    unittest.main()
