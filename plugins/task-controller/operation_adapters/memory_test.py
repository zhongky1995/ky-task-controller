"""In-memory adapter intended only for operation-dispatcher tests."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


class MemoryTestAdapter:
    adapter_id = "memory-test"
    fingerprint = "memory-test-adapter-v1"

    def __init__(self, *, fail_execute: bool = False, readback_mode: str = "match") -> None:
        self.fail_execute = fail_execute
        self.readback_mode = readback_mode
        self.calls = 0
        self.readback_calls = 0
        self.version = 0
        self.value: Any = None

    def execute(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.calls += 1
        if self.fail_execute:
            raise RuntimeError("simulated adapter failure")
        before = f"v{self.version}"
        self.value = deepcopy(dict(payload))
        self.version += 1
        return {"beforeVersion": before, "afterVersion": f"v{self.version}", "value": deepcopy(self.value)}

    def readback(self, spec: Mapping[str, Any], result: Any) -> dict[str, Any] | None:
        self.readback_calls += 1
        if self.readback_mode == "missing":
            return None
        if self.readback_mode == "inconsistent":
            return {"consistent": False, "beforeVersion": result.get("beforeVersion"), "afterVersion": result.get("afterVersion")}
        if result is None:
            return {"consistent": True, "beforeVersion": f"v{self.version}", "afterVersion": f"v{self.version}", "value": deepcopy(self.value)}
        return {"consistent": True, "beforeVersion": result["beforeVersion"], "afterVersion": result["afterVersion"], "value": deepcopy(self.value)}
