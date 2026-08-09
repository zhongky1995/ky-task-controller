"""Load only checked-in registry sources; never discover plugin caches at runtime."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REGISTRY_ROOT = Path(__file__).resolve().parent
CAPABILITY_FIELDS = (
    "id", "name", "version", "source", "fingerprint", "status", "capabilityType",
    "placement", "domains", "triggers", "exclusions", "resourcePatterns", "inputs",
    "outputs", "operations", "dependencies", "verification", "routing",
)
PACK_FIELDS = (
    "id", "version", "schemaVersion", "fingerprint", "compatibility", "match",
    "blueprintDefaults", "graphTemplate", "capabilityRequirements", "acceptanceCases",
    "verifierRequirements", "goldenFixtures",
)
SEMVER = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
PARTIAL_SEMVER = re.compile(
    r"^(?P<major>0|[1-9]\d*)(?:\.(?P<minor>0|[1-9]\d*))?(?:\.(?P<patch>0|[1-9]\d*))?"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class RegistryValidationError(ValueError):
    """Raised when a checked-in registry document is malformed."""


def _semver_key(version: str) -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]]:
    """Return a SemVer 2.0 precedence key; build metadata is deliberately ignored."""
    match = SEMVER.match(version)
    if not match:
        raise ValueError(f"Invalid semantic version: {version!r}")
    prerelease = match.group("prerelease")
    identifiers = () if prerelease is None else tuple(
        (0, int(identifier)) if identifier.isdigit() else (1, identifier)
        for identifier in prerelease.split(".")
    )
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        1 if prerelease is None else 0,
        identifiers,
    )


def _partial_semver_key(version: str) -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]]:
    """Parse supported abbreviated constraint versions, filling missing parts with zero."""
    match = PARTIAL_SEMVER.match(version)
    if not match:
        raise ValueError(f"Invalid semantic version constraint: {version!r}")
    normalized = ".".join((match.group("major"), match.group("minor") or "0", match.group("patch") or "0"))
    if match.group("prerelease"):
        normalized += f"-{match.group('prerelease')}"
    return _semver_key(normalized)


def _satisfies(version: str, constraint: str | None) -> bool:
    if not constraint or constraint in {"*", "latest"}:
        return True
    required = constraint.lstrip("=")
    if required.startswith("^"):
        lower = _partial_semver_key(required[1:])
        major, minor, patch = lower[:3]
        upper = (
            (major + 1, 0, 0, 1, ()) if major else
            (0, minor + 1, 0, 1, ()) if minor else
            (0, 0, patch + 1, 1, ())
        )
        version_key = _partial_semver_key(version)
        return lower <= version_key < upper
    return version == required


def _fingerprint(value: dict[str, Any]) -> str:
    stable = dict(value)
    stable.pop("fingerprint", None)
    encoded = json.dumps(stable, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _read_documents(directory: Path) -> Iterable[tuple[Path, dict[str, Any]]]:
    if not directory.is_dir():
        raise RegistryValidationError(f"Registry source directory is missing: {directory}")
    for path in sorted(directory.rglob("*.json")):
        if "__pycache__" in path.parts:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise RegistryValidationError(f"Invalid JSON in {path}: {error.msg}") from error
        if not isinstance(value, dict):
            raise RegistryValidationError(f"Registry document must be an object: {path}")
        yield path, value


def _require_fields(value: dict[str, Any], fields: tuple[str, ...], label: str) -> None:
    missing = [field for field in fields if field not in value]
    if missing:
        raise RegistryValidationError(f"{label} is missing required fields: {', '.join(missing)}")


def _require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryValidationError(f"{label} must be a non-empty string")
    return value


@dataclass(frozen=True)
class CapabilitySpec:
    data: dict[str, Any]
    locator: Path

    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def version(self) -> str:
        return self.data["version"]


@dataclass(frozen=True)
class ScenarioPack:
    data: dict[str, Any]
    locator: Path

    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def version(self) -> str:
        return self.data["version"]


def validate_capability(value: dict[str, Any]) -> None:
    _require_fields(value, CAPABILITY_FIELDS, "CapabilitySpec")
    _require_id(value["id"], "CapabilitySpec.id")
    if not isinstance(value["name"], str) or not SEMVER.match(value["version"]):
        raise RegistryValidationError("CapabilitySpec requires a name and semantic version")
    if value["status"] not in {"active", "unavailable", "deprecated", "shadowed"}:
        raise RegistryValidationError("CapabilitySpec.status is invalid")
    if not isinstance(value["source"], dict) or not _require_id(value["source"].get("type"), "source.type"):
        raise RegistryValidationError("CapabilitySpec.source must identify a source")
    if not _require_id(value["source"].get("locator"), "source.locator"):
        raise RegistryValidationError("CapabilitySpec.source.locator is required")
    for field in ("domains", "triggers", "exclusions", "resourcePatterns", "inputs", "outputs", "operations"):
        if not isinstance(value[field], list):
            raise RegistryValidationError(f"CapabilitySpec.{field} must be an array")
    for field in ("dependencies", "verification", "routing"):
        if not isinstance(value[field], dict):
            raise RegistryValidationError(f"CapabilitySpec.{field} must be an object")
    expected = _fingerprint(value)
    if value["fingerprint"] != expected:
        raise RegistryValidationError(f"CapabilitySpec fingerprint mismatch: {value['id']}")


def validate_scenario_pack(value: dict[str, Any], root: Path) -> None:
    _require_fields(value, PACK_FIELDS, "ScenarioPack")
    _require_id(value["id"], "ScenarioPack.id")
    if not SEMVER.match(value["version"]):
        raise RegistryValidationError("ScenarioPack.version must be semantic")
    if not isinstance(value["match"], dict) or not isinstance(value["blueprintDefaults"], dict):
        raise RegistryValidationError("ScenarioPack match and blueprintDefaults must be objects")
    graph = value["graphTemplate"]
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
        raise RegistryValidationError("ScenarioPack.graphTemplate requires nodes and edges arrays")
    ids = [node.get("id") for node in graph["nodes"] if isinstance(node, dict)]
    if len(ids) != len(graph["nodes"]) or len(set(ids)) != len(ids) or any(not isinstance(item, str) for item in ids):
        raise RegistryValidationError("ScenarioPack graph nodes require unique IDs")
    for field in ("capabilityRequirements", "verifierRequirements", "goldenFixtures"):
        if not isinstance(value[field], list) or not all(isinstance(item, str) and item for item in value[field]):
            raise RegistryValidationError(f"ScenarioPack.{field} must be an array of IDs")
    if not isinstance(value["acceptanceCases"], list) or not all(isinstance(item, dict) and item.get("id") for item in value["acceptanceCases"]):
        raise RegistryValidationError("ScenarioPack acceptanceCases require stable IDs")
    if value["fingerprint"] != _fingerprint(value):
        raise RegistryValidationError(f"ScenarioPack fingerprint mismatch: {value['id']}")
    for fixture in value["goldenFixtures"]:
        resolved = (root / fixture).resolve()
        if root.resolve() not in resolved.parents or not resolved.is_file():
            raise RegistryValidationError(f"ScenarioPack fixture is absent or outside registry: {fixture}")


class CapabilityRegistry:
    def __init__(self, root: Path, capabilities: list[CapabilitySpec], packs: list[ScenarioPack]) -> None:
        self.root = root
        self.capability_versions = list(capabilities)
        self.capabilities = {
            capability_id: self.capability_load(capability_id)
            for capability_id in {item.id for item in capabilities}
        }
        self.scenario_packs = packs

    def capability_load(self, capability_id: str, version_constraint: str | None = None) -> CapabilitySpec:
        matches = [
            capability for capability in self.capability_versions
            if capability.id == capability_id and _satisfies(capability.version, version_constraint)
        ]
        if not matches:
            raise RegistryValidationError(f"No version of capability {capability_id!r} satisfies {version_constraint!r}")
        active = [capability for capability in matches if capability.data["status"] == "active"]
        return max(active or matches, key=lambda capability: _semver_key(capability.version))

    def scenario_load(
        self,
        pack_id: str,
        version_constraint: str | None = None,
        task_blueprint_version: str | None = None,
    ) -> ScenarioPack:
        matches = [
            pack for pack in self.scenario_packs
            if pack.id == pack_id and _satisfies(pack.version, version_constraint)
        ]
        if not matches:
            raise RegistryValidationError(f"No scenario pack exists for {pack_id!r}")
        if task_blueprint_version:
            matches = [
                pack for pack in matches
                if _satisfies(task_blueprint_version, pack.data["compatibility"].get("taskBlueprint"))
            ]
        if not matches:
            raise RegistryValidationError(f"No version of {pack_id!r} satisfies {version_constraint!r}")
        return max(matches, key=lambda pack: _semver_key(pack.version))

    def scenario_discover(self) -> list[ScenarioPack]:
        return list(self.scenario_packs)


def load_registry(root: Path | str | None = None) -> CapabilityRegistry:
    """Load canonical source data under registry/capabilities and scenario_packs only."""
    registry_root = Path(root).resolve() if root else REGISTRY_ROOT
    capability_dir = registry_root / "capabilities"
    scenario_dir = registry_root.parent / "scenario_packs"
    capabilities: list[CapabilitySpec] = []
    for locator, value in _read_documents(capability_dir):
        validate_capability(value)
        capabilities.append(CapabilitySpec(value, locator))
    packs: list[ScenarioPack] = []
    for locator, value in _read_documents(scenario_dir):
        validate_scenario_pack(value, registry_root)
        packs.append(ScenarioPack(value, locator))
    return CapabilityRegistry(registry_root, capabilities, packs)
