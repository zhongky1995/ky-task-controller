# KY-TASK Work Orchestration v1

Status: implemented
Contract: `OrchestrationPlan 1.0`
Compatibility: existing `schemaVersion: 2` state remains readable

## Architecture Decision

Task orchestration is a first-class Control Plane stage between decomposition
and worker runtime selection.

```text
Task contract / TaskBlueprint
-> professional jobs (decomposition)
-> OrchestrationPlan (parallel/serial/ownership/join/handoff)
-> lane-level capability routes
-> lifecycle and runtime selection
-> ready-wave dispatch
```

The scheduler no longer treats a lane list as sufficient evidence of a correct
plan. `dependsOn` still drives runtime readiness, but the orchestration compiler
checks whether those dependencies have the right professional meaning.

## Before And After

| Concern | Before | v1 |
|---|---|---|
| lane purpose | often inferred from a name/kind | explicit professional `purpose` |
| primary result | several lanes could redefine it | one `semanticOwner` on the primary path |
| task importance | implicit | `primary`, `prerequisite`, `supporting`, `verification` |
| semantic authority | implicit | `define`, `constrain`, `implement`, `define-and-implement`, `verify` |
| parallel work | `dependsOn: []` only | explicit waves plus downstream join points |
| serial work | any listed dependency | every edge has a professional reason |
| artifact flow | mostly prose | producer/consumer `inputContracts` and `outputContracts` |
| QA timing | structural dependency only | verification must consume the judged artifact/decision/sample |
| design-to-build split | split by role label | assessed with handoff risk and contract |
| capability assignment | scenario/global task match | exact or suggested route per lane job/input/output/role |
| runtime | selected while planning lanes | selected only after orchestration passes |

## Modules

```text
plugins/task-controller/
  control_plane/
    orchestration.py                 # compiler, invariants, waves, capability routes
    solution_graph.py                # trusted scenario DAG and lane projection
    capability_router.py             # scenario-level shadow routing
  contracts/
    orchestration-plan.schema.json   # durable read-only plan contract
  scripts/
    task_controller_state.py         # CLI, state persistence, strict init gate
  mcp/
    server.mjs                       # tool schemas and thin CLI adapter
  skills/task-controller/references/
    work-orchestration.md            # model operating contract
  tests/
    test_orchestration.py            # generic orchestration regression cases
```

### File Responsibilities

- `control_plane/orchestration.py` owns no Session creation and no durable
  writes. It normalizes lanes, validates work semantics, computes waves/join
  points, and resolves lane-local capability requirements.
- `solution_graph.py` remains the trusted scenario-pack graph builder. Its lane
  projection now carries purpose and artifact contracts into orchestration.
- `task_controller_state.py` persists the plan and refuses explicit strict
  initialization with blockers. It also exposes wave information through
  `ready-lanes`.
- `server.mjs` exposes `task_controller_plan_orchestration` and accepts the new
  lane contract fields. It does not perform orchestration logic itself.
- `work-orchestration.md` tells the controller how to propose a correct generic
  map when no scenario pack matches.

## Core Object Drafts

### LaneOrchestrationSpec

```yaml
name: string
purpose: string
contributionRole: primary | prerequisite | supporting | verification
semanticAuthority: define | constrain | implement | define-and-implement | verify
semanticOwner: boolean
dependsOn: [lane-name]
dependencyReasons: {lane-name: reason}
inputContracts: [artifact-contract-id]
outputContracts: [artifact-contract-id]
externalInputs: [artifact-contract-id]
writeBoundary: read-only | draft-file | approved-target | review-only
writeTargets: [target-id]
handoffRisk: low | medium | high
handoffMode: same-lane | artifact-contract | independent
handoffContract: object | array
verificationScope: final-artifact | intermediate-artifact | upstream-decision
capabilityRequirements: [capability-id]
capabilityNeeds: object | array | string
estimatedEffort: number
continuityRequired: boolean
```

### OrchestrationPlan

```yaml
orchestrationVersion: "1.0"
policy: strict | advisory | legacy
source: trusted-solution-graph | lane-definitions
lanes: [LaneOrchestrationSpec]
topologicalOrder: [lane-name]
waves: [{wave, lanes, parallel}]
parallelGroups: [[lane-name]]
serialEdges: [{from, to, reason}]
joinPoints: [{lane, waitsFor}]
semanticOwnerLane: lane-name
primaryPath: [lane-name]
capabilityRoutes: [LaneCapabilityRoute]
runtimeSelectionStage: after-orchestration
orchestrationExecutable: boolean
blockers: [object]
warnings: [object]
orchestrationDigest: sha256
```

### LaneCapabilityRoute

```yaml
lane: lane-name
job: purpose
inputs: [contract-id]
outputs: [contract-id]
acceptanceRole: semantic-authority
selected: [{id, reason}]
suggestions: [{id, score, reasons}]
missing: [{id, reason}]
status: bound | suggested | blocked | unbound
```

## Invariants

Strict multi-lane plans enforce these properties:

1. Every lane explicitly declares purpose, contribution role, semantic
   authority, and dependencies.
2. Exactly one primary lane owns the result meaning.
3. Every serial edge has a reason; list order is rejected as a reason.
4. An input artifact has an upstream producer or is explicitly external.
5. Unordered writers cannot share a durable target.
6. Primary implementation follows the semantic owner unless both jobs are one
   `define-and-implement` lane.
7. A high-loss split requires an artifact handoff contract.
8. Verification follows the artifact it judges. Upstream decision review is
   explicit and does not masquerade as final QA.
9. Exact lane capabilities must be available under strict policy.
10. Runtime selection is recorded as downstream of orchestration.

Warnings expose inferred semantic ownership in trusted scenario graphs,
legacy-order serialization, ordered versioning of the same output contract, and
supporting effort that dominates primary effort.

## Generic No-Pack Path

Scenario packs remain useful accelerators for stable, repeated business
patterns. They are not required to orchestrate a task.

When no pack matches:

1. lock the TaskBlueprint/task contract;
2. propose the smallest lane set from actual professional jobs;
3. compile it with `task_controller_plan_orchestration` in strict mode;
4. fix blockers and bind lane capabilities;
5. initialize schema-v2 state from the accepted lane definitions;
6. resolve the Codex project and dispatch the first ready wave as visible
   Sessions under the existing Session-first policy.

No domain-specific pack should be added merely because a single task needed a
different graph.

## Compatibility

- Stored schema remains version 2.
- Existing states without an orchestration plan remain readable.
- Old initialization calls that contain no orchestration contract fields are
  treated as `legacy` and expose inferred ordered dependencies instead of being
  retroactively rejected.
- New tool/skill-generated composite plans explicitly use `strict`.
- Trusted scenario graphs compile through strict orchestration without requiring
  scenario JSON files to duplicate inferred fields.
- `dependsOn` remains the scheduler source; `effectiveDependsOn` and wave fields
  make legacy/compiled behavior auditable.

## Verification Coverage

Regression tests cover:

- independent prerequisite lanes in one parallel wave;
- fan-in to one semantic owner and final reviewer;
- premature QA before implementation;
- high-loss design/production split without a contract;
- per-lane capability binding;
- visible legacy serial inference;
- existing scenario-pack planning, state, runtime, permit, callback, and
  verification behavior.

## Next Steps

The following are intentionally outside this slice:

- automatic natural-language decomposition into strict lane definitions;
- a richer dynamic capability catalog hydrated directly from all installed
  skills/tools;
- topology-changing graph revision inside one active state;
- effort/cost optimization across waves;
- visual graph rendering in the Codex UI.

Those can build on `OrchestrationPlan` without coupling the Control Plane to a
specific worker runtime or domain scenario.
