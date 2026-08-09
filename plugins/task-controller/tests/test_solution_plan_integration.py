from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "task_controller_state.py"
SERVER = ROOT / "mcp" / "server.mjs"


def blueprint(domain: str = "client-deck", artifact_class: str = "presentation") -> dict:
    return {
        "blueprintVersion": "1.0", "id": f"plan-{domain}", "taskType": "client-facing-delivery", "interactionMode": "execute",
        "domains": [domain], "artifactClass": artifact_class,
        "outcome": {"businessGoal": "Approve the delivery", "supportedDecision": "Approve handoff"},
        "deliverable": {"id": "delivery", "kind": artifact_class, "target": "delivery-target", "format": "json", "audience": "client", "useMode": "handoff", "standalone": True, "artifactClass": artifact_class},
        "sources": [{"id": "source", "required": True}],
        "intentAnchors": [{"id": "anchor", "statement": "Stay in scope"}],
        "decisions": [{"id": "decision", "statement": "Use the approved narrative", "status": "binding"}],
        "changePolicy": {"preserve": [{"id": "preserve"}], "allowed": [{"id": "allowed"}], "forbidden": [{"id": "forbidden"}]},
        "acceptanceCases": [{"id": "acceptance", "description": "Delivery is verifiable"}],
        "approvals": {},
        "writePolicy": {"targets": [{"id": "delivery-target", "locator": "/approved/delivery"}], "allowedActions": ["update"], "destructiveActionsRequireApproval": True},
        "standards": [], "assumptions": [], "nonGoals": [], "capacity": {}, "changeTriggers": [],
    }


class SolutionPlanIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "state.json"

    def command(self, command: str, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(HELPER), command, *args], cwd=self.temp.name,
            text=True, capture_output=True, check=False,
        )
        if ok and result.returncode:
            self.fail(result.stderr or result.stdout)
        if not ok and not result.returncode:
            self.fail(f"command unexpectedly passed: {result.stdout}")
        return result

    def output(self, result: subprocess.CompletedProcess[str]) -> dict:
        return json.loads(result.stdout)

    def plan(self, item: dict, *args: str) -> dict:
        return self.output(self.command("plan-blueprint", "--task-blueprint", json.dumps(item), *args))

    def init_auto(self, item: dict | None = None, *args: str) -> dict:
        return self.output(self.command(
            "init", "--state", str(self.state), "--goal", "formal plan", "--task-blueprint",
            json.dumps(item or blueprint()), "--auto-plan", *args,
        ))

    def mcp_call(self, name: str, arguments: dict) -> dict:
        request = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments},
        }) + "\n"
        result = subprocess.run(["node", str(SERVER)], cwd=self.temp.name, input=request, text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        response = json.loads(result.stdout)
        self.assertNotIn("error", response)
        return response["result"]["structuredContent"]["result"]

    def test_plans_three_scenario_dags_and_packets_without_writing_state(self) -> None:
        expected = {
            ("client-deck", "presentation"): ["strategy", "page-map", "sample", "user-approval", "production", "review"],
            ("evidence-analysis", "workbook"): ["model", "source", "analysis", "report", "review"],
            ("lark-operations", "dashboard"): ["audit", "experience", "model", "sample-approval", "implementation", "readback", "review"],
        }
        for (domain, artifact_class), order in expected.items():
            with self.subTest(domain=domain):
                result = self.plan(blueprint(domain, artifact_class))
                self.assertTrue(result["planExecutable"])
                self.assertEqual(order, result["solutionGraph"]["topologicalOrder"])
                self.assertEqual(order, [packet["nodeId"] for packet in result["workerPackets"]])
                self.assertEqual(order, [lane["name"] for lane in result["laneProjection"]["laneDefinitions"]])
        self.assertFalse(self.state.exists())

    def test_auto_init_persists_projection_and_rejects_mismatched_explicit_lanes(self) -> None:
        state = self.init_auto()
        self.assertTrue(state["planExecutable"])
        self.assertEqual(state["solutionGraph"]["graphDigest"], state["solutionGraphDigest"])
        self.assertEqual([lane["name"] for lane in state["lanes"]], state["solutionGraph"]["topologicalOrder"])
        self.assertEqual(set(state["solutionGraph"]["topologicalOrder"]), set(state["workerPackets"]))
        graph_nodes = {node["id"]: node for node in state["solutionGraph"]["nodes"]}
        self.assertEqual(
            {name: graph_nodes[name]["dependsOn"] for name in state["solutionGraph"]["topologicalOrder"]},
            {lane["name"]: lane["dependsOn"] for lane in state["lanes"]},
        )
        other_state = Path(self.temp.name) / "mismatch.json"
        result = self.command(
            "init", "--state", str(other_state), "--goal", "mismatch", "--task-blueprint", json.dumps(blueprint()),
            "--auto-plan", "--lane-definitions", json.dumps([{"name": "wrong", "writeBoundary": "read-only"}]), ok=False,
        )
        self.assertIn("laneProjection", result.stderr)

    def test_missing_capability_blocks_plan_and_strict_risk_init(self) -> None:
        unavailable = self.plan(blueprint(), "--active-capability-ids", "deck-strategy")
        self.assertFalse(unavailable["planExecutable"])
        self.assertTrue(unavailable["blockers"])
        result = self.command(
            "init", "--state", str(self.state), "--goal", "blocked", "--task-blueprint", json.dumps(blueprint()),
            "--auto-plan", "--active-capability-ids", "deck-strategy", ok=False,
        )
        self.assertIn("executable SolutionGraph plan", result.stderr)

    def test_packet_registration_callback_revision_and_topology_guard(self) -> None:
        state = self.init_auto(
            None,
            "--execution-policy", json.dumps({"splitRequirement": "recommended", "mode": "multi_session", "eligibleRuntimes": ["managed_agent_worker"], "runtimeSelectionPolicy": "lane_lifecycle"}),
        )
        packet = state["workerPackets"]["strategy"]
        worker = self.output(self.command(
            "register-worker", "--state", str(self.state), "--worker-id", "strategy-worker", "--lane", "strategy",
            "--lane-runtime", "managed_agent_worker", "--request-id", "request-1", "--runtime-handle", "agent-1",
            "--thread-tool-check", "checked", "--packet-id", packet["packetId"], "--packet-digest", packet["packetDigest"],
            "--contract-digest", state["contractDigest"], "--deliverable-fingerprint", state["contractSpec"]["deliverableFingerprint"],
        ))
        self.assertEqual(packet["packetId"], worker["packetId"])
        self.assertTrue(worker["prompt"])
        self.command(
            "record-callback", "--state", str(self.state), "--worker-id", "strategy-worker", "--from-lane", "strategy",
            "--packet-id", packet["packetId"], "--packet-digest", packet["packetDigest"],
            "--contract-digest", state["contractDigest"], "--deliverable-fingerprint", state["contractSpec"]["deliverableFingerprint"],
            "--message-type", "blocker", "--gate-decision", "blocked", "--callback-mode-observed", "managed_result_collected",
        )
        revised_blueprint = deepcopy(blueprint())
        revised_blueprint["outcome"]["businessGoal"] = "Approve the revised delivery"
        revised = self.output(self.command(
            "revise-contract", "--state", str(self.state), "--invalid-from-lane", "strategy",
            "--task-blueprint", json.dumps(revised_blueprint),
        ))["state"]
        self.assertNotEqual(packet["packetDigest"], revised["workerPackets"]["strategy"]["packetDigest"])
        self.assertEqual("superseded", revised["workers"][0]["status"])
        changed = blueprint("evidence-analysis", "workbook")
        result = self.command(
            "revise-contract", "--state", str(self.state), "--invalid-from-lane", "strategy",
            "--task-blueprint", json.dumps(changed), ok=False,
        )
        self.assertIn("replan_requires_new_state", result.stderr)

    def test_graph_packet_registration_rejects_task_prompt_overrides_and_tampering(self) -> None:
        state = self.init_auto(
            None,
            "--execution-policy", json.dumps({"splitRequirement": "recommended", "mode": "multi_session", "eligibleRuntimes": ["managed_agent_worker"], "runtimeSelectionPolicy": "lane_lifecycle"}),
        )
        packet = state["workerPackets"]["strategy"]
        base = (
            "register-worker", "--state", str(self.state), "--lane", "strategy",
            "--lane-runtime", "managed_agent_worker", "--request-id", "request", "--runtime-handle", "agent",
            "--thread-tool-check", "checked", "--packet-id", packet["packetId"], "--packet-digest", packet["packetDigest"],
            "--contract-digest", state["contractDigest"], "--deliverable-fingerprint", state["contractSpec"]["deliverableFingerprint"],
        )
        for suffix in (("--task", "custom task"), ("--prompt", "custom prompt"), ("--task", "custom task", "--prompt", "custom prompt")):
            with self.subTest(override=suffix):
                result = self.command(*base, "--worker-id", "override-" + str(len(suffix)), *suffix, ok=False)
                self.assertIn("packet_task_override_forbidden", result.stderr)

        original_state = self.state.read_text(encoding="utf-8")
        for field, value in (("purpose", "tampered"), ("constraints", {}), ("packetDigest", "0" * 64)):
            with self.subTest(field=field):
                data = json.loads(self.state.read_text(encoding="utf-8"))
                data["workerPackets"]["strategy"][field] = value
                self.state.write_text(json.dumps(data), encoding="utf-8")
                result = self.command(*base, "--worker-id", "tampered-" + field, ok=False)
                self.assertIn("packet_integrity_error", result.stderr)
                persisted = json.loads(self.state.read_text(encoding="utf-8"))
                self.assertEqual([], persisted["workers"])
                self.state.write_text(original_state, encoding="utf-8")

        worker = self.output(self.command(*base, "--worker-id", "valid-worker"))
        self.assertEqual(packet, json.loads(worker["task"]))
        self.assertTrue(worker["prompt"])

    def test_legacy_state_and_mcp_forwarding_remain_compatible(self) -> None:
        legacy = self.output(self.command(
            "init", "--state", str(self.state), "--goal", "legacy", "--enforcement-mode", "workflow_only",
            "--lane-definitions", json.dumps([{"name": "research", "kind": "research"}]),
        ))
        worker = self.output(self.command(
            "register-worker", "--state", str(self.state), "--worker-id", "legacy-worker", "--lane", "research", "--task", "research",
        ))
        self.assertEqual("", worker["packetId"])
        self.assertEqual("research", worker["task"])
        payload = self.mcp_call("task_controller_plan_blueprint", {"taskBlueprint": blueprint()})
        self.assertTrue(payload["planExecutable"])
        mcp_state_path = str(Path(self.temp.name) / "mcp-state.json")
        mcp_state = self.mcp_call("task_controller_init", {
            "statePath": mcp_state_path, "goal": "MCP graph plan", "taskBlueprint": blueprint(), "autoPlan": True,
            "executionPolicy": {"splitRequirement": "recommended", "mode": "multi_session", "eligibleRuntimes": ["managed_agent_worker"], "runtimeSelectionPolicy": "lane_lifecycle"},
        })
        mcp_packet = mcp_state["workerPackets"]["strategy"]
        mcp_worker = self.mcp_call("task_controller_register_worker", {
            "statePath": mcp_state_path, "workerId": "mcp-worker", "lane": "strategy",
            "laneRuntime": "managed_agent_worker", "requestId": "mcp-request", "runtimeHandle": "mcp-agent", "threadToolCheck": "checked",
            "packetId": mcp_packet["packetId"], "packetDigest": mcp_packet["packetDigest"],
            "contractDigest": mcp_state["contractDigest"], "deliverableFingerprint": mcp_state["contractSpec"]["deliverableFingerprint"],
        })
        self.assertEqual(mcp_packet["packetDigest"], mcp_worker["packetDigest"])
        callback = self.mcp_call("task_controller_record_callback", {
            "statePath": mcp_state_path, "workerId": "mcp-worker", "fromLane": "strategy",
            "packetId": mcp_packet["packetId"], "packetDigest": mcp_packet["packetDigest"],
            "contractDigest": mcp_state["contractDigest"], "deliverableFingerprint": mcp_state["contractSpec"]["deliverableFingerprint"],
            "messageType": "blocker", "gateDecision": "blocked", "callbackModeObserved": "managed_result_collected",
        })
        self.assertTrue(callback["callbackReceived"])


if __name__ == "__main__":
    unittest.main()
