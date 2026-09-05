# Worker Orchestration

Use this reference when KY-TASK must split real work across independent workers.

For every distributed Codex Desktop worker Session, also apply `codex-thread-adapter.md`. Worker orchestration defines when and why to split; the adapter defines how to discover and use the host thread tools.

## Principle

Split by professional work type and write risk, not by convenience.

Session dispatch is downstream of work orchestration. First apply
`work-orchestration.md` and pass a strict `OrchestrationPlan`; only then use this
reference to place accepted lanes into worker Sessions. Never use Session
creation itself as the decomposition method.

KY-TASK follows the KY-style controller/lane pattern:

- `KY-TASK00-总控-任务伙伴` is the only fixed user-facing role.
- `KY-TASK01+` lanes are generated dynamically for the current task.
- Registered distributed lanes use real independent runtimes.
- This distribution requires `native_thread_lane` for distributed lanes through `runtimeSelectionPolicy: native_session_required`.
- This distribution requires every native worker to belong to one resolved saved Codex project through `projectAffinityPolicy: inherit_or_resolve_required`.
- Both runtime types are valid registered lanes when they have a distinct `runtimeHandle`, request identity, and recorded callback.

Runtime selection is a lifecycle decision, not a complexity badge:

- `ephemeral` + `packet_only`: one bounded task, one callback, no unrelated controller history; it still receives its own visible Session.
- `persistent` + `checkpoint_delta`: the lane must survive multiple controller turns, accept direct user intervention, or maintain an ongoing professional workbench; require `native_thread_lane`.
- The open-source distribution has no standing approval. After explicit task-scoped approval, state records `executionPolicy.nativeThreadUserApproved: true`.
- Evidence, calculation, implementation, and review do not become persistent merely because they are important.

Good worker boundaries:

- A worker can complete its output without needing to write the final artifact.
- A worker has a narrow input packet.
- A worker has a clear pass/fail gate.
- A worker's output can be merged by the controller.
- A worker has a `tool_profile` and, for external writes, a `credential_policy`.

Bad worker boundaries:

- Several workers can edit the same final Feishu/Base/doc/deck/code artifact.
- A worker is asked to "help with everything".
- A worker receives the whole conversation when only source files are needed.
- A worker is allowed to invent missing evidence.

## When To Create Independent Workers

Use independent workers when at least two of these are true:

- Evidence volume is high.
- Object modeling and product experience both matter.
- Implementation writes to external systems.
- Independent review is needed.
- Prior single-thread execution failed.
- The user explicitly requests split sessions or subagents.

If project discovery or native Session tools are unavailable, stop and report the blocker. Do not silently switch to managed subagents, sequential execution, or projectless Sessions under the installed policies.

Under `native_session_required`, check native project/creation/messaging/wait tools first. Managed agents are checked only for an explicit `lane_lifecycle` override; they are not an automatic fallback. Task creation still requires the user's task-scoped sidebar Session approval.

When Codex thread tools are the intended runtime, record the adapter capability state from `codex-thread-adapter.md` in the split decision and in each worker registration `threadToolCheck`.

## Split Decision Gate

Before execution, KY-TASK must classify the task into one of three modes:

- `direct`: current thread can complete the task without lane overhead.
- `sequential-lanes`: current thread runs named lanes one by one, leaving checkpoints.
- `distributed`: visible native Session workers produce lane artifacts and callback to the controller.

Output this compact decision when the task is not trivially small:

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

### Mandatory split rules

If any of these rules is true, KY-TASK must check for real independent worker runtimes before execution:

- The user explicitly asks for split conversations, worker Sessions, subagents, multi-lane execution, or says not to run everything in one thread.
- A prior run failed because evidence, modeling, product/experience design, implementation, and review were collapsed together.
- The task writes to external systems or durable artifacts such as Feishu Base, Feishu docs, decks, workbooks, repos, customer-facing files, or production assets.
- The task has three or more professional layers, such as evidence, object/model, metric/chart, product/experience, implementation, and review.
- Data correctness and product/user experience are both central to acceptance.
- Independent review is needed because the output is executive-facing, client-facing, financial, operationally sensitive, or hard to undo.

When either real worker runtime is eligible and execution is approved, the only valid result for a mandatory split task is `distributed`. `multi_session` remains a legacy stored alias.

`sequential-lanes` is a valid fallback for a mandatory split task only after KY-TASK has checked and recorded that real independent worker runtimes are unavailable, the user rejects background worker execution, or the current turn is planning-only with no final write.

Forbidden downgrade outputs for mandatory split tasks with available thread tools:

- `结论: sequential-lanes`
- `先在当前线程继续做`
- `不开多线程`
- `先预检查后直接搭`
- a single uninterrupted current-thread run that does evidence, model, product, implementation, and review.

### Recommended split rules

Use `sequential-lanes`, and consider `distributed` if the lanes can work independently, when two or more are true:

- Materials are numerous, mixed, or have disputed evidence status.
- Several roles or viewpoints must be represented, such as PM, finance, commercial, delivery, management, or customer.
- Old-version contamination is likely.
- The work needs rules before tooling, such as a management process or dashboard prototype.
- The user asks for both a business path and an information path.
- The output needs both source truth and readable business expression.

### Do-not-split rules

Use `direct` when the task is small and the overhead of lanes would reduce quality:

- one wording or label change
- one local file edit
- one chart value or style correction
- a concept explanation
- a focused review answer
- a bounded follow-up where the contract and artifact already exist

Do not create workers just to look rigorous. Split only when it reduces risk, rework, or context overload.

## Anti-Downgrade Rule

KY-TASK must not silently turn an agreed distributed plan into ordinary current-thread execution.

If the user has asked for distributed execution, split conversations, worker threads, or has complained that prior work failed because it was not split, then later confirmations such as `继续`, `好`, `进执行`, `按这个做`, or `优化吧` mean:

- continue the agreed split plan;
- check thread tools before claiming thread creation is unavailable;
- dispatch independent workers when runtimes are available and the user has approved execution;
- register each worker with KY-TASK state;
- require callback;
- run `task_controller_gate_check` before implementation and final review.

If no real worker runtime is available, state the fallback explicitly:

```text
原计划: distributed
当前限制: thread tools unavailable / not approved / task too small
降级方式: sequential-lanes
差异: worker 变成当前线程 checkpoint，不再是真实子对话 callback
```

If the user explicitly required real separate conversations, stop and ask for the missing thread capability or permission. Do not present sequential lane fallback as if it were distributed execution.

If the task is a Feishu/Base management demo, operating cockpit, dashboard prototype, or business process demo where both the business path and information path must work, treat it as a mandatory split task after execution is approved.

## Controller/Worker Boundary

Controller owns:

- task contract
- lane map
- user communication
- worker prompts
- merge decisions
- final write authorization
- final review
- registered lane state
- callback collection and merge decisions

Controller does not own:

- Feishu/Base/Doc/schema/view/record writes.
- dashboard implementation.
- workbook/deck/code final edits.
- recovery writes after a failed implementation.

When a real worker runtime is available, those execution tasks must belong to a registered managed or native worker.

Workers own:

- narrow lane artifact
- source notes
- risks and open questions
- pass/fail recommendation for their gate

Workers normally do not:

- talk to the user
- change task scope
- write the final artifact
- overwrite Feishu/Base/docs/decks/code
- mark the whole task complete
- complete silently inside their own thread without callback to the controller

Execution workers may write only when the handoff explicitly grants the approved target and write scope. They must still callback before the controller can continue.

## Dynamic Role Map

Before creating background lanes, output:

```text
role_map:
  controller: KY-TASK00-总控-任务伙伴
    project_type:
    target_project_id:
    target_project_path:
    project_resolution_source:
  desired_output:
  required_lanes:
  optional_lanes:
  each_lane:
    title:
    responsibility:
    contribution_role: primary | prerequisite | supporting | verification
    semantic_authority: define | constrain | implement | define-and-implement | verify
    semantic_owner: true | false
    input_materials:
    output_artifacts:
    tool_profile:
    credential_policy:
    worker_lifecycle: ephemeral | persistent
    context_policy: packet_only | checkpoint_delta
    runtime_preference: auto | managed_agent_worker | native_thread_lane
    depends_on: [] | [upstream lane names]
    dependency_reasons:
    input_contracts:
    output_contracts:
    handoff_risk: low | medium | high
    handoff_mode: same-lane | artifact-contract | independent
    capability_requirements:
    lane_runtime: managed_agent_worker | native_thread_lane | single_thread_section | thread_create_unavailable
    write_scope:
    forbidden_actions:
    acceptance_criteria:
    callback_expected:
    callback_mode_expected:
```

Do not ask the user which agents they want. KY-TASK proposes the role map and asks only for business decisions, missing materials, or write permission.

Common lane title examples:

```text
KY-TASK01-证据-来源台账
KY-TASK02-模型-对象状态
KY-TASK03-体验-首页路径
KY-TASK04-实现-唯一写入
KY-TASK05-验收-独立检查
```

These are examples, not a fixed team.

## Thread Dispatch Protocol

Before dispatching workers, output:

```text
分会话执行计划
- 控制会话:
- 归属项目: projectId / path / resolution source
- worker 清单:
- 每个 worker 的任务:
- 每个 worker 的输入:
- 每个 worker 的输出:
- 写入边界:
- 工具画像:
- 凭证策略:
  - 必需:
  - 可选:
  - 降级:
  - 阻塞条件:
- 禁止动作:
- 回传格式:
- 合并方式:
```

After execution is approved, call `task_controller_ready_lanes`, then claim each selected lane with `task_controller_claim_dispatch`. Only `creationAction: create` permits one new sidebar task. Reconcile repeated/uncertain requests without duplicating creation. The task-scoped `nativeThreadUserApproved: true` record covers these KY-TASK distributed Sessions. Read `dispatch-and-recovery.md` for admission and recovery.

Before that dispatch, call `list_projects` and resolve exactly one saved project. Prefer the controller thread's non-empty `projectId`. If it is empty, match the effective workspace, source-material path, or durable target to the deepest saved project path. If no unique project can be established, stop and ask the user; do not use `projectless` as a convenience fallback.

When the user explicitly requests real Codex Desktop sidebar tasks, use:

- controller thread title: `KY-TASK00-总控-任务伙伴`
- lane thread titles: `KY-TASKNN-角色-职责`
- `codex_app.create_thread` for new lane threads when available.
- `codex_app.send_message_to_thread` to send lane prompts and to ask lanes for callbacks.

The controller should register each native lane thread with KY-TASK state:

- `workerId`: thread id or stable lane id
- `claimId` and the matching `requestId`: the pre-creation reservation
- `threadId`: required Codex thread id
- `runtimeHandle`: required and exactly equal to `threadId`; native aliases are not accepted
- `projectTargetType`: required; `project` under the Session-first policy
- `projectId`: required and exactly equal to `executionPolicy.targetProjectId`
- `projectEnvironment`: `local` or `worktree`, matching the `create_thread` target
- `laneRuntime`: `native_thread_lane`
- `callbackExpected`: true
- `callbackModeExpected`: `active_message_required` for real worker threads when `send_message_to_thread` or equivalent worker-to-controller messaging is available.
- `toolProfile`: lane-specific tools needed by the worker
- `credentialPolicy`: required/optional credential and scope checks for external writes

Minimum dispatch sequence for mandatory split tasks:

1. Check `list_projects` plus native thread creation, messaging, listing, and wait tools.
2. Resolve and lock `targetProjectId`; initialize distributed state only after this succeeds.
3. Call `task_controller_ready_lanes`.
4. Atomically claim each ready lane; for `creationAction: create`, create its worker with `target: {type: "project", projectId, environment}`. Claims and live attempts together consume `maxParallelWorkers`.
5. Verify each new thread reports the locked `projectId`. A mismatched or empty project is a blocker and must not be registered as valid.
6. Send each worker a narrow prompt and register it with project identity, `claimId`, and `requestId`.
7. After the admitted batch is dispatched, call host waits with at most eight targets per call. The plugin supplies a grouping plan, not an automatic wait loop; the controller retains cursors and rotates groups.
8. Record each callback as workers finish and refill open slots from the next ready frontier.
9. Run the relevant dependency gate before downstream implementation.

If no eligible real runtime can perform steps 1-4, stop and report the blocker instead of continuing as a current-thread implementation.

Use `environment: {type: "local"}` for workers that intentionally share the saved project's checkout. Use a project `worktree` environment for isolated repository writes when appropriate. Both remain under the same saved project. Environment choice must never be implemented by changing the target to `projectless`.

### Execution Lane Isolation

Any lane that changes an external or durable artifact is an execution lane, including:

- Feishu Base schema repair.
- Feishu view filtering/sorting/field visibility.
- Feishu record import or association repair.
- Feishu Doc/Wiki edits.
- dashboard block changes.
- repository, workbook, deck, or client-facing file edits.

When the task is in `distributed` mode, both ephemeral and persistent lanes use `native_thread_lane` under the installed policy. The lifecycle changes context retention, not sidebar visibility.

### Dependency Frontier And Parallel Dispatch

- Every new lane declares `dependsOn`; `[]` means immediately ready.
- Missing `dependsOn` is legacy ordered-lane behavior and must not be used for new plans.
- Every serial edge in a strict plan declares why it is serial. List order is not a reason.
- Parallel siblings expose output contracts and a downstream join point; different job titles alone do not prove independence.
- Verification consumes the decision, sample, readback, or artifact it judges. It cannot run early and then dictate an artifact that does not yet exist.
- Build the primary semantic path first, then attach prerequisite/supporting work whose outputs it actually consumes.
- Dispatch all lanes returned by `task_controller_ready_lanes` before waiting.
- Total Lane count is not capped. Default concurrency is four Sessions; an explicit task may set `executionPolicy.maxParallelWorkers` as high as ten.
- Codex wait coordination accepts at most eight targets per call. If nine or ten Sessions are active, keep all of them running and rotate stable wait batches of at most eight; do not lower the active frontier merely to fit one wait call.
- Do not add a dependency only to make the diagram tidy. Add it only when a lane consumes the upstream artifact, shares a write target, or must wait for approval.
- Lanes that can read the same immutable source independently should normally be siblings in the same frontier.
- Writers to the same durable target are never parallel. Review depends on every writer it must cover.

Before dispatch, call `task_controller_plan_orchestration`. If it returns
`orchestrationExecutable: false`, do not create worker Sessions. Repair the lane
graph first. When no scenario pack matched, this generic strict plan is the
required path; do not fall back to the example five-lane sequence.

Do not register execution lanes as `single_thread_section` just because the change is small or described as "repair". A repair that writes to an external artifact has the same isolation requirement as implementation.

If the controller accidentally starts an execution lane in the current thread:

1. Stop further writes immediately.
2. Output a checkpoint listing completed writes and remaining writes.
3. Register the mistake in KY-TASK state.
4. Create a real worker thread for the remaining execution work.
5. Run a review worker before continuing to the next lane.

### Callback Collection Contract

Worker threads do not count as complete just because they have a final answer in their own thread. The controller must collect the callback and record it.

Required callback metadata:

- `request_id`: non-empty stable id assigned by the controller.
- `from_lane`: worker lane name.
- `to_lane`: `KY-TASK00-总控-任务伙伴`.
- `gate decision`: `pass`, `needs-work`, or `blocked`.
- `artifact`: result path or summary.
- `key findings`, `evidence`, `risks`, `next recommendation`.
- in semantic strict mode: current `contractDigest`, `deliverableFingerprint`, non-empty `artifactManifest`, complete `checkResults`, and any discovered `correctionEvents`.

Required worker registration fields:

- `runtimeHandle` for both real runtimes.
- `threadId` for native workers only; it is mandatory and must exactly equal `runtimeHandle`.
- `requestId`.
- `controllerThreadId`.
- `replyToThreadId`.
- `projectTargetType`, `projectId`, and `projectEnvironment` for native workers.
- `callbackExpected: true`.
- `callbackModeExpected`.

If direct worker-to-controller messaging is available, `callbackModeExpected` should be `active_message_required`: the worker must send the callback to `replyToThreadId`, and the controller records `callbackModeObserved: active_message`.

If direct worker-to-controller messaging is not available, use `callbackModeExpected: controller_poll_allowed`; the controller must use thread read/inspect tools to pull the worker final answer and then call `task_controller_record_callback` with `callbackModeObserved: controller_poll_recovery`.

Managed workers use `callbackModeExpected: managed_result_collected`; record the result returned by the managed runtime as `callbackModeObserved: managed_result_collected`.

If a worker only final-answers in its own thread when active messaging was required, the controller may recover the content for audit, but it must record `callbackModeObserved: controller_poll_recovery`. This is a degraded callback, not proof that the controller was actively triggered.

If any worker returns `needs-work` or `blocked`, `task_controller_gate_check` must block implementation or final review until a fix lane resolves the issue.

After a fix lane and review lane prove the issue is resolved, keep the original negative worker for audit but update it to `status: resolved` with notes naming the resolving lane/request. `resolved` means "the finding was valid, and later work fixed it"; it is different from `superseded`, which means "this worker was replaced, mistaken, duplicate, or only an audit placeholder."

Before independent review registration, provide `reviewsWorkerIds` covering its compiled `verificationSubjects` and assign a different `runtimeHandle`. Intermediate review consumes named input artifacts, not every earlier writer or future production. Final review covers final writers; legacy states retain earlier-writer scope. Writer completion does not wait for a future review; downstream review and final gates enforce coverage. A fresh prompt on the same runtime is still self-review. Strict semantic acceptance requirements remain in force.

If the user changes contract scope or acceptance, call `task_controller_revise_contract` from the earliest affected lane. Affected lane artifacts and all old callbacks become invalid for progression; dispatch new current-revision workers rather than reusing old callback data.

If a callback or user message contains correction language that changes target, canonical source, preserve rules, allowed/forbidden scope, or acceptance, record `correctionEvents` immediately. Do not translate it into an ordinary note or a pass. Open correction events block further dispatch/gate/completion until one revision consumes all of them; strict revision includes the full replacement contract and starts no later than the earliest recommended lane.

KY-TASK state cannot intercept a direct external write performed outside this protocol. The controller must therefore keep write tools inside registered execution lanes and must not call those tools directly to bypass a blocked dispatch, gate, or callback.

## Automatic Thread Creation Boundary

KY-TASK should drive explicitly requested sidebar task creation through Codex app thread tools. It should not hide thread creation inside the local MCP server.

Reason:

- Codex thread creation is a host/app capability, not a local JSON-state operation.
- The controller must see the thread ids and prompts it sends.
- Users should be able to inspect real worker conversations.

So the controller does:

1. Discover/check project and thread tools.
2. Resolve one saved project and lock its identity.
3. Create project-scoped lane threads and verify their project identity.
4. Register worker state in KY-TASK.
5. Wait for or request callbacks.
6. Record callbacks.
7. Run gate checks.

## Worker Prompt Template

```text
你是 KY-TASK 的一个独立 worker，不是总控。

controller_thread_id:
reply_to_thread_id:
request_id:
from_lane:
to_lane: KY-TASK00-总控-任务伙伴
callback_mode_expected: active_message_required
worker_lifecycle: persistent
context_policy: checkpoint_delta
runtime_preference: native_thread_lane
project_id: <executionPolicy.targetProjectId>
project_target_type: project
project_environment: local | worktree

任务:

允许使用的输入:

输出格式:

证据规则:

工具画像:

凭证策略:
- 必需:
- 可选:
- 降级:
- 阻塞条件:

写入边界:

禁止动作:

完成动作:
1. 首选: 使用可用的线程消息工具，把下面的 callback 发给 `reply_to_thread_id`。
2. 只有在线程消息工具不可用时，才在本 worker 线程最终回复 callback，并标注 `callback_mode_observed: controller_poll_recovery`。
3. 如果已主动发回总控，本 worker 线程可以只保留一行简短说明，不要把 callback 只留在本线程。

callback 格式:
- message_type: completion | blocker | review_request | fix_request
- request_id:
- from_lane:
- to_lane:
- callback_mode_observed: active_message | controller_poll_recovery | unavailable | unspecified
- artifact:
- key findings:
- evidence:
- risks:
- gate decision:
- next recommendation:
```

If the worker is a real thread, it must actively send this callback to the controller thread when thread messaging tools are available. A final answer only in the worker thread is not accepted as normal completion unless the controller is explicitly doing recovery/audit and records `callbackModeObserved: controller_poll_recovery`.

## Tool Access And Credential Policy

Sandbox, Keychain, and Feishu scope failures are tool-access findings, not reasons to collapse work back into the controller thread.

For each execution worker, classify tools before writing:

- `required`: the lane cannot pass without this tool/scope.
- `optional`: useful enrichment, but the lane can pass with a documented fallback.
- `fallback`: what to do if optional access fails.
- `blocker_if`: the exact condition that should stop the worker and callback as `blocker`.

Examples:

- `lark-base-record-write` is required for a Base record-fill lane.
- `lark-drive-search-optional` is optional when links enrich the demo but project titles and Base relationships still satisfy acceptance.
- `lark-drive-search-required` is required only if the lane acceptance explicitly depends on verified Drive URLs.

Workers must not request broad host or sandbox escalation for optional enrichment. If optional access fails, continue with fallback and report the risk. If required access fails, stop before unsafe partial writes unless the prompt already grants a safe partial-write route.

## Worker State

Record every worker with:

- worker id or thread id
- controller thread id
- reply-to thread id
- request id
- lane
- lane runtime
- task
- status
- artifact
- decision
- notes
- callback expected

Use KY-TASK state tools when available:

- `task_controller_register_worker`
- `task_controller_claim_dispatch`
- `task_controller_release_dispatch`
- `task_controller_update_worker`
- `task_controller_list_workers`
- `task_controller_record_callback`
- `task_controller_gate_check`

## Merge Gate

Before implementation:

- Evidence output must have source status.
- Object/model output must map sources to targets.
- Product/experience output must define the user path or unit contract.
- Conflicts between workers must be surfaced.
- Only the approved implementation worker may write the final artifact in distributed mode.
- `task_controller_gate_check` must allow the implementation lane.

Before final answer:

- Review worker or review lane must check acceptance cases.
- The controller must state unresolved risks.
- `task_controller_gate_check` must allow final review/completion.
