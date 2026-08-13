# Decision Governance v1

Status: approved for implementation
Scope: client-facing pricing and other high-impact commercial decisions
Compatibility baseline: `schemaVersion: 2`, `TaskBlueprint: 1.x`, `SolutionGraph: 1.x`

## Problem

The controller already governs worker isolation, callbacks, writes, and final
verification. It does not yet distinguish an editable presentation choice from
a commercial decision that changes what the client buys, pays for, or is judged
against. As a result, a controller can legally regroup billable modules, invent
or duplicate charge items, bind KPIs, and start workbook architecture before a
human has approved the commercial model.

This is a control-plane defect. Changing worker runtime or adding more Sessions
does not repair it.

## Architecture decision

High-impact decisions receive one of three explicit authority levels:

- `locked`: the agent must preserve the decision.
- `agent_may_decide`: the agent may decide within the stated boundary.
- `propose_then_confirm`: the agent may prepare a proposal, but downstream
  production is blocked until the exact reviewed artifact is approved.

Client-facing pricing uses a dedicated scenario graph. The pricing model must
depend on normalized evidence, pass an independent commercial review, and be
approved by the user before workbook architecture or implementation starts.
Commercial acceptance is evidence-backed; a free-text reviewer assertion is
not sufficient.

User correction language is classified through a controller operation. A
contract-level correction creates an open `correctionEvent`, invalidates active
approvals, and blocks progress until a revised contract consumes the event.

## Module boundaries

| Module | Responsibility | Inputs | Outputs | Must not own |
|---|---|---|---|---|
| `control_plane/decision_governance.py` | classify decision risk and user feedback; apply scenario policy defaults | TaskBlueprint, scenario pack, lane/state summary, feedback text | governance object, effective blueprint, feedback classification | state persistence, worker dispatch, provider calls |
| `control_plane/blueprint.py` | validate authority fields and compile governance into ContractSpec | effective TaskBlueprint, lane definitions | traceable ContractSpec, executable blockers | scenario routing, feedback mutation |
| `control_plane/capability_router.py` | prefer task-type-specific scenario packs | TaskBlueprint, registry | selected scenario and reasons | business decision classification |
| `scenario_packs/client-pricing.json` | define the client-pricing professional DAG and mandatory acceptance policy | scenario registry input | dependency graph template and policy defaults | runtime state mutation |
| `registry/capabilities/pricing-commercial-verifier.json` | identify the independent commercial-review methodology | capability registry input | verifier binding | approval or finalization |
| `scripts/task_controller_state.py` | persist feedback events and enforce approval/verification gates | compiled plan, controller state, feedback classification | state transitions and blockers | interpreting raw business intent beyond deterministic policy |
| `mcp/server.mjs` | expose feedback classification/ingestion through typed tools | MCP request | helper invocation | duplicate policy logic |

## Target directory shape

```text
plugins/task-controller/
├── control_plane/
│   ├── blueprint.py
│   ├── capability_router.py
│   └── decision_governance.py
├── contracts/
│   └── task-blueprint.schema.json
├── registry/capabilities/
│   └── pricing-commercial-verifier.json
├── scenario_packs/
│   └── client-pricing.json
├── scripts/
│   └── task_controller_state.py
├── mcp/
│   └── server.mjs
└── tests/
    ├── test_decision_governance.py
    └── test_client_pricing_plan.py
```

## Core objects

### DecisionGovernance

```json
{
  "policyVersion": "1.0",
  "riskLevel": "high",
  "confirmationRequired": true,
  "items": [
    {
      "id": "allowed-charge-model",
      "category": "billable_item",
      "authority": "propose_then_confirm",
      "source": "changePolicy.allowed"
    }
  ],
  "triggers": ["client_pricing", "billable_item"]
}
```

### Client-pricing approval chain

```text
source-normalization
  -> pricing-model
  -> commercial-review
  -> user-approval
  -> workbook-architecture
  -> implementation
  -> final-review
```

`commercial-review` must publish the fingerprinted
`commercial-pricing-model` artifact. `userApprovalGate` binds approval to that
artifact and blocks every production lane after the approval node.

### FeedbackClassification

```json
{
  "classification": "contract_correction",
  "action": "record_correction",
  "requiresContractRevision": true,
  "matchedTriggers": ["不能收费"],
  "impactedCategories": ["billable_item"],
  "suggestedInvalidFromLane": "pricing-model",
  "preserveUnmentioned": true
}
```

## Compatibility boundary

- Existing hand-authored states remain readable and are not rewritten on load.
- Existing Blueprint fields remain valid; `authority` is optional on semantic
  items and is deterministically defaulted.
- Generic evidence/pricing analysis continues to use `evidence-analysis`.
  Client-facing pricing is selected only when the task type or explicit domain
  identifies client pricing.
- Existing `record-correction` remains available. `ingest-feedback` is a safer
  controller shortcut that classifies and records in one atomic mutation.
- Runtime selection and Session-first policy are unchanged.

## Implementation sequence

1. Add deterministic decision/feedback classifiers and Blueprint authority
   compilation with fail-closed confirmation blockers.
2. Add the client-pricing scenario, commercial verifier, and task-type-aware
   routing; apply mandatory acceptance and approval defaults to the effective
   Blueprint.
3. Add atomic feedback ingestion plus MCP schemas and ensure corrections stale
   approvals and block progress.
4. Add regression, scenario, and compatibility tests; update public docs,
   version, validate the plugin, and reinstall it.
