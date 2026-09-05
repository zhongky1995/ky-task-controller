"""Generic workflow regressions. Host identities are synthetic; no tasks are created."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_orchestration import lane

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "task_controller_state.py"
SERVER = ROOT / "mcp" / "server.mjs"


class DispatchRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "state.json"

    def run_command(self, command: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(HELPER), command, "--state", str(self.state), *args], text=True, capture_output=True, cwd=self.temp.name)

    def command(self, command: str, *args: str) -> dict:
        result = self.run_command(command, *args)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def reject(self, code: str, command: str, *args: str) -> None:
        before = self.state.read_bytes()
        result = self.run_command(command, *args)
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn(code, result.stderr)
        self.assertEqual(before, self.state.read_bytes())

    def init_native(self, *, maximum: int = 1, confirmed: bool = True, definitions: list[dict] | None = None, review: bool = False) -> dict:
        definitions = definitions or [
            lane("design", role="primary", authority="define", owner=True, depends=[], capability="synthetic-skill"),
            lane("research", role="prerequisite", authority="constrain", depends=[], capability="synthetic-skill"),
        ]
        capabilities = {item for definition in definitions for item in definition["capabilityRequirements"]}
        return self.command("init", "--goal", "generic synthetic workflow", "--enforcement-mode", "workflow_only", "--semantic-downgrade-reason", "isolated test fixture; no real artifact writes", "--lane-definitions", json.dumps(definitions), "--active-capability-ids", ",".join(sorted(capabilities)), "--runtime-availability", json.dumps({item: True for item in capabilities} if confirmed else {}), "--execution-policy", json.dumps({
            "mode": "distributed", "eligibleRuntimes": ["native_thread_lane"], "nativeThreadUserApproved": True,
            "runtimeSelectionPolicy": "native_session_required", "orchestrationPolicy": "strict",
            "maxParallelWorkers": maximum, "projectAffinityPolicy": "inherit_or_resolve_required",
            "targetProjectId": "synthetic-project", "targetProjectPath": "/synthetic/project", "projectResolutionSource": "user_selected",
            "independentReviewRequired": review,
        }))

    def claim(self, name: str, request: str, evidence: dict | None = None) -> dict:
        return self.command("claim-dispatch", "--lane", name, "--request-id", request, "--capability-evidence", json.dumps(evidence or {}))

    def registration_args(self, name: str, worker: str, request: str, claim: dict | None = None, reviews: str = "") -> list[str]:
        args = ["--worker-id", worker, "--lane", name, "--request-id", request, "--lane-runtime", "native_thread_lane", "--thread-id", "synthetic-thread-" + worker, "--runtime-handle", "synthetic-thread-" + worker, "--project-target-type", "project", "--project-id", "synthetic-project", "--project-environment", "local", "--thread-tool-check", "synthetic native adapter check", "--task", "isolated fixture", "--tool-profile", "synthetic tools", "--credential-policy", "no real credentials"]
        if claim:
            args.extend(["--claim-id", claim["claimId"]])
        args.extend(["--controller-thread-id", "synthetic-controller", "--reply-to-thread-id", "synthetic-controller"])
        if reviews:
            args.extend(["--reviews-worker-ids", reviews])
        return args

    def finish(self, name: str, worker: str) -> None:
        self.command("record-callback", "--worker-id", worker, "--from-lane", name, "--artifact", "synthetic-" + name, "--gate-decision", "pass", "--callback-mode-observed", "active_message")
        self.command("complete-lane", "--lane", name, "--artifact", "synthetic-" + name)

    def test_corrected_output_reenters_frontier_and_cannot_appear_finalizable(self) -> None:
        self.command("init", "--goal", "direct correction", "--lanes", "design")
        self.command("complete-lane", "--lane", "design", "--artifact", "old-artifact")
        self.command("revise-contract", "--invalid-from-lane", "design", "--reason", "approved correction")
        ready = self.command("ready-lanes")
        self.assertEqual("ready", ready["status"])
        self.assertEqual("stale", ready["readyLanes"][0]["status"])
        self.assertEqual("design", self.command("next-lane")["name"])
        self.reject("all lanes done", "finalize")
        self.command("complete-lane", "--lane", "design", "--artifact", "corrected-artifact")
        self.assertEqual("finalizable", self.command("ready-lanes")["status"])
        self.command("finalize")
        self.assertEqual("finalized", self.command("ready-lanes")["status"])
        self.assertEqual("finalized", self.command("next-lane")["status"])

    def test_failed_and_blocked_lanes_require_explicit_recovery(self) -> None:
        self.command("init", "--goal", "direct failure", "--lanes", "design")
        for decision in ("needs-work", "blocked"):
            self.command("complete-lane", "--lane", "design", "--decision", decision)
            ready = self.command("ready-lanes")
            self.assertEqual("blocked", ready["status"])
            self.assertEqual([], ready["readyLanes"])
            self.assertEqual("resolve-or-revise", ready["blockedLanes"][0]["action"])
            self.assertEqual("blocked", self.command("next-lane")["status"])

    def test_claim_is_idempotent_capacity_is_atomic_and_binding_is_single_use(self) -> None:
        self.init_native()
        first = self.claim("design", "request-1")
        self.assertEqual("create", first["creationAction"])
        repeated = self.claim("design", "request-1")
        self.assertEqual(first["claimId"], repeated["claimId"])
        self.assertEqual("reconcile-existing-creation", repeated["creationAction"])
        self.reject("lane_dispatch_reserved", "claim-dispatch", "--lane", "design", "--request-id", "duplicate")
        self.reject("worker_capacity_exceeded", "claim-dispatch", "--lane", "research", "--request-id", "overflow")
        self.command("register-worker", *self.registration_args("design", "one", "request-1", first))
        self.assertEqual("already-registered", self.claim("design", "request-1")["creationAction"])
        ready = self.command("ready-lanes")
        self.assertEqual(1, ready["activeWorkers"])
        self.assertEqual(0, ready["reservedDispatches"])
        self.assertEqual(0, ready["availableSlots"])
        self.reject("dispatch_claim_mismatch", "register-worker", *self.registration_args("design", "two", "request-2", first))

    def test_strict_registration_requires_prior_claim(self) -> None:
        self.init_native()
        self.reject("dispatch_claim_required", "register-worker", *self.registration_args("design", "one", "request-1"))

    def test_unknown_runtime_needs_explicit_host_discovery_evidence(self) -> None:
        state = self.init_native(confirmed=False)
        self.assertFalse(state["orchestrationPlan"]["runtimeReady"])
        self.reject("capability_runtime_unverified", "claim-dispatch", "--lane", "design", "--request-id", "request")
        claim = self.claim("design", "request", {"synthetic-skill": "synthetic callable found in host tool inventory"})
        self.assertEqual("create", claim["creationAction"])

    def test_optional_worker_cannot_bypass_binding_when_actually_dispatched(self) -> None:
        definition = lane("design", role="primary", authority="define", owner=True, depends=[], capability="")
        definition.update(workerRequired=False, capabilityRequirements=[])
        self.command("init", "--goal", "direct lane with optional delegation", "--lane-definitions", json.dumps([definition]))
        self.reject("capability_unbound", "claim-dispatch", "--lane", "design", "--request-id", "unplanned-worker")

    def test_concurrent_claims_cannot_oversubscribe_or_duplicate_a_lane(self) -> None:
        self.init_native()
        jobs = [("design" if index % 2 == 0 else "research", f"request-{index}") for index in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda job: self.run_command("claim-dispatch", "--lane", job[0], "--request-id", job[1]), jobs))
        self.assertEqual(1, sum(result.returncode == 0 for result in results))
        state = self.command("status")
        self.assertEqual(1, len(state["dispatchClaims"]))
        self.assertEqual(0, self.command("ready-lanes")["availableSlots"])

    def test_uncertain_claim_survives_revision_until_reconciled(self) -> None:
        self.init_native()
        claim = self.claim("design", "request")
        self.command("revise-contract", "--invalid-from-lane", "design", "--reason", "approved correction during setup")
        ready = self.command("ready-lanes")
        self.assertEqual("waiting", ready["status"])
        self.assertEqual(1, ready["reservedDispatches"])
        self.reject("dispatch_claim_mismatch", "register-worker", *self.registration_args("design", "one", "request", claim))
        self.reject("dispatch_request_conflict", "claim-dispatch", "--lane", "design", "--request-id", "request")
        self.reject("invalid choice", "release-dispatch", "--claim-id", claim["claimId"], "--outcome", "timeout", "--evidence", "wait timed out")
        self.command("release-dispatch", "--claim-id", claim["claimId"], "--outcome", "not-created", "--evidence", "synthetic host inventory confirms no creation")
        self.assertEqual("ready", self.command("ready-lanes")["status"])

    def test_completed_callback_frees_capacity_without_auto_completing_the_lane(self) -> None:
        self.init_native()
        claim = self.claim("design", "request")
        self.command("register-worker", *self.registration_args("design", "one", "request", claim))
        self.command("record-callback", "--worker-id", "one", "--from-lane", "design", "--artifact", "synthetic artifact", "--gate-decision", "pass", "--callback-mode-observed", "active_message")
        ready = self.command("ready-lanes")
        self.assertEqual(0, ready["activeWorkers"])
        self.assertEqual(["research"], [item["name"] for item in ready["readyLanes"]])
        self.assertEqual("complete-lane", ready["blockedLanes"][0]["action"])
        self.assertEqual("research", self.command("next-lane")["name"])

    def test_legacy_registration_also_enforces_capacity_and_single_attempt(self) -> None:
        state = self.init_native()
        # Model an existing persisted state without the new mandatory-claim opt-in.
        state.pop("dispatchAdmission")
        self.state.write_text(json.dumps(state))
        self.command("register-worker", *self.registration_args("design", "one", "request-1"))
        self.reject("lane_attempt_exists", "register-worker", *self.registration_args("design", "two", "request-2"))
        self.reject("worker_capacity_exceeded", "register-worker", *self.registration_args("research", "three", "request-3"))
        self.command("update-worker", "--worker-id", "one", "--status", "superseded", "--runtime-stop-evidence", "synthetic runtime was stopped")
        self.command("register-worker", *self.registration_args("research", "three", "request-3"))
        self.reject("worker_capacity_exceeded", "update-worker", "--worker-id", "one", "--status", "running")

    def test_revision_does_not_free_a_still_running_superseded_worker(self) -> None:
        self.init_native()
        claim = self.claim("design", "request")
        self.command("register-worker", *self.registration_args("design", "one", "request", claim))
        self.command("revise-contract", "--invalid-from-lane", "design", "--reason", "approved change while worker runs")
        ready = self.command("ready-lanes")
        self.assertEqual(1, ready["activeWorkers"])
        self.assertEqual(0, ready["availableSlots"])
        self.reject("lane_runtime_not_stopped", "claim-dispatch", "--lane", "design", "--request-id", "replacement")
        self.reject("worker_capacity_exceeded", "claim-dispatch", "--lane", "research", "--request-id", "next")
        self.command("update-worker", "--worker-id", "one", "--status", "superseded", "--runtime-stop-evidence", "synthetic host confirmed task stopped")
        self.assertEqual("ready", self.command("ready-lanes")["status"])

    def test_sample_review_runtime_coverage_excludes_other_branch_and_future_production(self) -> None:
        definitions = [
            lane("design", role="primary", authority="define", owner=True, depends=[], capability="design", outputs=["spec"]),
            lane("sample", role="primary", authority="implement", depends=["design"], capability="writer", inputs=["spec"], outputs=["sample-artifact"], boundary="approved-target", targets=["sample-target"], handoff_risk="low", handoff_mode="artifact-contract"),
            lane("other-branch", role="primary", authority="implement", depends=["design"], capability="writer", inputs=["spec"], outputs=["other-artifact"], boundary="approved-target", targets=["other-target"], handoff_risk="low", handoff_mode="artifact-contract"),
            lane("sample-review", role="verification", authority="verify", depends=["sample"], capability="reviewer", inputs=["sample-artifact"], outputs=["sample-verdict"], boundary="review-only", verification_scope="intermediate-artifact"),
            lane("production", role="primary", authority="implement", depends=["sample-review"], capability="writer", inputs=["sample-verdict"], outputs=["final-artifact"], boundary="approved-target", targets=["final-target"], handoff_risk="low", handoff_mode="artifact-contract"),
            lane("final-review", role="verification", authority="verify", depends=["production", "other-branch"], capability="reviewer", inputs=["final-artifact", "other-artifact"], boundary="review-only"),
        ]
        self.init_native(maximum=2, definitions=definitions, review=True)
        for name in ("design", "sample", "other-branch", "sample-review", "production", "final-review"):
            reviews = "sample" if name == "sample-review" else "sample,other-branch,production" if name == "final-review" else ""
            claim = self.claim(name, "request-" + name)
            self.command("register-worker", *self.registration_args(name, name, "request-" + name, claim, reviews))
            self.finish(name, name)
        self.assertEqual("finalizable", self.command("ready-lanes")["status"])
        self.command("finalize")

    def test_mcp_claim_and_release_forwarding(self) -> None:
        self.init_native()
        def call(name: str, arguments: dict) -> dict:
            request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": {"statePath": str(self.state), **arguments}}}) + "\n"
            result = subprocess.run(["node", str(SERVER)], input=request, text=True, capture_output=True)
            response = json.loads(result.stdout)
            self.assertNotIn("error", response)
            return response["result"]["structuredContent"]["result"]
        claim = call("task_controller_claim_dispatch", {"lane": "design", "requestId": "request"})
        self.assertEqual("create", claim["creationAction"])
        released = call("task_controller_release_dispatch", {"claimId": claim["claimId"], "outcome": "not-created", "evidence": "synthetic host lookup"})
        self.assertEqual("released", released["status"])


if __name__ == "__main__":
    unittest.main()
