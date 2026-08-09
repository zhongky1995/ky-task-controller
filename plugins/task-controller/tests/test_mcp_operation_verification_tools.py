from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from verification.acceptance import validate_acceptance_case


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "task_controller_state.py"
SERVER = ROOT / "mcp" / "server.mjs"


def digest(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def blueprint() -> dict:
    return {
        "blueprintVersion": "1.0", "id": "mcp-operation-tools", "taskType": "client-facing-delivery", "interactionMode": "execute",
        "domains": ["client-deck"], "artifactClass": "presentation",
        "outcome": {"businessGoal": "Approve delivery", "supportedDecision": "Approve handoff"},
        "deliverable": {"id": "delivery", "kind": "presentation", "target": "deck", "format": "json", "audience": "client", "useMode": "handoff", "standalone": True, "artifactClass": "presentation"},
        "sources": [{"id": "source", "required": True}],
        "intentAnchors": [{"id": "anchor", "statement": "Stay in scope"}],
        "decisions": [{"id": "decision", "statement": "Use approved narrative", "status": "binding"}],
        "changePolicy": {"preserve": [{"id": "preserve"}], "allowed": [{"id": "allowed"}], "forbidden": [{"id": "forbidden"}]},
        "acceptanceCases": [
            {"id": "business", "description": "Independent business approval", "version": "1.0", "method": "business", "procedure": {"externalVerifier": "deck-verifier"}, "expected": {"approved": True}, "evidenceSchema": {"minItems": 1}, "minimumAttestation": "independent_reviewed"},
            {"id": "structure", "description": "Deck structure", "version": "1.0", "method": "structural", "procedure": {}, "expected": {"keys": ["pages"]}, "evidenceSchema": {"minItems": 1}, "minimumAttestation": "tool_verified"},
        ],
        "approvals": {}, "writePolicy": {"targets": [{"id": "deck", "locator": "/approved/deck"}], "allowedActions": ["update"], "destructiveActionsRequireApproval": True},
        "standards": [], "assumptions": [], "nonGoals": [], "capacity": {}, "changeTriggers": [],
    }


class McpOperationVerificationToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "state.json"
        self.env = {**os.environ, "KY_TASK_TEST_MODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        self.command("init", "--state", str(self.state), "--goal", "MCP operation tools", "--task-blueprint", json.dumps(blueprint()), "--auto-plan")
        self.prepare_writer()

    def command(self, command: str, *args: str) -> dict:
        result = subprocess.run([sys.executable, str(HELPER), command, *args], cwd=ROOT, text=True, capture_output=True, env=self.env, check=False)
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        return json.loads(result.stdout)

    def mcp(self, name: str, arguments: dict, *, error: bool = False) -> dict:
        request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}) + "\n"
        result = subprocess.run(["node", str(SERVER)], cwd=ROOT, input=request, text=True, capture_output=True, env=self.env, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        response = json.loads(result.stdout)
        if error:
            self.assertIn("error", response)
            return response["error"]
        self.assertNotIn("error", response)
        return response["result"]["structuredContent"]["result"]

    def prepare_writer(self) -> None:
        state = json.loads(self.state.read_text(encoding="utf-8"))
        production_index = next(index for index, lane in enumerate(state["lanes"]) if lane["name"] == "production")
        for index, lane in enumerate(state["lanes"]):
            if lane["name"] == "production":
                lane["status"] = "running"
            elif index < production_index:
                lane.update({"status": "done", "decision": "pass", "artifact": lane["name"] + ".json", "carriedForwardAtRevision": 1})
        packet = state["workerPackets"]["production"]
        state["workers"] = [{
            "workerId": "writer", "contractRevision": 1, "status": "running", "decision": "", "artifact": "", "lane": "production",
            "runtimeHandle": "writer-runtime", "laneRuntime": "managed_agent_worker", "packetId": packet["packetId"], "packetDigest": packet["packetDigest"],
            "contractDigest": state["contractDigest"], "deliverableFingerprint": state["contractSpec"]["deliverableFingerprint"],
            "writeBoundary": "approved-target", "callbackExpected": False, "callbackReceived": False,
        }]
        self.state.write_text(json.dumps(state), encoding="utf-8")

    def manifest(self) -> list[dict]:
        state = json.loads(self.state.read_text(encoding="utf-8"))
        receipt = next((item for item in state.get("operationReceipts", []) if item.get("status") == "consumed"), None)
        item = {"id": "delivery-artifact", "deliverableId": "delivery", "path": "/approved/deck", "artifactFingerprint": "a" * 64}
        if receipt:
            item.update({"operationReceiptId": receipt["receiptId"], "operationArtifactFingerprint": receipt["artifactFingerprint"], "targetVersion": receipt.get("afterVersion") or ""})
        return [item]

    def verification_result(self, case: dict, manifest_fingerprint: str) -> dict:
        normalized_case = validate_acceptance_case({key: value for key, value in case.items() if key not in {"fingerprint", "description", "statement", "verification"}})
        evidence = [{"proof": case["id"]}]
        return {
            "resultVersion": "1.0", "resultId": "result-" + case["id"], "caseId": case["id"], "caseVersion": case["version"],
            "caseFingerprint": normalized_case["fingerprint"], "artifactFingerprint": manifest_fingerprint,
            "evaluator": {"capabilityId": "deck-verifier", "version": "1.0", "runtimeHandle": "review-runtime"},
            "procedureFingerprint": digest(case["procedure"]), "method": case["method"], "normalizedInputDigest": digest({}),
            "expected": case["expected"], "actual": case["expected"], "status": "pass", "evidenceRefs": evidence,
            "evidenceDigest": digest(evidence), "confidence": 1, "executedAt": "2026-07-13T00:00:00Z",
            "attestationType": "independent_reviewed" if case["method"] == "business" else "tool_verified", "workerId": "writer",
        }

    def test_tools_list_and_cli_help_match_operation_protocol(self) -> None:
        listed = subprocess.run(["node", str(SERVER)], cwd=ROOT, input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n", text=True, capture_output=True, check=False)
        self.assertEqual(0, listed.returncode, listed.stderr)
        tools = {tool["name"]: tool for tool in json.loads(listed.stdout)["result"]["tools"]}
        expected = {
            "task_controller_issue_operation_permit": "issue-operation-permit",
            "task_controller_dispatch_operation": "dispatch-operation",
            "task_controller_reconcile_operation": "reconcile-operation",
            "task_controller_revoke_operation_permit": "revoke-operation-permit",
            "task_controller_record_verification_result": "record-verification-result",
        }
        self.assertTrue(set(expected).issubset(tools))
        permit = tools["task_controller_issue_operation_permit"]["inputSchema"]
        self.assertTrue({"permitId", "workerId", "payload", "readbackSpec", "adapterId"}.issubset(permit["required"]))
        self.assertFalse(permit.get("additionalProperties", True))
        self.assertEqual(["lark-cli", "memory-test"], permit["properties"]["adapterId"]["enum"])
        callback = tools["task_controller_record_callback"]["inputSchema"]["properties"]
        self.assertIn("operationReceiptIds", callback)
        self.assertIn("verificationResults", callback)
        self.assertFalse(tools["task_controller_dispatch_operation"]["inputSchema"].get("additionalProperties", True))
        lark_schema = permit["allOf"][0]["then"]["properties"]["payload"]
        self.assertEqual({"operation", "identity", "resource", "input"}, set(lark_schema["required"]))
        self.assertNotIn("args", lark_schema["properties"])
        cli_fields = {
            "task_controller_issue_operation_permit": {
                "permitId": "--permit-id", "workerId": "--worker-id", "capabilityId": "--capability-id",
                "operationId": "--operation-id", "targetId": "--target-id", "targetLocator": "--target-locator",
                "idempotencyKey": "--idempotency-key", "adapterId": "--adapter-id", "readbackSpec": "--readback-spec",
            },
            "task_controller_dispatch_operation": {"permitId": "--permit-id", "claimId": "--claim-id"},
            "task_controller_reconcile_operation": {"permitId": "--permit-id"},
            "task_controller_revoke_operation_permit": {"permitId": "--permit-id", "reason": "--reason"},
            "task_controller_record_verification_result": {
                "workerId": "--worker-id", "packetId": "--packet-id", "packetDigest": "--packet-digest",
                "caseId": "--case-id", "artifactManifest": "--artifact-manifest", "verificationResult": "--verification-result",
            },
        }
        for tool_name, command in expected.items():
            help_text = subprocess.run([sys.executable, str(HELPER), command, "--help"], cwd=ROOT, text=True, capture_output=True, env=self.env, check=False)
            self.assertEqual(0, help_text.returncode, help_text.stderr)
            self.assertIn("--state", help_text.stdout)
            properties = tools[tool_name]["inputSchema"]["properties"]
            self.assertIn("statePath", properties)
            for field, flag in cli_fields[tool_name].items():
                self.assertIn(field, properties)
                self.assertIn(flag, help_text.stdout)

    def test_mcp_forwards_permit_dispatch_verification_and_structured_callback(self) -> None:
        state = json.loads(self.state.read_text(encoding="utf-8"))
        packet = state["workerPackets"]["production"]
        permit = self.mcp("task_controller_issue_operation_permit", {
            "statePath": str(self.state), "permitId": "permit-mcp", "workerId": "writer", "capabilityId": "deck-script",
            "operationId": "update-deck", "targetId": "deck", "targetLocator": "/approved/deck", "action": "update",
            "payload": {"pages": 3}, "idempotencyKey": "mcp-write", "adapterId": "memory-test", "adapterOptions": {},
            "readbackSpec": {}, "expiresAt": "2030-01-01T00:00:00Z",
        })
        self.assertEqual("permit-mcp", permit["permitId"])
        receipt = self.mcp("task_controller_dispatch_operation", {"statePath": str(self.state), "permitId": "permit-mcp", "claimId": "mcp-claim"})
        self.assertEqual("consumed", receipt["status"])
        manifest = self.manifest()
        callback = self.mcp("task_controller_record_callback", {
            "statePath": str(self.state), "workerId": "writer", "fromLane": "production", "artifact": "deck.json",
            "packetId": packet["packetId"], "packetDigest": packet["packetDigest"], "contractDigest": state["contractDigest"],
            "deliverableFingerprint": state["contractSpec"]["deliverableFingerprint"], "callbackModeObserved": "managed_result_collected",
            "artifactManifest": manifest, "operationReceiptIds": [receipt["receiptId"]], "verificationResults": [],
        })
        self.assertEqual([receipt["receiptId"]], callback["operationReceiptIds"])
        self.assertTrue(callback["verificationSummary"]["allowed"])
        rejected = self.mcp("task_controller_revoke_operation_permit", {"statePath": str(self.state), "permitId": "unknown", "reason": "test forwarding"}, error=True)
        self.assertIn("not present", rejected["message"])


if __name__ == "__main__":
    unittest.main()
