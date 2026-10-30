"""Recorded core gaps gate completion, without pretending to judge prose quality."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

import test_inquiry as inquiry_tests
checkpoint, ROOT = inquiry_tests.checkpoint, inquiry_tests.ROOT

spec = importlib.util.spec_from_file_location("state_helper_core_test", ROOT / "scripts/task_controller_state.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class CoreCompletionTests(unittest.TestCase):
    setUp = inquiry_tests.InquiryTests.setUp
    run_cli = inquiry_tests.InquiryTests.run_cli
    ok = inquiry_tests.InquiryTests.ok
    update_args = inquiry_tests.InquiryTests.update_args
    patch_args = inquiry_tests.InquiryTests.patch_args
    def core(self):
        cp = checkpoint()
        cp["questions"][0].update(completionImpact="core", coreReason="The promised coverage cannot be established", evidenceIds=["e1"])
        return cp

    def start_core(self):
        self.ok("init", "--goal", "delivery", "--lanes", "design")
        self.ok(*self.update_args(self.core()))

    def resolve(self, seq=1, revision=1, status="answered", evidence="e2"):
        return self.patch_args({"evidence": [{"id": evidence, "source": "inspection:current-range:" + evidence, "summary": "Direct inspection establishes requested coverage"}],
            "questions": [{"id": "q1", "status": status, "waitingOn": "none", "answer": "Requested coverage established by the cited artifact", "evidenceIds": [evidence], "resolutionRevision": revision}]}, seq=seq, event="resolve-"+evidence)

    def test_open_core_blocks_completion_but_not_work(self):
        self.start_core()
        self.ok("complete-lane", "--lane", "design", "--artifact", "useful-output")
        self.assertNotEqual(0, self.run_cli("finalize").returncode)
        self.assertFalse(json.loads(self.run_cli("gate-check").stdout)["allowed"])
        self.assertIn("q1", self.ok("inquiry-status")["completionBlockers"][0])
        self.ok(*self.resolve())
        self.ok("finalize")
        self.assertEqual("core", self.ok("inquiry-status")["current"]["questions"][0]["completionImpact"])

    def test_downgrade_delete_reason_rewrite_and_empty_withdrawal_are_atomic(self):
        self.start_core()
        before = self.state.read_bytes()
        for patch in [
            {"questions": [{"id": "q1", "completionImpact": "local"}]},
            {"questions": [{"id": "q1", "coreReason": "Only a polish issue now"}]},
            {"questions": [{"id": "q1", "question": "Is it somewhat usable?"}]},
            {"questions": [{"id": "q1", "status": "withdrawn", "waitingOn": "none"}]},
            {"questions": [{"id": "q1", "status": "answered", "waitingOn": "none", "answer": "Good enough", "resolutionRevision": 1}]},
            {"evidence": [{**checkpoint()["evidence"][0], "id": "copy"}], "questions": [{"id": "q1", "status": "answered", "waitingOn": "none", "answer": "Same evidence under a new ID", "resolutionRevision": 1, "evidenceIds": ["copy"]}]},
        ]:
            self.assertNotEqual(0, self.run_cli(*self.patch_args(patch)).returncode)
            self.assertEqual(before, self.state.read_bytes())
        cp = self.core(); cp["questions"] = []
        self.assertNotEqual(0, self.run_cli(*self.update_args(cp, 1, "delete")).returncode)
        self.assertEqual(before, self.state.read_bytes())
        self.assertNotEqual(0, self.run_cli("init", "--force", "--goal", "replacement", "--lanes", "design").returncode)
        self.assertEqual(before, self.state.read_bytes())
        self.ok(*self.resolve(status="withdrawn"))
        self.assertEqual([], self.ok("inquiry-status")["completionBlockers"])

    def test_reopening_and_revision_do_not_erase_core_obligation(self):
        self.start_core()
        self.ok(*self.resolve())
        self.ok("complete-lane", "--lane", "design", "--artifact", "output")
        self.ok("finalize")
        self.ok(*self.patch_args({"questions": [{"id": "q1", "status": "open", "waitingOn": "controller"}]}, seq=2, event="reopen"))
        self.assertEqual("open", json.loads(self.state.read_text())["finalization"]["status"])
        self.assertNotEqual(0, self.run_cli("finalize").returncode)
        self.ok(*self.resolve(seq=3, evidence="e3"))
        self.ok("revise-contract", "--invalid-from-lane", "design", "--reason", "Updated implementation")
        self.ok("complete-lane", "--lane", "design", "--artifact", "new-output")
        self.assertNotEqual(0, self.run_cli("finalize").returncode)
        self.assertNotEqual(0, self.run_cli(*self.resolve(seq=4, evidence="e4")).returncode)
        self.ok(*self.resolve(seq=4, revision=2, evidence="e4"))
        self.ok("finalize")

    def test_review_completion_guard_and_review_admission_are_distinct(self):
        self.start_core()
        state = json.loads(self.state.read_text())
        lane = state["lanes"][0]
        lane.update(kind="review", verificationScope="final-artifact")
        self.state.write_text(json.dumps(state))
        self.assertNotEqual(0, self.run_cli("complete-lane", "--lane", "design", "--artifact", "review-report").returncode)
        self.assertFalse(json.loads(self.run_cli("gate-check", "--target-lane", "design").stdout)["allowed"])
        admission = helper.evaluate_gate(state, "design", require_target_worker=False)
        self.assertFalse(any("core question" in b for b in admission["blockers"]))
        lane.update(verificationScope="intermediate-artifact")
        self.state.write_text(json.dumps(state))
        self.ok("complete-lane", "--lane", "design", "--artifact", "intermediate-report")
        self.assertNotEqual(0, self.run_cli("finalize").returncode)

    def test_cannot_create_resolved_core_without_history(self):
        self.ok("init", "--goal", "delivery", "--lanes", "design")
        cp = self.core()
        cp["questions"][0].update(status="answered", waitingOn="none", answer="Already enough", resolutionRevision=1)
        self.assertNotEqual(0, self.run_cli(*self.update_args(cp)).returncode)

    def test_final_review_callback_cannot_pass_an_open_core_question(self):
        self.start_core()
        state = json.loads(self.state.read_text())
        state["lanes"][0].update(kind="review", status="running", verificationScope="final-artifact")
        state["workers"] = [{"workerId": "reviewer", "lane": "design", "contractRevision": 1,
                             "status": "running", "callbackReceived": False}]
        self.state.write_text(json.dumps(state))
        before = self.state.read_bytes()
        args = ["record-callback", "--worker-id", "reviewer", "--from-lane", "design", "--artifact", "useful-review",
                "--gate-decision", "pass", "--callback-mode-observed", "active_message"]
        result = self.run_cli(*args)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("core_completion_blocked", result.stderr)
        self.assertEqual(before, self.state.read_bytes())
        self.assertNotEqual(0, self.run_cli("update-worker", "--worker-id", "reviewer", "--status", "done", "--decision", "pass").returncode)
        args[args.index("--gate-decision") + 1] = "needs-work"
        result = self.ok(*args)
        self.assertEqual("needs-work", result["decision"])

    def test_precontract_core_survives_initialization(self):
        self.ok(*self.update_args(self.core()))
        self.ok("init", "--goal", "delivery", "--lanes", "design")
        self.ok("complete-lane", "--lane", "design", "--artifact", "useful")
        gate = helper.finalization_gate(json.loads(self.state.read_text()))
        self.assertFalse(gate["allowed"])
        self.assertEqual(1, sum("core question" in b for b in gate["blockers"]))
        self.ok(*self.resolve())
        self.ok("finalize")

    def test_precontract_resolution_does_not_require_execution_contract(self):
        self.ok(*self.update_args(self.core()))
        self.ok(*self.resolve(revision=0))
        self.assertEqual([], self.ok("inquiry-status")["completionBlockers"])
        self.ok("init", "--goal", "delivery", "--lanes", "design")
        self.assertTrue(self.ok("inquiry-status")["completionBlockers"])
        self.ok(*self.resolve(seq=2, revision=1, evidence="e3"))
        self.assertEqual([], self.ok("inquiry-status")["completionBlockers"])

    def test_evidence_can_be_collected_before_the_resolution_update(self):
        self.start_core()
        self.ok(*self.patch_args({"evidence": [{"id": "e2", "source": "artifact:new-inspection", "summary": "Coverage is established"}],
                                 "questions": [{"id": "q1", "evidenceIds": ["e1", "e2"]}]}, event="collect"))
        self.ok(*self.patch_args({"questions": [{"id": "q1", "status": "answered", "waitingOn": "none", "answer": "The inspected current artifact establishes coverage", "evidenceIds": ["e2"], "resolutionRevision": 1}]}, seq=2, event="close"))
        self.ok("complete-lane", "--lane", "design", "--artifact", "reviewed")
        self.ok("finalize")

    def test_mcp_core_fields_roundtrip_and_downgrade_rejected(self):
        import subprocess
        def call(args):
            request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "task_controller_update_inquiry", "arguments": {"statePath": str(self.state), **args}}}
            run = subprocess.run(["node", str(ROOT / "mcp/server.mjs")], input=json.dumps(request)+"\n", capture_output=True, text=True)
            return json.loads(run.stdout)
        self.ok("init", "--goal", "delivery", "--lanes", "design")
        args = {"eventId": "core", "expectedSequence": 0, "checkpoint": self.core(), "reason": "Core purpose missing", "evidenceIds": ["e1"], "impact": "none"}
        self.assertFalse(call(args)["result"].get("isError"))
        before = self.state.read_bytes()
        reply = call({"eventId": "downgrade", "expectedSequence": 1,
                      "patch": {"questions": [{"id": "q1", "completionImpact": "local"}]},
                      "reason": "The rest improved", "evidenceIds": ["e1"], "impact": "none"})
        self.assertTrue(reply.get("error") or reply.get("result", {}).get("isError"))
        self.assertEqual(before, self.state.read_bytes())


if __name__ == "__main__":
    unittest.main()
