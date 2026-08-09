from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from control_plane.capability_router import shadow_route  # noqa: E402
from control_plane.solution_graph import (  # noqa: E402
    build_solution_graph,
    projection_to_lane_definitions,
    validate_solution_graph,
)
from registry.loader import load_registry  # noqa: E402


def blueprint(domain: str, artifact_class: str) -> dict:
    return {
        "blueprintVersion": "1.0",
        "id": f"{domain}-blueprint",
        "taskType": "client-facing-delivery",
        "interactionMode": "execute",
        "domains": [domain],
        "artifactClass": artifact_class,
        "outcome": {"businessGoal": "Deliver a validated result", "supportedDecision": "Approve delivery"},
        "deliverable": {
            "id": "deliverable-main", "kind": "report", "target": "target-main", "format": "json",
            "audience": "client", "useMode": "direct handoff", "standalone": True, "artifactClass": artifact_class,
        },
        "sources": [{"id": "source-main", "required": True}],
        "intentAnchors": [{"id": "anchor-main", "statement": "Keep the approved scope"}],
        "decisions": [{"id": "decision-main", "statement": "Use the approved approach", "status": "binding"}],
        "changePolicy": {"preserve": [{"id": "preserve-main"}], "allowed": [{"id": "allowed-main"}], "forbidden": [{"id": "forbidden-main"}]},
        "acceptanceCases": [{"id": "acceptance-main", "description": "The delivery is complete and verifiable"}],
        "approvals": {},
        "writePolicy": {"targets": [{"id": "target-main", "locator": "/approved/target"}], "allowedActions": ["update"], "destructiveActionsRequireApproval": True},
        "standards": [], "assumptions": [], "nonGoals": [], "capacity": {}, "changeTriggers": [],
    }


def graph_for(domain: str, artifact_class: str) -> dict:
    item = blueprint(domain, artifact_class)
    routing = shadow_route(item)
    pack = load_registry().scenario_load(routing["scenarioPack"]["id"]).data
    return build_solution_graph(item, routing, pack)


class SolutionGraphTests(unittest.TestCase):
    def test_client_deck_has_required_approval_path(self) -> None:
        graph = graph_for("client-deck", "presentation")
        self.assertTrue(graph["graphExecutable"])
        self.assertEqual(["strategy", "page-map", "sample", "user-approval", "production", "review"], graph["topologicalOrder"])
        approval = next(node for node in graph["nodes"] if node["id"] == "user-approval")
        self.assertTrue(approval["userApprovalRequired"])

    def test_pricing_graph_has_fan_in_and_report_review(self) -> None:
        graph = graph_for("evidence-analysis", "workbook")
        analysis = next(node for node in graph["nodes"] if node["id"] == "analysis")
        report = next(node for node in graph["nodes"] if node["id"] == "report")
        self.assertEqual(["model", "source"], analysis["dependsOn"])
        self.assertEqual("approved-target", report["writeBoundary"])
        self.assertIn("report", next(node for node in graph["nodes"] if node["id"] == "review")["dependsOn"])

    def test_lark_graph_has_parallel_design_and_readback_review(self) -> None:
        graph = graph_for("lark-operations", "dashboard")
        approval = next(node for node in graph["nodes"] if node["id"] == "sample-approval")
        review = next(node for node in graph["nodes"] if node["id"] == "review")
        self.assertEqual(["experience", "model"], approval["dependsOn"])
        self.assertEqual(["readback"], review["dependsOn"])
        self.assertTrue(graph["graphExecutable"])

    def test_cycle_is_rejected(self) -> None:
        graph = graph_for("client-deck", "presentation")
        production = next(node for node in graph["nodes"] if node["id"] == "production")
        production["dependsOn"] = ["review"]
        graph["edges"] = [edge for edge in graph["edges"] if edge["to"] != "production"] + [{"from": "review", "to": "production"}]
        graph["graphDigest"] = ""
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_solution_graph(graph)

    def test_missing_capability_is_a_non_executable_blocker(self) -> None:
        item = blueprint("evidence-analysis", "workbook")
        routing = shadow_route(item, active_capability_ids={"evidence-workbook", "evidence-verifier"})
        pack = load_registry().scenario_load("evidence-analysis").data
        graph = build_solution_graph(item, routing, pack)
        self.assertFalse(graph["graphExecutable"])
        self.assertTrue(any(blocker["capabilityId"] == "pricing-analysis" for blocker in graph["blockers"]))

    def test_parallel_writers_to_same_target_are_rejected(self) -> None:
        graph = graph_for("evidence-analysis", "workbook")
        for node_id in ("source", "model"):
            node = next(item for item in graph["nodes"] if item["id"] == node_id)
            node["writeBoundary"] = "approved-target"
            node["writeTargets"] = [{"id": "target-main"}]
        graph["graphDigest"] = ""
        with self.assertRaisesRegex(ValueError, "unordered approved-target writers"):
            validate_solution_graph(graph)

    def test_review_must_depend_on_writer(self) -> None:
        graph = graph_for("evidence-analysis", "workbook")
        review = next(node for node in graph["nodes"] if node["id"] == "review")
        review["dependsOn"] = ["source"]
        graph["edges"] = [edge for edge in graph["edges"] if edge["to"] != "review"] + [{"from": "source", "to": "review"}]
        graph["topologicalOrder"] = ["model", "source", "analysis", "report", "review"]
        graph["graphDigest"] = ""
        with self.assertRaisesRegex(ValueError, "must depend on an approved-target writer"):
            validate_solution_graph(graph)

    def test_topology_and_digest_are_deterministic_for_unordered_inputs(self) -> None:
        item = blueprint("lark-operations", "dashboard")
        routing = shadow_route(item)
        pack = load_registry().scenario_load("lark-operations").data
        reordered_pack = deepcopy(pack)
        reordered_pack["graphTemplate"]["nodes"].reverse()
        reordered_pack["graphTemplate"]["edges"].reverse()
        reordered_routing = deepcopy(routing)
        reordered_routing["selected"].reverse()
        original = build_solution_graph(item, routing, pack)
        reordered = build_solution_graph(item, reordered_routing, reordered_pack)
        self.assertEqual(original["topologicalOrder"], reordered["topologicalOrder"])
        self.assertEqual(original["graphDigest"], reordered["graphDigest"])

    def test_semantic_blueprint_collection_order_does_not_change_digest(self) -> None:
        original_blueprint = blueprint("client-deck", "presentation")
        original_blueprint["sources"].append({"id": "source-second"})
        reordered_blueprint = deepcopy(original_blueprint)
        reordered_blueprint["sources"].reverse()
        pack = load_registry().scenario_load("client-deck").data
        original = build_solution_graph(original_blueprint, shadow_route(original_blueprint), pack)
        reordered = build_solution_graph(reordered_blueprint, shadow_route(reordered_blueprint), pack)
        self.assertEqual(original["blueprintDigest"], reordered["blueprintDigest"])
        self.assertEqual(original["graphDigest"], reordered["graphDigest"])

    def test_lane_projection_preserves_node_metadata_in_order(self) -> None:
        graph = graph_for("client-deck", "presentation")
        projection = projection_to_lane_definitions(graph)
        self.assertEqual(graph["topologicalOrder"], [lane["name"] for lane in projection["laneDefinitions"]])
        production = next(item for item in projection["mapping"] if item["nodeId"] == "production")
        self.assertEqual(["user-approval"], production["dependsOn"])
        self.assertEqual("approved-target", next(item for item in projection["laneDefinitions"] if item["name"] == "production")["writeBoundary"])


if __name__ == "__main__":
    unittest.main()
