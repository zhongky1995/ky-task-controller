# Changelog

## 0.6.0+codex.20260827

- Added first-class `OrchestrationPlan 1.0` between task decomposition and worker runtime selection.
- Added strict semantic ownership, contribution/authority roles, explicit parallel waves, justified serial edges, join points, artifact producer/consumer contracts, and shared-writer validation.
- Blocked premature QA/review that runs before the decision, sample, or artifact it judges.
- Added handoff-loss checks so high-cohesion design and production stay in one lane unless a concrete artifact contract preserves the handoff.
- Added lane-level capability matching from each job's purpose, inputs, outputs, and acceptance role instead of copying a global domain match across workers.
- Added `task_controller_plan_orchestration`, persisted orchestration state/digests, and wave details in `task_controller_ready_lanes`.
- Added a generic strict no-scenario-pack path; the controller no longer defaults new composite work to a fixed five-lane template.
- Preserved existing schema-v2 states and unversioned legacy lane callers through visible `legacy-order` compatibility.

## 0.5.0+codex.20260814

- Added explicit decision authority (`locked`, `agent_may_decide`, and
  `propose_then_confirm`) with fail-closed approval enforcement for high-impact
  commercial changes.
- Added the `client-pricing` scenario: evidence normalization, pricing model,
  independent commercial review, fingerprint-bound user approval, workbook
  architecture, implementation, and final review.
- Added evidence-backed acceptance cases for independent charge-item value,
  duplicate charges, KPI causality, budget filler lines, and client-purchasable
  module hierarchy.
- Added `task_controller_classify_feedback` and idempotent
  `task_controller_ingest_feedback`; contract corrections now stale approvals,
  invalidate finalization, and block execution until revision.
- Added task-type-specific scenario routing without changing generic internal
  pricing analysis or the Session-first runtime policy.

## 0.4.0+codex.20260811

- Added a fail-closed, versioned worker runtime profile registry shared by the
  Python controller and MCP schema.
- Replaced central runtime-name selection branches with capability requirements
  for independence, visibility, project scope, persistence, approval, identity,
  and callback behavior.
- Bound registered workers to the selected runtime profile version and
  fingerprint for audit and recovery.
- Added a second-adapter contract test proving a project-capable runtime can be
  selected without adding a new core runtime branch.
- Preserved the Session-first open-source default, project affinity, explicit
  approval, four-worker concurrency cap, and no-silent-Sub-Agent fallback.

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
