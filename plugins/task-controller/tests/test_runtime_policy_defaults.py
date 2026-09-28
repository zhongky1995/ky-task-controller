"""Missing configuration must not relax the distribution's runtime boundary."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import task_controller_state as controller
from runtime.worker_runtime import approved_runtime_ids, select_runtime


def test_missing_policy_keeps_session_and_project_requirements():
    with tempfile.TemporaryDirectory() as directory:
        with patch.object(controller, "PLUGIN_ROOT", Path(directory)):
            policy = controller.load_runtime_defaults()
    assert policy["runtimeSelectionPolicy"] == "native_session_required"
    assert policy["projectAffinityPolicy"] == "inherit_or_resolve_required"
    assert not policy["nativeThreadUserApproved"]
    assert not policy["projectlessUserApproved"]
    assert select_runtime(
        {"workerLifecycle": "ephemeral"},
        ["managed_agent_worker", "native_thread_lane"],
        approved_runtime_ids=approved_runtime_ids(policy),
        selection_policy=policy["runtimeSelectionPolicy"],
    ) == ""


def test_partial_policy_does_not_reenable_managed_fallback():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "config").mkdir()
        (root / "config/runtime-policy.json").write_text(
            json.dumps({"maxParallelWorkers": 2}), encoding="utf-8"
        )
        with patch.object(controller, "PLUGIN_ROOT", root):
            policy = controller.load_runtime_defaults()
    assert policy["maxParallelWorkers"] == 2
    assert select_runtime(
        {"workerLifecycle": "ephemeral"}, ["managed_agent_worker"],
        selection_policy=policy["runtimeSelectionPolicy"],
    ) == ""


def test_explicit_runtime_override_remains_supported():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "config").mkdir()
        (root / "config/runtime-policy.json").write_text(
            json.dumps({"runtimeSelectionPolicy": "lane_lifecycle"}), encoding="utf-8"
        )
        with patch.object(controller, "PLUGIN_ROOT", root):
            policy = controller.load_runtime_defaults()
    assert select_runtime(
        {"workerLifecycle": "ephemeral"}, ["managed_agent_worker"],
        selection_policy=policy["runtimeSelectionPolicy"],
    ) == "managed_agent_worker"
