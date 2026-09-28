# Execution Handoff Reference

Use this reference only after a task contract exists and the next question is how execution should be split. Do not use it to bypass the planning-only stop rule in `SKILL.md`.

Before choosing single-thread or distributed runtime, apply
`../../task-controller/references/work-orchestration.md`. Decomposition names
the professional jobs; orchestration proves which jobs are parallel or serial.
Runtime selection is the later placement decision.

## Execution Decision

Apply `../../task-controller/references/working-agreement.md` for mode selection, continuation and authority. It is the single decision source; this handoff does not add domain-specific split requirements.

Pass the selected outcome, ownership, authorized runtime, boundaries and unresolved choices to the controller. An existing agreement survives small follow-ups. Initial planning may recommend workers, but neither the recommendation nor a generic execution approval grants visible-conversation permission.

For composite work, use the smallest useful responsibility map and compile its dependencies through `work-orchestration.md`; required professional considerations need not each become a lane or Session.

## Worker Lifecycle Decision

Under the default Session-first policy, distributed execution means native Codex Sessions inside one resolved saved project unless the user explicitly overrides the task to `lane_lifecycle` or explicitly approves `allow_projectless`.

For every worker lane, declare:

```text
- worker_lifecycle: ephemeral | persistent
- context_policy: packet_only | checkpoint_delta
- runtime_preference: auto | managed_agent_worker | native_thread_lane
- depends_on: [] | [upstream lane names]
- dependency_reasons: {upstream lane: why this must be serial}
- contribution_role: primary | prerequisite | supporting | verification
- semantic_authority: define | constrain | implement | define-and-implement | verify
- input_contracts / output_contracts:
- capability_requirements:
```

Use `ephemeral + packet_only` for a genuinely one-off isolated job. It is appropriate when the lane has a
bounded input, one output contract, and one callback. Under the Session-first policy
it still runs in a visible native Session.

Use `persistent + checkpoint_delta` when the responsibility continues through related serial execution, correction or review, or must remain an ongoing
professional workbench across controller turns, accept direct user intervention,
or be resumed independently after a pause.

Do not choose persistence merely because the lane is important, writes a final
artifact, or needs independent review. State, artifact, and revision continuity
belong to KY-TASK. Compare retained-context cost against repeated setup and
handoff cost; planned related follow-ups usually favor a continuing Session.
Steps and checkpoints do not each need a conversation. Follow
`../../task-controller/references/dispatch-and-recovery.md` for safe reuse.

Declare `depends_on` for every lane. Independent siblings use `[]` or the same
upstream set and should be dispatched together. Shared-target writes and review
lanes declare the exact writers they must wait for.

Review/QA is not an upstream style guide unless explicitly reclassified as a
prerequisite constraint. Verification depends on the decision, sample, or
artifact it judges. If design and production have high handoff loss, keep them
in one `define-and-implement` lane or require a concrete artifact contract.

## Possible Execution Lanes

Choose only the lanes needed for the accepted contract:

- Evidence lane: source ledger, source quality, important fields, document links, sample records, and forbidden assumptions.
- Object/model lane: entities, states, relations, owner fields, status machine, and source-to-target mapping.
- Metric/chart lane: metric dictionary, chart matrix, denominators, filters, and reconciliation checks.
- Product/experience lane: audience path, first-screen priority, unit/page/dashboard tasks, down-drill path, and acceptance cases.
- Implementation lane: tool/API operations, schema creation, record import, document updates, scripts, and idempotency.
- Review lane: source-lineage check, user-path check, old-version contamination check, and final acceptance report.

For management systems and dashboards, cover the object model and user path before implementation where they affect acceptance. These considerations may belong to one cohesive owner; they do not mandate separate lanes.

These are examples, not a default five-lane template. When no scenario pack
matches, derive the smallest graph from the actual primary path and its consumed
prerequisites/support; do not instantiate every example lane.

## Handoff Stop Rule

Do not treat distributed execution as an automatic executor.

- During planning-only mode, output the handoff brief only.
- Do not create threads, message workers, launch background sessions, or modify final artifacts until the user confirms execution.
- If native thread or project discovery tools are unavailable, stop and record the limitation; do not silently create projectless workers.
- Do not bind the plan to a specific plugin unless the user explicitly requests that plugin and the tool is available.

## Execution Trigger Handling

When the user approves a previously locked contract, the controller must switch from planning to gated execution.

Do this first:

```text
执行就绪检查
- 已锁定契约:
- 本轮 lane:
- lane 输入:
- lane 输出:
- 写入边界:
- 禁止动作:
- 验收/回调:
```

Then execute only the approved lane or the approved lane sequence.

Rules:

- Do not regenerate the whole task contract unless a change trigger fires.
- Do not jump directly from a high-level contract into implementation when evidence, object/model, metric/chart, or product/experience lanes are required and missing.
- If the user says "continue", "execute", "go ahead", "进执行", "继续", "按这个做", or similar after accepting the plan, perform the next lane instead of answering with another plan.
- If the user previously said "完成规划后等确认", stopping after planning was correct. A later confirmation is the execution trigger.
- If the user asks "why was it not completed", explain which phase was completed and which execution trigger or lane gate was missing.
- Completion means the requested outcome and its applicable checks pass. A phase checkpoint is not final delivery; a separate review lane is required only when the agreement or risk requires independence.

## Handoff Brief

Use this compact brief before any distributed execution:

```text
Execution handoff brief
- 目标:
- 已锁定任务契约:
- 推荐模式: single-thread / distributed
- 推荐理由:
- worker lanes:
- 每个 worker 的 lifecycle / runtime:
- 每个 worker 的 depends_on:
- 每个串行依赖的原因 / 并行波次 / join point:
- semantic owner / primary path:
- 每个 worker 的 capability requirement:
- 每个 worker 的输入:
- 每个 worker 的输出:
- 写入边界:
- 禁止动作:
- 回调/验收:
- 需要用户确认:
```

## Distributed Worker Execution Package

Use this package when the accepted plan should be split across independent workers without binding to any plugin or runtime provider.

Rules:

- One controller owns the task contract, final artifact integration, user communication, and final verification.
- Workers receive narrow prompts and must not infer a broader task than assigned.
- Workers normally produce intermediate artifacts: source ledger, evidence review, section draft, chart data, critique memo, or verification report.
- Avoid concurrent writes to the same final artifact. Assign one writer per artifact and independent review when required by the contract or consequential risk.
- Give every worker its own lifecycle, runtime preference, dependency list, input set, forbidden actions, expected output, and callback format.
- Do not let a worker update Feishu/docs/decks/spreadsheets, code, or customer-facing assets unless the handoff explicitly grants that write scope.
- The controller must reconcile worker outputs against the original contract before final production.

When recommending distributed execution, include:

```text
分布式 worker 执行包
- 总控职责:
- worker 清单:
  - 名称:
  - lifecycle / runtime:
  - 任务:
  - 输入:
  - 输出:
  - 工具/读写边界:
  - 禁止动作:
  - 回传格式:
- 合并规则:
- 最终验收:
```

## Sequential Lane Fallback

If the current environment cannot run independent workers, report the limitation.
Use sequential controller execution only when the user's agreement and host rules
permit that fallback; under Session-first policy obtain an explicit override.
Lack of a runtime alone never cancels a controller-only role. If authorized, keep
only the needed intermediate checkpoints, for example:

1. Evidence lane output.
2. Object/model lane output.
3. Product/experience or unit contract output.
4. Implementation preview or dry-run.
5. Final implementation.
6. Review lane output.

Keep each lane's intermediate artifact or explicit checkpoint so its acceptance can be checked. Execution may continue uninterrupted across passing checkpoints within the authorized scope; lane separation does not require separate user turns.

Use these checkpoint labels:

- `Evidence lane checkpoint`
- `Object/model lane checkpoint`
- `Product/experience lane checkpoint`
- `Implementation lane checkpoint`
- `Review lane checkpoint`

At each checkpoint, verify the next lane's dependencies and authority internally, then continue when ready. Ask the user only for an actual reserved decision or missing permission, not because a checkpoint was reached. See `../../task-controller/references/continuous-execution.md`.

## Controller Responsibilities

The controller must:

- Preserve the locked task contract and change triggers.
- Decide which worker outputs are accepted, rejected, or need follow-up.
- Prevent unsupported claims from moving into final artifacts.
- Merge only after checking source lineage, audience fit, and production boundaries.
- Communicate one final outcome to the user.

## Worker Prompt Requirements

Each worker prompt should include:

- The narrow task.
- The exact input files, links, or snippets it may use.
- The expected output shape.
- The evidence or verification rule.
- Forbidden actions and forbidden assumptions.
- Whether the worker may write files or only return analysis.

Workers should not receive the whole conversation unless the whole conversation is necessary for their lane.

## Merge And Verification

Before final production, verify:

- Worker outputs match the original contract.
- Metrics, labels, dates, source files, and terminology are consistent.
- No worker exceeded its write boundary.
- The final artifact still matches the delivery mode.
- Any unresolved conflicts are surfaced as assumptions or open issues, not silently resolved.
