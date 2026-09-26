"""Multi-turn inquiry persistence and execution integration; no live workers."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/task_controller_state.py"


def checkpoint():
    return {
        "originalIntent": "Reduce incomplete delivery", "understanding": "Cause not yet known",
        "evidence": [{"id": "e1", "source": "user:initial-request", "summary": "User reports incomplete output"}],
        "hypotheses": [{"id": "h1", "claim": "Source coverage is insufficient", "status": "untested", "evidenceIds": []}],
        "questions": [{"id": "q1", "question": "Which sources cover the requested period?", "status": "open", "waitingOn": "controller", "answer": "", "evidenceIds": []}],
        "nextAction": "Inspect source coverage without asking user to diagnose it",
    }


class InquiryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "state.json"

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(HELPER), *args, "--state", str(self.state)], capture_output=True, text=True)

    def ok(self, *args):
        result = self.run_cli(*args)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def update_args(self, cp=None, seq=0, event="turn-1", impact="none"):
        return ["update-inquiry", "--event-id", event, "--expected-sequence", str(seq),
                "--checkpoint", json.dumps(cp or checkpoint()), "--reason", "Source inspection updates our working explanation",
                "--evidence-ids", "e1", "--impact", impact]

    def test_precontract_resume_then_adopt_without_losing_history(self):
        self.ok(*self.update_args())
        cp = checkpoint()
        cp["evidence"].append({"id": "e2", "source": "inspection:source-ledger", "summary": "Requested period is fully covered"})
        cp["hypotheses"][0].update(status="refuted", evidenceIds=["e2"])
        cp["questions"][0].update(status="answered", waitingOn="none", answer="Coverage exists", evidenceIds=["e2"])
        cp.update(understanding="Coverage is not the cause; inspect transformation next", nextAction="Inspect transformation")
        args = self.update_args(cp, 1, "turn-2")
        args[args.index("--evidence-ids") + 1] = "e2"
        self.ok(*args)
        before = self.state.read_bytes()
        read = self.ok("inquiry-status", "--history")
        self.assertEqual(2, len(read["history"]))
        self.assertEqual("untested", read["history"][0]["checkpoint"]["hypotheses"][0]["status"])
        self.assertEqual(before, self.state.read_bytes())
        self.assertNotEqual(0, self.run_cli("finalize").returncode)
        initialized = self.ok("init", "--goal", "Produce complete output", "--lanes", "design")
        self.assertEqual(2, initialized["inquiry"]["sequence"])
        self.assertNotIn("stateKind", initialized)
        self.ok("complete-lane", "--lane", "design", "--artifact", "verified-output")

    def test_idempotency_and_stale_writers(self):
        args = self.update_args()
        self.ok(*args)
        before = self.state.read_bytes()
        self.assertTrue(self.ok(*args)["idempotentReplay"])
        self.assertEqual(before, self.state.read_bytes())
        self.assertNotEqual(0, self.run_cli(*self.update_args(event="other")).returncode)
        cp = checkpoint()
        cp["understanding"] = "changed"
        self.assertNotEqual(0, self.run_cli(*self.update_args(cp)).returncode)
        self.assertEqual(before, self.state.read_bytes())

    def test_concurrent_updates_only_one_wins(self):
        self.ok(*self.update_args())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda event: self.run_cli(*self.update_args(seq=1, event=event)), ["a", "b"]))
        self.assertEqual(1, sum(result.returncode == 0 for result in results))
        self.assertEqual(2, self.ok("inquiry-status")["sequence"])

    def test_invalid_updates_are_atomic(self):
        self.ok(*self.update_args())
        before = self.state.read_bytes()
        mutations = []
        cp = checkpoint(); cp["originalIntent"] = "Unrelated new goal"; mutations.append(cp)
        cp = checkpoint(); cp["hypotheses"] = []; mutations.append(cp)
        cp = checkpoint(); cp["hypotheses"][0]["status"] = "supported"; mutations.append(cp)
        cp = checkpoint(); cp["hypotheses"][0]["evidenceIds"] = ["missing"]; mutations.append(cp)
        cp = checkpoint(); cp["evidence"][0]["summary"] = "Rewritten source"; mutations.append(cp)
        cp = checkpoint(); cp["questions"][0].update(status="answered", answer="yes", evidenceIds=["e1"]); mutations.append(cp)
        for cp in mutations:
            with self.subTest(cp=cp):
                self.assertNotEqual(0, self.run_cli(*self.update_args(cp, 1, "invalid")).returncode)
                self.assertEqual(before, self.state.read_bytes())

    def test_contract_impact_opens_correction_and_revision_preserves_inquiry(self):
        self.ok("init", "--goal", "delivery", "--lanes", "design")
        self.ok("complete-lane", "--lane", "design", "--artifact", "old")
        self.ok("finalize")
        args = self.update_args(impact="contract_change") + ["--requirement-ids", "source-period", "--recommended-invalid-from-lane", "design"]
        result = self.ok(*args)
        self.assertEqual("inquiry:turn-1", result["openCorrectionEvents"][0]["id"])
        self.assertNotEqual(0, self.run_cli("finalize").returncode)
        self.ok("revise-contract", "--invalid-from-lane", "design", "--consume-correction-event-ids", "inquiry:turn-1", "--reason", "Evidence requires corrected source")
        current = self.ok("inquiry-status")
        self.assertEqual(1, current["sequence"])
        self.assertEqual([], current["openCorrectionEvents"])
        self.assertEqual(1, current["lastChange"]["contractRevision"])
        self.assertEqual(2, current["contractRevision"])

    def test_uncertain_impact_fails_closed_but_ordinary_update_does_not_clear_it(self):
        self.ok("init", "--goal", "delivery", "--lanes", "design")
        args = self.update_args(impact="uncertain")
        before = self.state.read_bytes()
        self.assertNotEqual(0, self.run_cli(*args).returncode)
        self.assertEqual(before, self.state.read_bytes())
        self.ok(*(args + ["--requirement-ids", "coverage", "--recommended-invalid-from-lane", "design"]))
        self.ok(*self.update_args(seq=1, event="supplement", impact="none"))
        self.assertEqual(1, len(self.ok("inquiry-status")["openCorrectionEvents"]))
        self.assertNotEqual(0, self.run_cli("complete-lane", "--lane", "design", "--artifact", "output").returncode)

    def test_ordinary_update_does_not_invalidate_delivery_or_request_approval(self):
        self.ok("init", "--goal", "delivery", "--lanes", "design")
        self.ok("complete-lane", "--lane", "design", "--artifact", "output")
        self.ok("finalize")
        self.ok(*self.update_args())
        state = json.loads(self.state.read_text())
        self.assertEqual("finalized", state["finalization"]["status"])
        self.assertEqual([], state["correctionEvents"])
        self.assertEqual([], state["approvalRecords"])

    def test_unresolved_precontract_impact_cannot_enter_execution(self):
        self.ok(*self.update_args(impact="uncertain"))
        self.assertNotEqual(0, self.run_cli("init", "--goal", "delivery", "--lanes", "design").returncode)

    def test_mcp_update_and_read_roundtrip(self):
        def call(name, arguments):
            request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": {"statePath": str(self.state), **arguments}}}
            result = subprocess.run(["node", str(ROOT / "mcp/server.mjs")], input=json.dumps(request) + "\n", capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            reply = json.loads(result.stdout)
            self.assertNotIn("error", reply, reply)
            self.assertFalse(reply["result"].get("isError"), reply)
            return reply["result"]
        call("task_controller_update_inquiry", {"eventId": "mcp-1", "expectedSequence": 0, "checkpoint": checkpoint(), "reason": "Capture user observation", "evidenceIds": ["e1"], "impact": "none"})
        call("task_controller_update_inquiry", {"eventId": "mcp-patch", "expectedSequence": 1, "patch": {"nextAction": "Compare explanations"}, "reason": "Reconsider alternatives", "evidenceIds": ["e1"], "impact": "none"})
        before = self.state.read_bytes()
        read = call("task_controller_inquiry_status", {"history": True})
        self.assertIn("mcp-1", json.dumps(read))
        self.assertEqual(before, self.state.read_bytes())
        self.assertEqual("Compare explanations", json.loads(before)["inquiry"]["current"]["nextAction"])

    def test_replay_cannot_change_correction_target(self):
        self.ok("init", "--goal", "delivery", "--lanes", "design")
        args = self.update_args(impact="contract_change") + ["--requirement-ids", "r1", "--recommended-invalid-from-lane", "design"]
        self.ok(*args)
        before = self.state.read_bytes()
        args[args.index("--requirement-ids") + 1] = "r2"
        self.assertNotEqual(0, self.run_cli(*args).returncode)
        self.assertEqual(before, self.state.read_bytes())

    def patch_args(self, patch, seq=1, event="patch-1", impact="none"):
        args = self.update_args(seq=seq, event=event, impact=impact)
        index = args.index("--checkpoint")
        args[index:index+2] = ["--patch", json.dumps(patch)]
        return args

    def test_patch_preserves_history_and_merges_ids(self):
        self.ok(*self.update_args())
        patch = {"evidence": [{"id": "e2", "source": "sample", "summary": "Coverage is complete"}],
                 "hypotheses": [{"id": "h1", "status": "refuted", "evidenceIds": ["e2"]}],
                 "questions": [{"id": "q1", "status": "answered", "waitingOn": "none", "answer": "Complete", "evidenceIds": ["e2"]}],
                 "understanding": "Investigate a different explanation"}
        updated = self.ok(*self.patch_args(patch))
        self.assertEqual(2, len(updated["current"]["evidence"]))
        self.assertEqual(checkpoint()["hypotheses"][0]["claim"], updated["current"]["hypotheses"][0]["claim"])
        self.assertEqual(checkpoint()["nextAction"], updated["current"]["nextAction"])
        history = self.ok("inquiry-status", "--history")["history"]
        self.assertEqual(checkpoint(), history[0]["checkpoint"])
        self.assertEqual("refuted", history[1]["checkpoint"]["hypotheses"][0]["status"])

    def test_patch_replay_after_later_update_does_not_restore_old_state(self):
        self.ok(*self.update_args())
        args = self.patch_args({"nextAction": "Compare two candidates"})
        self.ok(*args)
        self.ok(*self.patch_args({"nextAction": "Execute the selected candidate"}, seq=2, event="patch-2"))
        before = self.state.read_bytes()
        replay = self.ok(*args)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(3, replay["sequence"])
        self.assertEqual("Execute the selected candidate", replay["current"]["nextAction"])
        changed = self.run_cli(*self.patch_args({"nextAction": "different"}))
        self.assertNotEqual(0, changed.returncode)
        self.assertEqual(before, self.state.read_bytes())

    def test_invalid_patches_and_stale_writes_are_atomic(self):
        self.assertNotEqual(0, self.run_cli(*self.patch_args({"understanding": "new"}, seq=0)).returncode)
        self.assertFalse(self.state.exists())
        self.ok(*self.update_args())
        before = self.state.read_bytes()
        for patch in ({}, {"originalIntent": "replacement"}, {"delete": ["h1"]},
                      {"evidence": [{"id": "e1", "summary": "changed"}]},
                      {"hypotheses": [{"id": "h1", "status": "supported", "evidenceIds": ["absent"]}]},
                      {"hypotheses": [{"id": "h1"}, {"id": "h1"}]},
                      {"questions": [{"id": "new"}]}, {"questions": None}):
            with self.subTest(patch=patch):
                self.assertNotEqual(0, self.run_cli(*self.patch_args(patch)).returncode)
                self.assertEqual(before, self.state.read_bytes())
        self.assertNotEqual(0, self.run_cli(*self.patch_args({"nextAction": "stale"}, seq=0)).returncode)
        self.assertEqual(before, self.state.read_bytes())

    def test_patch_preserves_contract_correction_guards(self):
        self.ok("init", "--goal", "delivery", "--lanes", "design")
        self.ok(*self.update_args())
        args = self.patch_args({"understanding": "New evidence affects source scope"}, impact="contract_change")
        before = self.state.read_bytes()
        self.assertNotEqual(0, self.run_cli(*args).returncode)
        self.assertEqual(before, self.state.read_bytes())
        self.ok(*(args + ["--requirement-ids", "coverage", "--recommended-invalid-from-lane", "design"]))
        self.assertNotEqual(0, self.run_cli("complete-lane", "--lane", "design", "--artifact", "output").returncode)
        self.ok(*self.patch_args({"questions": []}, seq=2, event="supplement"))
        self.assertEqual(1, len(self.ok("inquiry-status")["openCorrectionEvents"]))
        self.assertEqual(1, len(self.ok("inquiry-status")["current"]["questions"]))

    def test_concurrent_patches_and_mixed_payload_rejection(self):
        self.ok(*self.update_args())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda event: self.run_cli(*self.patch_args({"nextAction": event}, event=event)), ["a", "b"]))
        self.assertEqual(1, sum(result.returncode == 0 for result in results))
        before = self.state.read_bytes()
        self.assertNotEqual(0, self.run_cli(*self.patch_args({"nextAction": "x"}, seq=2), "--checkpoint", json.dumps(checkpoint())).returncode)
        self.assertEqual(before, self.state.read_bytes())


if __name__ == "__main__":
    unittest.main()
