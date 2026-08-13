from __future__ import annotations

import json
from hashlib import sha256
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "task_controller_state.py"
SERVER = ROOT / "mcp" / "server.mjs"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.task_controller_state import plan_blueprint_data
from verification.acceptance import validate_acceptance_case


def digest(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def pricing_blueprint(*, task_type: str = "client-facing-pricing", approvals: dict | None = None) -> dict:
    return {
        "blueprintVersion": "1.0",
        "id": "client-pricing-plan",
        "taskType": task_type,
        "interactionMode": "execute",
        "domains": ["pricing"],
        "artifactClass": "workbook",
        "outcome": {"businessGoal": "Approve a client quote", "supportedDecision": "Approve price and scope"},
        "deliverable": {
            "id": "quote",
            "kind": "workbook",
            "target": "quote-target",
            "format": "xlsx",
            "audience": "client" if "client" in task_type else "finance",
            "useMode": "commercial approval",
            "standalone": True,
            "artifactClass": "workbook",
        },
        "sources": [{"id": "source", "required": True}],
        "intentAnchors": [{"id": "anchor", "statement": "Do not duplicate charges"}],
        "decisions": [{"id": "decision", "statement": "Use source-backed rates", "status": "binding"}],
        "changePolicy": {
            "preserve": [{"id": "preserve"}],
            "allowed": [{"id": "charge-model", "statement": "May regroup billable items and unit prices"}],
            "forbidden": [{"id": "forbidden"}],
        },
        "acceptanceCases": [],
        "approvals": approvals or {},
        "writePolicy": {
            "targets": [{"id": "quote-target", "locator": "/approved/quote.xlsx"}],
            "allowedActions": ["update"],
            "destructiveActionsRequireApproval": True,
        },
        "standards": [],
        "assumptions": [],
        "nonGoals": [],
        "capacity": {},
        "changeTriggers": [],
    }


class ClientPricingPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "state.json"

    def command(self, command: str, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(HELPER), command, *args],
            cwd=self.temp.name,
            text=True,
            capture_output=True,
            check=False,
        )
        if ok and result.returncode:
            self.fail(result.stderr or result.stdout)
        if not ok and not result.returncode:
            self.fail(f"command unexpectedly passed: {result.stdout}")
        return result

    def output(self, result: subprocess.CompletedProcess[str]) -> dict:
        return json.loads(result.stdout)

    def mcp(self, name: str, arguments: dict) -> dict:
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }) + "\n"
        result = subprocess.run(
            ["node", str(SERVER)],
            cwd=self.temp.name,
            input=request,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        response = json.loads(result.stdout)
        self.assertNotIn("error", response)
        return response["result"]["structuredContent"]["result"]

    def register_worker(self, state: dict, lane: str, worker_id: str, runtime_handle: str, *extra: str) -> dict:
        packet = state["workerPackets"][lane]
        return self.output(self.command(
            "register-worker", "--state", str(self.state), "--worker-id", worker_id,
            "--lane", lane, "--lane-runtime", "managed_agent_worker",
            "--request-id", "request-" + worker_id, "--runtime-handle", runtime_handle,
            "--thread-tool-check", "checked", "--callback-mode-expected", "managed_result_collected",
            "--packet-id", packet["packetId"], "--packet-digest", packet["packetDigest"],
            "--contract-digest", state["contractDigest"],
            "--deliverable-fingerprint", state["contractSpec"]["deliverableFingerprint"],
            *extra,
        ))

    def pass_read_only_worker(
        self, state: dict, lane: str, worker_id: str, runtime_handle: str,
        manifest: list[dict], *, verification_results: list[dict] | None = None,
        reviews_worker_ids: list[str] | None = None,
    ) -> None:
        extra: tuple[str, ...] = ()
        if reviews_worker_ids:
            extra = ("--reviews-worker-ids", ",".join(reviews_worker_ids))
        self.register_worker(state, lane, worker_id, runtime_handle, *extra)
        packet = state["workerPackets"][lane]
        callback_args = [
            "record-callback", "--state", str(self.state), "--worker-id", worker_id,
            "--from-lane", lane, "--artifact", lane + ".json",
            "--packet-id", packet["packetId"], "--packet-digest", packet["packetDigest"],
            "--contract-digest", state["contractDigest"],
            "--deliverable-fingerprint", state["contractSpec"]["deliverableFingerprint"],
            "--callback-mode-observed", "managed_result_collected",
            "--artifact-manifest", json.dumps(manifest),
        ]
        if verification_results is not None:
            callback_args.extend(("--verification-results", json.dumps(verification_results)))
        self.command(*callback_args)
        self.command(
            "complete-lane", "--state", str(self.state), "--lane", lane,
            "--artifact", lane + ".json",
        )

    def review_results(self, packet: dict, manifest: list[dict]) -> list[dict]:
        manifest_fingerprint = digest(manifest)
        results = []
        for raw_case in packet["acceptanceCases"]:
            case = {
                key: value for key, value in raw_case.items()
                if key not in {"description", "statement", "verification", "fingerprint"}
            }
            normalized = validate_acceptance_case(case)
            required_keys = normalized["evidenceSchema"].get("requiredKeys", [])
            evidence = [{key: f"evidence-{key}" for key in required_keys}] or [{"proof": normalized["id"]}]
            result = {
                "resultVersion": "1.0",
                "resultId": "result-" + normalized["id"],
                "caseId": normalized["id"],
                "caseVersion": normalized["version"],
                "caseFingerprint": normalized["fingerprint"],
                "artifactFingerprint": manifest_fingerprint,
                "evaluator": {
                    "capabilityId": "pricing-commercial-verifier",
                    "version": "1.0",
                    "runtimeHandle": "commercial-review-runtime",
                },
                "procedureFingerprint": digest(normalized["procedure"]),
                "method": normalized["method"],
                "normalizedInputDigest": digest({}),
                "expected": normalized["expected"],
                "actual": normalized["expected"],
                "status": "pass",
                "evidenceRefs": evidence,
                "evidenceDigest": digest(evidence),
                "confidence": 1,
                "executedAt": "2026-08-14T00:00:00Z",
                "attestationType": "independent_reviewed" if normalized["method"] == "business" else "tool_verified",
                "workerId": "commercial-review-worker",
            }
            if normalized["method"] == "business":
                result["reviewedWorkerIds"] = ["pricing-model-worker"]
            results.append(result)
        return results

    def test_client_pricing_uses_governed_dependency_graph(self) -> None:
        plan, effective, compiled = plan_blueprint_data(pricing_blueprint())
        self.assertEqual("client-pricing", plan["routingDecision"]["scenarioPack"]["id"])
        self.assertEqual(
            [
                "source-normalization",
                "pricing-model",
                "commercial-review",
                "user-approval",
                "workbook-architecture",
                "implementation",
                "final-review",
            ],
            plan["solutionGraph"]["topologicalOrder"],
        )
        self.assertTrue(plan["planExecutable"])
        self.assertEqual(
            "commercial-pricing-model",
            compiled["contractSpec"]["userApprovalGate"]["artifactId"],
        )
        self.assertEqual(
            ["workbook-architecture", "implementation", "final-review"],
            compiled["contractSpec"]["userApprovalGate"]["blocks"],
        )
        self.assertEqual(6, len(effective["acceptanceCases"]))
        packets = {packet["nodeId"]: packet for packet in plan["workerPackets"]}
        self.assertEqual(6, len(packets["commercial-review"]["acceptanceCases"]))
        self.assertEqual("decision-review", next(
            node["kind"] for node in plan["solutionGraph"]["nodes"] if node["id"] == "commercial-review"
        ))

    def test_internal_pricing_analysis_keeps_generic_scenario(self) -> None:
        plan, _, _ = plan_blueprint_data(pricing_blueprint(task_type="internal-analysis"))
        self.assertEqual("evidence-analysis", plan["routingDecision"]["scenarioPack"]["id"])

    def test_explicit_client_pricing_domain_is_sufficient(self) -> None:
        item = pricing_blueprint(task_type="internal-analysis")
        item["domains"] = ["client-pricing"]
        plan, _, _ = plan_blueprint_data(item)
        self.assertEqual("client-pricing", plan["routingDecision"]["scenarioPack"]["id"])

    def test_manual_high_impact_blueprint_requires_an_approval_gate(self) -> None:
        result = self.output(self.command(
            "compile-blueprint",
            "--task-blueprint", json.dumps(pricing_blueprint()),
            "--lane-definitions", json.dumps([
                {"name": "pricing-model", "kind": "modeling"},
                {"name": "implementation", "kind": "implementation", "writeBoundary": "approved-target"},
            ]),
        ))
        self.assertFalse(result["compiledExecutable"])
        self.assertIn("approvals.userApprovalGate", result["requiredUnmapped"])

    def test_hand_authored_high_impact_contract_also_fails_closed(self) -> None:
        contract = {
            "specVersion": "2.0",
            "interactionMode": "execute",
            "deliverable": {
                "id": "quote", "kind": "workbook", "target": "quote-target", "format": "xlsx",
                "audience": ["client"], "useMode": "commercial approval", "standalone": True,
                "artifactClass": "workbook", "units": [],
            },
            "canonicalSources": [{"id": "source"}],
            "preserve": [],
            "allowedChanges": [{"id": "charge-model", "statement": "May regroup billable items and calibrate unit prices"}],
            "forbidden": [],
            "acceptance": [{"id": "acceptance"}],
            "intentAnchors": [],
            "decisionLedger": [],
            "sampleGate": {"required": False},
            "userApprovalGate": {"required": False},
            "writePolicy": {
                "targets": [{"id": "quote-target", "locator": "/approved/quote.xlsx"}],
                "allowedActions": ["update"], "destructiveActionsRequireApproval": True,
            },
        }
        result = self.command(
            "init", "--state", str(self.state), "--goal", "manual quote",
            "--lane-definitions", json.dumps([
                {"name": "pricing-model", "kind": "modeling"},
                {"name": "implementation", "kind": "implementation", "writeBoundary": "approved-target"},
            ]),
            "--contract-spec", json.dumps(contract),
            ok=False,
        )
        self.assertIn("decision_confirmation_gate_required", result.stderr)

    def test_auto_plan_preserves_human_approval_lane_and_ingests_feedback(self) -> None:
        state = self.output(self.command(
            "init", "--state", str(self.state), "--goal", "client pricing",
            "--task-blueprint", json.dumps(pricing_blueprint()), "--auto-plan",
        ))
        lanes = {lane["name"]: lane for lane in state["lanes"]}
        self.assertFalse(lanes["user-approval"]["workerRequired"])
        self.assertTrue(lanes["commercial-review"]["workerRequired"])
        first = self.output(self.command(
            "ingest-feedback", "--state", str(self.state),
            "--feedback", "UGC 和 KOC 节点费不能重复收费，其他内容不变",
        ))
        event = first["correctionEvent"]
        self.assertEqual("pricing-model", event["recommendedInvalidFromLane"])
        self.assertEqual("open", event["status"])
        self.assertTrue(event["preserveUnmentioned"])
        replay = self.output(self.command(
            "ingest-feedback", "--state", str(self.state),
            "--feedback", "UGC 和 KOC 节点费不能重复收费，其他内容不变",
        ))
        self.assertTrue(replay["idempotentReplay"])
        persisted = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(1, len(persisted["correctionEvents"]))
        self.assertEqual("open", persisted["finalization"]["status"])
        classified = self.mcp("task_controller_classify_feedback", {
            "statePath": str(self.state),
            "feedback": "KPI 扣款逻辑不对，其他不变",
        })
        self.assertEqual("pricing-model", classified["suggestedInvalidFromLane"])
        mcp_replay = self.mcp("task_controller_ingest_feedback", {
            "statePath": str(self.state),
            "feedback": "UGC 和 KOC 节点费不能重复收费，其他内容不变",
        })
        self.assertTrue(mcp_replay["idempotentReplay"])

    def test_reviewed_model_must_be_fingerprint_approved_before_architecture(self) -> None:
        state = self.output(self.command(
            "init", "--state", str(self.state), "--goal", "commercial approval chain",
            "--task-blueprint", json.dumps(pricing_blueprint()), "--auto-plan",
            "--execution-policy", json.dumps({
                "splitRequirement": "recommended",
                "mode": "distributed",
                "eligibleRuntimes": ["managed_agent_worker"],
                "runtimeSelectionPolicy": "lane_lifecycle",
            }),
        ))
        source_manifest = [{
            "id": "normalized-commercial-sources", "deliverableId": "quote",
            "path": "/tmp/sources.json", "artifactFingerprint": "a" * 64,
        }]
        self.pass_read_only_worker(
            state, "source-normalization", "source-worker", "source-runtime", source_manifest,
        )
        model_manifest = [{
            "id": "commercial-pricing-model", "deliverableId": "quote",
            "path": "/tmp/pricing-model.json", "artifactFingerprint": "b" * 64,
        }]
        self.pass_read_only_worker(
            state, "pricing-model", "pricing-model-worker", "pricing-model-runtime", model_manifest,
        )
        review_packet = state["workerPackets"]["commercial-review"]
        self.pass_read_only_worker(
            state,
            "commercial-review",
            "commercial-review-worker",
            "commercial-review-runtime",
            model_manifest,
            verification_results=self.review_results(review_packet, model_manifest),
            reviews_worker_ids=["pricing-model-worker"],
        )
        blocked = self.command(
            "complete-lane", "--state", str(self.state), "--lane", "user-approval",
            "--artifact", "approval.json", ok=False,
        )
        self.assertIn("User approval is required", blocked.stderr)
        self.command(
            "record-approval", "--state", str(self.state),
            "--artifact-id", "commercial-pricing-model",
            "--artifact-fingerprint", "b" * 64,
            "--approver", "user",
        )
        self.command(
            "complete-lane", "--state", str(self.state), "--lane", "user-approval",
            "--artifact", "approval.json",
        )
        frontier = self.output(self.command("ready-lanes", "--state", str(self.state)))
        self.assertEqual(["workbook-architecture"], [lane["name"] for lane in frontier["readyLanes"]])


if __name__ == "__main__":
    unittest.main()
