# Codex Thread Adapter

Use this reference for every distributed lane under the default `native_session_required` policy.

## Boundary

KY-TASK cannot bundle Codex Desktop host tools inside its local MCP server. Tools such as `create_thread`, `send_message_to_thread`, `list_threads`, `fork_thread`, and `set_thread_title` belong to the Codex app host.

KY-TASK bundles the adapter contract around those host tools:

- discover saved Codex projects and resolve one project binding;
- discover whether thread tools are available;
- decide whether the task must use real worker threads;
- create or message workers through the host tools when available;
- register each worker in KY-TASK state;
- require active callback to the controller thread;
- record callback mode and gate transitions;
- block or degrade explicitly when host thread tools are unavailable.

This keeps thread ownership visible to the user and avoids hiding desktop app actions inside a local plugin server.

Both `ephemeral` and `persistent` distributed lanes use visible native Session tasks in this installation. Ephemeral workers use `packet_only`; persistent workers use `checkpoint_delta`.

Native dispatch requires:

- lane `contextPolicy: packet_only | checkpoint_delta` matching its lifecycle;
- `executionPolicy.nativeThreadUserApproved: true`.
- `executionPolicy.runtimeSelectionPolicy: native_session_required`.
- `executionPolicy.projectAffinityPolicy: inherit_or_resolve_required`.
- non-empty `executionPolicy.targetProjectId` and `projectResolutionSource`.

## Required Tool Discovery

Before declaring native thread tools unavailable for an explicitly requested sidebar task, KY-TASK must check for them.

Use direct tools if already visible. If they are not visible and `tool_search` is available, search for:

```text
create_thread send_message_to_thread Codex thread tools
```

Recognized host thread tools include:

- `codex_app.list_projects`
- `codex_app.create_thread`
- `codex_app.send_message_to_thread`
- `codex_app.list_threads`
- `codex_app.fork_thread`
- `codex_app.set_thread_title`
- `codex_app.set_thread_pinned`
- `codex_app.set_thread_archived`

The minimum native tool set is:

- list saved projects;
- create or identify a worker thread;
- send the worker prompt;
- send or receive a callback into the controller thread.

## Strict Project Affinity

Resolve project affinity before `task_controller_init` and before any worker is created:

1. Call `list_projects`.
2. If the controller thread already has a non-empty saved-project `projectId`, verify it still exists and inherit it.
3. Otherwise compare the effective task workspace, source-material paths, and durable target paths with saved local project paths. Choose the deepest matching project path only when the result is unique.
4. If no unique saved project is available, ask the user to select or create a project. Stop dispatch while unresolved.
5. Lock the result in `executionPolicy.targetProjectId`, optional `targetProjectPath`, and `projectResolutionSource` (`controller_project`, `workspace_path_match`, `material_path_match`, or `user_selected`).

Create each worker with a project target. For example:

```text
target:
  type: project
  projectId: <executionPolicy.targetProjectId>
  environment:
    type: local | worktree
```

Never use `target.type: projectless` under `inherit_or_resolve_required`. Projectless dispatch is allowed only after the user explicitly approves a per-task override with `projectAffinityPolicy: allow_projectless` and `projectlessUserApproved: true`.

After creation, inspect/list the new thread and confirm its `projectId` equals the locked target. If the value is empty or different, do not register or dispatch that thread as a valid worker; report `project_affinity_mismatch`.

## Capability States

Record one of these states in the split decision and worker registration `threadToolCheck`:

- `native_threads_available`: host tools can create/message worker threads.
- `message_only_available`: existing worker threads can be messaged, but new threads cannot be created.
- `thread_read_only`: worker threads can be inspected but not messaged.
- `thread_tools_unavailable`: no thread creation or messaging tool is available.

Do not use `thread_tools_unavailable` until tool discovery has been attempted.

## Dispatch Flow

For each native worker lane:

1. Resolve the saved project and choose `local` or project `worktree` environment.
2. Claim the lane and slot with `task_controller_claim_dispatch` before host creation. Follow `dispatch-and-recovery.md`: only `creationAction: create` permits creation with the locked project target; repeated claims require host reconciliation.
3. Verify the created thread reports the locked `projectId`.
4. Send a narrow worker prompt that includes:
   - `controller_thread_id`
   - `reply_to_thread_id`
   - `request_id`
   - `from_lane`
   - `to_lane: KY-TASK00-总控-任务伙伴`
   - `callback_mode_expected: active_message_required`
5. Register the worker with KY-TASK:
   - `claimId: <pre-creation claim id>` and its matching `requestId`
   - `laneRuntime: native_thread_lane`
   - `threadId: <created-or-identified Codex thread id>`
   - `runtimeHandle: <the exact same Codex thread id>`
   - `projectTargetType: project`
   - `projectId: <executionPolicy.targetProjectId>`
   - `projectEnvironment: local | worktree`
   - `callbackExpected: true`
   - `callbackModeExpected: active_message_required`
   - `threadToolCheck: native_threads_available`
6. Wait for the worker to actively message the callback to `reply_to_thread_id`.
7. Record callback with `callbackModeObserved: active_message`.
8. Run `task_controller_gate_check` before the next lane.

The task graph has no total Lane-count cap. The controller may keep up to the
task policy's ten-worker maximum active, but each host wait call accepts at most
eight targets. For nine or ten active workers, use stable wait batches of at
most eight and rotate batches after a completion or bounded timeout. Do not
stop active Sessions merely to fit one wait call.

The grouping is advisory coordination output; the controller owns the host
wait calls and cursors. A pending worktree `clientThreadId` must not be bound as
a real `threadId`. Keep the original claim occupied until setup yields an actual
thread, or reconcile and release only after confirming no task was created or
that it stopped. A timed-out create call is not permission to create again.

Under this Session-first policy, every distributed lane enters this native dispatch flow. A managed worker is invalid unless the user explicitly overrides the task to `runtimeSelectionPolicy: lane_lifecycle`.

## Callback Recovery

If the worker finishes only inside its own thread and does not message the controller:

1. The controller may read the worker thread to recover the result for audit.
2. Record the callback with `callbackModeObserved: controller_poll_recovery`.
3. If `callbackModeExpected` was `active_message_required`, gate check should block or surface the issue.
4. Do not tell the user that the controller was triggered. Say that the result was recovered by polling.

This is the exact failure KY-TASK must prevent: worker work completed, but the controller was not visibly triggered.

## Fallback Rules

If native host thread tools are unavailable:

- Stop the distributed execution and report the exact missing capability.
- Offer `lane_lifecycle` or `sequential-lanes` only as an explicit user-approved policy change; do not apply either automatically.
- External-write lanes must not pretend to be native worker lanes.
- If the user explicitly required real split conversations, stop and report the missing host capability.
- If the user accepts a fallback, record:

```text
原计划: distributed
当前限制: thread_tools_unavailable
降级方式: sequential-lanes
差异: worker 不会出现在侧边栏，也不会主动 callback 到总控
```

If saved-project resolution is unavailable or ambiguous, use the same stop rule. Do not describe projectless creation as a normal native fallback.

## What KY-TASK Must Not Do

- Do not implement fake thread creation inside the MCP server.
- Do not call `create_thread` with a projectless target when strict project affinity is active.
- Do not infer a project from directory text alone when multiple saved projects match; choose the deepest unique match or ask.
- Do not hide worker prompts or thread ids from the controller.
- Do not mark a worker complete only because its own thread has a final answer.
- After sidebar-visible execution was requested, do not collapse implementation back into KY-TASK00 merely because native dispatch needs extra coordination.
- Do not call polling recovery a normal callback.
