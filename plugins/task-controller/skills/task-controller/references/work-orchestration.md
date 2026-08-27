# Work Orchestration Contract

Use this reference after the task boundary is known and before worker runtime
selection. It applies to every composite task; it is not a domain scenario pack.

## The Four Separate Decisions

Do not collapse these decisions into one role list:

```text
task decomposition
-> work orchestration
-> lane-level capability matching
-> worker lifecycle and runtime selection
```

- Decomposition identifies the professional jobs that exist.
- Orchestration decides which jobs are parallel, which are serial, where they
  join, and which output owns the final meaning.
- Capability matching selects a skill/tool profile from each lane's job,
  inputs, output contract, and acceptance role.
- Runtime selection decides Session visibility and persistence only after the
  work graph is valid.

A visible Session cannot repair a bad graph. It only executes that graph with a
cleaner context.

## Contribution Roles

Every strict multi-lane plan assigns one role to every lane:

- `primary`: directly defines or produces the result the user asked for.
- `prerequisite`: supplies evidence, constraints, decisions, or permission the
  primary path cannot safely work without.
- `supporting`: improves execution but does not own the result meaning.
- `verification`: judges an existing decision, sample, or artifact.

Also assign one semantic authority:

- `define`: decides what the primary result should mean.
- `constrain`: supplies facts, rules, or boundaries without redefining the result.
- `implement`: produces from an already defined contract.
- `define-and-implement`: keeps design and production in one lane because a
  handoff would lose important judgment.
- `verify`: checks an artifact or decision that already exists.

Exactly one primary lane is `semanticOwner: true`. Multiple professional lanes
may contribute, but one lane must resolve conflicts and own the result's meaning.

## Parallel Eligibility

Two lanes may be in the same wave only when all of these are true:

- neither consumes the other's output;
- neither needs the other's decision, sample, approval, or readback;
- they do not write the same durable target;
- neither is verification of an artifact the other has not produced yet;
- their outputs have a declared downstream join point;
- running them early cannot let a supporting lane redefine the primary result.

Reading the same immutable sources is not a dependency. Independent research
lanes should use `dependsOn: []` and run together.

## Valid Serial Reasons

Every strict dependency has a non-empty `dependencyReasons` entry. Valid reasons
include:

- consumes an upstream output contract;
- needs a binding decision or approval;
- needs a representative sample;
- must wait for a writer because it verifies the written artifact;
- shares a durable write target;
- must reconcile a named conflict at a join point.

`list-order`, `keep-order`, and “this is step 3” are not valid dependency reasons.

## Artifact Contracts

Use `inputContracts` and `outputContracts` to prove a dependency instead of
relying on lane names. A produced contract has one unambiguous producer unless
a later, ordered lane deliberately versions the same contract.

If an input comes from outside the lane graph, declare it under `externalInputs`.
If a lane consumes an output but does not depend on its producer, the plan is
invalid even if the lane list happens to put the producer first.

## Primary Path And Supporting Work

Build the primary path first:

```text
semantic owner -> primary production -> final verification
```

Then add prerequisite and supporting lanes only when their output is consumed by
that path. Supporting work must not become the default reading path, the dominant
artifact, or an early rulebook that forces the primary result into its own shape.

Estimate effort when supporting scope may expand. The plan should warn when
supporting effort exceeds primary effort without a task-specific justification.

## Verification Timing

Verification consumes something that exists:

- decision review depends on the decision model it reviews and declares
  `verificationScope: upstream-decision`;
- sample review depends on the sample;
- artifact QA/readback depends on the relevant writer;
- final review depends on every final writer it covers.

A QA lane that runs beside primary design and then becomes an input to the writer
is usually not QA. Reclassify it as a prerequisite constraint with a precise
output contract, or move it after the artifact it actually judges.

## Handoff Cohesion

Do not automatically split “design” and “writing/production”. First assess
`handoffRisk`:

- `low`: production is mostly mechanical from a stable contract.
- `medium`: some judgment crosses the boundary; preserve a structured contract.
- `high`: the output depends on continuous semantic judgment, voice, or local
  design decisions.

For a high-risk split, use `handoffMode: artifact-contract` and provide a concrete
`handoffContract`. Otherwise merge the work into one primary lane with
`semanticAuthority: define-and-implement`. `handoffMode: independent` is invalid
for a high-loss primary handoff.

## Lane-Level Capability Matching

Do not assign one globally matched skill to every lane because the task shares a
domain keyword. Match each lane from:

- actual professional job (`purpose`);
- required input contracts;
- promised output contracts;
- semantic/verification role;
- write boundary and tools;
- acceptance method.

Use exact `capabilityRequirements` when the capability is known. Use
`capabilityNeeds` to describe a required profile when discovery is still needed.
An unavailable exact requirement blocks strict orchestration. Suggestions are not
bindings until the controller selects and records one.

## Runtime Comes Last

After orchestration passes:

- choose `ephemeral + packet_only` for one bounded lane output;
- choose `persistent + checkpoint_delta` only for a continuing workbench;
- under `native_session_required`, dispatch every distributed lane as a visible
  project-scoped Session;
- dispatch the full current wave before waiting;
- do not use runtime choice to manufacture or erase semantic dependencies.

## Strict Lane Shape

```json
{
  "name": "primary-delivery",
  "kind": "implementation",
  "purpose": "Own the reader-facing result and produce the approved artifact",
  "contributionRole": "primary",
  "semanticAuthority": "define-and-implement",
  "semanticOwner": true,
  "dependsOn": ["evidence", "audience"],
  "dependencyReasons": {
    "evidence": "consumes evidence-ledger",
    "audience": "consumes audience-use-contract"
  },
  "inputContracts": ["evidence-ledger", "audience-use-contract"],
  "outputContracts": ["approved-artifact"],
  "writeBoundary": "approved-target",
  "writeTargets": ["delivery-target"],
  "workerRequired": true,
  "capabilityRequirements": ["delivery-capability"],
  "workerLifecycle": "ephemeral",
  "contextPolicy": "packet_only"
}
```

The names are illustrative. Generate the smallest set of lanes needed for the
actual task.

## Required Planning Flow

For a new multi-lane task:

1. Draft jobs from the locked TaskBlueprint or task contract.
2. Mark contribution role, semantic authority, and the one semantic owner.
3. Declare outputs before inputs; derive dependencies from consumption.
4. Give every serial edge a reason.
5. Identify parallel waves and downstream join points.
6. Check verification timing, shared writers, and handoff loss.
7. Match capabilities per lane.
8. Run `task_controller_plan_orchestration` in strict mode.
9. Fix every blocker before `task_controller_init` or Session creation.
10. Select lifecycle/runtime and dispatch the ready wave.

When no scenario pack matches, use this generic flow. Do not invent a new domain
pack merely to obtain a graph, and do not fall back to the historical five-lane
template.

## Failure Signals

Replan when any of these appears:

- verification precedes the artifact it judges;
- the writer depends on QA that was supposed to judge the writer;
- no semantic owner exists, or several lanes can redefine the result;
- a supporting output is not consumed by the primary path;
- design and production are split despite high handoff loss and no contract;
- several writers can touch the same target in one wave;
- missing `dependsOn` silently creates an ordered chain;
- one global capability is copied onto unrelated lanes;
- runtime selection occurs before the work graph is accepted.
