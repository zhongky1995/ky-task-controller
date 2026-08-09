# Execution Handoff Reference

Use this reference only after a task contract exists and the next question is how execution should be split. Do not use it to bypass the planning-only stop rule in `SKILL.md`.

## When To Stay Single-Threaded

Stay in the controller thread when:

- The task has one owner and one final artifact.
- The change surface is small or local.
- The next step is wording revision, one chart update, a focused file edit, or a small evidence correction.
- The main risk is consistency, and independent workers would create merge overhead.

## When To Recommend Distributed Execution

Consider distributed execution when:

- The task needs distinct professional lanes such as evidence audit, data processing, strategy judgment, draft writing, visual/chart production, or independent review.
- The task has many source files, several artifacts, disputed metrics, or multiple stakeholder perspectives.
- A wrong execution path would create expensive rework, customer-facing errors, or repeated misunderstanding.
- The controller should preserve the task contract while independent workers produce narrow intermediate artifacts.

## Mandatory Decomposition Gate

For high-standard composite tasks, do not proceed from accepted plan to broad execution until execution lanes are named.

Must output a lane split, then either recommend distributed execution or provide a written single-thread justification, when any of these are true:

- The task depends on three or more lanes, such as evidence intake, object modeling, metric design, artifact implementation, visual/dashboard design, and independent verification.
- The task combines source interpretation with external writes, such as updating Feishu docs, Base tables, dashboards, workbooks, or client-facing assets.
- Data correctness and product/reader experience are both central to success.
- The user has already experienced repeated rework, misunderstood outputs, or a failed prior execution.
- Different professional standards are required, such as data lineage, operations design, document writing, and tool/API implementation.

If native Codex Session tools are available and the user confirms execution, first call `list_projects`, resolve one saved project, and split the work into project-scoped visible worker Sessions. Under the installed `native_session_required` and `inherit_or_resolve_required` policies, do not silently emulate the split with managed subagents, sequential lanes, or projectless Sessions when native tools or project resolution are unavailable; report the blocker and request an explicit policy override.

## Split Decision And Anti-Downgrade

When the accepted task contract includes distributed execution, split conversations, independent workers, or the user has complained that prior execution failed because it was not split, later confirmations such as `继续`, `好`, `进执行`, `按这个做`, or `优化吧` must continue the split plan. Do not silently downgrade to ordinary single-thread execution.

Before execution, output a compact split decision:

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

Use distributed execution if any of these mandatory split rules are hit and worker tools are available:

- The user explicitly asks for split conversations, independent workers, subagents, multi-lane execution, or says not to run everything in one thread.
- A prior run failed because evidence, model, product/experience, implementation, and review were collapsed together.
- The task writes to external systems or durable artifacts such as Feishu Base, Feishu docs, decks, workbooks, repos, customer-facing files, or production assets.
- The task has three or more professional layers.
- Data correctness and product/user experience are both central to acceptance.
- Independent review is needed because the output is executive-facing, client-facing, financial, operationally sensitive, or hard to undo.

Before choosing `sequential-lanes` for a mandatory split task, first check and record whether an independent worker runtime is available. `sequential-lanes` is valid only when runtimes are unavailable, the user rejects background worker execution, or the current response is planning-only and will not write final artifacts.

If a real worker runtime is available and the user has confirmed execution, these outputs are invalid:

- `结论: sequential-lanes`
- `先在当前线程继续做`
- `不开多线程`
- `先预检查后直接搭`
- any one-pass execution that handles evidence, model, experience, implementation, and review in the same current-thread flow.

If real worker runtimes are unavailable, state the fallback explicitly and keep lane checkpoints separate. If the user explicitly required real separate conversations, stop and ask for the missing native-thread capability or permission instead of treating sequential lanes as equivalent.

For Feishu/Base management demos, operating dashboards, and project process cockpit work, execution after confirmation requires distributed workers whenever eligible worker tools exist.

## Worker Lifecycle Decision

Under the default Session-first policy, distributed execution means native Codex Sessions inside one resolved saved project unless the user explicitly overrides the task to `lane_lifecycle` or explicitly approves `allow_projectless`.

For every worker lane, declare:

```text
- worker_lifecycle: ephemeral | persistent
- context_policy: packet_only | checkpoint_delta
- runtime_preference: auto | managed_agent_worker | native_thread_lane
- depends_on: [] | [upstream lane names]
```

Use `ephemeral + packet_only` by default. It is appropriate when the lane has a
bounded input, one output contract, and one callback. Under the Session-first policy
it still runs in a visible native Session.

Use `persistent + checkpoint_delta` only when the lane must remain an ongoing
professional workbench across controller turns, accept direct user intervention,
or be resumed independently after a pause.

Do not choose persistence merely because the lane is important, writes a final
artifact, or needs independent review. State, artifact, and revision continuity
belong to KY-TASK; conversation persistence is an additional user-facing cost.

Declare `depends_on` for every lane. Independent siblings use `[]` or the same
upstream set and should be dispatched together. Shared-target writes and review
lanes declare the exact writers they must wait for.

## Common Execution Lanes

Choose only the lanes needed for the accepted contract:

- Evidence lane: source ledger, source quality, important fields, document links, sample records, and forbidden assumptions.
- Object/model lane: entities, states, relations, owner fields, status machine, and source-to-target mapping.
- Metric/chart lane: metric dictionary, chart matrix, denominators, filters, and reconciliation checks.
- Product/experience lane: audience path, first-screen priority, unit/page/dashboard tasks, down-drill path, and acceptance cases.
- Implementation lane: tool/API operations, schema creation, record import, document updates, scripts, and idempotency.
- Review lane: source-lineage check, user-path check, old-version contamination check, and final acceptance report.

When a task is a management system, operating dashboard, Feishu/Base demo, or project process cockpit, the product/experience lane and object/model lane must exist before implementation starts.

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
- Completion means the approved phase is complete. The final artifact is complete only after implementation and review lanes pass.

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
- Avoid concurrent writes to the same final artifact. If writing is necessary, assign exactly one writer per artifact and one independent reviewer.
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

If the current environment cannot run independent workers, run lanes sequentially in the controller thread:

1. Evidence lane output.
2. Object/model lane output.
3. Product/experience or unit contract output.
4. Implementation preview or dry-run.
5. Final implementation.
6. Review lane output.

Do not collapse these into one uninterrupted execution block. Each lane must leave an intermediate artifact or explicit checkpoint.

Use these checkpoint labels:

- `Evidence lane checkpoint`
- `Object/model lane checkpoint`
- `Product/experience lane checkpoint`
- `Implementation lane checkpoint`
- `Review lane checkpoint`

At each checkpoint, state whether the next lane is already approved or needs confirmation.

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
