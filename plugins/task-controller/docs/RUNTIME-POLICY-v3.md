# KY-TASK Runtime Policy v3

## Open-source default

This installation uses visible native Codex Session tasks for every distributed
lane:

```json
{
  "runtimeSelectionPolicy": "native_session_required",
  "nativeThreadUserApproved": false,
  "maxParallelWorkers": 4,
  "projectAffinityPolicy": "inherit_or_resolve_required",
  "projectlessUserApproved": false
}
```

The open-source distribution has no standing approval. After the user approves
distributed execution for the current task, the controller records
`executionPolicy.nativeThreadUserApproved: true`. If native thread creation or
messaging is unavailable, execution blocks. Managed subagents and sequential
lanes require an explicit per-task override to `lane_lifecycle`; they are not
automatic fallbacks.

## Strict project affinity

Before distributed initialization, the controller calls `list_projects` and
locks one saved project in `targetProjectId`. It inherits the controller's
project when available; otherwise it resolves the deepest unique saved-project
path match from the effective workspace, source materials, or durable target.
Ambiguous or missing matches block dispatch and require user selection.

Every `create_thread` call uses a project target with that id and either a
`local` or project `worktree` environment. After creation, the controller
verifies the worker thread reports the same project id. Worker registration
stores `projectId` and `projectEnvironment` and rejects missing or mismatched
values.

Projectless creation requires both a task-scoped
`projectAffinityPolicy: allow_projectless` override and explicit
`projectlessUserApproved: true`. It is never an automatic fallback.

## Lifecycle is separate from runtime visibility

- `ephemeral + packet_only`: one bounded Session worker with a narrow packet and
  one callback.
- `persistent + checkpoint_delta`: a resumable Session workbench that receives
  controlled checkpoint deltas across controller turns.

Both use `native_thread_lane` under the Session-first default. Lifecycle controls
context retention, not whether the worker appears in the sidebar.

## Dependency-aware concurrency

Every new lane declares `dependsOn`:

```json
[
  {"name": "research-a", "dependsOn": []},
  {"name": "research-b", "dependsOn": []},
  {"name": "synthesis", "dependsOn": ["research-a", "research-b"]}
]
```

`task_controller_ready_lanes` returns the current dependency frontier, bounded
by `maxParallelWorkers`. The controller creates every Session in that frontier
before waiting. As workers finish, it records callbacks and refills open slots.

Missing `dependsOn` preserves the old ordered-lane chain for legacy states.
New plans must not rely on list order as an implicit dependency graph.

## Capability-based runtime selection

Python state enforcement and the MCP schema now share
`config/worker-runtime-profiles.json` as the checked-in source of truth for
independent worker runtimes. The state machine asks whether a profile is
independent, user-visible, project-capable, persistent-capable, approved, and
callback-compatible instead of selecting by runtime-name branches.

This abstraction does not loosen the policy above. Under
`native_session_required`, `managed_agent_worker` fails the user-visible and
project-scope requirements, so it cannot be selected or registered. See
`WORKER-RUNTIME-PROFILES-v1.md` for the profile contract and compatibility
boundary.

## Write safety

- Independent read, research, analysis, and design lanes may run concurrently.
- Two lanes that write the same durable target must be dependency-serialized.
- A review lane depends on every writer it must cover and uses a distinct
  Session identity.
- Concurrency never relaxes permits, callbacks, semantic checks, or final gates.

## Compatibility override

For a task that explicitly needs managed subagents, set:

```json
{
  "runtimeSelectionPolicy": "lane_lifecycle",
  "eligibleRuntimes": ["managed_agent_worker", "native_thread_lane"]
}
```

This override is task-scoped and must be visible in the locked execution
policy.

For an explicitly approved projectless task, add:

```json
{
  "projectAffinityPolicy": "allow_projectless",
  "projectlessUserApproved": true
}
```
