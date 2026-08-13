from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.worker_runtime import (
    RUNTIME_REGISTRY,
    RuntimeProfileError,
    approved_runtime_ids,
    load_runtime_profiles,
    select_runtime,
)


class WorkerRuntimeProfileTests(unittest.TestCase):
    def test_checked_in_registry_is_versioned_and_fingerprinted(self) -> None:
        self.assertEqual("1.0", RUNTIME_REGISTRY.registry_version)
        self.assertEqual(
            {"native_thread_lane", "managed_agent_worker"},
            RUNTIME_REGISTRY.independent_runtime_ids(),
        )
        self.assertEqual(64, len(RUNTIME_REGISTRY.fingerprint))
        for profile in RUNTIME_REGISTRY.profiles:
            self.assertEqual(64, len(profile.fingerprint))

    def test_lane_lifecycle_policy_preserves_current_default_order(self) -> None:
        selected = select_runtime(
            {"workerLifecycle": "ephemeral", "runtimePreference": "auto"},
            ["native_thread_lane", "managed_agent_worker"],
            approved_runtime_ids=["native_thread_lane"],
        )
        self.assertEqual("managed_agent_worker", selected)

    def test_session_required_policy_selects_visible_project_runtime(self) -> None:
        lane = {"workerLifecycle": "ephemeral", "runtimePreference": "auto"}
        self.assertEqual(
            "",
            select_runtime(
                lane,
                ["native_thread_lane", "managed_agent_worker"],
                selection_policy="native_session_required",
            ),
        )
        self.assertEqual(
            "native_thread_lane",
            select_runtime(
                lane,
                ["native_thread_lane", "managed_agent_worker"],
                approved_runtime_ids=["native_thread_lane"],
                selection_policy="native_session_required",
            ),
        )

    def test_profile_declares_the_approval_policy_binding(self) -> None:
        self.assertEqual(
            {"managed_agent_worker"},
            approved_runtime_ids({"nativeThreadUserApproved": False}),
        )
        self.assertEqual(
            {"managed_agent_worker", "native_thread_lane"},
            approved_runtime_ids({"nativeThreadUserApproved": True}),
        )

    def test_second_adapter_can_satisfy_policy_without_core_runtime_branch(self) -> None:
        raw = json.loads(
            (ROOT / "config" / "worker-runtime-profiles.json").read_text(encoding="utf-8")
        )
        raw["profiles"].append(
            {
                "runtimeId": "external_session_worker",
                "profileVersion": "1.0",
                "independent": True,
                "userVisible": True,
                "supportsPersistent": True,
                "requiresExplicitApproval": False,
                "approvalPolicyField": "",
                "identityBinding": "opaque_runtime_handle",
                "scopeKinds": ["project"],
                "defaultScopeKind": "project",
                "callbackModes": ["active_message_required"],
                "defaultCallbackMode": "active_message_required",
                "requiresThreadRouting": False,
                "selectionPriority": 5,
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            registry = load_runtime_profiles(path)
        selected = select_runtime(
            {"workerLifecycle": "persistent", "runtimePreference": "auto"},
            ["external_session_worker"],
            selection_policy="native_session_required",
            registry=registry,
        )
        self.assertEqual("external_session_worker", selected)

    def test_invalid_registry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles.json"
            path.write_text(
                json.dumps({"registryVersion": "1.0", "profiles": [{"runtimeId": "unsafe"}]}),
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeProfileError):
                load_runtime_profiles(path)


if __name__ == "__main__":
    unittest.main()
