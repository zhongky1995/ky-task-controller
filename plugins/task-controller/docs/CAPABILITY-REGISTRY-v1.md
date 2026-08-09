# Capability Registry v1

Status: proposed contract
Purpose: allow KY-TASK to discover, compare, route, and verify skills and tools without embedding every domain implementation in the controller.

## 1. Architecture Position

Capabilities are organized in three layers:

1. **Controller kernel**: cross-domain judgment, policy, graph, state, permissions, and release decisions.
2. **Scenario packs**: domain workflow patterns, decomposition rules, and verifier contracts.
3. **Dynamic adapters**: currently installed skills, MCP tools, connectors, binaries, and provider runtimes.

Adding more skills without this registry increases ambiguity. The router must know what a capability does, what it consumes, what it writes, and how its output can be verified.

## 2. CapabilitySpec

```yaml
id: string
name: string
version: string
source:
  type: builtin | skill | plugin | mcp | connector | binary
  locator: string
fingerprint: string
status: active | unavailable | deprecated | shadowed

capabilityType: controller | workflow | methodology | artifact | tool-adapter | verifier
placement: kernel | scenario-pack | dynamic-adapter

domains: [string]
triggers: [string]
exclusions: [string]
resourcePatterns: [string]

inputs:
  - id: string
    type: string
    formats: [string]
    required: boolean
    sourcePriority: integer
    sensitivity: public | local-private | external-private

outputs:
  - id: string
    type: artifact | analysis | checkpoint | verification
    formats: [string]
    durable: boolean
    externalSideEffect: boolean

operations:
  - id: string
    action: string
    readRisk: R0 | R1 | R2
    writeRisk: W0 | W1 | W2 | W3 | W4
    targetTypes: [string]
    reversible: boolean
    approvalRequired: boolean
    readbackRequired: boolean

dependencies:
  skills: [string]
  tools: [string]
  binaries: [string]
  runtimes: [string]
  authScopes: [string]
  versionRange: string

verification:
  methods: [structural, semantic, visual, readback, lineage, independent-review, human-approval]
  verifierCapabilities: [string]

routing:
  priority: integer
  mutuallyExclusiveWith: [string]
  fallback: [string]
  unavailableBehavior: block | ask-user | equivalent-fallback
```

Risk is operation-specific. A single adapter may support safe reading and destructive deletion; it must not receive one coarse risk label.

## 2.1 Physical Registry and APIs

The first implementation uses checked-in, versioned files rather than scanning arbitrary skill prose at runtime:

```text
registry/
  capability.schema.json
  scenario-pack.schema.json
  capabilities/
    kernel/*.json
    scenario-packs/*.json
    adapters/*.json
  fixtures/
    sample-client-deck/
    pricing-analysis/
    lark-cockpit/
```

Required interfaces:

```text
registry.load(activeRuntimeManifest) -> ActiveCapabilitySet
registry.validate(CapabilitySpec) -> validation report
scenario.discover(activeRegistryRoot) -> ScenarioPackDescriptor[]
scenario.load(packId, versionConstraint) -> ScenarioPack
scenario.validate(ScenarioPack) -> validation report
scenario.resolveVersion(packId, activeSet) -> selected/shadowed/conflict report
router.match(TaskBlueprint, ActiveCapabilitySet) -> candidates
router.resolve(candidates, runtime, permissions) -> RoutingDecision
router.explain(RoutingDecision) -> selected/rejected/fallback reasons
```

The MCP surface should expose read-only discovery and explanation first. Write execution remains in the controller dispatcher, not the registry.

## 3. Risk Scale

### Read risk

| Level | Meaning |
|---|---|
| `R0` | public metadata or non-sensitive capability discovery |
| `R1` | local user files or approved workspace material |
| `R2` | private external systems, cross-resource reads, or identity-scoped data |

### Write risk

| Level | Meaning |
|---|---|
| `W0` | no persistent write |
| `W1` | temporary/controller state |
| `W2` | local draft or final artifact |
| `W3` | external, recoverable object creation/update |
| `W4` | delete, replace, publish, permission expansion, irreversible or broad write |

Unknown operations default to the higher applicable risk and fail closed.

## 4. Controller Kernel Capabilities

These capabilities belong inside KY-TASK because every domain depends on them:

| Capability | Input | Output | Verification |
|---|---|---|---|
| Task diagnosis | request, history, source availability | TaskDiagnosis | intent traceability and unacceptable-substitute check |
| Blueprint compilation | diagnosis, decisions, scenario defaults | TaskBlueprint, unmapped fields | schema and user-statement coverage |
| Capability routing | blueprint, registry, runtime availability | selected/rejected capabilities and reasons | explainable route and dependency check |
| SolutionGraph design | blueprint, capability contracts | dependency DAG and approval points | acyclic graph, complete outputs, no write conflicts |
| Permission and risk gate | operation, target, identity, scope | allow, approve, or block | policy decision and target match |
| Runtime state and correction | callbacks, approvals, corrections | revisions and invalidation | stale result rejection |
| Final release decision | verification results and review | pass, needs-work, blocked | process and business gates both pass |

The kernel must not produce domain artifacts when a domain capability is unavailable.

## 5. Scenario Packs

Scenario packs contain patterns and verifier declarations, not provider implementations.

| Pack | Typical capabilities | Example external skills | Required verification |
|---|---|---|---|
| `client-deck` | brief diagnosis, strategy story, page-task map, script, layout, final QC | `ppt-deck-intake`, `ppt-script-layout-generator`, `ppt-page-task-remapper`, `ppt-layout-composition-optimizer`, `ppt-template-html-deck-builder`, `ppt-deck-final-qc`, `client-proposal-copy-audit` | story, page role, evidence, visual overflow, client language |
| `evidence-analysis` | source ledger, comparable model, calculations, conclusions, standalone report | `quote-pricing-executor`, `专项分析底表`, `spreadsheets`, `documents`, `echarts-chart-builder` | source lineage, formula reproduction, comparison validity, reader entrypoint |
| `lark-operations` | operating model, object relations, dashboard path, controlled implementation | `team-workflow-system-builder`, `product-manager-architect`, `lark-base`, `lark-doc`, `lark-wiki`, `lark-sheets` | business path, information path, exact target, readback, role usability |
| `document-revision` | revision diagnosis, preservation map, sample, targeted edit | `doc-coauthoring`, `debug-aiwriting`, `client-proposal-copy-audit`, `documents`, `lark-doc` | preservation, audience fit, clean copy, render/readback |
| `spreadsheet-business` | source normalization, business logic, workbook production | `spreadsheets`, `brand-intent-clustering`, `loreal-daily-report`, `专项分析底表` | formulas, units, source coverage, workbook rendering |
| `marketing` | audience/market judgment, communication strategy, content mechanics | `koc-strategy-map`, `changan-hotspot-script`, `client-deck-research-and-assembly`, `client-proposal-copy-audit` | evidence boundary, brand fit, concrete action, client readiness |
| `product-design` | user loop, information architecture, requirements, UX handoff | `product-manager-architect`, `ux-ui-designer`, `ai-product-architecture-review`, `team-workflow-system-builder` | user path, states, MVP boundary, metric and handoff completeness |

`ppt-deck-governance` remains a sub-controller inside the deck pack. It should not become a global controller policy.

Each loadable scenario pack contains:

```yaml
id: string
version: string
match:
  domains: [string]
  artifactClasses: [string]
  exclusions: [string]
blueprintDefaults: object
graphTemplate:
  nodes: [LaneSpec]
  edges: [dependency]
capabilityRequirements: [abstract capability id]
acceptanceCases: [AcceptanceCase]
verifierRequirements: [capability id]
goldenFixtures: [path]
```

Scenario packs are executable only after schema validation and fixture evaluation. Narrative documentation alone is not a registered pack.

`scenario-pack.schema.json` requires all fields shown above, stable IDs for graph nodes and acceptance cases, semantic version, schema version, pack fingerprint, and compatibility ranges for `TaskBlueprint`, `SolutionGraph`, and registry schemas. Loading returns the validated pack, resolved capability requirements, fixture status, source locator, and fingerprint. Duplicate active versions or unresolved compatibility ranges block routing.

## 6. Dynamic Adapters

These remain external because availability, authentication, versions, or provider behavior can change at runtime:

- Lark: `lark-doc`, `lark-base`, `lark-sheets`, `lark-slides`, `lark-drive`, `lark-wiki`, and related atomic adapters.
- Office artifacts: `documents`, `spreadsheets`, `presentations`, `pptx`, and live Excel control.
- Research and browsing: web, browser, Playwright, Chrome, and connected repositories.
- Visual production: image generation, Figma, ECharts, deck builders, and canvas tools.
- Extension fallback: `lark-openapi-explorer` and `lark-skill-maker`, used only when established adapters lack coverage.

The registry binds the abstract capability requested by a scenario pack to a currently active provider.

## 7. Active Version Resolution

The registry must not scan every cache directory as an executable capability set.

Resolution order:

1. host-reported active tools and skills for the current task;
2. installed plugin manifest selected by the host;
3. canonical local skill roots outside plugin caches;
4. explicit user-selected provider;
5. unavailable.

Rules:

- exactly one active version per capability ID;
- inactive cache builds are marked `shadowed`;
- source fingerprint and loaded runtime fingerprint must match for high-risk execution;
- newly installed capabilities become active in a new task/runtime unless the host supports verified hot reload;
- stale MCP processes may continue only against preserved old files and cannot claim the new build ID.

## 8. Routing Order

1. Honor an explicitly named app, URL type, resource token, format, or skill when it satisfies the task.
2. Select the most specific scenario pack whose exclusions do not match.
3. Resolve every abstract graph requirement to candidate capabilities.
4. Filter by input compatibility, runtime availability, permission scope, risk, and verification support.
5. Prefer capabilities that preserve the requested artifact and acceptance semantics.
6. Record selected and rejected candidates with reasons.
7. Require user approval before a route introduces a new high-risk target or changes the final artifact shape.

Specific domain capabilities outrank generic transformation tools. For example, a pricing analysis method should define the comparison model before a generic spreadsheet tool writes the workbook.

## 9. Conflict Handling

| Conflict | Rule |
|---|---|
| two scenario packs match | choose the pack aligned with the final artifact; use the other only as a supporting methodology |
| user-specified tool conflicts with professional validity | narrow the tool role and explain why; do not let the tool define the method |
| two providers produce different artifact semantics | block automatic fallback and ask for a business decision |
| same source priority conflicts | block high-risk execution or request user authority |
| capability metadata is incomplete | allow read-only exploration; prohibit durable writes and final verification claims |
| verifier is the same implementation identity as writer | require an independent verifier for high-risk tasks |

## 10. Missing Capability and Fallback

A fallback is valid only when all are true:

- the final artifact format remains acceptable;
- the business method remains unchanged;
- the alternative can satisfy the same acceptance cases;
- write risk does not increase;
- the user did not explicitly require the missing provider.

Otherwise the router returns a blocker naming the missing capability, why it is required, and what can still be completed safely.

The controller must not silently replace:

- editable PPTX with screenshots when editability is required;
- a real Lark Base implementation with a local mock when the target is production;
- a client-ready report with an internal evidence index;
- domain verification with generic proofreading.

## 11. Example SolutionGraph: Client Deck

```text
hydrate approved client facts and referenced decisions
-> diagnose final artifact as 14-page client-ready presentation content
-> marketing strategy judgment
-> page-task map
-> representative evidence / strategy / execution pages
-> user approval
-> page-by-page client copy
-> optional layout/build capability
-> client-language + evidence + page-role + visual QC
-> delivery
```

Routing notes:

- `koc-strategy-map` or equivalent supports strategy judgment.
- `ppt-script-layout-generator` supports page production only after page tasks are locked.
- `client-proposal-copy-audit` verifies client readiness.
- `debug-aiwriting` improves language but cannot decide strategy or page structure.

## 12. Example SolutionGraph: Pricing Analysis

```text
inventory internal quotes and market channel inquiries
-> classify comparable / weak / excluded samples
-> define delivery-item and unit normalization
-> calculate comparable ranges and time-line changes
-> challenge conclusions against evidence
-> build standalone report and recommendation table
-> reproduce calculations and review reader usability
```

Routing notes:

- a pricing methodology capability owns comparability rules;
- `spreadsheets` owns deterministic extraction and calculation;
- `documents` owns final report production and rendering;
- public web research remains supporting evidence below real channel quotes.

## 13. Example SolutionGraph: Lark Operating Cockpit

```text
read operating rules and current Lark assets
-> diagnose management decisions and role paths
-> model projects, presales, delivery, finance, risks, and documents
-> design first-screen priority and drill-down path
-> build isolated demo and sample records
-> user approval
-> exact Base / Wiki / dashboard writes
-> readback and role-path verification
```

Routing notes:

- `team-workflow-system-builder` owns organization and information-flow design.
- `product-manager-architect` or product pack owns management experience.
- Lark adapters own atomic writes and readback.
- a reviewer validates both business path and information path.

## 14. Verification Contract

Each selected capability must declare at least one applicable verification method. High-risk graphs require a complete chain:

```text
capability selection evidence
-> worker packet fingerprint
-> artifact fingerprint and lineage
-> tool or domain verification results
-> independent review
-> human approval where required
```

Verification classes:

- `structural`: file, schema, units, fields, and required sections;
- `semantic`: claims, business logic, audience fit, and forbidden substitutions;
- `visual`: rendering, overflow, page hierarchy, and legibility;
- `readback`: external target identity, version, content, and links;
- `lineage`: source-to-claim and input-to-output traceability;
- `independent-review`: a separate runtime and appropriate domain method;
- `human-approval`: explicit user decision bound to a current artifact fingerprint.

Provider-backed write verification additionally requires:

- a controller-issued `OperationPermit`;
- provider/runtime fingerprint matching the selected adapter;
- dispatcher execution record;
- provider response and mandatory readback;
- exact target/action/idempotency binding;
- resulting `ArtifactRef` and `VerificationResult`.

Free-text evidence and worker-authored receipts remain compatibility observations, not proof of managed W3/W4 execution.

## 15. Registry Evaluation

Offline evaluation should include:

1. routing accuracy on known scenarios;
2. rejection of superficially similar but wrong capabilities;
3. correct artifact-shape preservation;
4. permission and risk decisions;
5. fallback correctness;
6. route explanation completeness;
7. business outcome acceptance after execution.

Minimum golden scenarios:

- client requests a page-by-page deck but supplies a strategy document;
- report must be standalone despite many internal source files;
- Lark work is discussion-only, then later receives exact write approval;
- spreadsheet calculation and client report need different capabilities;
- required provider is unavailable and no semantic-equivalent fallback exists.

## 16. Initial Registry Rollout

1. Define the schema and manually register the controller kernel plus three scenario packs.
2. Add adapters only for capabilities used in the three golden scenarios.
3. Run the router in shadow mode beside current manual skill selection and compare decisions.
4. Enable enforcement for read-only and draft workflows first.
5. Enable high-risk external writes only after permission, fallback, and verification evaluations pass.

The first executable vertical slice should be `lark-operations`, because it exercises diagnosis, routing, permissions, W3/W4 dispatch, readback, artifact identity, and business path verification in one bounded scenario. Deck and pricing packs can initially run in shadow-routing mode while their verifier contracts are developed.

The registry is a routing contract, not a catalogue page. Its value is measured by whether the system selects the right professional production path and proves why that path is valid.
