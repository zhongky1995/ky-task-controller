from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from control_plane.blueprint import compile_blueprint  # noqa: E402
from control_plane.capability_router import shadow_route  # noqa: E402
from control_plane.solution_graph import build_solution_graph  # noqa: E402
from control_plane.worker_packet import compile_worker_packets, render_worker_prompt, validate_worker_packet  # noqa: E402
from registry.loader import load_registry  # noqa: E402


def blueprint(domain: str = "client-deck", artifact_class: str = "presentation") -> dict:
    return {
        "blueprintVersion": "1.0", "id": "packet-blueprint", "taskType": "client-facing-delivery", "interactionMode": "execute",
        "domains": [domain], "artifactClass": artifact_class,
        "outcome": {"businessGoal": "Approve a deck", "supportedDecision": "Approve handoff"},
        "deliverable": {"id": "deck", "kind": "presentation", "target": "deck-target", "format": "pptx", "audience": "client", "useMode": "handoff", "standalone": True, "artifactClass": artifact_class, "units": [{"id": "page-1"}, {"id": "page-2"}]},
        "sources": [{"id": "source-global", "required": True}, {"id": "source-page-1", "appliesTo": ["page-1"]}],
        "intentAnchors": [{"id": "anchor", "statement": "Stay in scope"}],
        "decisions": [{"id": "decision-global", "statement": "Use the approved narrative", "status": "binding"}, {"id": "decision-page-1", "statement": "Lead with page one", "appliesTo": ["page-1"]}],
        "changePolicy": {"preserve": [{"id": "preserve"}], "allowed": [{"id": "allowed"}], "forbidden": [{"id": "forbidden"}]},
        "acceptanceCases": [{"id": "accept-global", "description": "The business outcome is addressed"}, {"id": "accept-page-1", "description": "Page one is coherent", "appliesTo": ["page-1"]}],
        "approvals": {}, "writePolicy": {"targets": [{"id": "deck-target", "locator": "/approved/deck"}], "allowedActions": ["update"], "destructiveActionsRequireApproval": True},
        "standards": ["client-ready"], "assumptions": [], "nonGoals": [], "capacity": {}, "changeTriggers": [],
    }


def compiled_graph(item: dict) -> tuple[dict, dict, dict]:
    routing = shadow_route(item)
    pack = load_registry().scenario_load(routing["scenarioPack"]["id"]).data
    graph = build_solution_graph(item, routing, pack)
    lanes = [{"name": node["id"], "writeBoundary": node["writeBoundary"]} for node in graph["nodes"]]
    return compile_blueprint(item, lanes), graph, routing


class WorkerPacketTests(unittest.TestCase):
    def packets(self, item: dict | None = None) -> list[dict]:
        value = item or blueprint()
        compiled, graph, routing = compiled_graph(value)
        return compile_worker_packets(value, compiled, graph, routing)

    def test_custom_acceptance_defaults_to_review_not_writer_packets(self) -> None:
        packets = {packet["nodeId"]: packet for packet in self.packets()}
        strategy = packets["strategy"]
        self.assertEqual([], strategy["unitSpecs"])
        self.assertEqual(["source-global"], [item["id"] for item in strategy["sourceSpecs"]])
        self.assertEqual(["decision-global"], [item["id"] for item in strategy["decisionSpecs"]])
        self.assertEqual([], strategy["acceptanceCases"])
        self.assertEqual([], packets["production"]["acceptanceCases"])
        review = packets["review"]
        self.assertEqual(["accept-page-1", "accept-global"], [item["id"] for item in review["acceptanceCases"]])
        self.assertTrue(all(item["verification"] == "business" for item in review["acceptanceCases"]))

    def test_registered_scenarios_assign_cases_only_to_declared_lanes(self) -> None:
        cases = (
            ("client-deck", "presentation", {"review": ["page-roles-defined", "story-coherent"]}),
            ("document-revision", "document", {"verify": ["audience-fit", "preservation-map"]}),
            ("evidence-analysis", "workbook", {"review": ["calculations-reproducible", "sources-traceable"]}),
            ("lark-operations", "dashboard", {"readback": ["target-readback"], "review": ["business-path-works"]}),
        )
        for domain, artifact_class, expected in cases:
            with self.subTest(domain=domain):
                item = blueprint(domain, artifact_class)
                item["acceptanceCases"] = [
                    {"id": case_id, "description": case_id.replace("-", " ")}
                    for case_ids in expected.values() for case_id in case_ids
                ]
                packets = {packet["nodeId"]: packet for packet in self.packets(item)}
                actual = {
                    node_id: [item["id"] for item in packet["acceptanceCases"]]
                    for node_id, packet in packets.items() if packet["acceptanceCases"]
                }
                self.assertEqual(expected, actual)
                for packet in packets.values():
                    if packet["nodeId"] in {"production", "report", "implementation"}:
                        self.assertEqual([], packet["acceptanceCases"])

    def test_global_binding_and_required_source_are_retained_when_graph_selection_omits_them(self) -> None:
        item = blueprint()
        compiled, graph, routing = compiled_graph(item)
        node = next(node for node in graph["nodes"] if node["id"] == "strategy")
        node["sourceIds"] = ["source-page-1"]
        node["decisionIds"] = ["decision-page-1"]
        node["acceptanceIds"] = ["accept-page-1"]
        graph["graphDigest"] = ""
        # Revalidate/re-digest by rebuilding from the real graph content is intentionally not needed here: compile rejects stale graphs.
        from control_plane.solution_graph import validate_solution_graph
        normalized = validate_solution_graph(graph, routing)
        from hashlib import sha256
        import json
        normalized["graphDigest"] = sha256(json.dumps({key: value for key, value in normalized.items() if key != "graphDigest"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        packet = compile_worker_packets(item, compiled, normalized, routing)[0]
        self.assertEqual(["source-global"], [entry["id"] for entry in packet["sourceSpecs"]])
        self.assertEqual(["decision-global"], [entry["id"] for entry in packet["decisionSpecs"]])
        self.assertEqual([], packet["acceptanceCases"])

    def test_source_applies_to_unit_and_write_boundaries_are_enforced(self) -> None:
        item = blueprint()
        compiled, graph, routing = compiled_graph(item)
        production = next(node for node in graph["nodes"] if node["id"] == "production")
        production["unitIds"] = ["page-1"]
        graph["graphDigest"] = ""
        from control_plane.solution_graph import validate_solution_graph
        from hashlib import sha256
        import json
        graph = validate_solution_graph(graph, routing)
        graph["graphDigest"] = sha256(json.dumps({key: value for key, value in graph.items() if key != "graphDigest"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        packets = {packet["nodeId"]: packet for packet in compile_worker_packets(item, compiled, graph, routing)}
        self.assertEqual(["source-page-1", "source-global"], [entry["id"] for entry in packets["production"]["sourceSpecs"]])
        self.assertEqual(["deck-target"], [entry["id"] for entry in packets["production"]["writePolicySlice"]["targets"]])
        self.assertEqual(["update"], packets["production"]["writePolicySlice"]["allowedActions"])
        self.assertEqual([], packets["review"]["writePolicySlice"]["targets"])
        self.assertEqual([], packets["review"]["writePolicySlice"]["allowedActions"])

    def test_digest_is_deterministic_and_changes_with_constraint_or_blueprint_decision(self) -> None:
        first = self.packets()
        self.assertEqual(first, self.packets(deepcopy(blueprint())))
        changed_constraint = blueprint()
        changed_constraint["changePolicy"]["forbidden"][0]["note"] = "No unapproved rewrite"
        self.assertNotEqual(first[0]["packetDigest"], self.packets(changed_constraint)[0]["packetDigest"])
        changed_decision = blueprint()
        changed_decision["decisions"][0]["statement"] = "Use the revised narrative"
        self.assertNotEqual(first[0]["packetDigest"], self.packets(changed_decision)[0]["packetDigest"])
        item = blueprint()
        compiled, graph, routing = compiled_graph(item)
        next(node for node in graph["nodes"] if node["id"] == "strategy")["purpose"] = "Define a revised narrative"
        graph["graphDigest"] = ""
        from control_plane.solution_graph import validate_solution_graph
        from hashlib import sha256
        import json
        graph = validate_solution_graph(graph, routing)
        graph["graphDigest"] = sha256(json.dumps({key: value for key, value in graph.items() if key != "graphDigest"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        changed_node = compile_worker_packets(item, compiled, graph, routing)
        self.assertNotEqual(first[0]["packetDigest"], changed_node[0]["packetDigest"])

    def test_prompt_is_a_rendered_view_not_source_of_truth(self) -> None:
        packet = self.packets()[0]
        prompt = render_worker_prompt(packet)
        self.assertIn(packet["packetId"], prompt)
        self.assertIn(packet["packetDigest"], prompt)
        self.assertEqual(packet, validate_worker_packet(packet))
        modified_prompt = prompt.replace(packet["purpose"], "different text")
        self.assertNotEqual(modified_prompt, prompt)
        self.assertEqual(packet, validate_worker_packet(packet))

    def test_missing_graph_binding_cannot_generate_a_packet(self) -> None:
        item = blueprint()
        compiled, graph, routing = compiled_graph(item)
        strategy = next(node for node in graph["nodes"] if node["id"] == "strategy")
        strategy["capabilityBindings"] = []
        graph["graphDigest"] = ""
        with self.assertRaisesRegex(ValueError, "capability"):
            compile_worker_packets(item, compiled, graph, routing)


if __name__ == "__main__":
    unittest.main()
