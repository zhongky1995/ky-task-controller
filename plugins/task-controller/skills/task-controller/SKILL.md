---
name: task-controller
description: 编排和继续 KY-TASK 管理的多阶段项目，用于用户要求总控、依赖调度、独立工作者、阶段验收，或审计已有 KY-TASK 执行。普通飞书、文档、表格、代码修改以及一般理解和诊断任务本身不需要总控流程。
---

# KY-TASK

## Activation boundary

Choose this controller when the user's intended workflow actually needs coordinated workers or an existing KY-TASK contract. First understand the requested outcome and current context. Tool writes, complexity words, uncertainty or a past failure alone do not require this controller. Ordinary work can use the relevant domain capability directly.

When KY-TASK is selected, preserve its runtime, commercial authority and verification contracts below. This narrower routing does not relax those operational controls or authorize new visible tasks.

## Purpose and responsibility

Own the integrated result throughout authorized work. Inspect and use the evolving artifact, form a professional judgment about whether it serves the user's purpose, and resolve conflicts between contributions. Worker reports, completed contracts and passing gates support this responsibility; they do not discharge it.

When a discovered gap prevents fulfillment of the current commitment, record it as a core question in the existing [inquiry ledger](references/inquiry-ledger.md). Keep it open until evidence resolves the original reason or supports retracting the finding. Usable work and progress do not by themselves authorize overall completion.

Collaborative inquiry develops unresolved understanding and choices. Product and other domain skills develop the substance of a solution. The planner bounds commitments and dependencies. KY-TASK coordinates actual execution and preserves the whole result through changes. These responsibilities can share one owner; they are not a mandatory skill pipeline or fixed team.

Within an established distributed workflow, the controller may read, use, compare and synthesize artifacts without taking over an assigned writer's mutations. Keep tightly coupled professional design and production together where practical. Splitting a task must not split away responsibility for its meaning or quality.

## Preserve The Working Agreement

On continuation, correction, or handoff, restore the current outcome, controller/worker responsibilities, runtime agreement and authority before choosing the next action. A small follow-up does not silently turn an established controller into the implementation owner. Read `references/working-agreement.md` for these transitions and when actual actions disagree with the recorded workflow. Use existing contract, inquiry and worker records; do not create another mandatory form or confirmation phase.

Host instructions take precedence over this plugin's Session preference. Tool availability is not user authorization: visible conversations require an explicit user request for those conversations or an explicitly authorized ongoing conversation-coordination workflow. A generic request to execute, or to use independent workers, does not supply that authorization. Preserve valid task-scoped authorization across turns; if the required runtime is unauthorized or disallowed, report the precise conflict rather than silently using subagents. This plugin cannot intercept host tool calls made outside its protocol.

KY-TASK role model:

- `KY-TASK00-总控-任务伙伴` is the fixed user-facing controller.
- `KY-TASK01+` lanes are dynamically generated for the actual task.
- A registered distributed lane must use a real independent worker runtime.
- This distribution uses `runtimeSelectionPolicy: native_session_required` for distributed work.
- Every distributed lane therefore uses a visible `native_thread_lane`; managed subagents are not the silent fallback.
- This distribution also uses `projectAffinityPolicy: inherit_or_resolve_required`.
- Every native worker Session must be created with a saved Codex `projectId`; silent `projectless` creation is forbidden.
- The open-source distribution ships without standing approval. Before creating sidebar-visible KY-TASK worker Sessions, obtain explicit approval for the current task and record `executionPolicy.nativeThreadUserApproved: true`.
- Both runtimes are real workers. `single_thread_section` is only a documented fallback, not an equivalent worker.

Runtime is subordinate to the controller contract:

- KY-TASK must first decide which professional responsibilities must be isolated.
- It then chooses whether each worker is `ephemeral` or `persistent`.
- `ephemeral` defaults to `contextPolicy: packet_only` and still runs in its own visible native Session under the Session-first policy.
- `persistent` requires `contextPolicy: checkpoint_delta` and a native Session that can be resumed across controller turns.
- Lifecycle controls context retention; runtime visibility is controlled separately by `runtimeSelectionPolicy`.
- Use `lane_lifecycle` only when the user explicitly asks to restore managed-subagent behavior for a task.

Steps, lanes, dispatch attempts and Sessions are different objects. Use the smallest useful set of professional responsibilities, not one Session per action or checkpoint. Prefer a continuing `persistent` Session for related execution and correction work, and a separate continuing reviewer where independent review is required. Serial lanes may reuse a compatible idle Session; a new revision requires fresh evidence/attempt identity, not automatically a new conversation. Read `references/dispatch-and-recovery.md` before reuse. A one-turn task may justify isolation, but turn count alone neither requires nor forbids a Session. Before adding one, state the isolation, parallelism or context benefit and why reuse is unsuitable; this is a controller decision, not another user confirmation form.

Parallelism is dependency-driven:

- Every new lane definition must include `dependsOn`.
- `dependsOn: []` means the lane is immediately eligible to run beside other ready lanes.
- Lanes that share a write target must be serialized by dependencies; independent read/research/design lanes should not be serialized merely by list order.
- Missing `dependsOn` is accepted only for legacy states and preserves the historical ordered-lane chain.
- Total Lane count is not capped. Dispatch the full ready frontier, up to `maxParallelWorkers` (distribution default: 4; explicit task maximum: 10), before waiting for any worker.
- If nine or ten Sessions are active, keep them all active and coordinate waits in stable batches of at most eight targets per host wait call.

Orchestration is a first-class control stage, not a side effect of lane order:

- Keep four decisions separate: task decomposition -> work orchestration -> lane-level capability matching -> lifecycle/runtime selection.
- Before Session creation, compile a strict `OrchestrationPlan` with `task_controller_plan_orchestration`.
- Every multi-lane plan declares one `semanticOwner`, and every lane declares `contributionRole`, `semanticAuthority`, `purpose`, `dependsOn`, and the reason for each serial edge.
- Classify lanes as `primary`, `prerequisite`, `supporting`, or `verification`. Supporting work must feed the primary path; verification must consume the decision, sample, or artifact it judges.
- Use `inputContracts` and `outputContracts` to derive dependencies. List position is never a valid dependency reason.
- Match capabilities from each lane's actual job, inputs, outputs, write boundary, and acceptance role. Do not copy a globally matched domain skill onto every lane.
- Suggestions are planning drafts, not bindings. Unknown host availability requires explicit discovery evidence before dispatch admission.
- Assess handoff loss before splitting design from production. High-loss work stays in one `define-and-implement` lane unless a concrete artifact handoff contract preserves the judgment.
- Runtime selection happens only after orchestration passes. A clean Session executes the graph; it does not make a wrong graph correct.

## Bound and develop the work

Use the task-boundary planner only when scope, responsibility or consequential dependencies need clarification. Restore an existing effective agreement instead of producing it again. The planner does not require every domain decision to become a form or prerequisite document.

Read [continuous execution](references/continuous-execution.md) when evidence, feedback or production changes the direction. Develop the most consequential uncertain judgment in a concrete part of the artifact when useful, then use that result to refine the larger work. Do not add a universal sample, review or approval phase. Required sample, commercial, independent-review and runtime gates still apply.

For consequential cross-turn inquiry in managed work, use the existing checkpoint described in [inquiry ledger](references/inquiry-ledger.md); maintain it at meaningful changes, not every reply. It preserves concise current understanding and evidence, not a second product specification or private reasoning transcript.

## Controller Rules

- Throughout production, inspect the actual integrated result and reconcile contributions against its intended use. Resolve the cause of poor results, preserve effective decisions and existing quality, and retain evidence appropriate to consequential claims. Reuse valid checks; do not replace professional judgment with another review round.
- Give workers bounded jobs with enough whole-project context to judge their contribution: original concern/source, intended use, relevant relationships and unresolved premises. A narrow write scope does not imply a context-free task. Preserve the distinction between user requirements and the controller's interpretation.
- Do not let multiple lanes write the same final artifact.
- Evidence and design workers may create their assigned research, draft or prototype artifacts. Changes to production targets require an explicit execution write boundary; a lane name alone grants no write authority.
- Implementation writes only to the approved target.
- Every registered worker should include a lane-specific `toolProfile`; every external-write worker should also include a `credentialPolicy` and `threadToolCheck` in the registration notes/state.
- Any lane that writes external or durable assets, including schema repair, view configuration, document edits, record import, dashboard changes, code edits, or workbook/deck writes, is an execution lane.
- When an eligible worker runtime is available and split execution is mandatory, execution lanes must use `managed_agent_worker` or `native_thread_lane`; the controller may not run them as `single_thread_section`.
- In distributed execution, the controller owns understanding, evidence assessment, orchestration, synthesis, callback/gate recording and stop/recovery coordination. It must not take over the assigned implementation worker's external writes; synthesizing the user-facing conclusion is part of its job, not a prohibited implementation shortcut.
- Required independent review must be separate from implementation; ordinary checks do not each require a reviewer lane. Apply the decision rules in `references/working-agreement.md`.
- Commercial authority must be explicit: `locked`, `agent_may_decide`, or `propose_then_confirm`. Client-facing pricing structure, billable items, budget allocation, KPI binding, scope commitments, and contract terms default to `propose_then_confirm`.
- A client-facing pricing workbook must use the `client-pricing` scenario graph. Do not start workbook architecture until the evidence-backed commercial model has passed an independent decision review and the user has approved its exact fingerprint.
- A missing worker runtime does not authorize fallback. Apply `references/working-agreement.md`; record an authorized policy change and its reason before changing execution mode.
- Do not bind to a specific multi-agent plugin unless the user explicitly requests it and callable tools are available.
- Do not ask the user which workers they want. Propose a role map from the task, materials, risks, tools, write boundaries, and acceptance criteria.
- A background lane must callback to `KY-TASK00`; a final answer inside the background thread is not enough.

## Execution Decision

Read `references/working-agreement.md` before initial mode selection and on continuation/correction. Its decision rules are the single source for when to use direct work, sequential checkpoints or distributed workers; scenario examples and workflow templates do not override them.

State the chosen responsibility split and its benefit briefly when it changes. Keep detailed admission records internally, not as recurring user forms. Once distributed execution is selected and authorized, use the installed Session-first policy and project affinity; unavailable permissions or tools are a blocker, not automatic permission for a different runtime.

Read `references/controller-protocol.md` when preparing the controller plan or handoff.
Read `references/lane-contracts.md` when generating lane prompts or checkpoints.
Read `references/work-orchestration.md` for every new composite lane map, generic no-pack task, dependency correction, or failure involving wrong parallel/serial order.
Read `references/session-orchestration.md` when the task needs distributed execution, worker prompts, thread dispatch, or worker result merge.
Read `references/codex-thread-adapter.md` when checking, creating, messaging, or recovering Codex Desktop worker threads.
Read `references/dispatch-and-recovery.md` before creating/replacing a worker, handling a creation timeout, or continuing after correction.
Read `references/business-delivery-presets.md` for client page decks, evidence-led analysis, Feishu Base/dashboard/Wiki delivery, or revision of an existing document.

## Controller Workflow

This is the distributed execution workflow, after mode and authority have been
resolved through `references/working-agreement.md`. Direct work does not need
project discovery or a full lane graph merely to satisfy this template.

1. Confirm the locked contract or produce a compact controller contract.
2. Resolve project affinity:
   - call `list_projects`;
   - inherit the controller's saved `projectId`, or resolve one deterministic path match;
   - lock `targetProjectId`, optional `targetProjectPath`, and `projectResolutionSource`;
   - stop for user selection when no unique saved project exists.
3. Compile work orchestration:
   - define the one semantic owner and the primary path;
   - classify prerequisite, supporting, primary, and verification work;
   - derive dependencies from artifact/decision/sample consumption;
   - state a reason for every serial edge and identify the parallel waves/join points;
   - match capability requirements per lane;
   - run `task_controller_plan_orchestration` with `orchestrationPolicy: strict` and fix all blockers.
4. Choose execution mode:
   - `single-thread lanes`: current thread runs each lane sequentially.
   - `distributed`: visible native Session workers produce lane artifacts.
5. Create the accepted lane map.
6. For each lane, state:
   - input
   - output
   - write boundary
   - forbidden actions
   - pass gate
   - `dependsOn`
7. Call `task_controller_ready_lanes`; atomically claim each selected lane with `task_controller_claim_dispatch` before host creation.
8. For each newly admitted attempt (`creationAction: create`), first check for a compatible idle Session; create one with `target.type: project` and the locked `projectId` only when reuse is unsuitable. Reconcile repeated/uncertain claims without creating or messaging again blindly.
9. Verify project affinity, then register the actual thread with its `claimId`, `requestId`, `projectId`, and `projectEnvironment`. Admit the whole available frontier before waiting.
10. Wait on the batch together; record callbacks and lane checkpoints as workers finish.
11. Refill freed capacity from the newly ready frontier.
12. Final review checks project affinity, source lineage, user path, write boundary, stale-version contamination, and acceptance cases.

## Decomposition and continuity

Split by useful responsibilities and actual dependencies, not document titles or stage labels. Each contribution needs a consumer; closely coupled design and implementation should retain their professional judgment across revisions. The primary owner and controller remain responsible for how the result works as a whole.

Apply [working agreement](references/working-agreement.md) for execution mode, [work orchestration](references/work-orchestration.md) for the graph, and [dispatch/recovery](references/dispatch-and-recovery.md) for attempt and Session reuse. These are the maintained operational sources; do not infer a new team or conversation from each corrective step.

## Local State Helper

Use `scripts/task_controller_state.py` when useful to keep lane status outside chat memory.

Typical commands:

```bash
python3 scripts/task_controller_state.py plan-orchestration --lane-definitions @lane-definitions.json
python3 scripts/task_controller_state.py init --state /tmp/controller.json --goal "Approved task goal" \
  --lane-definitions @lane-definitions.json --execution-policy @execution-policy.json \
  --task-blueprint @task-blueprint.json
python3 scripts/task_controller_state.py status --state /tmp/controller.json
python3 scripts/task_controller_state.py ready-lanes --state /tmp/controller.json
python3 scripts/task_controller_state.py next-lane --state /tmp/controller.json
```

`task_controller_init` accepts `contract`, either `lanes` or explicit `laneDefinitions`, and `executionPolicy`. Lane definitions can lock `workerLifecycle`, `contextPolicy`, `runtimePreference`, and `dependsOn`. The policy locks `splitRequirement`, `mode`, `eligibleRuntimes`, `downgradeReason`, `requiredWorkerLanes`, `independentReviewRequired`, `runtimeSelectionPolicy`, `nativeThreadUserApproved`, `maxParallelWorkers`, `projectAffinityPolicy`, `projectlessUserApproved`, `targetProjectId`, `targetProjectPath`, and `projectResolutionSource`. Mandatory work with an eligible real runtime cannot initialize as `direct` or `sequential_lanes`; a no-runtime fallback requires an explicit downgrade reason. Under the Session-first policy, distributed native initialization also fails until a saved project is resolved.

Prepare the JSON files above from the actual approved contract, not a fixed role template. For any new composite lane map, use `plan-orchestration` first. It returns parallel waves, justified serial edges, join points, semantic ownership, handoff blockers, and lane-level capability routes without dispatching workers. New initialization defaults to strict even when fields are missing; it never silently opts into legacy. Missing or blank declarations must be supplied. Existing states remain readable; a deliberate old-contract import must explicitly set `orchestrationPolicy: legacy`.

For a new `TaskBlueprint`, use `plan-blueprint` to read-only compile the routing decision, formal `SolutionGraph`, `OrchestrationPlan`, projected lanes, and `WorkerPackets`. It never dispatches workers. `init --task-blueprint --auto-plan` persists that plan and uses its lane projection when no `laneDefinitions` are supplied. A graph-backed worker registration and callback must include the current packet ID and digest; workers are not dispatched automatically by planning or initialization.

For change-policy items, set `authority` only when the user has actually fixed that boundary. Preserve and forbidden items are always `locked`. Ordinary allowed edits default to `agent_may_decide`; commercially material allowed edits default to `propose_then_confirm`. Scenario policy may inject mandatory acceptance cases and a fingerprint-bound approval gate into the effective Blueprint. Treat those applications as control policy, not optional suggestions.

The helper records state only. It does not create threads, call Feishu, or write final artifacts.

### TaskBlueprint and shadow routing

`TaskBlueprint` is the canonical semantic judgment for blueprint-based work. Use the helper to inspect its deterministic schema-v2 projection before initialization:

```bash
python3 scripts/task_controller_state.py compile-blueprint \
  --task-blueprint @task-blueprint.json \
  --lane-definitions @lane-definitions.json
```

`init --task-blueprint` compiles after lane definitions are fixed and stores the blueprint, digest, traceability, executable flag, and compiled `contractSpec`. In semantic-strict risk execution, a non-executable compilation fails initialization. When both `--task-blueprint` and `--contract-spec` are supplied, the normalized contract must exactly match the compiled projection; the blueprint remains canonical. Blueprint-based strict revisions use `revise-contract --task-blueprint` so lineage is retained. Existing hand-authored `contractSpec` states remain supported.

Use `route-capabilities --task-blueprint --active-capability-ids ...` or the corresponding MCP tool only for read-only shadow suggestions. Shadow routing never registers a worker, grants authorization, invokes a provider, or writes controller state. The controller must still apply the locked lane, runtime, callback, approval, and write-policy gates before any execution.

### Structured-v1 operation gate

New auto-planned `TaskBlueprint` / `SolutionGraph` state uses the `structured-v1` hard gate. For an `approved-target` lane, the sequence is fixed:

1. Claim dispatch, create the host worker, and register it with its `claimId` and current `WorkerPacket` identity.
2. Issue an `OperationPermit` with `task_controller_issue_operation_permit` for the packet-allowlisted capability, target, action, payload, and readback plan.
3. Dispatch that permit with `task_controller_dispatch_operation`; only the restricted dispatcher can create the ledger `OperationReceipt`.
4. If dispatch was interrupted after its claim was persisted, use `task_controller_reconcile_operation`; this performs readback only and never repeats the write.
5. Record manifest-bound verification results with `task_controller_record_verification_result` or in the callback.
6. Record the callback with `operationReceiptIds`, artifact manifest/fingerprint, target version, and dispatcher readback fingerprint; then run independent review and finalization.

An `approved-target` structured pass requires `OperationPermit` + dispatcher-generated consumed `OperationReceipt` + accepted verification results. Free-text evidence and legacy `writeReceipt` cannot satisfy it. `writeReceipt` remains available only for manual legacy, non-structured state.

Semantic and business cases must declare an external verifier and cannot be self-attested. High-risk work still requires independent review by a distinct worker/runtime. A contract revision invalidates affected prior receipts, artifact manifests/fingerprints, verification results, callbacks, and approvals; affected lanes must register and dispatch against current identities again.

`MemoryTestAdapter` is test-only and must never be used in production. `lark-cli` accepts only typed allowlisted operation descriptors (`operation`, `identity`, `resource`, `input`). The adapter compiles the command and binds resource tokens to the approved locator; callers cannot provide argv, shell, environment, working directory, executable, delete command, or a replacement target. Unsupported operations fail closed. KY-TASK cannot technically block a direct external-tool bypass, but that write has no valid receipt or verification result and cannot pass callback, review, or finalization gates.

### Semantic enforcement

Schema version remains `2`. Contract spec `2.x` adds the strict business-delivery contract: `interactionMode`, audience/use/standalone/artifact class, optional units/package, source priority, binding decisions, user approval, and exact write policy.

- A task with any `approved-target` lane, or with `independentReviewRequired: true`, defaults to `semantic_strict`.
- An explicit `workflow_only` downgrade for such a risk task requires a non-empty `semanticDowngradeReason`.
- A newly inserted lane with `kind: review` or `writeBoundary: review-only` is also treated as semantic risk. In `workflow_only`, `task_controller_insert_lane` rejects it unless the existing state has a non-empty `semanticDowngradeReason`.
- Insertion does not auto-enable `executionPolicy.independentReviewRequired`. That policy activates writer coverage and independent-runtime gates and must be locked only when the lane map contains the required implementation and review roles.
- A legacy schema-v2 file without `enforcementMode` remains readable through `status` and `list-workers` without rewriting it. If it has an `approved-target` lane or `independentReviewRequired: true`, every mutation, registration, gate, completion, callback, correction, and revision must fail with semantic migration/upgrade required until the state is explicitly migrated.
- `semantic_strict` requires a complete `contractSpec`: `specVersion`, one deliverable with `id/kind/target/format`, non-empty `canonicalSources`, and arrays for `preserve`, `allowedChanges`, `forbidden`, and `acceptance`. IDs are unique; lane and sample-gate references must resolve.
- The helper computes `deliverableFingerprint` and revision-bound `contractDigest` with canonical JSON SHA256. If a fingerprint is supplied, it must match.

Strict worker registration must send the current `contractRevision`, `contractDigest`, and `deliverableFingerprint`. A strict pass callback must repeat both hashes and include a non-empty `artifactManifest` plus complete `checkResults`. Contract spec 2.x manifests cover every declared unit; self-contained packages include an `entrypoint`. Binding decision-ledger items are required checks.

`discuss_only` and `plan_only` prohibit registration, gate, callback pass, and completion of `approved-target` lanes. `execute` requires a matching `writePolicy`. Manual legacy contract-spec 2.x approved-target passes use a matching `writeReceipt`; structured-v1 requires the permit, dispatcher receipt and verification chain described above.

When `userApprovalGate.required` is true, record approval with `record-approval` against the exact current-revision artifact fingerprint before any blocked lane. A correction makes current approvals stale and open corrections continue to block progress.

When `sampleGate.required` is true, the sample lane must be current-revision `done/pass`, including its named `acceptanceIds`, before any lane in `blocks` can register, gate, callback-pass, or complete.

If a worker finds a confirmed contract-impacting correction or contradictory evidence, it must submit a `correctionEvents` entry with an explicit `recommendedInvalidFromLane`; that callback cannot pass. The controller must assess meaning and affected premises, not just correction keywords. `task_controller_classify_feedback` is read-only heuristic assistance: quoted/negated correction words and diagnostic questions can be false positives, and evidence without keywords can be missed. For confirmed impact, use `task_controller_ingest_feedback` when its classification matches the actual change, or `task_controller_record_correction` with evidence and affected requirements when it does not. Do not ignore an actual change or dispatch dependent work while its material impact remains unresolved. Then call `task_controller_revise_contract` to consume every open event ID, using an `invalidFromLane` no later than the earliest recommendation. Every open correction blocks registration, gates, and completion; a false positive already ingested must also be resolved through revision, not bypassed. Strict revision always supplies the complete replacement `contractSpec`; proactive revision without a correction is still allowed. See `references/continuous-execution.md`.

This state machine is not a security sandbox. It cannot stop a controller or worker that bypasses KY-TASK and directly calls an external write tool. It only makes KY-TASK-managed dispatch, registration, callback pass, gate, and completion fail closed. Controller prompts and operating discipline must prohibit direct-write bypasses.

Mutating CLI commands use an advisory file lock across their complete read-modify-write cycle, and state replacement is atomic. This prevents lost updates between cooperating controller processes; the JSON checkpoint is still not a distributed transaction database.

## Worker registration and callbacks

Use current callable MCP schemas or the state helper for status, claims, registration, callbacks, corrections and finalization. The distributed workflow above and [session orchestration](references/session-orchestration.md) define their ordering; do not initialize another workflow for the same work.

Insert newly required correction or review lanes with `task_controller_insert_lane` rather than hand-editing state. A required gate must pass before its dependent action. Verify actual host state when dispatch or callbacks are interrupted.

Worker registration is incomplete unless it includes:

- `runtimeHandle` for every real worker. Managed workers use the returned agent/session handle.
- both an explicit `threadId` and `runtimeHandle` for `native_thread_lane`; both values must be the same Codex thread id so recovery and worker location use one identity.
- `projectTargetType`, `projectId`, and `projectEnvironment` for every native worker. Under strict project affinity, target type is `project`, `projectId` must equal `executionPolicy.targetProjectId`, and environment is `local` or `worktree`.
- non-empty `requestId`.
- the pre-creation `claimId` for independent workers in new strict states.
- `controllerThreadId` and `replyToThreadId`: native `active_message_required` workers must use the real user-facing controller thread id. Managed workers may leave them empty or use a stable logical controller identifier such as `KY-TASK00`; a logical identifier must not be represented as a native thread id.
- `callbackExpected: true`.
- `callbackModeExpected`: `active_message_required` under the native Session policy; `managed_result_collected` only under an explicit managed-worker override.
- `toolProfile`, describing the worker's expected tool surface.
- for `approved-target` workers, a `credentialPolicy` that names required credentials/scopes, optional credentials/scopes, and safe fallback behavior.
- `threadToolCheck`, recording the worker capability check. It may describe managed-agent availability even though the historical field name says "thread".
- in `semantic_strict`, the current `contractRevision`, `contractDigest`, and `deliverableFingerprint`.

If any field required by the selected runtime and callback mode is missing, the controller must repair the registration before waiting for callbacks.

If a worker is replaced by a new native worker, update the old worker to `superseded` with notes that identify the replacement `requestId` and thread. Do not mark a replaced worker as `done/pass` merely to unblock a gate.

If a worker's negative callback is fixed by a later lane, update the old worker to `resolved` with notes identifying the repair/review lane. Do not rewrite the original finding as if it had passed at the time.

Do not assume that a final answer inside a worker thread automatically updates KY-TASK state. The controller owns callback collection. A callback is complete only after `task_controller_record_callback` is called and `task_controller_gate_check` sees it.

Callback mode rules:

- `active_message_required`: the worker must use thread messaging to send the callback to `replyToThreadId`. If the controller later recovers the result by reading the worker thread, record `callbackModeObserved: controller_poll_recovery`; this should block or warn according to the gate instead of looking like a normal callback.
- `active_message_preferred`: active callback is expected, but controller polling is allowed as a degraded recovery path and must be reported.
- `controller_poll_allowed`: use only when thread messaging is unavailable or the host explicitly cannot support worker-to-controller messaging.
- `managed_result_collected`: the controller received the result from a distinct managed-agent invocation; this is a real worker callback, not a single-thread checkpoint.

## Completion And Revision Guards

`task_controller_complete_lane --decision pass` is guarded. It requires a non-empty lane artifact, all upstream lanes to be current-revision `done/pass`, and every applicable current worker to be `done/pass` with an artifact and accepted callback mode. A `workerRequired` lane cannot pass without a registered real worker and callback.

In `semantic_strict`, completion uses the same semantic callback guard as `record-callback`; manually setting lane or worker status cannot substitute for a manifest and complete passing evidence.

Each review worker names the current workers in its compiled `verificationSubjects` through `reviewsWorkerIds`, using a different `runtimeHandle`. An `intermediate-artifact` review derives subjects from the producers of its `inputContracts`; independent branches and future production are not subjects. Final review covers all final writers. Historical legacy states retain their earlier-writer scope. Coverage is enforced when entering/completing review and at finalization. Strict semantic callbacks still require their configured acceptance evidence; changing scope does not waive independent review or write authorization.

When the user changes a locked contract term, call `task_controller_revise_contract` with the earliest `invalidFromLane`. It increments the revision and invalidates affected outputs/callbacks. Current invalidation is still an ordered suffix, not dependency-local graph migration. The resulting `stale` lanes re-enter the ready frontier once dependencies pass and old execution is reconciled. A still-running superseded worker retains capacity until host stop evidence is recorded. Follow `dispatch-and-recovery.md`; do not reuse stale evidence or blindly retry `needs-work` / `blocked` work.

## Tool Profile And Credential Policy

KY-TASK write boundaries are not enough on their own. Execution workers also need a lane tool profile so the controller can predict sandbox, credential, and external-permission issues before the worker is halfway through a write.

Typical tool profiles:

- `read-only-evidence`: local files, Feishu read APIs, no durable writes.
- `lark-base-schema-write`: Feishu Base fields, options, views, formulas, relation fields.
- `lark-base-record-write`: Feishu Base records, record-to-record links, row updates.
- `lark-doc-write`: Feishu Docx/Wiki page creation or edits.
- `lark-drive-search-optional`: Drive/Doc search used only to enrich links; not required for the core gate.
- `review-only`: readback and acceptance checks only.

For external-write workers, the worker prompt must state:

```text
tool_profile:
credential_policy:
  required:
  optional:
  fallback:
  blocker_if:
```

Credential policy rules:

- Required credentials or scopes must be checked before the first durable write when practical.
- Optional enrichment tools must not block the lane if the core acceptance can pass without them.
- If a tool requires macOS Keychain, a browser login, extra Feishu scope, or another host-level approval, the worker must classify it as `required` or `optional` before attempting a workaround.
- If optional access fails, continue with the approved fallback and report the risk in the callback.
- If required access fails, stop with a `blocker` callback before partial writes unless the prompt already defined a safe partial-write path.
- Do not request broad sandbox or credential escalation merely to enrich demo links. For example, a project document link search can be optional if the project title and Base relationship are enough for the sample gate.

Sandbox/credential issue wording:

- Treat this as a tool-profile and credential-scope issue, not as a reason to downgrade from distributed execution.
- A worker thread can be valid while one specific command is blocked by Keychain or missing Feishu scope.
- The controller should update state with the worker's fallback or blocker; it should not take over the external write in the controller thread.

## Handoff and reporting

Use [lane contracts](references/lane-contracts.md) and [session orchestration](references/session-orchestration.md) for worker packets and exact callback fields. Keep user-facing updates about substantive decisions, outcomes and remaining limitations; internal admission records need not become recurring forms.

Thread creation belongs to the host runtime; KY-TASK records and guards the managed workflow. The local state helper does not create workers or make external writes. Preserve the installed project and runtime policies.

## Failure Rules

- If the final artifact is being written before upstream lane gates exist, stop and create the missing lane artifact.
- If verification or QA is scheduled before the decision, sample, or artifact it judges, reject the plan and move/reclassify that lane before dispatch.
- If missing dependencies are being interpreted as list-order serialization, stop and compile an explicit strict orchestration plan.
- If design and production have high handoff loss, merge them into one primary lane or create a concrete artifact handoff contract.
- If one capability was assigned from the overall domain rather than the lane's actual job/input/output, reroute capabilities per lane.
- If a worker output lacks source lineage, do not merge it into the final artifact.
- If old-version artifacts are visible in a clean demo, fail review.
- If implementation passes API checks but fails the user path, the task is not done.
