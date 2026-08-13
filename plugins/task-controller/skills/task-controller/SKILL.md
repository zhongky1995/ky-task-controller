---
name: task-controller
description: KY-TASK controls complex Codex work after or around a task contract. Use when the user wants a 总控 Agent, visible multi-Session execution, dependency-aware parallel lanes, worker prompts, lane checkpoints, clean execution of Feishu/Base/dashboard/document/code tasks, or review of whether a prior run followed the agreed lanes. This skill coordinates execution but does not replace domain skills such as lark-base, lark-doc, spreadsheets, or code skills.
---

# KY-TASK

## Purpose

Act as KY-TASK, the controller for complex work. Preserve the task contract, split execution into lanes, prevent premature final writes, and verify that each lane produces the artifact needed by the next lane.

This skill is not a general executor. It coordinates domain tools and skills.

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

Parallelism is dependency-driven:

- Every new lane definition must include `dependsOn`.
- `dependsOn: []` means the lane is immediately eligible to run beside other ready lanes.
- Lanes that share a write target must be serialized by dependencies; independent read/research/design lanes should not be serialized merely by list order.
- Missing `dependsOn` is accepted only for legacy states and preserves the historical ordered-lane chain.
- Dispatch the full ready frontier, up to `maxParallelWorkers` (distribution default: 4), before waiting for any worker.

## Use With Task Boundary Planner

- If no task contract exists, first create or request one. If `task-boundary-planner` is available and relevant, use it to lock the contract.
- If a contract already exists and the user says to continue, do not replan. Dispatch the next dependency-ready batch.
- If the user asks why a previous execution failed, compare the run against the lane gates and write-boundary rules.

## Controller Rules

- One controller owns the final answer and final verification.
- Workers or lanes receive narrow tasks, not the whole project.
- Do not let multiple lanes write the same final artifact.
- Evidence, object/model, metric/chart, and product/experience lanes are normally read-only.
- Implementation writes only to the approved target.
- Every registered worker should include a lane-specific `toolProfile`; every external-write worker should also include a `credentialPolicy` and `threadToolCheck` in the registration notes/state.
- Any lane that writes external or durable assets, including schema repair, view configuration, document edits, record import, dashboard changes, code edits, or workbook/deck writes, is an execution lane.
- When an eligible worker runtime is available and split execution is mandatory, execution lanes must use `managed_agent_worker` or `native_thread_lane`; the controller may not run them as `single_thread_section`.
- The controller may perform only emergency stop messages, callback collection, gate recording, and user-facing merge decisions. It must not use its own thread as the implementation worker for external writes.
- Review must be separate from implementation.
- Commercial authority must be explicit: `locked`, `agent_may_decide`, or `propose_then_confirm`. Client-facing pricing structure, billable items, budget allocation, KPI binding, scope commitments, and contract terms default to `propose_then_confirm`.
- A client-facing pricing workbook must use the `client-pricing` scenario graph. Do not start workbook architecture until the evidence-backed commercial model has passed an independent decision review and the user has approved its exact fingerprint.
- If no real worker runtime is available, record a non-empty downgrade reason before emulating the lanes sequentially in the current thread.
- Do not bind to a specific multi-agent plugin unless the user explicitly requests it and callable tools are available.
- Do not ask the user which workers they want. Propose a role map from the task, materials, risks, tools, write boundaries, and acceptance criteria.
- A background lane must callback to `KY-TASK00`; a final answer inside the background thread is not enough.

## Split Decision Rule

Before execution, KY-TASK must decide whether the task should run as direct single-thread work, sequential gated lanes, or distributed worker execution.

Output a compact split decision when the task is complex, user-facing, tool-writing, or previously failed:

```text
拆分判断
- 结论: direct / sequential-lanes / distributed
- worker runtime check:
  - checked:
  - available:
  - decision:
- 命中规则:
- 不拆的代价:
- 执行模式:
- lane map:
- 唯一写入 lane:
- callback / gate:
```

### Hard Distributed-Execution Gate

If any mandatory split rule is hit, KY-TASK must check for independent worker runtimes before choosing an execution mode.

If an eligible real worker runtime is available and the user has approved execution, the result must be `distributed`. Do not choose `sequential-lanes` just because it is faster, simpler, or easier to merge. The stored legacy value `multi_session` remains accepted but should not be used for new plans.

For this Session-first policy, check Codex Desktop project/thread tools such as `list_projects`, `create_thread`, `send_message_to_thread`, and `wait_threads` first. Resolve and lock `targetProjectId` before initializing distributed state or creating workers. If the controller already belongs to a saved project, inherit that project. Otherwise match the effective workspace/material path to the deepest saved project path; if there is no unique match, ask the user. If native thread creation or project resolution is unavailable, stop and report the blocker. Do not silently substitute managed subagents or create a `projectless` Session. `lane_lifecycle` and `allow_projectless` are explicit per-task overrides, not automatic fallbacks.

Until this check is recorded in the split decision, KY-TASK must not enter implementation, create Feishu/Base/docs/deck/code artifacts, or claim that execution has started.

`sequential-lanes` is allowed after a mandatory split rule only when one of these is true:

- independent worker runtimes were checked and are unavailable in the current host;
- the user explicitly rejects background worker execution;
- the current turn is planning-only and no final artifact will be written;
- the task is explicitly scoped to a narrow local edit or focused explanation despite earlier context.

When any mandatory split rule is hit and a real worker runtime is available, these responses are invalid:

- `结论: sequential-lanes`
- `先在当前线程继续做`
- `不开多线程`
- `先预检查后直接搭`
- any plan that performs evidence, modeling, product design, implementation, and review in one uninterrupted current-thread run.

Use `distributed` when any mandatory split rule is hit and a real worker runtime is available:

- The user explicitly asks for split conversations, worker Sessions, subagents, multi-lane execution, or says not to run everything in one thread.
- A prior run failed because evidence, modeling, product design, implementation, and review were collapsed together.
- The work writes to external systems or final artifacts such as Feishu Base, Feishu docs, decks, workbooks, repos, client-facing files, or production assets.
- The task requires three or more professional layers, such as evidence intake, object/model design, metric design, product/experience design, implementation, and review.
- Data correctness and user experience/product path both materially affect acceptance.
- Independent review is needed because the output is executive-facing, client-facing, financial, operationally sensitive, or hard to undo.

Use `sequential-lanes` only for recommended split cases where real independent workers would add more merge cost than value, or as the explicit fallback described above.

Use `direct` only for small local tasks such as one wording fix, one file edit, one chart label correction, a concept explanation, or a clearly bounded follow-up.

## Anti-Downgrade Rule

If the user has requested distributed execution, split conversations, independent workers, or complained that a prior execution failed because it was not split, KY-TASK must not silently downgrade to single-thread execution.

On later confirmations such as `继续`, `好`, `进执行`, `按这个做`, or `优化吧`, treat the message as approval to continue the already agreed split plan unless the user says not to execute.

If native thread tools are available, dispatch the entire dependency-ready batch as visible Sessions. If they are unavailable, say so explicitly. Under `native_session_required`, do not use a sequential or managed-worker fallback without a fresh user-approved policy override:

```text
原计划: distributed
当前限制: thread tools unavailable / not approved / task too small
降级方式: sequential-lanes
差异: worker 变成当前线程 checkpoint，不再是真实子对话 callback
```

If the user explicitly required real separate conversations, stop and ask for the missing thread capability or permission instead of pretending sequential lanes are equivalent.

If a referenced or resumed task matches the mandatory split rules, do not rely on the prior thread's last execution mode. Re-evaluate the split decision under this rule and correct any earlier downgrade before continuing.

Read `references/controller-protocol.md` when preparing the controller plan or handoff.
Read `references/lane-contracts.md` when generating lane prompts or checkpoints.
Read `references/session-orchestration.md` when the task needs distributed execution, worker prompts, thread dispatch, or worker result merge.
Read `references/codex-thread-adapter.md` when checking, creating, messaging, or recovering Codex Desktop worker threads.
Read `references/business-delivery-presets.md` for client page decks, evidence-led analysis, Feishu Base/dashboard/Wiki delivery, or revision of an existing document.

## Controller Workflow

1. Confirm the locked contract or produce a compact controller contract.
2. Resolve project affinity:
   - call `list_projects`;
   - inherit the controller's saved `projectId`, or resolve one deterministic path match;
   - lock `targetProjectId`, optional `targetProjectPath`, and `projectResolutionSource`;
   - stop for user selection when no unique saved project exists.
3. Choose execution mode:
   - `single-thread lanes`: current thread runs each lane sequentially.
   - `distributed`: visible native Session workers produce lane artifacts.
4. Create lane map.
5. For each lane, state:
   - input
   - output
   - write boundary
   - forbidden actions
   - pass gate
   - `dependsOn`
6. Call `task_controller_ready_lanes` and dispatch every returned lane, bounded by `maxParallelWorkers`.
7. Create all Session workers with `target.type: project` and the locked `projectId` before waiting for any one of them.
8. Verify each created thread reports the same `projectId`, then register it with `projectId` and `projectEnvironment`.
9. Wait on the batch together; record callbacks and lane checkpoints as workers finish.
10. Refill freed capacity from the newly ready frontier.
11. Final review checks project affinity, source lineage, user path, write boundary, stale-version contamination, and acceptance cases.

## Actual Task Decomposition

When the task cannot be completed reliably in one uninterrupted flow, split by real work type, not by arbitrary step labels.

Typical split:

- Evidence worker: source ledger and evidence status.
- Model worker: objects, fields, state machines, source-to-target mapping.
- Product worker: user path, first screen, unit contracts, drill-down design.
- Implementation worker: the single approved writer for the final artifact.
- Review worker: independent acceptance check.

The controller must state which lanes are independent, which lanes depend on prior outputs, and which lane is allowed to write the final artifact.

When distributed execution is approved, the controller must dispatch visible native Codex Session workers. Do not use managed subagents under the installed `native_session_required` policy. Run lanes sequentially only after the user explicitly overrides that policy for the current task.

Execution lane rule:

- `Implementation worker`, `recovery write worker`, `schema repair worker`, `view repair worker`, and any lane with `writeBoundary: approved-target` must use a real independent worker when one is eligible.
- Use `native_thread_lane` for both ephemeral and persistent distributed lanes. Ephemeral lanes still use `packet_only`; persistent lanes use `checkpoint_delta`.
- Do not register an external-write lane as `single_thread_section` unless all real worker runtimes were checked and unavailable or the user explicitly rejected background worker execution.
- If an execution lane is accidentally started inside the controller thread, stop it, checkpoint what changed, and re-dispatch the remaining work to a real worker.
- If an old, mistaken, duplicate, or replaced worker should be kept only for audit, mark that worker `status: superseded` instead of `done/pass`. A superseded worker is ignored by gates, but it is not proof that its lane passed. The replacement native worker callback is the only valid pass evidence.
- If a worker correctly returned `needs-work` or `blocked` and a later repair/review lane proves the issue is fixed, update that worker to `status: resolved` with notes naming the resolving lane/request. A resolved worker is kept as historical evidence but no longer blocks gates.

KY-TASK thread naming:

```text
KY-TASK00-总控-任务伙伴
KY-TASK01-证据-来源台账
KY-TASK02-模型-对象状态
KY-TASK03-体验-首页路径
KY-TASK04-实现-唯一写入
KY-TASK05-验收-独立检查
```

These are examples. Create only the lanes that the real task needs.

## Local State Helper

Use `scripts/task_controller_state.py` when useful to keep lane status outside chat memory.

Typical commands:

```bash
python3 scripts/task_controller_state.py init --state /tmp/controller.json --goal "Build clean v3 dashboard" \
  --lane-definitions '[{"name":"implementation","kind":"implementation","workerRequired":true,"workerLifecycle":"ephemeral","contextPolicy":"packet_only","dependsOn":[]},{"name":"review","kind":"review","workerRequired":true,"workerLifecycle":"ephemeral","contextPolicy":"packet_only","dependsOn":["implementation"]}]' \
  --execution-policy '{"splitRequirement":"mandatory","mode":"distributed","eligibleRuntimes":["native_thread_lane"],"requiredWorkerLanes":["implementation","review"],"independentReviewRequired":true,"runtimeSelectionPolicy":"native_session_required","nativeThreadUserApproved":true,"maxParallelWorkers":4,"projectAffinityPolicy":"inherit_or_resolve_required","projectlessUserApproved":false,"targetProjectId":"<id-from-list_projects>","targetProjectPath":"<saved-project-path>","projectResolutionSource":"controller_project"}'
python3 scripts/task_controller_state.py status --state /tmp/controller.json
python3 scripts/task_controller_state.py ready-lanes --state /tmp/controller.json
python3 scripts/task_controller_state.py complete-lane --state /tmp/controller.json --lane evidence --artifact source-ledger.md --decision pass
python3 scripts/task_controller_state.py next-lane --state /tmp/controller.json
```

`task_controller_init` accepts `contract`, either `lanes` or explicit `laneDefinitions`, and `executionPolicy`. Lane definitions can lock `workerLifecycle`, `contextPolicy`, `runtimePreference`, and `dependsOn`. The policy locks `splitRequirement`, `mode`, `eligibleRuntimes`, `downgradeReason`, `requiredWorkerLanes`, `independentReviewRequired`, `runtimeSelectionPolicy`, `nativeThreadUserApproved`, `maxParallelWorkers`, `projectAffinityPolicy`, `projectlessUserApproved`, `targetProjectId`, `targetProjectPath`, and `projectResolutionSource`. Mandatory work with an eligible real runtime cannot initialize as `direct` or `sequential_lanes`; a no-runtime fallback requires an explicit downgrade reason. Under the Session-first policy, distributed native initialization also fails until a saved project is resolved.

For a new `TaskBlueprint`, use `plan-blueprint` to read-only compile the routing decision, formal `SolutionGraph`, projected lanes, and `WorkerPackets`. It never dispatches workers. `init --task-blueprint --auto-plan` persists that plan and uses its lane projection when no `laneDefinitions` are supplied. A graph-backed worker registration and callback must include the current packet ID and digest; workers are not dispatched automatically by planning or initialization.

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

1. Register the active current-revision worker with its `WorkerPacket` identity.
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

`discuss_only` and `plan_only` prohibit registration, gate, callback pass, and completion of `approved-target` lanes. `execute` requires a matching `writePolicy`. Every contract spec 2.x approved-target pass includes a `writeReceipt` whose target and action match that policy.

When `userApprovalGate.required` is true, record approval with `record-approval` against the exact current-revision artifact fingerprint before any blocked lane. A correction makes current approvals stale and open corrections continue to block progress.

When `sampleGate.required` is true, the sample lane must be current-revision `done/pass`, including its named `acceptanceIds`, before any lane in `blocks` can register, gate, callback-pass, or complete.

If a worker sees correction language, it must submit a `correctionEvents` entry with an explicit `recommendedInvalidFromLane` instead of interpreting the text as ordinary notes. The callback cannot pass. If the controller directly observes user language such as “不对”, “我要的是”, “按上一版”, “目标变了”, “不要改这个”, “保留原样”, “不能收费”, “重复收费”, “样稿不对”, or “来源换了”, call `task_controller_ingest_feedback` immediately. It classifies and atomically records contract-level feedback; do not first reinterpret it as an ordinary edit. Use `task_controller_classify_feedback` only for read-only inspection. Then call `task_controller_revise_contract` to consume every open event ID, using an `invalidFromLane` no later than the earliest recommendation. Every open correction blocks registration, gates, and completion. Strict revision always supplies the complete replacement `contractSpec`; proactive revision without a correction is still allowed. `task_controller_record_correction` remains the explicit low-level fallback.

This state machine is not a security sandbox. It cannot stop a controller or worker that bypasses KY-TASK and directly calls an external write tool. It only makes KY-TASK-managed dispatch, registration, callback pass, gate, and completion fail closed. Controller prompts and operating discipline must prohibit direct-write bypasses.

Mutating CLI commands use an advisory file lock across their complete read-modify-write cycle, and state replacement is atomic. This prevents lost updates between cooperating controller processes; the JSON checkpoint is still not a distributed transaction database.

Installed MCP tools can also record worker/session state:

- `task_controller_init`
- `task_controller_compile_blueprint`
- `task_controller_route_capabilities`
- `task_controller_status`
- `task_controller_next_lane`
- `task_controller_ready_lanes`
- `task_controller_complete_lane`
- `task_controller_insert_lane`
- `task_controller_register_worker`
- `task_controller_update_worker`
- `task_controller_list_workers`
- `task_controller_classify_feedback`
- `task_controller_ingest_feedback`
- `task_controller_record_correction`
- `task_controller_record_approval`
- `task_controller_record_callback`
- `task_controller_gate_check`
- `task_controller_revise_contract`
- `task_controller_finalize`
- `task_controller_plan_blueprint`

## Automatic Thread / Callback / Gate Flow

KY-TASK can control the full workflow, but implementation is split across two tool layers:

- Codex app thread tools create the visible Session workers required by this Session-first policy. Managed-agent tools are used only under an explicit `lane_lifecycle` override.
- KY-TASK MCP tools record state, collect callbacks, and block gates.

When distributed execution is approved, run:

1. Produce `role_map`.
2. Call `list_projects`, resolve one saved project, and lock it in `executionPolicy.targetProjectId`.
3. Initialize KY-TASK state with `task_controller_init`.
4. Call `task_controller_ready_lanes`; create every returned `native_thread_lane` with a project target before waiting.
5. Verify project affinity and register each lane with `task_controller_register_worker`.
6. Require every native worker to callback to `KY-TASK00`.
7. Record native active messaging as `active_message`, native polling recovery as `controller_poll_recovery`, and managed result collection as `managed_result_collected`.
8. Record callbacks with `task_controller_record_callback`.
9. Wait on all active Session workers together. When one finishes, record it and refill the available slot from `task_controller_ready_lanes`.
10. Before entering a dependent lane, call `task_controller_gate_check`.
11. If the gate blocks, do not enter implementation or final answer; fix the blocker or ask the user for the missing decision.

When a correction, recovery, or review lane is discovered after the original state was initialized, insert it into the main lane order with `task_controller_insert_lane`. Do not hand-edit the state JSON unless the tool is unavailable.

Worker registration is incomplete unless it includes:

- `runtimeHandle` for every real worker. Managed workers use the returned agent/session handle.
- both an explicit `threadId` and `runtimeHandle` for `native_thread_lane`; both values must be the same Codex thread id so recovery and worker location use one identity.
- `projectTargetType`, `projectId`, and `projectEnvironment` for every native worker. Under strict project affinity, target type is `project`, `projectId` must equal `executionPolicy.targetProjectId`, and environment is `local` or `worktree`.
- non-empty `requestId`.
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

Each review worker must name every current-revision `approved-target` writer in an earlier lane in `reviewsWorkerIds`, regardless of lane kind, and use a different `runtimeHandle`. Writers in later lanes are outside that review's responsibility. A final review placed after all writers therefore covers every current writer. Writer callback and completion do not require a future review to be registered; coverage is enforced when entering or completing each downstream review and at the final gate. Strict review callbacks must still cover every `preserve`, `allowedChanges`, `forbidden`, and `acceptance` ID. A review performed by the same thread or managed-agent identity as a covered writer is self-review and must be rejected.

When the user changes scope, acceptance, sources, or another locked contract term, call `task_controller_revise_contract` with the earliest `invalidFromLane`. It increments `contractRevision`, preserves upstream lanes, invalidates downstream outputs, and supersedes old workers/callbacks. Do not reuse an old artifact or callback; dispatch new current-revision workers and rerun the affected gates.

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

For a task like a Feishu/Base management demo, project operating cockpit, dashboard prototype, or artifact with business path plus information path, the default lane plan is:

1. Evidence worker.
2. Object/model worker.
3. Product/experience worker.
4. Implementation writer, as the only final-artifact writer.
5. Review worker.

The implementation writer may start only after upstream callbacks are recorded and the gate passes.

Do not try to make the local MCP server create Codex Desktop threads directly. Thread and project discovery/creation belong to the Codex app runtime, while KY-TASK owns the controller protocol and state. Never call `create_thread` with `target.type: projectless` under the installed policy.

## Output Shapes

### Controller Contract

```text
Controller contract
- 目标:
- 已锁定任务契约:
- 执行模式:
- lane map:
- 当前 lane:
- 写入边界:
- 禁止动作:
- 验收:
```

### Lane Checkpoint

```text
<Lane name> checkpoint
- 输入:
- 输出:
- 关键发现:
- 产物:
- gate 结果:
- 下一 lane:
- 是否需要确认:
```

### Worker Prompt

```text
Worker prompt
- 任务:
- 可用输入:
- 输出格式:
- 证据规则:
- worker_lifecycle: ephemeral | persistent
- context_policy: packet_only | checkpoint_delta
- runtime_preference: auto | managed_agent_worker | native_thread_lane
- depends_on: [] | [upstream lane names]
- tool_profile:
- credential_policy:
  - required:
  - optional:
  - fallback:
  - blocker_if:
- callback_mode: managed_result_collected | active_message_required | active_message_preferred | controller_poll_allowed
- 写入边界:
- 禁止动作:
- 完成动作:
  - managed_result_collected: 在 managed worker 结果中返回 callback，由 controller 收集并登记。
  - active_message_required: 使用线程消息工具把 callback 发给真实 reply_to_thread_id。
  - active_message_preferred / controller_poll_allowed: 无法主动回传时，在 worker 结果中返回 callback，并标注 callback_mode_observed: controller_poll_recovery。
- 回传格式:
  - callback_mode_observed:
  - contract_revision / contract_digest / deliverable_fingerprint:
  - artifact_manifest:
  - check_results:
  - correction_events:
```

## Failure Rules

- If the final artifact is being written before upstream lane gates exist, stop and create the missing lane artifact.
- If a worker output lacks source lineage, do not merge it into the final artifact.
- If old-version artifacts are visible in a clean demo, fail review.
- If implementation passes API checks but fails the user path, the task is not done.
