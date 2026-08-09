# KY-TASK Runtime Policy v2

> Historical policy retained for migration reference. The active distribution
> policy is `RUNTIME-POLICY-v3.md`.

## Decision

KY-TASK controls delivery correctness. It does not maximize the number of
Sessions.

Professional lanes, write boundaries, and independent review are decided
before runtime selection. Runtime selection then answers one narrower question:
does this lane need a bounded controller-managed worker or a persistent
user-visible workbench?

## Execution modes

- `direct`: one small bounded task in the controller.
- `sequential_lanes`: named controller checkpoints used only when independent
  worker execution is not required or cannot be used with a recorded reason.
- `distributed`: one or more lanes use real independent workers.
- `multi_session`: legacy wire alias for `distributed`; accepted for existing
  state and integrations, but not recommended for new plans.

Distributed execution does not imply native Codex Sessions.

## Lane runtime fields

```json
{
  "workerLifecycle": "ephemeral",
  "contextPolicy": "packet_only",
  "runtimePreference": "auto"
}
```

### Ephemeral lane

- One bounded input and output contract.
- One callback to the controller.
- No direct user conversation is required.
- Default context is only the lane packet and declared upstream artifacts.
- `auto` prefers `managed_agent_worker`.

This is the default for evidence, model, calculation, implementation, readback,
and independent-review lanes.

### Persistent lane

- The lane is an ongoing professional workbench across controller turns.
- It may need direct user intervention or independent resumption.
- It uses `contextPolicy: checkpoint_delta`.
- It requires `native_thread_lane`.
- It requires `executionPolicy.nativeThreadUserApproved: true`.

Importance, write risk, or review independence alone do not justify persistence.
Those concerns are governed by KY-TASK state, permits, callbacks, and gates.

## Compatibility

- `schemaVersion` remains `2`.
- Existing states without lifecycle fields use:
  - `workerLifecycle: ephemeral`
  - `contextPolicy: packet_only`
  - `runtimePreference: auto`
- Existing states without `nativeThreadUserApproved` may continue their already
  initialized native-thread flow.
- New states default `nativeThreadUserApproved` to `false`.
- TaskBlueprint, SolutionGraph, WorkerPacket, and their digests are unchanged.

## Examples

### Default controlled delivery

```json
{
  "laneDefinitions": [
    {
      "name": "implementation",
      "kind": "implementation",
      "workerRequired": true,
      "writeBoundary": "approved-target",
      "workerLifecycle": "ephemeral",
      "contextPolicy": "packet_only",
      "runtimePreference": "auto"
    },
    {
      "name": "review",
      "kind": "review",
      "workerRequired": true,
      "writeBoundary": "review-only",
      "workerLifecycle": "ephemeral",
      "contextPolicy": "packet_only",
      "runtimePreference": "auto"
    }
  ],
  "executionPolicy": {
    "splitRequirement": "mandatory",
    "mode": "distributed",
    "eligibleRuntimes": ["managed_agent_worker"],
    "requiredWorkerLanes": ["implementation", "review"],
    "independentReviewRequired": true,
    "nativeThreadUserApproved": false
  }
}
```

### Approved persistent strategy workbench

```json
{
  "laneDefinitions": [
    {
      "name": "strategy-workbench",
      "workerRequired": true,
      "workerLifecycle": "persistent",
      "contextPolicy": "checkpoint_delta",
      "runtimePreference": "native_thread_lane"
    }
  ],
  "executionPolicy": {
    "splitRequirement": "mandatory",
    "mode": "distributed",
    "eligibleRuntimes": ["native_thread_lane"],
    "requiredWorkerLanes": ["strategy-workbench"],
    "nativeThreadUserApproved": true
  }
}
```
