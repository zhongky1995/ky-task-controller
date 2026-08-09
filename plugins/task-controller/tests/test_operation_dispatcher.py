from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import subprocess
import unittest
from typing import Any

from operation_adapters import LarkCliAdapter, LarkCliAdapterError, MemoryTestAdapter
from runtime.operation_dispatcher import (
    Dispatcher,
    OperationPermitStore,
    PermitStateError,
    PermitValidationError,
    issue_permit,
)


NOW = "2026-07-13T00:00:00Z"
LATER = "2026-07-13T01:00:00Z"
EXPIRED = "2026-07-12T23:59:59Z"


def permit(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "permitId": "permit-1",
        "planIdentity": {"id": "plan-1", "digest": "a" * 64},
        "graphIdentity": {"id": "graph-1", "digest": "b" * 64},
        "packetIdentity": {"id": "packet-1", "digest": "c" * 64},
        "blueprintIdentity": {"id": "blueprint-1", "digest": "d" * 64},
        "contractIdentity": {"id": "contract-1", "digest": "e" * 64},
        "workerId": "worker-1",
        "runtimeHandle": "runtime-1",
        "capabilityId": "capability-1",
        "operationId": "operation-1",
        "targetId": "target-1",
        "targetLocator": "/approved/target",
        "action": "update",
        "payload": {"nested": {"b": 2, "a": 1}, "value": "approved"},
        "restrictedFields": ["targetId"],
        "approvalRefs": ["approval-1"],
        "idempotencyKey": "write-1",
        "adapterId": "memory-test",
        "readbackSpec": {},
        "expiresAt": LATER,
    }
    data.update(overrides)
    return issue_permit(data, now=NOW)


class OperationDispatcherTests(unittest.TestCase):
    def test_payload_tampering_is_rejected(self) -> None:
        dispatcher = Dispatcher({"memory-test": MemoryTestAdapter()})
        issued = permit()
        with self.assertRaises(PermitValidationError):
            dispatcher.dispatch(issued, {"nested": {"a": 1, "b": 2}, "value": "tampered"}, now=NOW)

    def test_expired_permit_is_marked_and_never_executed(self) -> None:
        adapter = MemoryTestAdapter()
        dispatcher = Dispatcher({"memory-test": adapter})
        issued = permit(expiresAt="2026-07-13T00:00:01Z")
        with self.assertRaises(PermitStateError):
            dispatcher.dispatch(issued, now="2026-07-13T00:00:01Z")
        self.assertEqual(0, adapter.calls)
        self.assertEqual("expired", dispatcher.permits.get(issued["permitId"])["status"])

    def test_atomic_claim_allows_exactly_one_worker(self) -> None:
        store = OperationPermitStore()
        issued = store.issue(permit())

        def claim(worker: str) -> str:
            try:
                return store.transition(issued["permitId"], "claim", claim_id=worker, now=NOW)["claimId"]
            except PermitStateError:
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(claim, ["worker-a", "worker-b"]))
        self.assertEqual(1, sum(outcome != "rejected" for outcome in outcomes))
        self.assertEqual("claimed", store.get(issued["permitId"])["status"])

    def test_replay_returns_original_receipt_without_second_execution(self) -> None:
        adapter = MemoryTestAdapter()
        dispatcher = Dispatcher({"memory-test": adapter})
        issued = permit()
        first = dispatcher.dispatch(issued, now=NOW)
        replay = dispatcher.dispatch(issued, now=NOW)
        self.assertEqual(first, replay)
        self.assertEqual(1, adapter.calls)
        self.assertEqual(1, adapter.readback_calls)

    def test_missing_and_inconsistent_readback_require_reconciliation(self) -> None:
        for mode in ("missing", "inconsistent"):
            with self.subTest(mode=mode):
                adapter = MemoryTestAdapter(readback_mode=mode)
                dispatcher = Dispatcher({"memory-test": adapter})
                issued = permit(permitId=f"permit-{mode}", idempotencyKey=f"write-{mode}")
                receipt = dispatcher.dispatch(issued, now=NOW)
                self.assertEqual("reconcile_required", receipt["status"])
                self.assertIn("readback", receipt["reconcileReason"])
                self.assertEqual("reconcile_required", dispatcher.permits.get(issued["permitId"])["status"])

    def test_adapter_without_readback_requires_reconciliation(self) -> None:
        class ExecuteOnlyAdapter:
            adapter_id = "execute-only"

            def execute(self, payload: Any) -> dict[str, str]:
                return {"beforeVersion": "v0", "afterVersion": "v1"}

        issued = permit(permitId="permit-no-readback", idempotencyKey="write-no-readback", adapterId="execute-only")
        receipt = Dispatcher({"execute-only": ExecuteOnlyAdapter()}).dispatch(issued, now=NOW)
        self.assertEqual("reconcile_required", receipt["status"])
        self.assertIn("readback", receipt["reconcileReason"])

    def test_adapter_failure_requires_reconciliation(self) -> None:
        dispatcher = Dispatcher({"memory-test": MemoryTestAdapter(fail_execute=True)})
        issued = permit(permitId="permit-failure", idempotencyKey="write-failure")
        receipt = dispatcher.dispatch(issued, now=NOW)
        self.assertEqual("reconcile_required", receipt["status"])
        self.assertIn("simulated adapter failure", receipt["reconcileReason"])

    def test_receipt_is_deterministically_bound_to_permit_and_payload(self) -> None:
        first = Dispatcher({"memory-test": MemoryTestAdapter()}).dispatch(permit(), now=NOW)
        second = Dispatcher({"memory-test": MemoryTestAdapter()}).dispatch(permit(), now=NOW)
        self.assertEqual(first["receiptId"], second["receiptId"])
        self.assertEqual(first["payloadFingerprint"], second["payloadFingerprint"])
        self.assertEqual("permit-1", first["permitId"])

    def test_lark_cli_compiles_typed_operation_and_separate_readback(self) -> None:
        calls: list[tuple[list[str], dict[str, Any]]] = []

        def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, stdout='{"ok": true}', stderr="")

        adapter = LarkCliAdapter(
            binary_path="/safe/lark-cli", timeout=12, runner=runner,
            operation_id="base.record.upsert", action="update",
            target_locator="lark-base://app-1/table/tbl-1/record/rec-1",
        )
        result = adapter.execute({
            "operation": "base.record.upsert", "identity": "user",
            "resource": {"baseToken": "app-1", "tableId": "tbl-1", "recordId": "rec-1"},
            "input": {"fields": {"Name": "safe"}},
        })
        observation = adapter.readback({
            "operation": "base.record.get", "identity": "user",
            "resource": {"baseToken": "app-1", "tableId": "tbl-1", "recordId": "rec-1"},
            "input": {},
        }, result)
        self.assertTrue(observation["consistent"])
        self.assertEqual(["/safe/lark-cli", "base", "+record-upsert", "--as", "user", "--format", "json", "--base-token", "app-1", "--record-id", "rec-1", "--table-id", "tbl-1", "--json", '{"Name":"safe"}'], calls[0][0])
        self.assertEqual(["/safe/lark-cli", "base", "+record-get", "--as", "user", "--format", "json", "--base-token", "app-1", "--record-id", "rec-1", "--table-id", "tbl-1"], calls[1][0])
        self.assertFalse(calls[0][1]["shell"])
        self.assertNotIn("env", calls[0][1])
        self.assertEqual(12.0, calls[0][1]["timeout"])

    def test_lark_cli_rejects_shell_and_environment_injection(self) -> None:
        calls: list[Any] = []

        def runner(*args: Any, **kwargs: Any) -> Any:
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args[0], 0, stdout="{}", stderr="")

        adapter = LarkCliAdapter(
            binary_path="/safe/lark-cli", runner=runner,
            operation_id="docs.update", action="update", target_locator="lark-docx://doc-1",
        )
        for unsafe in (
            {"args": ["drive", "file", "delete"], "shell": True},
            {"operation": "docs.update", "identity": "user", "resource": {"doc": "doc-1"}, "input": {"command": "append"}, "env": {"TOKEN": "x"}},
            {"operation": "docs.delete", "identity": "user", "resource": {"doc": "doc-1"}, "input": {}},
            {"operation": "docs.update", "identity": "user", "resource": {"doc": "other"}, "input": {"command": "append", "content": "x"}},
        ):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(LarkCliAdapterError):
                    adapter.execute(unsafe)
        with self.assertRaises(LarkCliAdapterError):
            adapter.readback({}, {})
        self.assertEqual([], calls)

    def test_lark_cli_refuses_destructive_command_hidden_in_update(self) -> None:
        adapter = LarkCliAdapter(
            binary_path="/safe/lark-cli", runner=lambda *args, **kwargs: None,
            operation_id="docs.update", action="update", target_locator="lark-docx://doc-1",
        )
        with self.assertRaises(LarkCliAdapterError):
            adapter.execute({
                "operation": "docs.update", "identity": "user",
                "resource": {"doc": "doc-1"},
                "input": {"command": "block_delete", "blockId": "block-1"},
            })

    def test_lark_base_operation_requires_resource_specific_target(self) -> None:
        adapter = LarkCliAdapter(
            binary_path="/safe/lark-cli", runner=lambda *args, **kwargs: None,
            operation_id="base.record.upsert", action="create",
            target_locator="lark-base://app-1",
        )
        with self.assertRaisesRegex(LarkCliAdapterError, "not specific enough"):
            adapter.execute({
                "operation": "base.record.upsert", "identity": "user",
                "resource": {"baseToken": "app-1", "tableId": "unapproved-table"},
                "input": {"fields": {"Name": "unsafe"}},
            })


if __name__ == "__main__":
    unittest.main()
