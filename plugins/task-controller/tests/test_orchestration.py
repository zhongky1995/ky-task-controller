from __future__ import annotations

import sys
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HELPER = ROOT / "scripts" / "task_controller_state.py"
SERVER = ROOT / "mcp" / "server.mjs"

from control_plane.orchestration import compile_orchestration_plan  # noqa: E402


def lane(
    name: str,
    *,
    role: str,
    authority: str,
    depends: list[str],
    capability: str,
    purpose: str | None = None,
    owner: bool = False,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    boundary: str = "read-only",
    targets: list[str] | None = None,
    handoff_risk: str | None = None,
    handoff_mode: str | None = None,
    handoff_contract: dict | None = None,
    verification_scope: str | None = None,
) -> dict:
    result = {
        "name": name,
        "kind": name,
        "purpose": purpose or f"Complete {name}",
        "contributionRole": role,
        "semanticAuthority": authority,
        "semanticOwner": owner,
        "dependsOn": depends,
        "dependencyReasons": {dependency: "consumes upstream artifact" for dependency in depends},
        "inputContracts": inputs or [],
        "outputContracts": outputs or [],
        "writeBoundary": boundary,
        "writeTargets": targets or [],
        "workerRequired": True,
        "capabilityRequirements": [capability],
    }
    if handoff_risk:
        result["handoffRisk"] = handoff_risk
    if handoff_mode:
        result["handoffMode"] = handoff_mode
    if handoff_contract is not None:
        result["handoffContract"] = handoff_contract
    if verification_scope:
        result["verificationScope"] = verification_scope
    return result


class OrchestrationPlanTests(unittest.TestCase):
    def test_parallel_frontier_and_serial_join_are_planned_separately(self) -> None:
        lanes = [
            lane("evidence", role="prerequisite", authority="constrain", depends=[], capability="evidence-skill", outputs=["evidence-ledger"]),
            lane("audience", role="prerequisite", authority="constrain", depends=[], capability="audience-skill", outputs=["audience-contract"]),
            lane(
                "primary-delivery", role="primary", authority="define-and-implement", owner=True,
                depends=["evidence", "audience"], capability="delivery-skill",
                inputs=["evidence-ledger", "audience-contract"], outputs=["approved-artifact"],
                boundary="approved-target", targets=["delivery-target"],
            ),
            lane(
                "review", role="verification", authority="verify", depends=["primary-delivery"],
                capability="review-skill", inputs=["approved-artifact"], outputs=["review-report"],
                boundary="review-only",
            ),
        ]
        plan = compile_orchestration_plan(
            lanes,
            active_capability_ids={"evidence-skill", "audience-skill", "delivery-skill", "review-skill"},
        )
        self.assertTrue(plan["orchestrationExecutable"], plan["blockers"])
        self.assertEqual([["evidence", "audience"]], plan["parallelGroups"])
        self.assertEqual(["evidence", "audience"], plan["joinPoints"][0]["waitsFor"])
        self.assertEqual("primary-delivery", plan["semanticOwnerLane"])
        self.assertEqual("after-orchestration", plan["runtimeSelectionStage"])

    def test_qa_that_runs_before_the_artifact_is_rejected(self) -> None:
        lanes = [
            lane("source-evidence", role="prerequisite", authority="constrain", depends=[], capability="evidence-skill", outputs=["source-ledger"]),
            lane(
                "delivery-contract", role="primary", authority="define", owner=True,
                depends=["source-evidence"], capability="design-skill", inputs=["source-ledger"], outputs=["delivery-spec"],
            ),
            lane(
                "ops-qa", role="verification", authority="verify", depends=["source-evidence"],
                capability="qa-skill", inputs=["source-ledger"], outputs=["qa-rules"], boundary="review-only",
            ),
            lane(
                "implementation", role="primary", authority="implement", depends=["delivery-contract", "ops-qa"],
                capability="writer-skill", inputs=["delivery-spec", "qa-rules"], outputs=["built-artifact"],
                boundary="approved-target", targets=["delivery-target"], handoff_risk="low",
                handoff_mode="artifact-contract", handoff_contract={"artifact": "delivery-spec"},
            ),
            lane(
                "final-review", role="verification", authority="verify", depends=["implementation"],
                capability="qa-skill", inputs=["built-artifact"], boundary="review-only",
            ),
        ]
        plan = compile_orchestration_plan(
            lanes,
            active_capability_ids={"evidence-skill", "design-skill", "qa-skill", "writer-skill"},
        )
        self.assertFalse(plan["orchestrationExecutable"])
        self.assertTrue(any(item["code"] == "premature_verification" and item.get("lane") == "ops-qa" for item in plan["blockers"]))

    def test_high_loss_design_to_writer_split_requires_artifact_contract(self) -> None:
        lanes = [
            lane("design", role="primary", authority="define", owner=True, depends=[], capability="design-skill", outputs=["design"]),
            lane(
                "write", role="primary", authority="implement", depends=["design"], capability="writer-skill",
                inputs=["design"], outputs=["artifact"], boundary="approved-target", targets=["target"],
                handoff_risk="high", handoff_mode="independent",
            ),
            lane("review", role="verification", authority="verify", depends=["write"], capability="review-skill", inputs=["artifact"], boundary="review-only"),
        ]
        plan = compile_orchestration_plan(
            lanes,
            active_capability_ids={"design-skill", "writer-skill", "review-skill"},
        )
        self.assertTrue(any(item["code"] == "lossy_handoff" for item in plan["blockers"]))

    def test_capabilities_are_bound_per_lane_not_from_global_domain(self) -> None:
        lanes = [
            lane("research", role="prerequisite", authority="constrain", depends=[], capability="research-skill", outputs=["facts"]),
            lane(
                "delivery", role="primary", authority="define-and-implement", owner=True,
                depends=["research"], capability="delivery-skill", inputs=["facts"], outputs=["artifact"],
                boundary="approved-target", targets=["target"],
            ),
            lane("review", role="verification", authority="verify", depends=["delivery"], capability="review-skill", inputs=["artifact"], boundary="review-only"),
        ]
        plan = compile_orchestration_plan(
            lanes,
            active_capability_ids={"research-skill", "delivery-skill", "review-skill"},
        )
        selected = {
            route["lane"]: [item["id"] for item in route["selected"]]
            for route in plan["capabilityRoutes"]
        }
        self.assertEqual(["research-skill"], selected["research"])
        self.assertEqual(["delivery-skill"], selected["delivery"])
        self.assertEqual(["review-skill"], selected["review"])

    def test_legacy_missing_dependencies_are_visible_as_serial_inference(self) -> None:
        plan = compile_orchestration_plan(
            [{"name": "one", "kind": "research"}, {"name": "two", "kind": "support"}],
            policy="legacy",
        )
        self.assertEqual([{"wave": 1, "lanes": ["one"], "parallel": False}, {"wave": 2, "lanes": ["two"], "parallel": False}], plan["waves"])
        self.assertTrue(any(item["code"] == "legacy_order_dependency" for item in plan["warnings"]))


class OrchestrationIntegrationTests(unittest.TestCase):
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

    def strict_lanes(self) -> list[dict]:
        return [
            lane("evidence", role="prerequisite", authority="constrain", depends=[], capability="evidence-skill", outputs=["evidence"]),
            lane("audience", role="prerequisite", authority="constrain", depends=[], capability="audience-skill", outputs=["audience"]),
            lane(
                "synthesis", role="primary", authority="define", owner=True,
                depends=["evidence", "audience"], capability="synthesis-skill",
                inputs=["evidence", "audience"], outputs=["draft"], boundary="draft-file",
            ),
            lane(
                "review", role="verification", authority="verify", depends=["synthesis"],
                capability="review-skill", inputs=["draft"], boundary="review-only",
            ),
        ]

    def test_strict_init_persists_plan_and_ready_parallel_wave(self) -> None:
        lanes = self.strict_lanes()
        active = ["evidence-skill", "audience-skill", "synthesis-skill", "review-skill"]
        state = json.loads(self.command(
            "init", "--state", str(self.state), "--goal", "strict orchestration",
            "--enforcement-mode", "workflow_only",
            "--lane-definitions", json.dumps(lanes),
            "--active-capability-ids", ",".join(active),
            "--execution-policy", json.dumps({"mode": "direct", "orchestrationPolicy": "strict"}),
        ).stdout)
        self.assertTrue(state["orchestrationExecutable"])
        self.assertEqual(["evidence", "audience"], state["orchestrationPlan"]["parallelGroups"][0])
        ready = json.loads(self.command("ready-lanes", "--state", str(self.state)).stdout)
        self.assertEqual(["evidence", "audience"], [item["name"] for item in ready["readyLanes"]])
        self.assertEqual(1, ready["orchestration"]["activeWave"])

    def test_mcp_exposes_read_only_orchestration_tool(self) -> None:
        request = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {
                "name": "task_controller_plan_orchestration",
                "arguments": {
                    "laneDefinitions": self.strict_lanes(),
                    "activeCapabilityIds": ["evidence-skill", "audience-skill", "synthesis-skill", "review-skill"],
                },
            },
        }) + "\n"
        result = subprocess.run(
            ["node", str(SERVER)], cwd=self.temp.name, input=request,
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        response = json.loads(result.stdout)
        self.assertNotIn("error", response)
        plan = response["result"]["structuredContent"]["result"]
        self.assertTrue(plan["orchestrationExecutable"])
        self.assertEqual("after-orchestration", plan["runtimeSelectionStage"])
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
