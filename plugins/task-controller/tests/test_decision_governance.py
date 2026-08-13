from __future__ import annotations

import unittest
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.blueprint import validate_blueprint
from control_plane.decision_governance import (
    classify_feedback,
    derive_decision_governance,
)


def blueprint() -> dict:
    return {
        "blueprintVersion": "1.0",
        "id": "decision-governance",
        "taskType": "client-facing-pricing",
        "interactionMode": "execute",
        "domains": ["pricing"],
        "outcome": {"businessGoal": "Approve a quote", "supportedDecision": "Approve price and scope"},
        "deliverable": {
            "id": "quote",
            "kind": "workbook",
            "target": "quote-target",
            "format": "xlsx",
            "audience": "client",
            "useMode": "commercial approval",
            "standalone": True,
            "artifactClass": "workbook",
        },
        "sources": [{"id": "source"}],
        "intentAnchors": [{"id": "anchor"}],
        "decisions": [{"id": "decision", "statement": "Use the approved source"}],
        "changePolicy": {
            "preserve": [{"id": "preserve"}],
            "allowed": [{"id": "charge-model", "statement": "May regroup billable items and unit prices"}],
            "forbidden": [{"id": "forbidden"}],
        },
        "acceptanceCases": [{"id": "acceptance", "description": "Quote is correct"}],
        "approvals": {},
        "standards": [],
        "assumptions": [],
        "nonGoals": [],
        "capacity": {},
        "changeTriggers": [],
    }


class DecisionGovernanceTests(unittest.TestCase):
    def test_high_impact_change_defaults_to_propose_then_confirm(self) -> None:
        governance = derive_decision_governance(blueprint())
        item = next(item for item in governance["items"] if item["id"] == "charge-model")
        self.assertEqual("billable_item", item["category"])
        self.assertEqual("propose_then_confirm", item["authority"])
        self.assertTrue(governance["confirmationRequired"])

    def test_explicit_user_authority_can_allow_a_commercial_decision(self) -> None:
        item = blueprint()
        item["changePolicy"]["allowed"][0]["authority"] = "agent_may_decide"
        governance = derive_decision_governance(item)
        self.assertFalse(governance["confirmationRequired"])

    def test_locked_collections_reject_non_locked_authority(self) -> None:
        item = blueprint()
        item["changePolicy"]["preserve"][0]["authority"] = "agent_may_decide"
        with self.assertRaisesRegex(ValueError, "authority=locked"):
            validate_blueprint(item)

    def test_feedback_classification_finds_contract_scope_and_lane(self) -> None:
        classification = classify_feedback(
            "UGC 和 KOC 节点费不能重复收费，其他内容不变",
            lane_names=["source-normalization", "pricing-model", "commercial-review", "implementation"],
            governance=derive_decision_governance(blueprint()),
        )
        self.assertEqual("contract_correction", classification["classification"])
        self.assertEqual("pricing-model", classification["suggestedInvalidFromLane"])
        self.assertEqual(["charge-model"], classification["impactedRequirementIds"])
        self.assertTrue(classification["preserveUnmentioned"])

    def test_approval_and_question_do_not_open_contract_revision(self) -> None:
        self.assertEqual("approval", classify_feedback("确认")["classification"])
        self.assertFalse(classify_feedback("这个数字的来源是什么？")["requiresContractRevision"])


if __name__ == "__main__":
    unittest.main()
