from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from control_plane.blueprint import compile_blueprint, validate_blueprint  # noqa: E402


LANES = [
    {"name": "research", "writeBoundary": "none"},
    {"name": "publish", "writeBoundary": "approved-target"},
]


def blueprint() -> dict:
    return {
        "blueprintVersion": "1.0",
        "id": "blueprint-1",
        "taskType": "internal-analysis",
        "interactionMode": "execute",
        "outcome": {"businessGoal": "Choose a release plan", "supportedDecision": "Approve scope"},
        "deliverable": {
            "id": "deliverable-1", "kind": "report", "target": "target-main", "format": "md",
            "audience": "operations", "useMode": "decision support", "standalone": True,
            "artifactClass": "report",
        },
        "sources": [{"id": "source-1", "required": True, "priority": 1}],
        "intentAnchors": [{"id": "anchor-1", "statement": "Preserve the requested scope"}],
        "decisions": [{"id": "decision-1", "statement": "Use the approved scope", "status": "approved"}],
        "changePolicy": {"preserve": [{"id": "preserve-1"}], "allowed": [{"id": "allowed-1"}], "forbidden": [{"id": "forbidden-1"}]},
        "acceptanceCases": [{"id": "acceptance-1", "description": "Contains a supported recommendation"}],
        "approvals": {},
        "writePolicy": {"targets": [{"id": "target-main", "locator": "/approved/target"}], "allowedActions": ["update"], "destructiveActionsRequireApproval": True},
        "standards": [], "assumptions": [], "nonGoals": [], "capacity": {}, "changeTriggers": [],
    }


class BlueprintCompilerTests(unittest.TestCase):
    def test_normal_compile(self) -> None:
        compiled = compile_blueprint(blueprint(), LANES)
        spec = compiled["contractSpec"]
        self.assertEqual("2.0", spec["specVersion"])
        self.assertEqual(["operations"], spec["deliverable"]["audience"])
        self.assertEqual("binding", spec["decisionLedger"][0]["status"])
        self.assertTrue(compiled["compiledExecutable"])
        self.assertFalse(compiled["requiredUnmapped"])

    def test_missing_required_field(self) -> None:
        item = blueprint()
        del item["outcome"]
        with self.assertRaisesRegex(ValueError, "outcome"):
            validate_blueprint(item)

    def test_per_p_units_are_preserved(self) -> None:
        item = blueprint()
        item["deliverable"]["units"] = [{"id": "page-1", "acceptanceIds": ["acceptance-1"]}, {"id": "page-2"}]
        compiled = compile_blueprint(item, LANES)
        self.assertEqual(item["deliverable"]["units"], compiled["contractSpec"]["deliverable"]["units"])

    def test_binding_decision(self) -> None:
        compiled = compile_blueprint(blueprint(), LANES)
        self.assertEqual("binding", compiled["contractSpec"]["decisionLedger"][0]["status"])

    def test_discussion_mode_does_not_require_write_policy(self) -> None:
        item = blueprint()
        item["interactionMode"] = "discuss_only"
        del item["writePolicy"]
        compiled = compile_blueprint(item, LANES)
        self.assertNotIn("writePolicy", compiled["contractSpec"])
        self.assertTrue(compiled["compiledExecutable"])

    def test_write_policy_projects_exactly(self) -> None:
        item = blueprint()
        compiled = compile_blueprint(item, LANES)
        self.assertEqual(item["writePolicy"], compiled["contractSpec"]["writePolicy"])

    def test_digest_is_deterministic(self) -> None:
        item = blueprint()
        self.assertEqual(
            compile_blueprint(item, LANES)["blueprintDigest"],
            compile_blueprint(deepcopy(item), deepcopy(LANES))["blueprintDigest"],
        )

    def test_required_unmapped_blocks_executable_output(self) -> None:
        item = blueprint()
        item["capacity"] = {"required": True, "maxWorkers": 2}
        compiled = compile_blueprint(item, LANES)
        self.assertIn("capacity", compiled["requiredUnmapped"])
        self.assertFalse(compiled["compiledExecutable"])


if __name__ == "__main__":
    unittest.main()
