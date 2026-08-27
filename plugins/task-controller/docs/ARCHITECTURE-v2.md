# KY-TASK v2 System Architecture

Status: living architecture; Blueprint/SolutionGraph/WorkerPacket/permit/verification and OrchestrationPlan slices are implemented
Scope: task judgment, solution design, capability routing, execution control, and outcome verification
Compatibility baseline: current `schemaVersion: 2`

## 0. Current State Versus Target State

This document is a target architecture and migration contract. It does not claim that the current implementation already provides blueprint compilation, capability routing, dispatcher-enforced external writes, or reproducible business verification.

| Area | Current implementation | Target architecture |
|---|---|---|
| task definition | human-readable Planner output plus manually created `contractSpec` | validated `TaskBlueprint` compiled from one diagnosis |
| decomposition and orchestration | `SolutionGraph` plus `OrchestrationPlan` with semantic ownership, waves, justified serial edges, join points, handoff checks, and legacy lane projection | versioned dependency DAG with richer cost/lease optimization |
| worker assignment | free-text task and prompt with contract hashes | immutable `WorkerPacket` compiled from the graph |
| write governance | callback receipt validation and operating discipline | controller-issued `OperationPermit` and dispatcher-only W3/W4 execution |
| verification | worker/reviewer check IDs with free-text evidence | artifact-bound, reproducible `VerificationResult` objects |
| routing | scenario-level registry routing plus lane-level exact/suggested capability routes | broader dynamic catalog with equivalent-capability proofs |

Until the relevant migration step ships, current limitations remain explicit and must not be presented as implemented guarantees.

## 1. Product Goal

KY-TASK should turn a user's request into a correct, executable, and verifiable solution path. It must do more than keep workers orderly.

The system succeeds when it can answer and enforce five questions:

1. What business outcome does the user actually need?
2. What final artifact will support that outcome in the real usage context?
3. What professional method and capabilities are required to produce it?
4. How should the work be decomposed, executed, and corrected?
5. What evidence proves that the final result is useful, not merely complete?

## 2. User Loop

```text
User request and referenced history
-> Task diagnosis
-> TaskBlueprint confirmation
-> SolutionGraph and capability routing
-> representative sample / user approval when needed
-> controlled domain execution
-> business verification and independent review
-> final delivery or scoped correction
```

Human involvement is mandatory when:

- the intended audience, final artifact, or business decision remains ambiguous;
- a representative sample determines the direction of a large production run;
- an external, destructive, or hard-to-reverse write is requested;
- authoritative sources conflict at the same priority;
- a business acceptance case cannot be verified by tools or independent review.

## 3. Non-goals

- The controller does not replace marketing, pricing, spreadsheet, document, deck, product, or Lark domain skills.
- The controller does not contain every provider implementation.
- The controller does not treat more workers as better decomposition.
- The controller does not accept worker self-attestation as sufficient business verification.
- The controller does not regenerate business intent independently at every layer.

## 4. Target System Layers

| Plane | Main components | Responsibility | Inputs | Outputs | Allowed dependencies | Must not own |
|---|---|---|---|---|---|---|
| Control Plane | Task Diagnoser, Blueprint Compiler, Solution Architect, Capability Router, policy rules | Interpret the request once, define the canonical task, choose methods and capabilities | user request, referenced tasks, source summary, capability registry | TaskBlueprint, SolutionGraph, routing decision, approval requirements | registry, scenario packs, policy configuration | domain artifact production, direct external writes |
| Runtime Plane | Controller Runtime, worker dispatcher, gate engine, verifier orchestration | Execute the approved graph, isolate writers, collect artifacts and verification | compiled graph, worker packets, approvals, runtime capability state | artifacts, callbacks, verification results, finalization decision | worker runtimes, tool adapters, state store | reinterpreting the task, inventing domain standards |
| Data / Memory Plane | blueprint store, decision ledger, artifact registry, evidence graph, execution state | Preserve truth, lineage, versions, decisions, corrections, and artifact identities | user decisions, source refs, worker outputs, readback receipts | immutable references, revision snapshots, traceability map | local durable state and approved external metadata | making routing or business judgments |
| Ops Plane | scenario evals, observability, release controls, cost and latency budgets | Detect regressions, explain failures, control rollout, and support recovery | traces, decisions, tool calls, evaluation results, release metadata | dashboards, alerts, feature flags, rollback decisions | test runners, package/release tooling | changing user artifacts or contract terms |

## 5. Canonical Request Lifecycle

1. **Intake and hydration**
   - Read the current user request, explicitly referenced tasks, and approved prior decisions.
   - Classify the interaction as discussion, planning, execution, correction, or continuation.
   - Record source availability and context budget.

2. **Task diagnosis**
   - Distinguish the surface request from the actual business objective.
   - Identify the audience, use context, decision/action supported, and unacceptable substitutes.
   - Produce intent anchors and blocking unknowns.

3. **Blueprint compilation**
   - Convert diagnosis into a structured `TaskBlueprint`.
   - Produce a traceability report showing how user statements map to blueprint fields.
   - High-risk tasks fail closed when required intent is unmapped.

4. **Solution design, orchestration, and routing**
   - Select a scenario pattern when one fits.
   - Build a dependency graph based on actual professional work, not generic lane names.
   - Compile one semantic owner, the primary path, parallel waves, justified serial edges, join points, and handoff-loss decisions.
   - Match capabilities against each lane's job/input/output/acceptance role before selecting worker runtime.
   - Resolve required abstract capabilities to currently available skills and tools.
   - Apply capacity, cost, permission, and write-risk checks.

5. **Alignment and approval**
   - For client-facing, large-batch, or previously failed work, create representative units.
   - Verify them against the original intent and domain standards.
   - Record user approval against the artifact fingerprint when required.

6. **Execution**
   - Generate immutable `WorkerPacket` objects from the approved graph.
   - Workers receive exact inputs, output schema, constraints, acceptance cases, and permissions.
   - Exactly one writer owns each durable target.

7. **Verification and review**
   - Run structural, semantic, visual, lineage, readback, and business acceptance checks as applicable.
   - Independent review consumes actual artifacts and verification evidence.
   - A reviewer may challenge the blueprint when the result meets the contract but not the user outcome.

8. **Delivery or correction**
   - Finalize only when process and business gates pass.
   - Corrections invalidate the smallest safely computable dependency scope.
   - When dependency impact is uncertain, fall back to lane-suffix invalidation.

## 6. Core Objects

| Object | Purpose | Required content | Truth owner |
|---|---|---|---|
| `TaskBlueprint` | Canonical business definition of the task | intent, outcome, audience, use mode, deliverables, scope, non-goals, standards, assumptions, decisions, change policy | Control Plane |
| `EvidenceSpec` | Describes a source and its authority | source locator, role, priority, status, applicability, sensitivity, freshness | Evidence layer |
| `ClaimSpec` | Connects a proposed claim to evidence | claim text/type, supporting sources, confidence, allowed use, affected units | Blueprint / domain methodology |
| `UnitSpec` | Defines one page, section, table, chart, node, or module | task, expected conclusion/function, required evidence, implementation constraints, forbidden content, acceptance IDs | Blueprint Compiler |
| `SolutionGraph` | Full production dependency graph | nodes, edges, stage purpose, capacity and approval gates | Solution Architect |
| `OrchestrationPlan` | Proves how work should run | semantic owner, contribution/authority roles, waves, serial reasons, join points, artifact flow, handoff checks, lane capability routes | Solution Architect |
| `LaneSpec` | Executable graph node | inputs, output schema, capability requirements, standard IDs, acceptance IDs, write policy | Solution Architect |
| `CapabilitySpec` | Routable capability definition | domain, triggers, exclusions, input/output contracts, operations, dependencies, verification | Capability Registry |
| `WorkerPacket` | Immutable task assigned to one worker | contract slice, input artifact refs, output schema, constraints, acceptance cases, permissions, callback contract | Blueprint Compiler / Controller |
| `ArtifactRef` | Verifiable artifact identity | locator, type, fingerprint, producer, revision, lineage, unit coverage, role | Runtime / artifact store |
| `AcceptanceCase` | Reproducible test of a requirement | evaluator type, procedure, inputs, expected result, threshold, evidence schema, applicable units | Domain pack / verifier |
| `VerificationResult` | Actual result of an acceptance case | actual observation, evidence refs, artifact fingerprint, evaluator/version, status, confidence | Verifier |
| `ReviewReport` | Independent outcome judgment | coverage, business validity, residual risk, required fixes, release recommendation | Review worker |
| `ExecutionState` | Runtime governance state | revision, workers, approvals, callbacks, receipts, invalidation, finalization | Controller Runtime |
| `OperationPermit` | Authorizes one exact persistent operation | permit ID, graph/packet revision, worker identity, capability operation, target, action, payload fingerprint, restricted fields, expiry, approval refs, idempotency key, lifecycle status | Controller Runtime |

## 7. Component Contracts

### Task Diagnoser

```text
UserRequest + ReferencedHistory + SourceAvailability
-> TaskDiagnosis
```

`TaskDiagnosis` includes the business objective, final use, audience, artifact hypothesis, intent anchors, unacceptable substitutes, and blocking unknowns.

### Blueprint Compiler

```text
TaskDiagnosis + ScenarioPattern + ApprovedDecisions
-> TaskBlueprint + TraceabilityMap + UnmappedFields
```

It must not silently drop Planner content. High-risk execution is blocked when required fields are unmapped.

### Solution Architect and Capability Router

```text
TaskBlueprint + CapabilityRegistry + RuntimeAvailability
-> SolutionGraph + OrchestrationPlan + RoutingDecision + PermissionPlan + CapacityPlan
```

Every routing decision includes selected and rejected capabilities, reasons, fallback rules, and expected verification.

### Controller Runtime

```text
Approved SolutionGraph + ExecutionState
-> WorkerPackets + gated execution + ArtifactRefs
```

The controller renders human-readable prompts from packets. Prompts are not the source of truth.

### Domain Worker

```text
WorkerPacket
-> ArtifactRefs + observations + assertions
```

Assertions remain unverified until linked to a `VerificationResult`.

For W3/W4 operations, a worker must call a controller-owned dispatcher with an active `OperationPermit`. Direct provider calls are outside the managed architecture and cannot produce a valid controller receipt.

### Operation Dispatcher

```text
OperationPermit + typed provider adapter + exact operation descriptor
-> provider result + mandatory readback + controller-ledger OperationReceipt
```

The dispatcher validates permit identity, target, action, exact normalized payload fingerprint, restricted-field policy, expiry, approval, idempotency key, and provider fingerprint before execution. Provider adapters compile typed allowlisted descriptors; workers never supply an executable or argv. The permit claim is persisted before the external call. An interrupted claim can only enter readback-only reconciliation, never automatic re-execution. Callback manifests bind the receipt ID, target locator, target version, and readback-derived artifact fingerprint. A worker-authored receipt is not sufficient.

Permit lifecycle:

```text
issued -> claimed -> consumed
   |         |
   +-------> revoked
   +-------> expired
```

- `issued` may be claimed exactly once through an atomic state transition.
- `claimed` records dispatcher attempt identity and cannot be claimed by another request.
- a successful provider operation and readback produce `consumed` plus an immutable receipt;
- an interrupted provider result remains `claimed` and enters readback-only reconciliation instead of being executed again;
- contract revision, correction, approval withdrawal, expiry, or target change produces `revoked`/`expired`;
- completed retries return the existing ledger receipt; interrupted retries require reconciliation rather than a newly mutable payload;
- payload normalization and hashing rules are versioned with the permit schema.

### Verifier and Reviewer

```text
AcceptanceCases + ArtifactRefs
-> VerificationResults

TaskBlueprint + VerificationResults + ArtifactRefs
-> ReviewReport
```

Final gates accept current artifact-bound verification, not arbitrary evidence text.

### Verification Result Contract

Every high-risk result includes:

```yaml
acceptanceCaseId: string
acceptanceCaseVersion: string
acceptanceCaseFingerprint: string
artifactFingerprint: string
evaluator:
  capabilityId: string
  version: string
procedureFingerprint: string
method: structural | semantic | visual | readback | lineage | business
inputs: [ArtifactRef]
normalizedInputDigest: string
expected: object
actual: object
status: pass | fail | blocked
evidenceRefs: [ArtifactRef]
evidenceDigest: string
confidence: number
executedAt: timestamp
```

`self_attested` observations may help diagnosis but cannot independently satisfy a high-risk business acceptance case.

## 8. Dual Acceptance Model

### Process acceptance

Checks whether execution followed the approved contract:

- correct revision and worker identity;
- approved target and write boundary;
- source, unit, and writer coverage;
- approval and callback integrity;
- complete artifact manifest and readback receipt.

### Business outcome acceptance

Checks whether the artifact works in the real use context:

- it answers the business question;
- the final audience can understand and act on it;
- evidence supports the material conclusions;
- the artifact shape is not replaced by an easier but wrong format;
- the result is independently usable when required;
- domain-specific quality thresholds pass.

Both must pass. Process compliance cannot compensate for weak business validity.

## 9. Key Mechanism Matrix

| Mechanism | Target behavior | Initial implementation boundary |
|---|---|---|
| Prompt / Rules | Prompts render structured objects and never become the only truth source | versioned renderers for diagnosis, worker, and review packets |
| Tool contracts | Tools declare operations, risks, target types, readback, and verification | capability registry plus operation-level metadata |
| Permissions | unknown permissions fail closed; destructive or external writes require explicit authorization | preserve current writePolicy and user approval, extend to operation registry |
| Context | load only sources and decisions relevant to the current blueprint and unit | context manifest, token budget, truncation notice, source hydration record |
| Memory | retain approved decisions and correction patterns, not uncontrolled conversation summaries | decision ledger and immutable revision snapshots |
| Evaluation | scenario-level offline tests and artifact-specific acceptance cases | golden cases for deck, pricing report, and Lark cockpit |
| Observability | trace every interpretation, routing choice, artifact, verification, and correction | structured event log and traceability viewer |
| Release | architecture and behavior changes roll out behind versioned schema/feature flags | dual-run compiler, compatibility mode, rollback to current schema-2 path |
| Cost / SLO | plan capacity before fan-out and track retries, latency, and user interventions | per-graph worker/token/time budgets and timeout policy |

### Worker lifecycle and runtime selection

Professional decomposition and runtime persistence are separate decisions.

```text
task contract
-> professional lanes and write/review boundaries
-> semantic work orchestration and lane-level capability binding
-> distributed-execution decision
-> per-lane lifecycle decision
-> runtime dispatch
```

- `ephemeral + packet_only` is the default lifecycle for one bounded output and
  one callback. Provider-neutral architecture does not dictate its runtime.
- `persistent + checkpoint_delta` is reserved for an ongoing professional
  workbench that must survive controller turns or accept direct user
  intervention.
- A native Codex thread is user-visible state. Provider-neutral deployments
  require approval; each distributed task records explicit approval and
  selects native Sessions for distributed lanes.
- Contract, artifact, revision, and verification continuity remain in KY-TASK
  state. They must not depend on conversation persistence.
- The stored execution value `multi_session` is a legacy alias for
  `distributed`; runtime selection comes from the locked runtime policy.

### Session-first scheduler policy

The distribution adds an operational policy above the provider-neutral
architecture:

- `native_session_required` selects a visible native Codex Session for every
  distributed lane.
- `dependsOn` projects the SolutionGraph DAG into controller lane state.
- `task_controller_ready_lanes` returns the concurrency frontier rather than a
  single next lane.
- `maxParallelWorkers` bounds simultaneous Session workers; the distribution
  default is four.
- `projectAffinityPolicy: inherit_or_resolve_required` requires a saved Codex
  project to be resolved and locked before native dispatch.
- Native worker registration records `projectId` and `projectEnvironment` and
  rejects a project id that differs from the locked target.
- `projectless` is a user-approved compatibility exception, never an implicit
  scheduler fallback.
- Legacy states without `dependsOn` retain their historical ordered-lane chain.

This changes scheduling and runtime visibility, but not TaskBlueprint,
SolutionGraph, WorkerPacket, permit, receipt, or verification semantics.

## 10. Context and Memory Policy

- The current user message and explicit corrections outrank historical summaries.
- Referenced tasks are hydrated into approved, rejected, superseded, and unresolved decisions.
- Raw conversation history is not injected into every worker.
- Each `WorkerPacket` includes only applicable intent, decisions, sources, units, and acceptance cases.
- Context truncation must be recorded; missing authoritative context blocks high-risk execution.
- Learning from corrections updates scenario evaluations and routing rules only after review; it does not silently change active contracts.

## 11. Failure and Recovery

| Failure | Required response |
|---|---|
| blueprint does not match user intent | stop before routing; revise diagnosis and blueprint |
| required capability unavailable | use declared equivalent fallback only if output and verification semantics remain unchanged; otherwise block |
| provider permission missing | block the affected node; do not let the controller perform the write |
| worker output schema mismatch | reject artifact; rerun or repair the node |
| sample rejected by user | invalidate the affected blueprint/solution scope, not merely the wording lane |
| verification fails | create an explicit repair node and rerun independent verification |
| external write partially succeeds | preserve receipts and readback; enter recovery path before further writes |

## 12. Primary Risks and Gaps

| Gap | Current consequence | Target repair layer |
|---|---|---|
| Planner output remains prose | business requirements are lost during manual translation | Blueprint Compiler |
| legacy missing dependency metadata | old states serialize by lane order | strict OrchestrationPlan for all new composite plans; visible legacy inference for compatibility |
| worker prompt is free text | workers receive another interpretation of the task | immutable WorkerPacket |
| evidence is self-attested text | review proves formal coverage but not truth | AcceptanceCase + VerificationResult |
| no capability metadata standard | routing depends on model memory and skill descriptions | Capability Registry |
| no domain verifier contract | independent review may lack the method to judge output | verifier adapters in scenario packs |
| limited timeout and recovery | workers may remain running indefinitely | runtime leases and reconciliation |
| no full migration/rollback command | architecture changes are risky to release | immutable snapshots and migration tooling |

## 13. Target Repository Modules

```text
task-controller/
  control_plane/
    diagnosis.py              # TaskDiagnosis schema and validation
    blueprint.py              # TaskBlueprint schema and compiler
    solution_graph.py         # DAG construction and validation
    orchestration.py          # semantic ownership, waves, joins, handoff and per-lane capability routing
    capability_router.py      # registry matching and routing explanation
  runtime/
    controller_state.py       # current execution governance, extracted from helper
    packet_dispatch.py        # immutable WorkerPacket creation and registration
    gate_engine.py            # process and business gate composition
    operation_dispatcher.py   # permit-bound W3/W4 provider execution and readback
  data/
    artifact_registry.py      # ArtifactRef and lineage
    evidence_graph.py         # EvidenceSpec / ClaimSpec relations
    revision_store.py         # immutable snapshots and corrections
  verification/
    acceptance.py             # AcceptanceCase and VerificationResult schemas
    review.py                 # ReviewPacket and ReviewReport contracts
  registry/
    capability.schema.json    # CapabilitySpec contract
    scenario_packs/           # workflow patterns and domain verifier declarations
  mcp/
    server.mjs                # thin tool adapter only
  scripts/
    task_controller_state.py  # compatibility CLI during migration
  tests/
    unit/
    scenarios/
    migration/
  docs/
```

The target structure is a migration destination, not an instruction to move files immediately.

## 14. Migration Roadmap

### Step 1: Add blueprint and registry alongside schema 2

- Introduce `TaskBlueprint`, `CapabilitySpec`, and traceability schemas.
- Keep current `contractSpec`, lanes, workers, gates, and MCP tools unchanged.
- Compile blueprint into current contract fields and report unmapped content.
- Acceptance: current 61 tests pass plus blueprint mapping tests.

Required schema artifacts for this step:

- `TaskDiagnosis.schema.json`
- `TaskBlueprint.schema.json`
- `CapabilitySpec.schema.json`
- explicit `TaskBlueprint -> contractSpec` field map
- `TraceabilityMap` with `mapped`, `unmapped`, and `inferred` fields

The compiler runs in shadow mode first. It cannot authorize execution while required fields remain unmapped.

Initial field mapping:

| TaskBlueprint field | contractSpec / state target | Conversion rule | Unmapped behavior |
|---|---|---|---|
| `interaction.mode` | `contractSpec.interactionMode` | exact enum mapping | block |
| `deliverables.primary` | `contractSpec.deliverable` | copy ID/kind/target/format/audience/useMode/standalone/artifactClass | block |
| `deliverables.units` | `contractSpec.deliverable.units` | preserve stable unit IDs and applicable acceptance IDs | block for unit-based artifacts |
| `sources` | `canonicalSources` | preserve priority, role, required, appliesTo | block required source loss |
| `intentAnchors` | `intentAnchors` | exact statement/source mapping | block high-risk task if empty |
| `decisions` | `decisionLedger` | map approved decisions to binding, others to advisory/superseded | block binding decision loss |
| `changePolicy.preserve` | `preserve` | exact IDs and lane/unit applicability | block |
| `changePolicy.allowed` | `allowedChanges` | exact IDs and applicability | block |
| `changePolicy.forbidden` | `forbidden` | exact IDs and applicability | block |
| `acceptanceCases` | `acceptance` plus verifier store | contractSpec keeps IDs/descriptions; full cases stored separately by fingerprint | block high-risk empty cases |
| `approvals.sample` | `sampleGate` | copy lane, blocks, acceptance IDs | block when required fields missing |
| `approvals.user` | `userApprovalGate` | copy artifact and blocked nodes/lanes | block |
| `writePolicy` | `writePolicy` | exact target/action projection | block approved-target execution |
| `standards` | new blueprint-only store, referenced by graph nodes | do not flatten into free-text contract | block if required node has no standard |
| `assumptions/nonGoals/capacity/changeTriggers` | blueprint-only store | retained in packet projection and traceability map | warn for low risk; block when marked required |

Every mapping result is labeled `direct`, `defaulted`, `inferred`, `unmapped`, or `conflict`. Defaults are versioned. Inference requires evidence and cannot satisfy a binding user decision. The shadow compiler compares normalized current contract output with compiled output and reports semantic differences before enforcement is enabled.

### Step 2: Add SolutionGraph and immutable WorkerPacket

- Generate graph nodes and packets from the blueprint.
- Keep the current ordered lane array as a compatibility projection.
- Persist packet fingerprints and reject callbacks from stale packets.
- Acceptance: three real scenarios reproduce their correct domain-specific work graphs.

Compatibility rules:

- each graph node has a stable `nodeId` and exactly one compatibility lane name;
- graph edges define dependencies; the lane array is a deterministic topological sort, not the source of dependency truth;
- independent nodes may run concurrently only when their write sets do not overlap;
- fan-in nodes wait for all required upstream artifact contracts;
- graph revision changes supersede packets from affected nodes and descendants;
- when old schema-2 states have no graph, sequential lane order is imported as a linear graph and marked `legacy-inferred`;
- correction invalidation follows graph descendants, falling back to lane suffix when dependency metadata is incomplete.

### Step 3: Add domain verification

- Introduce `AcceptanceCase`, `VerificationResult`, and artifact-bound evidence.
- Distinguish `self_attested`, `tool_verified`, `independent_reviewed`, and `human_approved`.
- High-risk finalization rejects pure self-attestation.
- Acceptance: deck, pricing report, and Lark cockpit scenario evaluations pass.

The first vertical slice is `lark-operations`:

- define versioned `OperationPermit`, dispatcher, provider adapter identity, and `OperationReceipt`;
- require every managed W3/W4 call to pass through the dispatcher;
- bind readback and resulting artifact fingerprint to `VerificationResult`;
- reject callbacks that contain only worker-authored receipt text;
- retain the existing callback writeReceipt as a compatibility field until dispatcher receipts are universal.

### Step 4: Modularize and retire ambiguous compatibility fields

- Extract control, runtime, data, verification, and registry modules.
- Add migration dry-run, immutable revision snapshots, rollback, leases, and reconciliation.
- Deprecate opaque contract strings and free-form worker prompts only after dual-run parity.
- Acceptance: migration and rollback tests pass; old states remain readable and explicitly marked legacy.

## 15. Architecture Decision

The next version is not a larger task checklist. It is a compiler-driven agent control system:

```text
one user intent
-> one canonical blueprint
-> one explainable solution graph
-> one accepted work orchestration plan
-> capability-bound worker packets
-> artifact-bound verification
-> one final business decision
```

The existing controller remains the execution kernel. The new work belongs before it (diagnosis, compilation, routing) and after it (domain verification and outcome review).
