from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from control_plane.capability_router import shadow_route
from registry.loader import _semver_key, _satisfies, load_registry


class CapabilityRegistryTestCase(unittest.TestCase):
    @staticmethod
    def fingerprint(value: dict) -> str:
        import hashlib

        stable = dict(value)
        stable.pop("fingerprint", None)
        return hashlib.sha256(
            json.dumps(stable, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def test_loads_only_checked_in_sources_not_cache(self) -> None:
        registry = load_registry()
        self.assertGreaterEqual(len(registry.capabilities), 10)
        self.assertEqual({pack.id for pack in registry.scenario_packs}, {
            "client-deck", "evidence-analysis", "lark-operations", "document-revision"
        })
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "plugin-cache" / "capabilities"
            cache.mkdir(parents=True)
            (cache / "untrusted.json").write_text(json.dumps({"id": "untrusted"}), encoding="utf-8")
            self.assertNotIn("untrusted", load_registry().capabilities)

    def test_specific_client_deck_pack_is_selected(self) -> None:
        result = shadow_route({"domains": ["client-deck"], "artifactClass": "presentation"})
        self.assertEqual(result["mode"], "shadow")
        self.assertEqual(result["scenarioPack"]["id"], "client-deck")
        self.assertIn("deck-strategy", {item["id"] for item in result["selected"]})
        verifier = next(item for item in result["selected"] if item["id"] == "deck-verifier")
        self.assertEqual("verifier", verifier["role"])
        self.assertIn("shadow-only", " ".join(result["reasons"]))

    def test_scenario_pack_supports_version_selection(self) -> None:
        pack = load_registry().scenario_load("client-deck", "^1.0")
        self.assertEqual(pack.version, "1.0.0")

    def test_semver_prerelease_identifiers_sort_numerically(self) -> None:
        self.assertGreater(_semver_key("1.0.0-alpha.10"), _semver_key("1.0.0-alpha.2"))

    def test_semver_release_sorts_after_prerelease_and_ignores_build(self) -> None:
        self.assertGreater(_semver_key("1.0.0"), _semver_key("1.0.0-rc.1"))
        self.assertEqual(_semver_key("1.0.0+build.1"), _semver_key("1.0.0+build.2"))

    def test_caret_constraints_enforce_semver_upper_and_lower_bounds(self) -> None:
        cases = (
            ("^1.2.3", "1.2.3", "1.9.9", "2.0.0"),
            ("^0.2.3", "0.2.3", "0.2.9", "0.3.0"),
            ("^0.0.3", "0.0.3", "0.0.3+build.1", "0.0.4"),
        )
        for constraint, lower, within, upper in cases:
            with self.subTest(constraint=constraint):
                self.assertTrue(_satisfies(lower, constraint))
                self.assertTrue(_satisfies(within, constraint))
                self.assertFalse(_satisfies(upper, constraint))
                self.assertFalse(_satisfies("0.0.0", constraint))

    def test_pricing_missing_capability_blocks_executable_route(self) -> None:
        result = shadow_route(
            {"domains": ["evidence-analysis", "pricing"], "artifactClass": "workbook"},
            active_capability_ids={"evidence-workbook", "evidence-verifier"},
        )
        self.assertEqual(result["scenarioPack"]["id"], "evidence-analysis")
        self.assertTrue(any(item["id"] == "pricing-analysis" for item in result["missing"]))
        self.assertIn("block", " ".join(result["reasons"]).lower())

    def test_lark_provider_unavailable_is_explained(self) -> None:
        result = shadow_route(
            {"domains": ["lark-operations"], "artifactClass": "dashboard"},
            runtime_availability={"lark-base-operations": False},
        )
        missing = next(item for item in result["missing"] if item["id"] == "lark-base-operations")
        self.assertEqual(missing["reason"], "capability runtime 'lark-base-operations' is unavailable")
        self.assertEqual(result["scenarioPack"]["id"], "lark-operations")

    def test_provider_runtime_unavailable_blocks_lark_capabilities(self) -> None:
        result = shadow_route(
            {"domains": ["lark-operations"], "artifactClass": "dashboard"},
            runtime_availability={"lark": False},
        )
        missing = {item["id"]: item["reason"] for item in result["missing"]}
        self.assertEqual("provider runtime 'lark' is unavailable", missing["lark-base-operations"])
        self.assertEqual("provider runtime 'lark' is unavailable", missing["lark-verifier"])
        self.assertNotIn("lark-base-operations", {item["id"] for item in result["selected"]})

    def test_semantic_versions_choose_latest_active_capability_and_compatible_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(ROOT / "registry", root / "registry")
            shutil.copytree(ROOT / "scenario_packs", root / "scenario_packs")

            capability = json.loads((root / "registry" / "capabilities" / "deck-strategy.json").read_text(encoding="utf-8"))
            capability["version"] = "1.10.0"
            capability["fingerprint"] = self.fingerprint(capability)
            (root / "registry" / "capabilities" / "deck-strategy-1.10.0.json").write_text(
                json.dumps(capability), encoding="utf-8"
            )
            pack = json.loads((root / "scenario_packs" / "client-deck.json").read_text(encoding="utf-8"))
            pack["version"] = "1.10.0"
            pack["fingerprint"] = self.fingerprint(pack)
            (root / "scenario_packs" / "client-deck-1.10.0.json").write_text(json.dumps(pack), encoding="utf-8")

            registry = load_registry(root / "registry")
            self.assertEqual("1.10.0", registry.capability_load("deck-strategy").version)
            self.assertEqual("1.10.0", registry.scenario_load("client-deck", task_blueprint_version="1.0").version)
            result = shadow_route(
                {"blueprintVersion": "1.0", "domains": ["client-deck"], "artifactClass": "presentation"},
                registry_root=root / "registry",
            )
            self.assertEqual("1.10.0", result["scenarioPack"]["version"])

    def test_scenario_load_excludes_higher_incompatible_pack_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(ROOT / "registry", root / "registry")
            shutil.copytree(ROOT / "scenario_packs", root / "scenario_packs")
            pack = json.loads((root / "scenario_packs" / "client-deck.json").read_text(encoding="utf-8"))
            pack["version"] = "2.0.0"
            pack["compatibility"]["taskBlueprint"] = "^2.0.0"
            pack["fingerprint"] = self.fingerprint(pack)
            (root / "scenario_packs" / "client-deck-2.0.0.json").write_text(json.dumps(pack), encoding="utf-8")

            selected = load_registry(root / "registry").scenario_load(
                "client-deck", task_blueprint_version="1.0.0"
            )
            self.assertEqual("1.0.0", selected.version)

    def test_document_revision_route_is_explainable(self) -> None:
        result = shadow_route({"domains": ["document-revision"], "artifactClass": "document"})
        self.assertEqual(result["scenarioPack"]["id"], "document-revision")
        self.assertTrue(result["selected"])
        self.assertTrue(result["reasons"])


if __name__ == "__main__":
    unittest.main()
