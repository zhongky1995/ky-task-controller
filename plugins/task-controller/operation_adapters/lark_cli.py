"""Policy-bound adapter for a small allowlist of Lark CLI operations.

Callers provide structured descriptors. They never provide argv, a command
prefix, a shell, an environment, a working directory, or an executable.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlparse


class LarkCliAdapterError(RuntimeError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LarkCliAdapterError(f"{field} must be a non-empty string")
    return value.strip()


def _flag(name: str) -> str:
    return "--" + re.sub(r"(?<!^)(?=[A-Z])", "-", name).replace("_", "-").lower()


WRITE_CATALOG: dict[str, dict[str, Any]] = {
    "docs.update": {
        "prefix": ["docs", "+update"], "kind": "docx", "actions": {"update"},
        "resource": {"doc"}, "requiredResource": {"doc"},
        "input": {"command", "content", "docFormat", "pattern", "blockId", "srcBlockIds", "revisionId"},
        "requiredInput": {"command"},
        "allowedInputValues": {
            "command": {"append", "str_replace", "block_insert_after", "block_replace", "block_copy_insert_after", "block_move_after"},
            "docFormat": {"xml", "markdown"},
        },
    },
    "docs.replace": {
        "prefix": ["docs", "+update"], "kind": "docx", "actions": {"replace", "overwrite"},
        "resource": {"doc"}, "requiredResource": {"doc"},
        "input": {"content", "docFormat", "revisionId"}, "requiredInput": {"content"},
        "fixed": {"command": "overwrite"},
    },
    "base.record.upsert": {
        "prefix": ["base", "+record-upsert"], "kind": "base", "actions": {"create", "update"},
        "resource": {"baseToken", "tableId", "recordId"}, "requiredResource": {"baseToken", "tableId"},
        "input": {"fields"}, "requiredInput": {"fields"}, "jsonInput": "fields",
    },
    "base.record.batch-create": {
        "prefix": ["base", "+record-batch-create"], "kind": "base", "actions": {"create"},
        "resource": {"baseToken", "tableId"}, "requiredResource": {"baseToken", "tableId"},
        "input": {"data"}, "requiredInput": {"data"}, "jsonInput": "data",
    },
    "base.record.batch-update": {
        "prefix": ["base", "+record-batch-update"], "kind": "base", "actions": {"update"},
        "resource": {"baseToken", "tableId"}, "requiredResource": {"baseToken", "tableId"},
        "input": {"data"}, "requiredInput": {"data"}, "jsonInput": "data",
    },
    "base.field.create": {
        "prefix": ["base", "+field-create"], "kind": "base", "actions": {"create"},
        "resource": {"baseToken", "tableId"}, "requiredResource": {"baseToken", "tableId"},
        "input": {"field"}, "requiredInput": {"field"}, "jsonInput": "field",
    },
    "base.field.update": {
        "prefix": ["base", "+field-update"], "kind": "base", "actions": {"update"},
        "resource": {"baseToken", "tableId", "fieldId"}, "requiredResource": {"baseToken", "tableId", "fieldId"},
        "input": {"field"}, "requiredInput": {"field"}, "jsonInput": "field",
    },
    "base.table.create": {
        "prefix": ["base", "+table-create"], "kind": "base", "actions": {"create"},
        "resource": {"baseToken"}, "requiredResource": {"baseToken"},
        "input": {"name", "fields", "views"}, "requiredInput": {"name"},
    },
    "base.table.update": {
        "prefix": ["base", "+table-update"], "kind": "base", "actions": {"update"},
        "resource": {"baseToken", "tableId"}, "requiredResource": {"baseToken", "tableId"},
        "input": {"name"}, "requiredInput": {"name"},
    },
    "base.dashboard.create": {
        "prefix": ["base", "+dashboard-create"], "kind": "base", "actions": {"create"},
        "resource": {"baseToken"}, "requiredResource": {"baseToken"},
        "input": {"name"}, "requiredInput": {"name"},
    },
    "base.dashboard.update": {
        "prefix": ["base", "+dashboard-update"], "kind": "base", "actions": {"update"},
        "resource": {"baseToken", "dashboardId"}, "requiredResource": {"baseToken", "dashboardId"},
        "input": {"name"}, "requiredInput": {"name"},
    },
    "base.dashboard-block.create": {
        "prefix": ["base", "+dashboard-block-create"], "kind": "base", "actions": {"create"},
        "resource": {"baseToken", "dashboardId"}, "requiredResource": {"baseToken", "dashboardId"},
        "input": {"name", "type", "dataConfig", "userIdType"},
        "requiredInput": {"name", "type", "dataConfig"},
    },
    "base.dashboard-block.update": {
        "prefix": ["base", "+dashboard-block-update"], "kind": "base", "actions": {"update"},
        "resource": {"baseToken", "dashboardId", "blockId"},
        "requiredResource": {"baseToken", "dashboardId", "blockId"},
        "input": {"name", "type", "dataConfig", "userIdType"}, "requiredInput": set(),
    },
}

READ_CATALOG: dict[str, dict[str, Any]] = {
    "docs.fetch": {"prefix": ["docs", "+fetch"], "kind": "docx", "resource": {"doc"}, "requiredResource": {"doc"}, "input": {"scope", "detail"}},
    "base.record.get": {"prefix": ["base", "+record-get"], "kind": "base", "resource": {"baseToken", "tableId", "recordId"}, "requiredResource": {"baseToken", "tableId", "recordId"}, "input": set()},
    "base.field.get": {"prefix": ["base", "+field-get"], "kind": "base", "resource": {"baseToken", "tableId", "fieldId"}, "requiredResource": {"baseToken", "tableId", "fieldId"}, "input": set()},
    "base.field.list": {"prefix": ["base", "+field-list"], "kind": "base", "resource": {"baseToken", "tableId"}, "requiredResource": {"baseToken", "tableId"}, "input": set()},
    "base.table.get": {"prefix": ["base", "+table-get"], "kind": "base", "resource": {"baseToken", "tableId"}, "requiredResource": {"baseToken", "tableId"}, "input": set()},
    "base.table.list": {"prefix": ["base", "+table-list"], "kind": "base", "resource": {"baseToken"}, "requiredResource": {"baseToken"}, "input": set()},
    "base.dashboard.get": {"prefix": ["base", "+dashboard-get"], "kind": "base", "resource": {"baseToken", "dashboardId"}, "requiredResource": {"baseToken", "dashboardId"}, "input": set()},
    "base.dashboard.list": {"prefix": ["base", "+dashboard-list"], "kind": "base", "resource": {"baseToken"}, "requiredResource": {"baseToken"}, "input": set()},
    "base.dashboard-block.get": {"prefix": ["base", "+dashboard-block-get"], "kind": "base", "resource": {"baseToken", "dashboardId", "blockId"}, "requiredResource": {"baseToken", "dashboardId", "blockId"}, "input": set()},
    "base.dashboard-block.list": {"prefix": ["base", "+dashboard-block-list"], "kind": "base", "resource": {"baseToken", "dashboardId"}, "requiredResource": {"baseToken", "dashboardId"}, "input": set()},
}

RESOURCE_FLAGS = {
    "doc": "--doc", "baseToken": "--base-token", "tableId": "--table-id",
    "recordId": "--record-id", "fieldId": "--field-id", "dashboardId": "--dashboard-id",
    "blockId": "--block-id",
}


def _locator_identity(locator: str) -> dict[str, str]:
    locator = _nonempty(locator, "targetLocator")
    if locator.startswith("lark-docx://"):
        return {"kind": "docx", "doc": _nonempty(locator[len("lark-docx://"):].split("/", 1)[0], "target doc token")}
    if locator.startswith("lark-base://"):
        rest = locator[len("lark-base://"):].strip("/")
        parts = rest.split("/") if rest else []
        if not parts:
            raise LarkCliAdapterError("canonical Base locator requires a base token")
        result = {"kind": "base", "baseToken": parts[0]}
        aliases = {"table": "tableId", "record": "recordId", "field": "fieldId", "dashboard": "dashboardId", "block": "blockId"}
        tail = parts[1:]
        if len(tail) % 2:
            raise LarkCliAdapterError("canonical Base locator segments must be key/value pairs")
        for index in range(0, len(tail), 2):
            if tail[index] not in aliases or not tail[index + 1]:
                raise LarkCliAdapterError("canonical Base locator contains an unsupported resource segment")
            result[aliases[tail[index]]] = tail[index + 1]
        return result
    parsed = urlparse(locator)
    parts = [part for part in parsed.path.split("/") if part]
    if "docx" in parts:
        index = parts.index("docx")
        if index + 1 >= len(parts):
            raise LarkCliAdapterError("document URL is missing its token")
        return {"kind": "docx", "doc": parts[index + 1]}
    if "base" in parts:
        index = parts.index("base")
        if index + 1 >= len(parts):
            raise LarkCliAdapterError("Base URL is missing its token")
        result = {"kind": "base", "baseToken": parts[index + 1]}
        query = parse_qs(parsed.query)
        if query.get("table"):
            result["tableId"] = query["table"][0]
        return result
    raise LarkCliAdapterError("targetLocator must be a canonical Lark locator or a direct docx/base URL")


def _validate_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise LarkCliAdapterError(f"{field} must be an object")
    return dict(value)


def _compile_descriptor(descriptor: Mapping[str, Any], catalog: Mapping[str, dict[str, Any]], *, target_locator: str, action: str | None = None, operation_id: str | None = None) -> list[str]:
    raw = _validate_object(descriptor, "operation descriptor")
    if set(raw) != {"operation", "identity", "resource", "input"}:
        raise LarkCliAdapterError("operation descriptor requires exactly operation, identity, resource, input")
    operation = _nonempty(raw["operation"], "descriptor.operation")
    if operation not in catalog:
        raise LarkCliAdapterError(f"operation is not allowlisted: {operation}")
    if operation_id is not None and operation != operation_id:
        raise LarkCliAdapterError("descriptor.operation does not match permit operationId")
    identity = _nonempty(raw["identity"], "descriptor.identity")
    if identity not in {"user", "bot"}:
        raise LarkCliAdapterError("descriptor.identity must be user or bot")
    resource = _validate_object(raw["resource"], "descriptor.resource")
    inputs = _validate_object(raw["input"], "descriptor.input")
    spec = catalog[operation]
    if action is not None:
        effective_actions = set(spec.get("actions", set()))
        if operation == "base.record.upsert":
            effective_actions = {"update"} if resource.get("recordId") else {"create"}
        if action not in effective_actions:
            raise LarkCliAdapterError("descriptor operation does not match permit action")
    unknown_resource = set(resource) - set(spec["resource"])
    unknown_input = set(inputs) - set(spec["input"])
    if unknown_resource or unknown_input:
        raise LarkCliAdapterError("descriptor contains unsupported fields: " + ", ".join(sorted(unknown_resource | unknown_input)))
    missing_resource = set(spec["requiredResource"]) - set(resource)
    missing_input = set(spec.get("requiredInput", set())) - set(inputs)
    if missing_resource or missing_input:
        raise LarkCliAdapterError("descriptor is missing required fields: " + ", ".join(sorted(missing_resource | missing_input)))
    for key, allowed_values in spec.get("allowedInputValues", {}).items():
        if key in inputs and inputs[key] not in allowed_values:
            raise LarkCliAdapterError(f"descriptor.input.{key} is not allowlisted")
    locator = _locator_identity(target_locator)
    if locator["kind"] != spec["kind"]:
        raise LarkCliAdapterError("descriptor resource kind does not match targetLocator")
    required_scope = set(spec["requiredResource"])
    if operation == "base.record.upsert" and resource.get("recordId"):
        required_scope.add("recordId")
    missing_locator_scope = required_scope - set(locator)
    if missing_locator_scope:
        raise LarkCliAdapterError(
            "targetLocator is not specific enough for this operation: "
            + ", ".join(sorted(missing_locator_scope))
        )
    for key, expected in locator.items():
        if key != "kind" and resource.get(key) != expected:
            raise LarkCliAdapterError(f"descriptor resource {key} does not match targetLocator")
    argv = [*spec["prefix"], "--as", identity, "--format", "json"]
    for key in sorted(resource):
        argv.extend([RESOURCE_FLAGS[key], _nonempty(resource[key], f"descriptor.resource.{key}")])
    merged_inputs = {**spec.get("fixed", {}), **inputs}
    json_input = spec.get("jsonInput")
    for key, value in merged_inputs.items():
        flag = "--json" if key == json_input else _flag(key)
        rendered = _canonical(value) if isinstance(value, (dict, list)) else str(value)
        argv.extend([flag, rendered])
    return argv


class LarkCliAdapter:
    adapter_id = "lark-cli"

    def __init__(self, *, operation_id: str | None = None, action: str | None = None, target_locator: str | None = None, binary_path: str | os.PathLike[str] | None = None, timeout: float = 30.0, runner: Callable[..., Any] | None = None) -> None:
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout must be positive")
        chosen = str(binary_path) if binary_path is not None else os.environ.get("LARK_CLI_PATH") or shutil.which("lark-cli")
        if not chosen:
            raise LarkCliAdapterError("lark CLI binary not found; set binary_path or LARK_CLI_PATH")
        self.binary_path = str(Path(chosen))
        self.timeout = float(timeout)
        self._runner = runner or subprocess.run
        self.operation_id = operation_id
        self.action = action
        self.target_locator = target_locator
        self.fingerprint = sha256(_canonical({"adapterId": self.adapter_id, "binaryPath": self.binary_path, "operationId": operation_id, "action": action, "targetLocator": target_locator}).encode("utf-8")).hexdigest()

    def validate_execute_descriptor(self, payload: Mapping[str, Any]) -> list[str]:
        if not self.operation_id or not self.action or not self.target_locator:
            raise LarkCliAdapterError("production execution requires permit-bound operationId, action, and targetLocator")
        return _compile_descriptor(payload, WRITE_CATALOG, target_locator=self.target_locator, action=self.action, operation_id=self.operation_id)

    def validate_readback_descriptor(self, spec: Mapping[str, Any]) -> list[str]:
        if not self.target_locator:
            raise LarkCliAdapterError("readback requires a permit-bound targetLocator")
        return _compile_descriptor(spec, READ_CATALOG, target_locator=self.target_locator)

    def _run(self, argv: list[str]) -> dict[str, Any]:
        command = [self.binary_path, *argv]
        try:
            completed = self._runner(command, input=None, text=True, capture_output=True, timeout=self.timeout, check=False, shell=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise LarkCliAdapterError(f"lark CLI invocation failed: {error}") from error
        returncode = getattr(completed, "returncode", None)
        stdout = getattr(completed, "stdout", "")
        stderr = getattr(completed, "stderr", "")
        if returncode != 0:
            raise LarkCliAdapterError(f"lark CLI exited with {returncode}: {stderr}")
        try:
            body: Any = json.loads(stdout) if stdout else None
        except json.JSONDecodeError:
            body = stdout
        return {"args": argv, "stdout": stdout, "stderr": stderr, "body": body}

    def execute(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._run(self.validate_execute_descriptor(payload))

    def readback(self, spec: Mapping[str, Any], result: Any) -> dict[str, Any]:
        output = self._run(self.validate_readback_descriptor(spec))
        output["consistent"] = True
        return output
