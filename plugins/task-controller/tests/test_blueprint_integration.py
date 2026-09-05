from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "task_controller_state.py"
SERVER = ROOT / "mcp" / "server.mjs"

LANES = [
    {"name": "research", "kind": "research"},
    {"name": "publish", "kind": "implementation", "writeBoundary": "approved-target"},
]


def task_blueprint() -> dict:
    return {
        "blueprintVersion": "1.0",
        "id": "integration-blueprint",
        "taskType": "internal-analysis",
        "interactionMode": "execute",
        "outcome": {"businessGoal": "Choose a release plan", "supportedDecision": "Approve scope"},
        "deliverable": {
            "id": "deliverable-main",
            "kind": "report",
            "target": "target-main",
            "format": "md",
            "audience": "operations",
            "useMode": "decision support",
            "standalone": True,
            "artifactClass": "report",
        },
        "sources": [{"id": "source-1", "required": True}],
        "intentAnchors": [{"id": "anchor-1", "statement": "Keep the approved scope"}],
        "decisions": [{"id": "decision-1", "statement": "Use approved scope", "status": "binding"}],
        "changePolicy": {
            "preserve": [{"id": "preserve-1"}],
            "allowed": [{"id": "allowed-1"}],
            "forbidden": [{"id": "forbidden-1"}],
        },
        "acceptanceCases": [{"id": "acceptance-1", "description": "Contains a recommendation"}],
        "approvals": {},
        "writePolicy": {
            "targets": [{"id": "target-main", "locator": "/approved/target"}],
            "allowedActions": ["update"],
            "destructiveActionsRequireApproval": True,
        },
        "standards": [],
        "assumptions": [],
        "nonGoals": [],
        "capacity": {},
        "changeTriggers": [],
    }


def manual_contract_spec() -> dict:
    return {
        "specVersion": "1.0",
        "deliverable": {"id": "manual-deliverable", "kind": "code", "target": "/target", "format": "source"},
        "canonicalSources": [{"id": "source-1"}],
        "preserve": [],
        "allowedChanges": [],
        "forbidden": [],
        "acceptance": [],
    }


class BlueprintIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.state = Path(self.temp_dir.name) / "state.json"

    def command(self, command: str, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        # These manually ordered fixtures test Blueprint semantic lineage, not
        # strict lane decomposition. Compatibility must now be explicit.
        if command == "init":
            args = (*args, "--orchestration-policy", "legacy")
        result = subprocess.run(
            [sys.executable, str(HELPER), command, *args],
            cwd=self.temp_dir.name,
            text=True,
            capture_output=True,
            check=False,
        )
        if ok and result.returncode != 0:
            self.fail(result.stderr or result.stdout)
        if not ok and result.returncode == 0:
            self.fail(f"command unexpectedly passed: {result.stdout}")
        return result

    def output(self, result: subprocess.CompletedProcess[str]) -> dict:
        return json.loads(result.stdout)

    def init_blueprint(self, blueprint: dict | None = None, *extra: str) -> dict:
        return self.output(
            self.command(
                "init",
                "--state",
                str(self.state),
                "--goal",
                "blueprint integration",
                "--lane-definitions",
                json.dumps(LANES),
                "--task-blueprint",
                json.dumps(blueprint or task_blueprint()),
                *extra,
            )
        )

    def mcp_call(self, name: str, arguments: dict) -> dict:
        if name == "task_controller_init":
            arguments = {**arguments, "executionPolicy": {"orchestrationPolicy": "legacy"}}
        request = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
        ) + "\n"
        result = subprocess.run(
            ["node", str(SERVER)], cwd=self.temp_dir.name, input=request, text=True, capture_output=True, check=False
        )
        self.assertEqual(0, result.returncode, result.stderr)
        response = json.loads(result.stdout.strip())
        self.assertNotIn("error", response)
        return response["result"]["structuredContent"]["result"]

    def test_cli_compile_is_read_only_and_uses_plugin_root_imports(self) -> None:
        compiled = self.output(
            self.command(
                "compile-blueprint",
                "--task-blueprint",
                json.dumps(task_blueprint()),
                "--lane-definitions",
                json.dumps(LANES),
            )
        )
        self.assertTrue(compiled["compiledExecutable"])
        self.assertEqual("2.0", compiled["contractSpec"]["specVersion"])
        self.assertFalse(self.state.exists())

    def test_blueprint_init_persists_compiler_lineage(self) -> None:
        state = self.init_blueprint()
        self.assertEqual(task_blueprint()["id"], state["taskBlueprint"]["id"])
        self.assertEqual(64, len(state["blueprintDigest"]))
        self.assertIsInstance(state["blueprintTraceability"], dict)
        self.assertTrue(state["blueprintCompiledExecutable"])
        self.assertEqual("2.0", state["contractSpec"]["specVersion"])

    def test_non_executable_blueprint_blocks_semantic_strict_risk_init(self) -> None:
        blueprint = task_blueprint()
        blueprint["capacity"] = {"required": True, "maxWorkers": 1}
        result = self.command(
            "init",
            "--state",
            str(self.state),
            "--goal",
            "blocked blueprint",
            "--lane-definitions",
            json.dumps(LANES),
            "--task-blueprint",
            json.dumps(blueprint),
            ok=False,
        )
        self.assertIn("compiledExecutable", result.stderr)
        self.assertFalse(self.state.exists())

    def test_dual_input_requires_semantic_equivalence(self) -> None:
        compiled = self.output(
            self.command(
                "compile-blueprint",
                "--task-blueprint",
                json.dumps(task_blueprint()),
                "--lane-definitions",
                json.dumps(LANES),
            )
        )["contractSpec"]
        compiled["deliverable"]["format"] = "pdf"
        compiled.pop("deliverableFingerprint", None)
        result = self.command(
            "init",
            "--state",
            str(self.state),
            "--goal",
            "mismatch",
            "--lane-definitions",
            json.dumps(LANES),
            "--task-blueprint",
            json.dumps(task_blueprint()),
            "--contract-spec",
            json.dumps(compiled),
            ok=False,
        )
        self.assertIn("does not semantically match", result.stderr)

    def test_blueprint_revision_recompiles_and_preserves_lineage(self) -> None:
        initial = self.init_blueprint()
        revised_blueprint = deepcopy(task_blueprint())
        revised_blueprint["outcome"]["businessGoal"] = "Choose the revised release plan"
        revised = self.output(
            self.command(
                "revise-contract",
                "--state",
                str(self.state),
                "--invalid-from-lane",
                "research",
                "--task-blueprint",
                json.dumps(revised_blueprint),
            )
        )["state"]
        self.assertEqual(2, revised["contractRevision"])
        self.assertEqual(revised_blueprint["outcome"], revised["taskBlueprint"]["outcome"])
        self.assertNotEqual(initial["blueprintDigest"], revised["blueprintDigest"])
        self.assertTrue(revised["blueprintCompiledExecutable"])

    def test_legacy_manual_contract_spec_revision_remains_compatible(self) -> None:
        initial = self.output(
            self.command(
                "init",
                "--state",
                str(self.state),
                "--goal",
                "manual contract",
                "--lane-definitions",
                json.dumps(LANES),
                "--contract-spec",
                json.dumps(manual_contract_spec()),
            )
        )
        revised = self.output(
            self.command(
                "revise-contract",
                "--state",
                str(self.state),
                "--invalid-from-lane",
                "research",
                "--contract-spec",
                json.dumps(manual_contract_spec()),
            )
        )["state"]
        self.assertIsNone(initial["taskBlueprint"])
        self.assertIsNone(revised["taskBlueprint"])
        self.assertEqual(2, revised["contractRevision"])

    def test_mcp_compile_route_and_init_forwarding(self) -> None:
        blueprint = task_blueprint()
        compiled = self.mcp_call(
            "task_controller_compile_blueprint",
            {"taskBlueprint": blueprint, "laneDefinitions": LANES},
        )
        self.assertTrue(compiled["compiledExecutable"])

        route_blueprint = deepcopy(blueprint)
        route_blueprint["domains"] = ["client-deck"]
        route_blueprint["artifactClass"] = "presentation"
        route = self.mcp_call(
            "task_controller_route_capabilities",
            {"taskBlueprint": route_blueprint, "activeCapabilityIds": ["deck-strategy", "deck-script", "deck-verifier"]},
        )
        self.assertEqual("shadow", route["mode"])
        self.assertFalse(self.state.exists())

        lark_blueprint = deepcopy(blueprint)
        lark_blueprint["domains"] = ["lark-operations"]
        lark_blueprint["artifactClass"] = "dashboard"
        unavailable_lark = self.mcp_call(
            "task_controller_route_capabilities",
            {"taskBlueprint": lark_blueprint, "runtimeAvailability": {"lark": False}},
        )
        missing = {item["id"]: item["reason"] for item in unavailable_lark["missing"]}
        self.assertEqual("provider runtime 'lark' is unavailable", missing["lark-base-operations"])

        state = self.mcp_call(
            "task_controller_init",
            {"statePath": str(self.state), "goal": "MCP blueprint", "laneDefinitions": LANES, "taskBlueprint": blueprint},
        )
        self.assertEqual(blueprint["id"], state["taskBlueprint"]["id"])
        self.assertTrue(state["blueprintCompiledExecutable"])


if __name__ == "__main__":
    unittest.main()
