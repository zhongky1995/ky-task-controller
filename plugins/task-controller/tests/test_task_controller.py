from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "task_controller_state.py"
SERVER = ROOT / "mcp" / "server.mjs"


class ControllerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.state = Path(self.temp_dir.name) / "state.json"

    def command(self, command: str, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        # This suite predates orchestration contracts and tests runtime/semantic
        # enforcement independently. Import those fixtures explicitly as legacy;
        # strict default/provenance/admission have dedicated integration tests.
        if command == "init" and "--orchestration-policy" not in args:
            args = list(args)
            if "--execution-policy" in args:
                index = args.index("--execution-policy") + 1
                policy = json.loads(args[index])
                policy.setdefault("orchestrationPolicy", "legacy")
                args[index] = json.dumps(policy)
            else:
                args.extend(["--orchestration-policy", "legacy"])
        result = subprocess.run(
            [sys.executable, str(HELPER), command, "--state", str(self.state), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if ok and result.returncode != 0:
            self.fail(f"command failed: {result.stderr or result.stdout}")
        if not ok and result.returncode == 0:
            self.fail(f"command unexpectedly passed: {result.stdout}")
        return result

    def output(self, result: subprocess.CompletedProcess[str]) -> Any:
        return json.loads(result.stdout)

    def init_state(
        self,
        lanes: list[dict[str, Any]],
        *,
        split_requirement: str = "mandatory",
        mode: str = "multi_session",
        eligible_runtimes: list[str] | None = None,
        required_worker_lanes: list[str] | None = None,
        independent_review: bool = False,
        native_thread_user_approved: bool = False,
        runtime_selection_policy: str = "lane_lifecycle",
        max_parallel_workers: int = 4,
        project_affinity_policy: str = "allow_projectless",
        projectless_user_approved: bool = True,
        target_project_id: str = "",
        target_project_path: str = "",
        project_resolution_source: str = "",
    ) -> dict[str, Any]:
        eligible = ["managed_agent_worker"] if eligible_runtimes is None else eligible_runtimes
        required = required_worker_lanes or []
        policy = {
            # These fixtures intentionally exercise pre-orchestration workflow
            # contracts. New strict planning is covered in test_orchestration.
            "orchestrationPolicy": "legacy",
            "splitRequirement": split_requirement,
            "mode": mode,
            "eligibleRuntimes": eligible,
            "downgradeReason": "worker runtime unavailable" if not eligible else "",
            "requiredWorkerLanes": required,
            "independentReviewRequired": independent_review,
            "nativeThreadUserApproved": native_thread_user_approved,
            "runtimeSelectionPolicy": runtime_selection_policy,
            "maxParallelWorkers": max_parallel_workers,
            "projectAffinityPolicy": project_affinity_policy,
            "projectlessUserApproved": projectless_user_approved,
            "targetProjectId": target_project_id,
            "targetProjectPath": target_project_path,
            "projectResolutionSource": project_resolution_source,
        }
        return self.output(
            self.command(
                "init",
                "--goal",
                "regression test",
                "--enforcement-mode",
                "workflow_only",
                "--semantic-downgrade-reason",
                "legacy workflow compatibility fixture",
                "--lane-definitions",
                json.dumps(lanes),
                "--execution-policy",
                json.dumps(policy),
            )
        )

    def strict_spec(self, *, sample: bool = False) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "specVersion": "1.0",
            "deliverable": {
                "id": "deliverable-main",
                "kind": "code",
                "target": "/approved/target",
                "format": "source",
            },
            "canonicalSources": [{"id": "source-1", "required": True}],
            "preserve": [{"id": "preserve-1"}],
            "allowedChanges": [{"id": "change-1"}],
            "forbidden": [{"id": "forbidden-1"}],
            "acceptance": [{"id": "acceptance-1"}],
        }
        if sample:
            spec["sampleGate"] = {
                "required": True,
                "lane": "sample",
                "blocks": ["implementation"],
                "acceptanceIds": ["acceptance-1"],
            }
        return spec

    def business_spec(
        self,
        *,
        interaction_mode: str = "execute",
        units: list[dict[str, Any]] | None = None,
        self_contained: bool = False,
        user_approval: bool = False,
    ) -> dict[str, Any]:
        spec = self.strict_spec()
        spec["specVersion"] = "2.0"
        spec["interactionMode"] = interaction_mode
        spec["deliverable"].update(
            {
                "audience": "client",
                "useMode": "direct handoff",
                "standalone": True,
                "artifactClass": "source-package",
                "units": units or [],
                "deliveryPackage": {
                    "selfContained": self_contained,
                    "maxRequiredOpens": 1,
                    **({"entrypoint": "main-entry"} if self_contained else {}),
                },
            }
        )
        spec["writePolicy"] = {
            "targets": [{"id": "target-main", "locator": "/approved/target", "environment": "test"}],
            "allowedActions": ["update", "delete"],
            "destructiveActionsRequireApproval": True,
        }
        spec["decisionLedger"] = [
            {"id": "decision-binding", "statement": "Preserve client-ready output", "status": "binding"}
        ]
        if user_approval:
            spec["userApprovalGate"] = {
                "required": True,
                "blocks": ["implementation"],
                "artifactId": "sample-artifact",
            }
        return spec

    def business_register(self, worker_id: str, lane: str, handle: str, *, ok: bool = True):
        state = json.loads(self.state.read_text(encoding="utf-8"))
        lane_state = next(item for item in state["lanes"] if item["name"] == lane)
        boundary: tuple[str, ...] = ()
        if lane_state["writeBoundary"] == "approved-target":
            boundary = ("--tool-profile", "repo-write", "--credential-policy", "local-only")
        return self.register_managed(
            worker_id,
            lane,
            f"request-{worker_id}",
            handle,
            *self.strict_identity_args(),
            *boundary,
            ok=ok,
        )

    def business_callback(
        self,
        worker_id: str,
        lane: str,
        manifest: list[dict[str, Any]],
        *,
        receipt: dict[str, Any] | None = None,
        ok: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        args = [
            "record-callback",
            "--worker-id",
            worker_id,
            "--from-lane",
            lane,
            "--artifact",
            f"{lane}.artifact",
            *self.strict_identity_args(),
            "--artifact-manifest",
            json.dumps(manifest),
            "--check-results",
            json.dumps(self.strict_checks("source-1", "preserve-1", "change-1", "forbidden-1", "acceptance-1", "decision-binding")),
        ]
        if receipt is not None:
            args.extend(("--write-receipt", json.dumps(receipt)))
        return self.command(*args, ok=ok)

    def write_receipt(self, *, target_id: str = "target-main", locator: str = "/approved/target") -> dict[str, str]:
        return {
            "targetId": target_id,
            "targetLocator": locator,
            "action": "update",
            "beforeVersion": "",
            "afterVersion": "v2",
            "readbackEvidence": "readback matched",
            "idempotencyKey": "write-1",
        }

    def init_strict(
        self,
        lanes: list[dict[str, Any]],
        *,
        spec: dict[str, Any] | None = None,
        independent_review: bool = False,
    ) -> dict[str, Any]:
        policy = {
            "splitRequirement": "mandatory",
            "mode": "multi_session",
            "eligibleRuntimes": ["managed_agent_worker"],
            "requiredWorkerLanes": [lane["name"] for lane in lanes],
            "independentReviewRequired": independent_review,
            "runtimeSelectionPolicy": "lane_lifecycle",
        }
        return self.output(
            self.command(
                "init",
                "--goal",
                "strict regression",
                "--lane-definitions",
                json.dumps(lanes),
                "--execution-policy",
                json.dumps(policy),
                "--contract-spec",
                json.dumps(spec or self.strict_spec()),
            )
        )

    def strict_identity_args(self) -> tuple[str, ...]:
        state = json.loads(self.state.read_text(encoding="utf-8"))
        return (
            "--contract-digest",
            state["contractDigest"],
            "--deliverable-fingerprint",
            state["contractSpec"]["deliverableFingerprint"],
        )

    def strict_checks(self, *ids: str) -> list[dict[str, str]]:
        selected = ids or ("source-1", "preserve-1", "change-1", "forbidden-1", "acceptance-1")
        return [{"id": item, "status": "pass", "evidence": f"verified {item}"} for item in selected]

    def strict_callback(
        self,
        worker_id: str,
        lane: str,
        *,
        checks: list[dict[str, str]] | None = None,
        corrections: list[dict[str, Any]] | None = None,
        ok: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return self.command(
            "record-callback",
            "--worker-id",
            worker_id,
            "--from-lane",
            lane,
            "--artifact",
            f"{lane}.artifact",
            *self.strict_identity_args(),
            "--artifact-manifest",
            json.dumps(
                [{"id": f"{lane}-artifact", "deliverableId": "deliverable-main", "path": f"/{lane}"}]
            ),
            "--check-results",
            json.dumps(checks if checks is not None else self.strict_checks()),
            "--correction-events",
            json.dumps(corrections or []),
            "--gate-decision",
            "pass",
            ok=ok,
        )

    def register_managed(
        self,
        worker_id: str,
        lane: str,
        request_id: str,
        runtime_handle: str,
        *extra: str,
        ok: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return self.command(
            "register-worker",
            "--worker-id",
            worker_id,
            "--lane",
            lane,
            "--task",
            f"work on {lane}",
            "--lane-runtime",
            "managed_agent_worker",
            "--runtime-handle",
            runtime_handle,
            "--request-id",
            request_id,
            "--thread-tool-check",
            "managed-agent-available",
            *extra,
            ok=ok,
        )

    def callback(
        self,
        worker_id: str,
        lane: str,
        artifact: str,
        *,
        request_id: str = "",
        observed_mode: str = "",
        ok: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        identity = ["--request-id", request_id] if request_id else ["--worker-id", worker_id]
        observed = ["--callback-mode-observed", observed_mode] if observed_mode else []
        return self.command(
            "record-callback",
            *identity,
            "--from-lane",
            lane,
            "--artifact",
            artifact,
            "--gate-decision",
            "pass",
            *observed,
            ok=ok,
        )


class ExecutionPolicyTests(ControllerTestCase):
    def test_explicit_approval_uses_native_sessions(self) -> None:
        state = self.output(
            self.command(
                "init",
                "--goal",
                "native session default",
                "--lane-definitions",
                json.dumps([{"name": "research", "workerRequired": True, "dependsOn": []}]),
                "--execution-policy",
                json.dumps(
                    {
                        "splitRequirement": "mandatory",
                        "mode": "distributed",
                        "eligibleRuntimes": ["managed_agent_worker", "native_thread_lane"],
                        "requiredWorkerLanes": ["research"],
                        "nativeThreadUserApproved": True,
                        "targetProjectId": "project-main",
                        "targetProjectPath": "/workspace/project-main",
                        "projectResolutionSource": "controller_project",
                    }
                ),
            )
        )
        policy = state["executionPolicy"]
        self.assertEqual("native_session_required", policy["runtimeSelectionPolicy"])
        self.assertTrue(policy["nativeThreadUserApproved"])
        self.assertEqual(4, policy["maxParallelWorkers"])
        self.assertEqual("inherit_or_resolve_required", policy["projectAffinityPolicy"])
        self.assertFalse(policy["projectlessUserApproved"])
        self.assertEqual("project-main", policy["targetProjectId"])
        self.assertEqual("controller_project", policy["projectResolutionSource"])
        self.assertEqual("native_thread_lane", state["lanes"][0]["recommendedRuntime"])

    def test_parallel_worker_ceiling_can_be_raised_to_ten(self) -> None:
        lanes = [
            {"name": f"research-{index}", "workerRequired": True, "dependsOn": []}
            for index in range(10)
        ]
        state = self.init_state(
            lanes,
            required_worker_lanes=[lane["name"] for lane in lanes],
            max_parallel_workers=10,
        )
        self.assertEqual(10, state["executionPolicy"]["maxParallelWorkers"])
        frontier = self.output(self.command("ready-lanes"))
        self.assertEqual(10, len(frontier["readyLanes"]))
        self.assertEqual([], frontier["deferredReadyLanes"])
        self.assertTrue(frontier["waitCoordination"]["requiresBatching"])
        self.assertEqual(8, frontier["waitCoordination"]["maxTargetsPerCall"])
        self.assertEqual([8, 2], [len(batch) for batch in frontier["waitCoordination"]["laneBatches"]])

    def test_parallel_worker_ceiling_rejects_eleven(self) -> None:
        rejected = self.command(
            "init",
            "--goal",
            "reject excessive concurrency",
            "--lane-definitions",
            json.dumps([{"name": "research", "dependsOn": []}]),
            "--execution-policy",
            json.dumps({"maxParallelWorkers": 11}),
            ok=False,
        )
        self.assertIn("maxParallelWorkers must be an integer from 1 to 10", rejected.stderr)

    def test_strict_policy_blocks_native_dispatch_without_resolved_project(self) -> None:
        rejected = self.command(
            "init",
            "--goal",
            "native project affinity",
            "--lane-definitions",
            json.dumps([{"name": "research", "workerRequired": True, "dependsOn": []}]),
            "--execution-policy",
            json.dumps(
                {
                    "splitRequirement": "mandatory",
                    "mode": "distributed",
                    "eligibleRuntimes": ["native_thread_lane"],
                    "requiredWorkerLanes": ["research"],
                    "nativeThreadUserApproved": True,
                }
            ),
            ok=False,
        )
        self.assertIn("project_affinity_required", rejected.stderr)

    def test_native_session_required_rejects_managed_registration(self) -> None:
        self.init_state(
            [{"name": "research", "workerRequired": True, "dependsOn": []}],
            mode="distributed",
            eligible_runtimes=["managed_agent_worker", "native_thread_lane"],
            required_worker_lanes=["research"],
            native_thread_user_approved=True,
            runtime_selection_policy="native_session_required",
        )
        rejected = self.register_managed(
            "worker-1", "research", "request-1", "agent-1", ok=False
        )
        self.assertIn("native_session_required", rejected.stderr)

    def test_projectless_override_requires_explicit_user_approval(self) -> None:
        rejected = self.command(
            "init",
            "--goal",
            "projectless exception",
            "--lane-definitions",
            json.dumps([{"name": "research", "workerRequired": True, "dependsOn": []}]),
            "--execution-policy",
            json.dumps(
                {
                    "splitRequirement": "mandatory",
                    "mode": "distributed",
                    "eligibleRuntimes": ["native_thread_lane"],
                    "requiredWorkerLanes": ["research"],
                    "nativeThreadUserApproved": True,
                    "runtimeSelectionPolicy": "native_session_required",
                    "projectAffinityPolicy": "allow_projectless",
                    "projectlessUserApproved": False,
                }
            ),
            ok=False,
        )
        self.assertIn("projectlessUserApproved=true", rejected.stderr)

    def test_mandatory_eligible_runtime_rejects_sequential_and_direct(self) -> None:
        lanes = [{"name": "implementation"}]
        for mode in ("sequential_lanes", "direct"):
            with self.subTest(mode=mode):
                self.state = Path(self.temp_dir.name) / f"{mode}.json"
                result = self.command(
                    "init",
                    "--goal",
                    "must split",
                    "--lane-definitions",
                    json.dumps(lanes),
                    "--execution-policy",
                    json.dumps(
                        {
                            "splitRequirement": "mandatory",
                            "mode": mode,
                            "eligibleRuntimes": ["managed_agent_worker"],
                        }
                    ),
                    ok=False,
                )
                self.assertIn("requires mode=distributed", result.stderr)

    def test_distributed_mode_is_preferred_and_legacy_alias_remains_valid(self) -> None:
        distributed = self.init_state(
            [{"name": "evidence", "workerRequired": True}],
            mode="distributed",
            required_worker_lanes=["evidence"],
        )
        lane = distributed["lanes"][0]
        self.assertEqual("distributed", distributed["executionPolicy"]["mode"])
        self.assertEqual("managed_agent_worker", lane["recommendedRuntime"])
        self.assertEqual("ephemeral", lane["workerLifecycle"])
        self.assertEqual("packet_only", lane["contextPolicy"])

        self.state = Path(self.temp_dir.name) / "legacy.json"
        legacy = self.init_state(
            [{"name": "evidence", "workerRequired": True}],
            mode="multi_session",
            required_worker_lanes=["evidence"],
        )
        self.assertEqual("multi_session", legacy["executionPolicy"]["mode"])
        self.assertEqual("managed_agent_worker", legacy["lanes"][0]["recommendedRuntime"])

    def test_persistent_lane_requires_approved_native_thread(self) -> None:
        rejected = self.command(
            "init",
            "--goal",
            "persistent lane",
            "--lane-definitions",
            json.dumps(
                [
                    {
                        "name": "strategy-workbench",
                        "workerLifecycle": "persistent",
                    }
                ]
            ),
            "--execution-policy",
            json.dumps(
                {
                    "splitRequirement": "mandatory",
                    "mode": "distributed",
                    "eligibleRuntimes": ["native_thread_lane"],
                    "nativeThreadUserApproved": False,
                }
            ),
            ok=False,
        )
        self.assertIn("nativeThreadUserApproved=true", rejected.stderr)

    def test_persistent_lane_cannot_use_direct_mode(self) -> None:
        rejected = self.command(
            "init",
            "--goal",
            "invalid persistent direct lane",
            "--lane-definitions",
            json.dumps(
                [{"name": "strategy-workbench", "workerLifecycle": "persistent"}]
            ),
            "--execution-policy",
            json.dumps(
                {
                    "splitRequirement": "none",
                    "mode": "direct",
                    "eligibleRuntimes": ["native_thread_lane"],
                    "nativeThreadUserApproved": True,
                }
            ),
            ok=False,
        )
        self.assertIn("requires mode=distributed", rejected.stderr)

    def test_persistent_lane_selects_native_thread_after_approval(self) -> None:
        state = self.init_state(
            [
                {
                    "name": "strategy-workbench",
                    "workerLifecycle": "persistent",
                }
            ],
            mode="distributed",
            eligible_runtimes=["native_thread_lane"],
            native_thread_user_approved=True,
        )
        lane = state["lanes"][0]
        self.assertTrue(lane["workerRequired"])
        self.assertEqual("checkpoint_delta", lane["contextPolicy"])
        self.assertEqual("native_thread_lane", lane["recommendedRuntime"])

    def test_mandatory_without_runtime_allows_documented_fallback(self) -> None:
        state = self.init_state(
            [{"name": "implementation"}],
            mode="sequential_lanes",
            eligible_runtimes=[],
        )
        self.assertEqual("sequential_lanes", state["executionPolicy"]["mode"])
        self.assertEqual([], state["executionPolicy"]["eligibleRuntimes"])
        self.assertTrue(state["executionPolicy"]["downgradeReason"])

    def test_multi_session_auto_requires_write_lanes(self) -> None:
        state = self.init_state(
            [
                {"name": "evidence", "kind": "evidence"},
                {"name": "implementation", "kind": "implementation", "workerRequired": False},
                {"name": "migration", "kind": "support", "writeBoundary": "approved-target"},
            ],
            required_worker_lanes=["evidence"],
        )
        lanes = {lane["name"]: lane for lane in state["lanes"]}
        required = state["executionPolicy"]["requiredWorkerLanes"]
        for name in ("implementation", "migration"):
            self.assertTrue(lanes[name]["workerRequired"])
            self.assertIn(name, required)

    def test_insert_lane_auto_requires_multi_session_write_workers(self) -> None:
        self.init_state([{"name": "evidence"}], required_worker_lanes=["evidence"])
        implementation = self.output(
            self.command("insert-lane", "--lane", "build", "--kind", "implementation")
        )["inserted"]
        approved_target = self.output(
            self.command(
                "insert-lane",
                "--lane",
                "migration",
                "--kind",
                "support",
                "--write-boundary",
                "approved-target",
            )
        )["inserted"]
        state = self.output(self.command("status"))
        self.assertTrue(implementation["workerRequired"])
        self.assertTrue(approved_target["workerRequired"])
        self.assertTrue(
            {"build", "migration"}.issubset(state["executionPolicy"]["requiredWorkerLanes"])
        )

    def test_insert_lane_rejects_new_semantic_risk_without_downgrade_reason(self) -> None:
        self.command(
            "init", "--goal", "low risk", "--enforcement-mode", "workflow_only",
            "--lane-definitions", json.dumps([{"name": "evidence", "kind": "evidence"}]),
        )
        rejected = self.command(
            "insert-lane", "--lane", "publish", "--kind", "support",
            "--write-boundary", "approved-target", ok=False,
        )
        self.assertIn("semantic_upgrade_required", rejected.stderr)
        self.assertEqual(["evidence"], [lane["name"] for lane in self.output(self.command("status"))["lanes"]])

    def test_insert_lane_allows_risk_with_existing_semantic_downgrade_reason(self) -> None:
        self.command(
            "init", "--goal", "documented downgrade", "--enforcement-mode", "workflow_only",
            "--semantic-downgrade-reason", "approved compatibility exception",
            "--lane-definitions", json.dumps([{"name": "evidence", "kind": "evidence"}]),
        )
        inserted = self.output(
            self.command(
                "insert-lane", "--lane", "publish", "--kind", "support",
                "--write-boundary", "approved-target",
            )
        )["inserted"]
        self.assertEqual("approved-target", inserted["writeBoundary"])

    def test_insert_review_lane_rejects_workflow_only_without_downgrade_reason(self) -> None:
        self.command(
            "init", "--goal", "low risk", "--enforcement-mode", "workflow_only",
            "--lane-definitions", json.dumps([{"name": "evidence", "kind": "evidence"}]),
        )
        rejected = self.command(
            "insert-lane", "--lane", "final-review", "--kind", "review", ok=False,
        )
        self.assertIn("semantic_upgrade_required", rejected.stderr)
        state = self.output(self.command("status"))
        self.assertEqual(["evidence"], [lane["name"] for lane in state["lanes"]])

    def test_insert_review_only_lane_allows_documented_workflow_only_downgrade(self) -> None:
        reason = "review evidence remains externally audited"
        self.command(
            "init", "--goal", "documented review downgrade", "--enforcement-mode", "workflow_only",
            "--semantic-downgrade-reason", reason,
            "--lane-definitions", json.dumps([{"name": "evidence", "kind": "evidence"}]),
        )
        inserted = self.output(
            self.command(
                "insert-lane", "--lane", "quality-check", "--kind", "support",
                "--write-boundary", "review-only",
            )
        )["inserted"]
        state = self.output(self.command("status"))
        self.assertEqual("review-only", inserted["writeBoundary"])
        self.assertEqual("workflow_only", state["enforcementMode"])
        self.assertEqual(reason, state["semanticDowngradeReason"])
        self.assertFalse(state["executionPolicy"]["independentReviewRequired"])


class WorkerGateTests(ControllerTestCase):
    def test_explicit_dependency_frontier_allows_parallel_registration(self) -> None:
        self.init_state(
            [
                {"name": "research-a", "workerRequired": True, "dependsOn": []},
                {"name": "research-b", "workerRequired": True, "dependsOn": []},
                {
                    "name": "synthesis",
                    "workerRequired": True,
                    "dependsOn": ["research-a", "research-b"],
                },
            ],
            required_worker_lanes=["research-a", "research-b", "synthesis"],
            max_parallel_workers=2,
        )
        frontier = self.output(self.command("ready-lanes"))
        self.assertEqual(["research-a", "research-b"], [lane["name"] for lane in frontier["readyLanes"]])
        self.assertEqual(2, frontier["availableSlots"])

        self.register_managed("worker-a", "research-a", "request-a", "agent-a")
        self.register_managed("worker-b", "research-b", "request-b", "agent-b")
        waiting = self.output(self.command("ready-lanes"))
        self.assertEqual("waiting", waiting["status"])
        self.assertEqual(0, waiting["availableSlots"])

        self.callback("worker-a", "research-a", "a.md")
        self.command("complete-lane", "--lane", "research-a", "--artifact", "a.md")
        still_waiting = self.output(self.command("ready-lanes"))
        self.assertEqual([], still_waiting["readyLanes"])

        self.callback("worker-b", "research-b", "b.md")
        self.command("complete-lane", "--lane", "research-b", "--artifact", "b.md")
        next_frontier = self.output(self.command("ready-lanes"))
        self.assertEqual(["synthesis"], [lane["name"] for lane in next_frontier["readyLanes"]])

    def test_required_lane_without_worker_is_blocked(self) -> None:
        self.init_state(
            [{"name": "implementation", "kind": "implementation", "workerRequired": True}],
            required_worker_lanes=["implementation"],
        )
        gate = self.output(self.command("gate-check", "--target-lane", "implementation"))
        self.assertFalse(gate["allowed"])
        self.assertIn("Required worker missing for lane: implementation", gate["blockers"])

    def test_complete_pass_requires_worker_and_callback(self) -> None:
        self.init_state(
            [{"name": "implementation", "kind": "implementation", "workerRequired": True}],
            required_worker_lanes=["implementation"],
        )
        no_worker = self.command(
            "complete-lane", "--lane", "implementation", "--artifact", "build.zip", ok=False
        )
        self.assertIn("Required worker missing", no_worker.stderr)
        self.register_managed(
            "impl-worker",
            "implementation",
            "request-1",
            "agent-1",
            "--tool-profile",
            "repo-write",
            "--credential-policy",
            "local-only",
        )
        no_callback = self.command(
            "complete-lane", "--lane", "implementation", "--artifact", "build.zip", ok=False
        )
        self.assertIn("Worker not done", no_callback.stderr)
        self.assertIn("Worker callback missing", no_callback.stderr)

    def test_managed_agent_worker_can_pass(self) -> None:
        self.init_state(
            [{"name": "evidence", "kind": "evidence", "workerRequired": True}],
            required_worker_lanes=["evidence"],
        )
        worker = self.output(self.register_managed("evidence-worker", "evidence", "request-1", "agent-1"))
        self.assertEqual("managed_agent_worker", worker["laneRuntime"])
        self.assertEqual("managed_result_collected", worker["callbackModeExpected"])
        self.assertEqual("", worker["controllerThreadId"])
        self.assertEqual("", worker["replyToThreadId"])
        self.assertEqual("ephemeral", worker["workerLifecycle"])
        self.assertEqual("packet_only", worker["contextPolicy"])
        self.assertIn("Runtime envelope:", worker["prompt"])
        callback = self.output(self.callback("evidence-worker", "evidence", "evidence.md"))
        self.assertEqual("managed_result_collected", callback["callbackModeObserved"])
        lane = self.output(
            self.command("complete-lane", "--lane", "evidence", "--artifact", "evidence.md")
        )
        self.assertEqual("done", lane["status"])

    def test_duplicate_request_id_is_rejected(self) -> None:
        self.init_state([{"name": "one"}, {"name": "two"}])
        self.register_managed("worker-1", "one", "same-request", "agent-1")
        result = self.register_managed("worker-2", "one", "same-request", "agent-2", ok=False)
        self.assertIn("requestId already exists", result.stderr)

    def test_wrong_from_lane_is_rejected(self) -> None:
        self.init_state([{"name": "one"}, {"name": "two"}])
        self.register_managed("worker-1", "one", "request-1", "agent-1")
        result = self.callback("worker-1", "two", "artifact.md", ok=False)
        self.assertIn("fromLane must match", result.stderr)

    def test_callback_replay_is_rejected(self) -> None:
        self.init_state([{"name": "one"}])
        self.register_managed("worker-1", "one", "request-1", "agent-1")
        self.callback("worker-1", "one", "artifact.md")
        replay = self.callback("worker-1", "one", "changed.md", ok=False)
        self.assertIn("Callback already recorded", replay.stderr)

    def test_controller_poll_allowed_rejects_missing_or_unavailable_pass_evidence(self) -> None:
        for observed_mode in ("", "unspecified", "unavailable"):
            with self.subTest(observed_mode=observed_mode or "empty"):
                self.state = Path(self.temp_dir.name) / f"poll-{observed_mode or 'empty'}.json"
                self.init_state([{"name": "one"}])
                self.register_managed(
                    "worker-1",
                    "one",
                    "request-1",
                    "agent-1",
                    "--callback-mode-expected",
                    "controller_poll_allowed",
                )
                result = self.callback(
                    "worker-1", "one", "artifact.md", observed_mode=observed_mode, ok=False
                )
                self.assertIn("callback mode mismatch", result.stderr)
                worker = self.output(self.command("list-workers"))[0]
                self.assertFalse(worker["callbackReceived"])
                self.assertEqual("pending", worker["status"])

    def test_active_message_preferred_accepts_poll_recovery_with_warning(self) -> None:
        self.init_state([{"name": "one"}])
        self.register_managed(
            "worker-1",
            "one",
            "request-1",
            "agent-1",
            "--callback-mode-expected",
            "active_message_preferred",
        )
        callback = self.output(
            self.callback(
                "worker-1",
                "one",
                "artifact.md",
                observed_mode="controller_poll_recovery",
            )
        )
        self.assertIn("degraded to controller poll recovery", callback["notes"])
        self.command("complete-lane", "--lane", "one", "--artifact", "artifact.md")
        gate = self.output(self.command("gate-check"))
        self.assertTrue(gate["allowed"], gate["blockers"])
        self.assertTrue(
            any("degraded to controller poll recovery" in warning for warning in gate["warnings"])
        )

    def test_active_message_preferred_rejects_unavailable_pass_evidence(self) -> None:
        self.init_state([{"name": "one"}])
        self.register_managed(
            "worker-1",
            "one",
            "request-1",
            "agent-1",
            "--callback-mode-expected",
            "active_message_preferred",
        )
        result = self.callback(
            "worker-1", "one", "artifact.md", observed_mode="unavailable", ok=False
        )
        self.assertIn("callback mode mismatch", result.stderr)

    def test_downstream_worker_waits_for_upstream_gate_and_marks_lane_running(self) -> None:
        self.init_state(
            [{"name": "one", "workerRequired": True}, {"name": "two", "workerRequired": True}],
            required_worker_lanes=["one", "two"],
        )
        self.register_managed("worker-1", "one", "request-1", "agent-1")
        early = self.register_managed("worker-2", "two", "request-2", "agent-2", ok=False)
        self.assertIn("upstream_gate_blocked", early.stderr)
        self.assertIn("Lane not complete: one", early.stderr)
        self.assertIn("Worker callback missing: worker-1", early.stderr)

        self.callback("worker-1", "one", "one.md")
        self.command("complete-lane", "--lane", "one", "--artifact", "one.md")
        self.register_managed("worker-2", "two", "request-2", "agent-2")
        state = self.output(self.command("status"))
        lane = next(item for item in state["lanes"] if item["name"] == "two")
        self.assertEqual("running", lane["status"])

    def test_callback_requires_owning_lane_running(self) -> None:
        self.init_state([{"name": "one"}])
        self.register_managed("worker-1", "one", "request-1", "agent-1")
        state = json.loads(self.state.read_text(encoding="utf-8"))
        state["lanes"][0]["status"] = "pending"
        self.state.write_text(json.dumps(state), encoding="utf-8")
        early = self.callback("worker-1", "one", "artifact.md", ok=False)
        self.assertIn("requires lane running", early.stderr)

    def test_callback_rechecks_upstream_gate(self) -> None:
        self.init_state(
            [{"name": "one"}, {"name": "two", "workerRequired": True}],
            required_worker_lanes=["two"],
        )
        self.command("complete-lane", "--lane", "one", "--artifact", "one.md")
        self.register_managed("worker-2", "two", "request-2", "agent-2")
        state = json.loads(self.state.read_text(encoding="utf-8"))
        state["lanes"][0].update({"status": "pending", "artifact": "", "decision": ""})
        self.state.write_text(json.dumps(state), encoding="utf-8")
        early = self.callback("worker-2", "two", "two.md", ok=False)
        self.assertIn("upstream_gate_blocked", early.stderr)
        self.assertIn("Lane not complete: one", early.stderr)

    def test_native_thread_checks_and_reply_ids_are_required(self) -> None:
        self.init_state(
            [{"name": "one"}],
            eligible_runtimes=["native_thread_lane"],
            native_thread_user_approved=True,
        )
        base = (
            "--worker-id",
            "native-worker",
            "--lane",
            "one",
            "--task",
            "work on one",
            "--lane-runtime",
            "native_thread_lane",
            "--thread-id",
            "thread-1",
            "--runtime-handle",
            "thread-1",
            "--request-id",
            "request-1",
        )
        no_check = self.command("register-worker", *base, ok=False)
        self.assertIn("threadToolCheck", no_check.stderr)
        no_reply_ids = self.command(
            "register-worker", *base, "--thread-tool-check", "native-threads-available", ok=False
        )
        self.assertIn("controllerThreadId and replyToThreadId", no_reply_ids.stderr)
        worker = self.output(
            self.command(
                "register-worker",
                *base,
                "--thread-tool-check",
                "native-threads-available",
                "--controller-thread-id",
                "controller-thread",
                "--reply-to-thread-id",
                "controller-thread",
            )
        )
        self.assertEqual("controller-thread", worker["controllerThreadId"])
        self.assertEqual("controller-thread", worker["replyToThreadId"])
        self.assertEqual("thread-1", worker["threadId"])
        self.assertEqual(worker["threadId"], worker["runtimeHandle"])

    def test_native_thread_requires_explicit_matching_thread_identity(self) -> None:
        self.init_state(
            [{"name": "one"}],
            eligible_runtimes=["native_thread_lane"],
            native_thread_user_approved=True,
        )
        base = (
            "--worker-id", "native-worker", "--lane", "one", "--task", "work on one",
            "--lane-runtime", "native_thread_lane", "--request-id", "request-1",
        )
        no_thread = self.command(
            "register-worker", *base, "--runtime-handle", "thread-1", ok=False,
        )
        self.assertIn("non-empty threadId", no_thread.stderr)
        no_runtime_handle = self.command(
            "register-worker", *base, "--thread-id", "thread-1", ok=False,
        )
        self.assertIn("runtimeHandle equal to threadId", no_runtime_handle.stderr)
        mismatch = self.command(
            "register-worker", *base, "--thread-id", "thread-1",
            "--runtime-handle", "thread-alias", ok=False,
        )
        self.assertIn("runtimeHandle must equal threadId", mismatch.stderr)

    def test_strict_project_affinity_requires_matching_native_worker_project(self) -> None:
        self.init_state(
            [{"name": "one"}],
            eligible_runtimes=["native_thread_lane"],
            native_thread_user_approved=True,
            runtime_selection_policy="native_session_required",
            project_affinity_policy="inherit_or_resolve_required",
            projectless_user_approved=False,
            target_project_id="project-main",
            target_project_path="/workspace/project-main",
            project_resolution_source="controller_project",
        )
        base = (
            "--worker-id", "native-worker", "--lane", "one", "--task", "work on one",
            "--lane-runtime", "native_thread_lane", "--request-id", "request-1",
            "--thread-id", "thread-1", "--runtime-handle", "thread-1",
            "--thread-tool-check", "native-threads-available",
            "--controller-thread-id", "controller-thread",
            "--reply-to-thread-id", "controller-thread",
        )
        missing = self.command("register-worker", *base, ok=False)
        self.assertIn("project_affinity_required", missing.stderr)
        mismatch = self.command(
            "register-worker", *base,
            "--project-id", "project-other",
            "--project-environment", "local",
            ok=False,
        )
        self.assertIn("project_affinity_mismatch", mismatch.stderr)
        worker = self.output(
            self.command(
                "register-worker", *base,
                "--project-target-type", "project",
                "--project-id", "project-main",
                "--project-environment", "worktree",
            )
        )
        self.assertEqual("project", worker["projectTargetType"])
        self.assertEqual("project-main", worker["projectId"])
        self.assertEqual("worktree", worker["projectEnvironment"])
        self.assertIn("projectId: project-main", worker["prompt"])
        self.assertEqual("1.0", worker["runtimeRegistryVersion"])
        self.assertEqual("1.0", worker["runtimeProfileVersion"])
        self.assertEqual(64, len(worker["runtimeProfileFingerprint"]))

    def test_native_thread_registration_requires_explicit_user_approval(self) -> None:
        self.init_state(
            [{"name": "one"}],
            eligible_runtimes=["managed_agent_worker", "native_thread_lane"],
        )
        rejected = self.command(
            "register-worker",
            "--worker-id",
            "native-worker",
            "--lane",
            "one",
            "--task",
            "work on one",
            "--lane-runtime",
            "native_thread_lane",
            "--thread-id",
            "thread-1",
            "--runtime-handle",
            "thread-1",
            "--request-id",
            "request-1",
            "--thread-tool-check",
            "native-threads-available",
            "--controller-thread-id",
            "controller-thread",
            "--reply-to-thread-id",
            "controller-thread",
            ok=False,
        )
        self.assertIn("nativeThreadUserApproved=true", rejected.stderr)

    def test_persistent_lane_rejects_managed_worker(self) -> None:
        self.init_state(
            [{"name": "one", "workerLifecycle": "persistent"}],
            eligible_runtimes=["managed_agent_worker", "native_thread_lane"],
            native_thread_user_approved=True,
        )
        rejected = self.register_managed(
            "worker-1", "one", "request-1", "agent-1", ok=False
        )
        self.assertIn("persistent and requires native_thread_lane", rejected.stderr)

    def test_runtime_profile_rejects_unsupported_project_scope(self) -> None:
        self.init_state([{"name": "one"}])
        rejected = self.register_managed(
            "worker-1",
            "one",
            "request-1",
            "agent-1",
            "--project-target-type",
            "project",
            "--project-id",
            "project-main",
            "--project-environment",
            "local",
            ok=False,
        )
        self.assertIn("not supported by the managed_agent_worker runtime profile", rejected.stderr)


class IndependentReviewTests(ControllerTestCase):
    def init_review_state(self) -> None:
        self.init_state(
            [
                {
                    "name": "implementation",
                    "kind": "implementation",
                    "workerRequired": True,
                    "writeBoundary": "approved-target",
                },
                {"name": "review", "kind": "review", "workerRequired": True, "writeBoundary": "review-only"},
            ],
            required_worker_lanes=["implementation", "review"],
            independent_review=True,
        )
        self.register_managed(
            "impl-worker",
            "implementation",
            "impl-request",
            "agent-impl",
            "--tool-profile",
            "repo-write",
            "--credential-policy",
            "local-only",
        )
        self.callback("impl-worker", "implementation", "build.zip")
        self.command("complete-lane", "--lane", "implementation", "--artifact", "build.zip")

    def test_same_runtime_self_review_is_rejected(self) -> None:
        self.init_review_state()
        result = self.register_managed(
            "review-worker",
            "review",
            "review-request",
            "agent-impl",
            "--reviews-worker-ids",
            "impl-worker",
            ok=False,
        )
        self.assertTrue(
            "runtimeHandle already has" in result.stderr or "independent runtime identity" in result.stderr
        )

    def test_independent_review_passes(self) -> None:
        self.init_review_state()
        self.register_managed(
            "review-worker",
            "review",
            "review-request",
            "agent-review",
            "--reviews-worker-ids",
            "impl-worker",
        )
        self.callback("review-worker", "review", "review.md")
        self.command("complete-lane", "--lane", "review", "--artifact", "review.md")
        gate = self.output(self.command("gate-check"))
        self.assertTrue(gate["allowed"], gate["blockers"])


class DynamicReviewOrderTests(ControllerTestCase):
    def init_dynamic_state(self, *, include_final_review: bool = True) -> None:
        lanes = [
            {"name": "writer1", "kind": "implementation", "writeBoundary": "approved-target"},
            {"name": "review1", "kind": "review", "writeBoundary": "review-only"},
            {"name": "writer2", "kind": "support", "writeBoundary": "approved-target"},
        ]
        if include_final_review:
            lanes.append({"name": "review2", "kind": "review", "writeBoundary": "review-only"})
        self.init_state(
            lanes,
            required_worker_lanes=[lane["name"] for lane in lanes],
            independent_review=True,
        )

    def register_writer(self, number: int) -> None:
        self.register_managed(
            f"writer-{number}",
            f"writer{number}",
            f"writer-request-{number}",
            f"agent-writer-{number}",
            "--tool-profile",
            "repo-write",
            "--credential-policy",
            "local-only",
        )

    def complete_worker_lane(self, worker_id: str, lane: str) -> None:
        artifact = f"{lane}.artifact"
        self.callback(worker_id, lane, artifact)
        self.command("complete-lane", "--lane", lane, "--artifact", artifact)

    def complete_first_review(self) -> None:
        self.register_writer(1)
        self.complete_worker_lane("writer-1", "writer1")
        self.register_managed(
            "reviewer-1",
            "review1",
            "review-request-1",
            "agent-review-1",
            "--reviews-worker-ids",
            "writer-1",
        )
        self.complete_worker_lane("reviewer-1", "review1")

    def test_early_review_gate_ignores_future_writer(self) -> None:
        self.init_dynamic_state()
        self.complete_first_review()
        self.register_writer(2)

        gate = self.output(self.command("gate-check", "--target-lane", "writer2"))

        self.assertTrue(gate["allowed"], gate["blockers"])
        self.assertFalse(any("review" in blocker.lower() and "writer-2" in blocker for blocker in gate["blockers"]))

    def test_future_writer_callback_succeeds_without_future_review(self) -> None:
        self.init_dynamic_state()
        self.complete_first_review()
        self.register_writer(2)

        callback = self.output(self.callback("writer-2", "writer2", "writer2.artifact"))

        self.assertEqual("done", callback["status"])
        self.assertEqual("pass", callback["decision"])

    def test_later_review_can_register_for_all_preceding_writers(self) -> None:
        self.init_dynamic_state()
        self.complete_first_review()
        self.register_writer(2)
        self.complete_worker_lane("writer-2", "writer2")

        reviewer = self.output(
            self.register_managed(
                "reviewer-2",
                "review2",
                "review-request-2",
                "agent-review-2",
                "--reviews-worker-ids",
                "writer-1,writer-2",
            )
        )

        self.assertEqual(["writer-1", "writer-2"], reviewer["reviewsWorkerIds"])

    def test_final_gate_blocks_writer_without_downstream_review_coverage(self) -> None:
        self.init_dynamic_state(include_final_review=False)
        self.complete_first_review()
        self.register_writer(2)
        self.complete_worker_lane("writer-2", "writer2")

        gate = self.output(self.command("gate-check"))

        self.assertFalse(gate["allowed"])
        self.assertTrue(any("Final review coverage" in blocker and "writer-2" in blocker for blocker in gate["blockers"]))


class RevisionAndCompatibilityTests(ControllerTestCase):
    def test_revise_contract_invalidates_downstream_outputs_and_old_callback(self) -> None:
        self.init_state(
            [{"name": "evidence"}, {"name": "implementation"}, {"name": "review"}],
            required_worker_lanes=["implementation"],
        )
        self.command("complete-lane", "--lane", "evidence", "--artifact", "evidence-v1.md")
        self.register_managed(
            "impl-worker",
            "implementation",
            "impl-request",
            "agent-impl",
            "--tool-profile",
            "repo-write",
            "--credential-policy",
            "local-only",
        )
        self.callback("impl-worker", "implementation", "build-v1.zip")
        self.command("complete-lane", "--lane", "implementation", "--artifact", "build-v1.zip")
        self.command("complete-lane", "--lane", "review", "--artifact", "review-v1.md")

        revised = self.output(
            self.command(
                "revise-contract",
                "--invalid-from-lane",
                "implementation",
                "--contract",
                "contract v2",
                "--reason",
                "user changed acceptance",
            )
        )["state"]
        lanes = {lane["name"]: lane for lane in revised["lanes"]}
        self.assertEqual("done", lanes["evidence"]["status"])
        self.assertEqual("evidence-v1.md", lanes["evidence"]["artifact"])
        for name in ("implementation", "review"):
            self.assertEqual("stale", lanes[name]["status"])
            self.assertEqual("", lanes[name]["artifact"])
            self.assertEqual(1, lanes[name]["invalidatedOutputs"][0]["contractRevision"])
        self.assertEqual("superseded", revised["workers"][0]["status"])
        old_callback = self.callback(
            "impl-worker", "implementation", "build-v1.zip", request_id="impl-request", ok=False
        )
        self.assertIn("cannot satisfy the current revision", old_callback.stderr)

    def test_v1_status_is_readable_but_continuing_requires_migration(self) -> None:
        self.state.write_text(
            json.dumps({"goal": "legacy", "lanes": [{"name": "one", "status": "pending"}]}),
            encoding="utf-8",
        )
        status = self.output(self.command("status"))
        self.assertEqual("legacy", status["goal"])
        result = self.command("next-lane", ok=False)
        self.assertIn("migration_required", result.stderr)

    def test_legacy_v2_approved_target_is_readable_but_all_continuations_require_semantic_migration(self) -> None:
        legacy = {
            "schemaVersion": 2,
            "contractRevision": 1,
            "goal": "legacy risk",
            "executionPolicy": {"mode": "direct", "independentReviewRequired": False},
            "lanes": [
                {
                    "name": "implementation", "kind": "implementation",
                    "writeBoundary": "approved-target", "status": "pending",
                }
            ],
            "workers": [],
        }
        self.state.write_text(json.dumps(legacy), encoding="utf-8")
        self.assertIn("Semantic migration/upgrade", self.output(self.command("status"))["compatibilityWarnings"][0])
        self.assertEqual([], self.output(self.command("list-workers")))
        blocked_commands = (
            ("gate-check",),
            ("complete-lane", "--lane", "implementation", "--artifact", "build"),
            ("insert-lane", "--lane", "extra"),
            ("add-note", "--lane", "implementation", "--notes", "note"),
            ("register-worker", "--worker-id", "w", "--lane", "implementation", "--task", "work"),
            ("update-worker", "--worker-id", "w"),
            ("record-callback", "--worker-id", "w", "--from-lane", "implementation"),
            (
                "record-correction", "--event-id", "c1", "--summary", "wrong target",
                "--category", "target", "--requirement-ids", "deliverable-main",
                "--recommended-invalid-from-lane", "implementation",
            ),
            ("revise-contract", "--invalid-from-lane", "implementation"),
        )
        for command in blocked_commands:
            with self.subTest(command=command[0]):
                result = self.command(*command, ok=False)
                self.assertIn("semantic_migration_required", result.stderr)

    def test_legacy_v2_independent_review_risk_requires_semantic_migration(self) -> None:
        legacy = {
            "schemaVersion": 2,
            "contractRevision": 1,
            "goal": "legacy review risk",
            "executionPolicy": {"mode": "direct", "independentReviewRequired": True},
            "lanes": [
                {"name": "implementation", "kind": "implementation", "writeBoundary": "draft-file", "status": "pending"},
                {"name": "review", "kind": "review", "writeBoundary": "review-only", "status": "pending"},
            ],
            "workers": [],
        }
        self.state.write_text(json.dumps(legacy), encoding="utf-8")
        result = self.command("gate-check", ok=False)
        self.assertIn("semantic_migration_required", result.stderr)


class SemanticStrictTests(ControllerTestCase):
    WRITER = {"name": "implementation", "kind": "implementation", "writeBoundary": "approved-target"}

    def register_strict(self, worker_id: str, lane: str, handle: str, *extra: str, ok: bool = True):
        lane_state = next(item for item in json.loads(self.state.read_text())["lanes"] if item["name"] == lane)
        boundary_args: tuple[str, ...] = ()
        if lane_state["writeBoundary"] == "approved-target":
            boundary_args = ("--tool-profile", "repo-write", "--credential-policy", "local-only")
        return self.register_managed(
            worker_id,
            lane,
            f"request-{worker_id}",
            handle,
            *self.strict_identity_args(),
            *boundary_args,
            *extra,
            ok=ok,
        )

    def test_risk_task_defaults_to_semantic_strict(self) -> None:
        state = self.init_strict([self.WRITER])
        self.assertEqual("semantic_strict", state["enforcementMode"])
        self.assertEqual(64, len(state["contractDigest"]))
        self.assertEqual([], state["correctionEvents"])

    def test_explicit_workflow_downgrade_requires_reason(self) -> None:
        base = (
            "--goal", "downgrade", "--lane-definitions", json.dumps([self.WRITER]),
            "--enforcement-mode", "workflow_only",
        )
        rejected = self.command("init", *base, ok=False)
        self.assertIn("semanticDowngradeReason", rejected.stderr)
        state = self.output(self.command("init", *base, "--semantic-downgrade-reason", "accepted legacy risk"))
        self.assertEqual("workflow_only", state["enforcementMode"])

    def test_contract_requires_nonempty_canonical_sources(self) -> None:
        spec = self.strict_spec()
        spec["canonicalSources"] = []
        result = self.command(
            "init", "--goal", "invalid", "--lane-definitions", json.dumps([self.WRITER]),
            "--contract-spec", json.dumps(spec), ok=False,
        )
        self.assertIn("canonicalSources must be non-empty", result.stderr)

    def test_contract_rejects_duplicate_ids(self) -> None:
        spec = self.strict_spec()
        spec["acceptance"][0]["id"] = "source-1"
        result = self.command(
            "init", "--goal", "invalid", "--lane-definitions", json.dumps([self.WRITER]),
            "--contract-spec", json.dumps(spec), ok=False,
        )
        self.assertIn("globally unique", result.stderr)

    def test_contract_rejects_bad_lane_and_sample_references(self) -> None:
        for mutation, message in (("lane", "missing lane"), ("sample", "unknown acceptance")):
            with self.subTest(mutation=mutation):
                self.state = Path(self.temp_dir.name) / f"{mutation}.json"
                spec = self.strict_spec()
                if mutation == "lane":
                    spec["acceptance"][0]["lane"] = "missing"
                else:
                    spec["sampleGate"] = {"required": True, "lane": "implementation", "blocks": ["review"], "acceptanceIds": ["missing"]}
                lanes = [self.WRITER, {"name": "review", "kind": "review"}]
                result = self.command(
                    "init", "--goal", "invalid", "--lane-definitions", json.dumps(lanes),
                    "--contract-spec", json.dumps(spec), ok=False,
                )
                self.assertIn(message, result.stderr)

    def test_deliverable_fingerprint_is_computed_and_verified(self) -> None:
        state = self.init_strict([self.WRITER])
        canonical = json.dumps(state["contractSpec"]["deliverable"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(), state["contractSpec"]["deliverableFingerprint"])
        self.state = Path(self.temp_dir.name) / "bad-fingerprint.json"
        spec = self.strict_spec()
        spec["deliverableFingerprint"] = "0" * 64
        bad = self.command(
            "init", "--goal", "invalid", "--lane-definitions", json.dumps([self.WRITER]),
            "--contract-spec", json.dumps(spec), ok=False,
        )
        self.assertIn("does not match", bad.stderr)

    def test_contract_digest_is_canonical_and_revision_bound(self) -> None:
        first = self.init_strict([self.WRITER])
        first_digest = first["contractDigest"]
        revised = self.output(self.command(
            "revise-contract", "--invalid-from-lane", "implementation",
            "--contract-spec", json.dumps(self.strict_spec()), "--reason", "proactive revision",
        ))["state"]
        self.assertNotEqual(first_digest, revised["contractDigest"])
        self.assertEqual(2, revised["contractRevision"])

    def test_strict_worker_must_bind_current_digest_and_fingerprint(self) -> None:
        self.init_strict([self.WRITER])
        missing = self.register_managed(
            "writer", "implementation", "request-writer", "agent-writer",
            "--tool-profile", "repo-write", "--credential-policy", "local-only", ok=False,
        )
        self.assertIn("contractDigest", missing.stderr)
        worker = self.output(self.register_strict("writer", "implementation", "agent-writer"))
        self.assertEqual(json.loads(self.state.read_text())["contractDigest"], worker["contractDigest"])

    def test_strict_pass_requires_manifest_and_complete_check_results(self) -> None:
        variants = (
            ([], self.strict_checks(), "artifactManifest"),
            ([{"id": "a", "deliverableId": "deliverable-main"}], self.strict_checks("source-1"), "missing required IDs"),
            ([{"id": "a", "deliverableId": "deliverable-main"}], self.strict_checks() + [{"id": "unknown", "status": "pass", "evidence": "x"}], "unknown ID"),
            ([{"id": "a", "deliverableId": "deliverable-main"}], [{**item, "status": "fail"} if item["id"] == "source-1" else item for item in self.strict_checks()], "must pass"),
        )
        for index, (manifest, checks, message) in enumerate(variants):
            with self.subTest(index=index):
                self.state = Path(self.temp_dir.name) / f"callback-{index}.json"
                self.init_strict([self.WRITER])
                self.register_strict("writer", "implementation", f"agent-{index}")
                result = self.command(
                    "record-callback", "--worker-id", "writer", "--from-lane", "implementation",
                    "--artifact", "build", *self.strict_identity_args(),
                    "--artifact-manifest", json.dumps(manifest), "--check-results", json.dumps(checks), ok=False,
                )
                self.assertIn(message, result.stderr)

    def test_artifact_manifest_must_bind_the_main_deliverable(self) -> None:
        for index, manifest in enumerate(
            ([{"id": "unrelated"}], [{"id": "unrelated", "deliverableId": "other-deliverable"}])
        ):
            with self.subTest(index=index):
                self.state = Path(self.temp_dir.name) / f"manifest-{index}.json"
                self.init_strict([self.WRITER])
                self.register_strict("writer", "implementation", f"agent-{index}")
                result = self.command(
                    "record-callback", "--worker-id", "writer", "--from-lane", "implementation",
                    "--artifact", "build", *self.strict_identity_args(),
                    "--artifact-manifest", json.dumps(manifest),
                    "--check-results", json.dumps(self.strict_checks()), ok=False,
                )
                self.assertIn("artifactManifest deliverableId", result.stderr)

        self.state = Path(self.temp_dir.name) / "forged-manifest.json"
        self.init_strict([self.WRITER])
        self.register_strict("writer", "implementation", "agent-forged")
        state = json.loads(self.state.read_text(encoding="utf-8"))
        state["workers"][0].update(
            {
                "status": "done", "decision": "pass", "artifact": "forged", "callbackReceived": True,
                "callbackModeObserved": "managed_result_collected",
                "artifactManifest": [{"id": "unrelated", "deliverableId": "other-deliverable"}],
                "checkResults": self.strict_checks(),
            }
        )
        self.state.write_text(json.dumps(state), encoding="utf-8")
        blocked = self.command("complete-lane", "--lane", "implementation", "--artifact", "forged", ok=False)
        self.assertIn("does not cover deliverable deliverable-main", blocked.stderr)

    def test_sample_gate_blocks_registration_until_sample_acceptance_passes(self) -> None:
        lanes = [
            {"name": "sample", "kind": "support", "writeBoundary": "draft-file"},
            self.WRITER,
        ]
        self.init_strict(lanes, spec=self.strict_spec(sample=True))
        early = self.register_strict("writer", "implementation", "agent-writer", ok=False)
        self.assertIn("Sample gate lane has not passed", early.stderr)
        self.register_strict("sample-worker", "sample", "agent-sample")
        self.strict_callback("sample-worker", "sample", checks=self.strict_checks("source-1", "acceptance-1"))
        self.command("complete-lane", "--lane", "sample", "--artifact", "sample.artifact")
        self.register_strict("writer", "implementation", "agent-writer")

    def test_correction_event_is_persisted_and_blocks_progress(self) -> None:
        self.init_strict([self.WRITER])
        self.register_strict("writer", "implementation", "agent-writer")
        result = self.strict_callback(
            "writer", "implementation",
            corrections=[{"id": "corr-1", "reason": "target changed", "recommendedInvalidFromLane": "implementation"}],
            ok=False,
        )
        self.assertIn("correction_opened", result.stderr)
        state = self.output(self.command("status"))
        self.assertEqual("open", state["correctionEvents"][0]["status"])
        gate = self.output(self.command("gate-check", "--target-lane", "implementation"))
        self.assertFalse(gate["allowed"])
        bypass = self.command("complete-lane", "--lane", "implementation", "--artifact", "build", ok=False)
        self.assertIn("Open correctionEvents", bypass.stderr)

    def test_callback_correction_requires_recommended_invalid_from_lane(self) -> None:
        self.init_strict([self.WRITER])
        self.register_strict("writer", "implementation", "agent-writer")
        result = self.strict_callback(
            "writer", "implementation", corrections=[{"id": "corr-1", "reason": "target changed"}], ok=False,
        )
        self.assertIn("correction recommendedInvalidFromLane", result.stderr)

    def test_controller_record_correction_is_independent_and_blocks_progress(self) -> None:
        self.command(
            "init", "--goal", "controller correction", "--enforcement-mode", "workflow_only",
            "--lane-definitions", json.dumps([{"name": "evidence", "kind": "evidence"}]),
        )
        event_args = (
            "--event-id", "user-correction-1", "--summary", "按上一版保留来源",
            "--category", "preservation", "--requirement-ids", "source-1,preserve-1",
            "--recommended-invalid-from-lane", "evidence",
        )
        event = self.output(self.command("record-correction", *event_args))
        self.assertEqual("open", event["status"])
        self.assertEqual("controller", event["source"])
        self.assertEqual(["source-1", "preserve-1"], event["requirementIds"])
        duplicate = self.command("record-correction", *event_args, ok=False)
        self.assertIn("already exists", duplicate.stderr)
        gate = self.output(self.command("gate-check", "--target-lane", "evidence"))
        self.assertFalse(gate["allowed"])
        self.assertIn("Open correctionEvents", gate["blockers"][0])
        registration = self.command(
            "register-worker", "--worker-id", "worker", "--lane", "evidence", "--task", "work", ok=False,
        )
        self.assertIn("Open correctionEvents", registration.stderr)
        completion = self.command(
            "complete-lane", "--lane", "evidence", "--decision", "needs-work", ok=False,
        )
        self.assertIn("Open correctionEvents", completion.stderr)

    def test_revise_consumes_all_corrections_and_enforces_earliest_lane(self) -> None:
        lanes = [{"name": "evidence", "kind": "evidence"}, self.WRITER]
        self.init_strict(lanes)
        self.register_strict("evidence-worker", "evidence", "agent-evidence")
        self.strict_callback(
            "evidence-worker", "evidence", checks=self.strict_checks("source-1"),
            corrections=[{"id": "corr-early", "reason": "source changed", "recommendedInvalidFromLane": "evidence"}], ok=False,
        )
        late = self.command(
            "revise-contract", "--invalid-from-lane", "implementation", "--contract-spec", json.dumps(self.strict_spec()),
            "--consume-correction-event-ids", "corr-early", ok=False,
        )
        self.assertIn("later than", late.stderr)
        revised = self.output(self.command(
            "revise-contract", "--invalid-from-lane", "evidence", "--contract-spec", json.dumps(self.strict_spec()),
            "--consume-correction-event-ids", "corr-early",
        ))["state"]
        self.assertEqual("consumed", revised["correctionEvents"][0]["status"])
        self.assertEqual(2, revised["contractRevision"])

    def test_review_covers_every_approved_target_writer_and_semantic_item(self) -> None:
        lanes = [
            self.WRITER,
            {"name": "migration", "kind": "support", "writeBoundary": "approved-target"},
            {"name": "review", "kind": "review", "writeBoundary": "review-only"},
        ]
        self.init_strict(lanes, independent_review=True)
        for worker_id, lane in (("impl", "implementation"), ("migration", "migration")):
            self.register_strict(worker_id, lane, f"agent-{worker_id}")
            self.strict_callback(worker_id, lane)
            self.command("complete-lane", "--lane", lane, "--artifact", f"{lane}.artifact")
        missing = self.register_strict(
            "reviewer", "review", "agent-review", "--reviews-worker-ids", "impl", ok=False,
        )
        self.assertIn("migration", missing.stderr)
        self.register_strict(
            "reviewer", "review", "agent-review", "--reviews-worker-ids", "impl,migration",
        )
        self.strict_callback("reviewer", "review")
        self.command("complete-lane", "--lane", "review", "--artifact", "review.artifact")

    def test_complete_lane_cannot_bypass_strict_callback_evidence(self) -> None:
        self.init_strict([self.WRITER])
        self.register_strict("writer", "implementation", "agent-writer")
        state = json.loads(self.state.read_text())
        worker = state["workers"][0]
        worker.update({"status": "done", "decision": "pass", "artifact": "forged", "callbackReceived": True})
        self.state.write_text(json.dumps(state))
        result = self.command("complete-lane", "--lane", "implementation", "--artifact", "forged", ok=False)
        self.assertIn("semantic artifactManifest missing", result.stderr)

    def test_a800_legacy_v2_reads_but_strict_risk_without_contract_fails_closed(self) -> None:
        legacy = {
            "schemaVersion": 2, "contractRevision": 1, "goal": "A800 legacy",
            "executionPolicy": {"mode": "direct", "independentReviewRequired": False},
            "lanes": [{"name": "implementation", "kind": "implementation", "writeBoundary": "approved-target", "status": "pending"}],
            "workers": [],
        }
        self.state.write_text(json.dumps(legacy))
        status = self.output(self.command("status"))
        self.assertIn("compatibilityWarnings", status)
        self.assertNotIn("enforcementMode", json.loads(self.state.read_text()))
        self.state.unlink()
        result = self.command(
            "init", "--goal", "A800 strict", "--lane-definitions", json.dumps([self.WRITER]), ok=False,
        )
        self.assertIn("contractSpec", result.stderr)


class BusinessDeliveryContractTests(ControllerTestCase):
    WRITER = {"name": "implementation", "kind": "implementation", "writeBoundary": "approved-target"}

    def test_discuss_and_plan_modes_hard_block_approved_target(self) -> None:
        for mode in ("discuss_only", "plan_only"):
            with self.subTest(mode=mode):
                self.state = Path(self.temp_dir.name) / f"{mode}.json"
                self.init_strict([self.WRITER], spec=self.business_spec(interaction_mode=mode))
                registration = self.business_register("writer", "implementation", f"agent-{mode}", ok=False)
                self.assertIn(f"interactionMode={mode}", registration.stderr)
                gate = self.output(self.command("gate-check", "--target-lane", "implementation"))
                self.assertFalse(gate["allowed"])
                self.assertIn(f"interactionMode={mode}", gate["blockers"][0])
                completion = self.command(
                    "complete-lane", "--lane", "implementation", "--decision", "needs-work", ok=False,
                )
                self.assertIn(f"interactionMode={mode}", completion.stderr)

    def test_user_approval_binds_revision_and_artifact_fingerprint_then_stales(self) -> None:
        lanes = [
            {"name": "sample", "kind": "support", "writeBoundary": "draft-file"},
            self.WRITER,
        ]
        self.init_strict(lanes, spec=self.business_spec(user_approval=True))
        self.business_register("sample-worker", "sample", "agent-sample")
        self.business_callback(
            "sample-worker",
            "sample",
            [{
                "id": "sample-artifact",
                "deliverableId": "deliverable-main",
                "artifactFingerprint": "sample-sha-1",
                "role": "entrypoint",
            }],
        )
        self.command("complete-lane", "--lane", "sample", "--artifact", "sample.artifact")
        blocked = self.business_register("writer", "implementation", "agent-writer", ok=False)
        self.assertIn("User approval is required", blocked.stderr)
        mismatch = self.command(
            "record-approval", "--artifact-id", "sample-artifact",
            "--artifact-fingerprint", "wrong", "--approver", "client-owner", ok=False,
        )
        self.assertIn("must match", mismatch.stderr)
        approval = self.output(self.command(
            "record-approval", "--approval-id", "approval-1", "--artifact-id", "sample-artifact",
            "--artifact-fingerprint", "sample-sha-1", "--approver", "client-owner",
            "--timestamp", "2026-07-12T10:00:00+08:00",
        ))
        self.assertEqual(1, approval["contractRevision"])
        self.business_register("writer", "implementation", "agent-writer")
        self.command(
            "record-correction", "--event-id", "correction-approval", "--summary", "sample changed",
            "--category", "approval", "--requirement-ids", "acceptance-1",
            "--recommended-invalid-from-lane", "sample",
        )
        state = self.output(self.command("status"))
        self.assertEqual("stale", state["approvalRecords"][0]["status"])

    def test_manifest_must_cover_all_units(self) -> None:
        units = [{"id": "page-1"}, {"id": "page-2"}]
        self.init_strict([self.WRITER], spec=self.business_spec(units=units))
        self.business_register("writer", "implementation", "agent-writer")
        result = self.business_callback(
            "writer",
            "implementation",
            [{"id": "page-one", "deliverableId": "deliverable-main", "unitId": "page-1"}],
            receipt=self.write_receipt(),
            ok=False,
        )
        self.assertIn("missing deliverable unitIds: page-2", result.stderr)

    def test_write_receipt_target_must_match_write_policy(self) -> None:
        self.init_strict([self.WRITER], spec=self.business_spec())
        self.business_register("writer", "implementation", "agent-writer")
        result = self.business_callback(
            "writer",
            "implementation",
            [{"id": "main-entry", "deliverableId": "deliverable-main", "role": "entrypoint"}],
            receipt=self.write_receipt(target_id="wrong-target"),
            ok=False,
        )
        self.assertIn("must exactly match", result.stderr)

    def test_self_contained_package_requires_manifest_entrypoint(self) -> None:
        self.init_strict([self.WRITER], spec=self.business_spec(self_contained=True))
        self.business_register("writer", "implementation", "agent-writer")
        missing = self.business_callback(
            "writer",
            "implementation",
            [{"id": "appendix", "deliverableId": "deliverable-main", "role": "appendix"}],
            receipt=self.write_receipt(),
            ok=False,
        )
        self.assertIn("requires an artifactManifest entrypoint", missing.stderr)

    def test_atomic_locked_mutations_do_not_lose_concurrent_insertions(self) -> None:
        self.command(
            "init", "--goal", "concurrency", "--enforcement-mode", "workflow_only",
            "--lane-definitions", json.dumps([{"name": "base", "kind": "support"}]),
        )
        processes = [
            subprocess.Popen(
                [
                    sys.executable, str(HELPER), "insert-lane", "--state", str(self.state),
                    "--lane", f"parallel-{index}", "--after", "base",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for index in range(12)
        ]
        results = [process.communicate(timeout=20) + (process.returncode,) for process in processes]
        self.assertTrue(all(returncode == 0 for _, _, returncode in results), results)
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(13, len(state["lanes"]))
        self.assertEqual(13, len({lane["name"] for lane in state["lanes"]}))
        self.assertEqual([], list(self.state.parent.glob(f".{self.state.name}.*.tmp")))

    def test_next_lane_requires_explicit_finalize(self) -> None:
        self.command(
            "init", "--goal", "finalize", "--enforcement-mode", "workflow_only",
            "--lane-definitions", json.dumps([{"name": "draft", "kind": "support"}]),
        )
        self.command("complete-lane", "--lane", "draft", "--artifact", "draft.txt")
        pending = self.output(self.command("next-lane"))
        self.assertEqual("finalizable", pending["status"])
        finalized = self.output(self.command("finalize"))
        self.assertEqual("finalized", finalized["status"])
        after = self.output(self.command("next-lane"))
        self.assertEqual("finalized", after["status"])

    def test_business_delivery_presets_cover_required_scenarios(self) -> None:
        preset = ROOT / "skills" / "task-controller" / "references" / "business-delivery-presets.md"
        content = preset.read_text(encoding="utf-8")
        for heading in ("逐P对客稿", "客户报价", "证据型分析", "飞书 Base / 驾驶舱 / Wiki", "现有文档修订"):
            self.assertIn(heading, content)


class McpSchemaTests(unittest.TestCase):
    def test_tools_list_exposes_v2_tools_and_runtime_enums(self) -> None:
        request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
        result = subprocess.run(
            ["node", str(SERVER)],
            cwd=ROOT,
            input=request,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        response = json.loads(result.stdout.strip())
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}
        expected = {
            "task_controller_init",
            "task_controller_status",
            "task_controller_next_lane",
            "task_controller_ready_lanes",
            "task_controller_complete_lane",
            "task_controller_insert_lane",
            "task_controller_register_worker",
            "task_controller_update_worker",
            "task_controller_list_workers",
            "task_controller_classify_feedback",
            "task_controller_ingest_feedback",
            "task_controller_record_correction",
            "task_controller_record_approval",
            "task_controller_record_callback",
            "task_controller_gate_check",
            "task_controller_revise_contract",
            "task_controller_finalize",
        }
        self.assertTrue(expected.issubset(tools))
        register = tools["task_controller_register_worker"]["inputSchema"]["properties"]
        registry = json.loads(
            (ROOT / "config" / "worker-runtime-profiles.json").read_text(encoding="utf-8")
        )
        configured_runtimes = {
            profile["runtimeId"] for profile in registry["profiles"] if profile["independent"]
        }
        self.assertTrue(configured_runtimes.issubset(set(register["laneRuntime"]["enum"])))
        self.assertIn("managed_agent_worker", register["laneRuntime"]["enum"])
        self.assertIn("managed_result_collected", register["callbackModeExpected"]["enum"])
        register_schema = tools["task_controller_register_worker"]["inputSchema"]
        native_rule = next(
            rule for rule in register_schema["allOf"]
            if rule["if"]["properties"]["laneRuntime"].get("const") == "native_thread_lane"
            and "threadId" in rule["then"]["required"]
        )
        self.assertTrue({"threadId", "runtimeHandle"}.issubset(native_rule["then"]["required"]))
        native_target_rule = next(
            rule for rule in register_schema["allOf"]
            if rule["if"]["properties"].get("laneRuntime", {}).get("const") == "native_thread_lane"
            and "projectTargetType" in rule["then"]["required"]
        )
        self.assertIn("projectTargetType", native_target_rule["then"]["required"])
        self.assertEqual(1, register["threadId"]["minLength"])
        callback = tools["task_controller_record_callback"]["inputSchema"]["properties"]
        self.assertIn("managed_result_collected", callback["callbackModeObserved"]["enum"])
        policy = tools["task_controller_init"]["inputSchema"]["properties"]["executionPolicy"]
        self.assertIn("distributed", policy["properties"]["mode"]["enum"])
        self.assertIn("multi_session", policy["properties"]["mode"]["enum"])
        self.assertIn("nativeThreadUserApproved", policy["properties"])
        for field in (
            "projectAffinityPolicy",
            "projectlessUserApproved",
            "targetProjectId",
            "targetProjectPath",
            "projectResolutionSource",
        ):
            self.assertIn(field, policy["properties"])
        lane_definition = tools["task_controller_init"]["inputSchema"]["properties"]["laneDefinitions"]["items"]["properties"]
        for field in ("workerLifecycle", "contextPolicy", "runtimePreference", "dependsOn"):
            self.assertIn(field, lane_definition)
        insert_lane = tools["task_controller_insert_lane"]["inputSchema"]["properties"]
        for field in ("workerLifecycle", "contextPolicy", "runtimePreference", "dependsOn"):
            self.assertIn(field, insert_lane)
        self.assertEqual("native_session_required", policy["properties"]["runtimeSelectionPolicy"]["default"])
        self.assertEqual(4, policy["properties"]["maxParallelWorkers"]["default"])
        self.assertEqual(10, policy["properties"]["maxParallelWorkers"]["maximum"])
        self.assertEqual(
            "inherit_or_resolve_required",
            policy["properties"]["projectAffinityPolicy"]["default"],
        )
        self.assertFalse(policy["properties"]["projectlessUserApproved"]["default"])
        self.assertIn("projectTargetType", register)
        self.assertIn("projectId", register)
        self.assertIn("projectEnvironment", register)
        self.assertEqual(["local", "worktree"], register["projectEnvironment"]["enum"])
        init_props = tools["task_controller_init"]["inputSchema"]["properties"]
        self.assertIn("semantic_strict", init_props["enforcementMode"]["enum"])
        self.assertIn("contractSpec", init_props)
        for field in ("contractDigest", "deliverableFingerprint", "artifactManifest", "checkResults", "writeReceipt", "correctionEvents"):
            self.assertIn(field, callback)
        manifest_item = callback["artifactManifest"]["items"]
        self.assertIn("deliverableId", manifest_item["required"])
        callback_correction = callback["correctionEvents"]["items"]
        self.assertIn("recommendedInvalidFromLane", callback_correction["required"])
        canonical_item = init_props["contractSpec"]["properties"]["canonicalSources"]["items"]
        self.assertIn("required", canonical_item["oneOf"][1]["properties"])
        self.assertIn("priority", canonical_item["oneOf"][1]["properties"])
        contract_props = init_props["contractSpec"]["properties"]
        for field in ("interactionMode", "decisionLedger", "decisionGovernance", "writePolicy", "userApprovalGate"):
            self.assertIn(field, contract_props)
        deliverable_props = contract_props["deliverable"]["properties"]
        for field in ("audience", "useMode", "standalone", "artifactClass", "units", "deliveryPackage"):
            self.assertIn(field, deliverable_props)
        approval = tools["task_controller_record_approval"]["inputSchema"]
        self.assertTrue({"artifactId", "artifactFingerprint", "approver"}.issubset(approval["required"]))
        correction = tools["task_controller_record_correction"]["inputSchema"]
        for field in (
            "statePath", "eventId", "summary", "category", "requirementIds", "recommendedInvalidFromLane",
        ):
            self.assertIn(field, correction["required"])
        ingest_feedback = tools["task_controller_ingest_feedback"]["inputSchema"]
        self.assertTrue({"statePath", "feedback"}.issubset(ingest_feedback["required"]))
        classify_feedback = tools["task_controller_classify_feedback"]["inputSchema"]
        self.assertEqual(["feedback"], classify_feedback["required"])
        revise = tools["task_controller_revise_contract"]["inputSchema"]["properties"]
        self.assertIn("contractSpec", revise)
        self.assertIn("consumeCorrectionEventIds", revise)
        update = tools["task_controller_update_worker"]["inputSchema"]["properties"]
        self.assertNotIn("done", update["status"]["enum"])
        self.assertNotIn("pass", update["decision"]["enum"])

    def test_mcp_forwards_semantic_init_fields_to_python_helper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "mcp-strict.json")
            spec = {
                "specVersion": "1.0",
                "deliverable": {"id": "d", "kind": "code", "target": "/target", "format": "source"},
                "canonicalSources": [{"id": "s"}],
                "preserve": [],
                "allowedChanges": [],
                "forbidden": [],
                "acceptance": [],
            }
            request = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "task_controller_init",
                        "arguments": {
                            "statePath": state_path,
                            "goal": "MCP strict forwarding",
                            "enforcementMode": "semantic_strict",
                            "contractSpec": spec,
                            "laneDefinitions": [
                                {"name": "implementation", "kind": "implementation", "writeBoundary": "approved-target"}
                            ],
                        },
                    },
                }
            ) + "\n"
            result = subprocess.run(
                ["node", str(SERVER)], cwd=ROOT, input=request, text=True, capture_output=True,
                check=False, timeout=10,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            response = json.loads(result.stdout.strip())
            state = response["result"]["structuredContent"]["result"]
            self.assertEqual("semantic_strict", state["enforcementMode"])
            self.assertEqual(64, len(state["contractDigest"]))
            self.assertEqual(64, len(state["contractSpec"]["deliverableFingerprint"]))

    def test_mcp_forwards_native_project_affinity_to_worker_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "mcp-project-affinity.json")
            init_request = json.dumps(
                {
                    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {
                        "name": "task_controller_init",
                        "arguments": {
                            "statePath": state_path,
                            "goal": "MCP project affinity",
                            "enforcementMode": "workflow_only",
                            "laneDefinitions": [
                                {"name": "research", "kind": "evidence", "workerRequired": True, "dependsOn": []}
                            ],
                            "executionPolicy": {
                                "orchestrationPolicy": "legacy",
                                "splitRequirement": "mandatory",
                                "mode": "distributed",
                                "eligibleRuntimes": ["native_thread_lane"],
                                "requiredWorkerLanes": ["research"],
                                "runtimeSelectionPolicy": "native_session_required",
                                "nativeThreadUserApproved": True,
                                "projectAffinityPolicy": "inherit_or_resolve_required",
                                "projectlessUserApproved": False,
                                "targetProjectId": "project-main",
                                "targetProjectPath": "/workspace/project-main",
                                "projectResolutionSource": "controller_project",
                            },
                        },
                    },
                }
            ) + "\n"
            register_request = json.dumps(
                {
                    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {
                        "name": "task_controller_register_worker",
                        "arguments": {
                            "statePath": state_path,
                            "workerId": "worker-1",
                            "threadId": "thread-1",
                            "runtimeHandle": "thread-1",
                            "requestId": "request-1",
                            "controllerThreadId": "controller-thread",
                            "replyToThreadId": "controller-thread",
                            "projectTargetType": "project",
                            "projectId": "project-main",
                            "projectEnvironment": "local",
                            "lane": "research",
                            "laneRuntime": "native_thread_lane",
                            "task": "research the assigned evidence",
                            "threadToolCheck": "native-threads-available",
                        },
                    },
                }
            ) + "\n"
            result = subprocess.run(
                ["node", str(SERVER)], cwd=ROOT, input=init_request + register_request,
                text=True, capture_output=True, check=False, timeout=10,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            responses = [json.loads(line) for line in result.stdout.splitlines()]
            worker = responses[1]["result"]["structuredContent"]["result"]
            self.assertEqual("project", worker["projectTargetType"])
            self.assertEqual("project-main", worker["projectId"])
            self.assertEqual("local", worker["projectEnvironment"])

    def test_mcp_forwards_controller_correction_to_python_helper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "mcp-correction.json")
            init_request = json.dumps(
                {
                    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {
                        "name": "task_controller_init",
                        "arguments": {
                            "statePath": state_path, "goal": "MCP correction",
                            "enforcementMode": "workflow_only",
                            "laneDefinitions": [{"name": "evidence", "kind": "evidence"}],
                        },
                    },
                }
            ) + "\n"
            correction_request = json.dumps(
                {
                    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {
                        "name": "task_controller_record_correction",
                        "arguments": {
                            "statePath": state_path, "eventId": "mcp-correction-1",
                            "summary": "use prior source", "category": "source",
                            "requirementIds": ["source-1"], "recommendedInvalidFromLane": "evidence",
                        },
                    },
                }
            ) + "\n"
            result = subprocess.run(
                ["node", str(SERVER)], cwd=ROOT, input=init_request + correction_request,
                text=True, capture_output=True, check=False, timeout=10,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            responses = [json.loads(line) for line in result.stdout.splitlines()]
            event = responses[1]["result"]["structuredContent"]["result"]
            self.assertEqual("mcp-correction-1", event["id"])
            self.assertEqual("open", event["status"])


if __name__ == "__main__":
    unittest.main()
