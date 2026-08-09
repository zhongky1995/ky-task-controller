# Changelog

## 0.3.1+codex.20260808

- Added strict project affinity for native Codex worker Sessions.
- Required distributed controllers to resolve and lock a saved Codex
  `targetProjectId` before native dispatch.
- Added worker registration checks that reject missing or mismatched project
  identities under the Session-first policy.
- Added explicit, user-approved `allow_projectless` as the only projectless
  override; silent projectless Session creation is blocked.
- Documented deterministic project resolution, project-scoped `create_thread`
  targets, post-creation verification, and local/worktree project environments.

## 0.3.0+codex.20260808

- Added an auditable `native_session_required` policy with explicit user
  approval for visible KY-TASK worker Sessions.
- Added explicit lane `dependsOn` dependencies while preserving ordered-lane
  semantics for legacy states.
- Added `task_controller_ready_lanes` to return a bounded parallel dispatch
  frontier.
- Added `maxParallelWorkers` with a distribution default of four.
- Blocked managed-subagent registration under the Session-required policy.
- Updated controller and planner instructions to create the entire ready Session
  batch before waiting for results.

## 0.2.0+codex.20260723

- Reframed `multi_session` as the legacy wire alias of `distributed` worker
  execution.
- Added per-lane `workerLifecycle`, `contextPolicy`, `runtimePreference`, and
  computed `recommendedRuntime`.
- Made `ephemeral + packet_only + managed_agent_worker` the default.
- Restricted native Codex tasks to approved `persistent + checkpoint_delta`
  lanes through `executionPolicy.nativeThreadUserApproved`.
- Preserved schema-v2 compatibility and TaskBlueprint, SolutionGraph, and
  WorkerPacket digests.
- Added runtime-policy documentation and lifecycle/compatibility regression
  tests.
