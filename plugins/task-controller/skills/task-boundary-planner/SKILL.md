---
name: task-boundary-planner
description: Generate and control a reliable task contract before complex work, then continue into gated execution lanes after explicit approval. Clarify requirements, task boundaries, delivery/use mode, evidence status, domain-specific professional standards, minimum reliable standards, production/tool boundaries, capacity limits, execution triggers, optional single-thread or distributed-worker handoff plans, risks, assumptions, and acceptance criteria. Use when the user asks to 梳理需求, define task boundaries, plan a complex task, reduce hallucination risk, decide what to ask before execution, create acceptance criteria, review prior task failures, plan script/creative/content outputs, plan case/whitepaper material work, plan operating dashboards or Feishu/Base management systems, plan or continue distributed/gated execution, or analyze a repository/project before substantial work.
---

# Task Boundary Planner

## Purpose

Convert an ambiguous request into a reliable current-version task contract. Do not try to make requirements perfect. Define what can be done now, what professional standards apply, what evidence is required, what is out of scope, and what would justify reopening the boundary.

Core principle: allow unknowns, but do not allow an unbounded task.

## Outcome

For complex tasks, produce a compact `任务契约 v0` before substantial execution. When this skill is explicitly invoked as a planning step, stop at the contract, gates, and execution/handoff plan. After the user explicitly approves the locked contract or says to continue execution, advance through the agreed execution lanes instead of replanning from scratch. Do not keep reopening the boundary unless a change trigger fires.

## Operating Rules

- Lead with your own professional diagnosis; do not turn clarification into a questionnaire.
- Ask at most 2 questions in the first pass, only for blocking unknowns that change direction, risk, or acceptance.
- Classify unknowns as blocking, assumable, or observable.
- Decide whether the request is a single task or a composite task chain.
- For a composite task, keep decomposition, orchestration, capability matching, and runtime selection as four separate decisions. Do not derive parallel/serial order from the lane list.
- Treat explicit `$task-boundary-planner` invocation as planning-only by default: do not modify final artifacts, update external documents, generate polished deliverables, launch background sessions, or perform broad execution in the same response.
- Treat a later user message such as "继续", "进执行", "按这个执行", "优化吧", or "开始做" after a locked contract as an execution trigger unless the same message says not to execute.
- On execution-trigger turns, do not repeat the full contract. Identify the next lane, restate its write boundary, execute only that lane or the approved execution phase, leave an intermediate artifact/checkpoint, and state whether the final deliverable is complete.
- Identify the final deliverable first. The final deliverable sets the main acceptance standard.
- If the user asks to "think first" or "do not execute yet", still separate the final deliverable from the current phase deliverable.
- Identify the professional lens and minimum reliable standard. Do not stop at generic labels like "high standard".
- For high-standard composite tasks, define the object model before execution: metrics, business lines, units, artifacts, actors, charts, modules, or scenes.
- Identify capacity drivers and one-pass limits. Do not stop at generic labels like "high capacity".
- Lock the current task version once a workable contract exists.
- After locking, prefer local corrections over boundary resets.
- Execution starts only after an execution trigger: user confirmation after the contract, or a previously agreed workflow contract that already grants execution.
- Reopen the contract only when a defined change trigger fires.

## Stable Protocol

Use this sequence for complex tasks:

1. Deliverable: define the final artifact, audience, use context, and decision/action it supports.
2. Delivery mode: decide how the artifact will be consumed or operated; set mode-specific constraints.
3. Professional lens: identify the main domain standard and required secondary standards.
4. Composite chain: if the task has multiple layers, map evidence -> judgment -> production -> verification.
5. Minimum reliable standard: define the few professional checks that must pass in this run.
6. Evidence and capacity: define the first evidence packet, artifact graph, concrete capacity drivers, and one-pass envelope.
7. Task contract: output `任务契约 v0`, including assumptions and non-goals.
8. Unit contract: if the final deliverable has pages, sections, modules, scenes, scripts, charts, or files, define the per-unit gate before production.
9. Production path: choose the build method and tool boundary; name what must be deterministic, what can be generative, and what needs human-visible review.
10. Work orchestration: identify one semantic owner, primary/prerequisite/supporting/verification roles, parallel waves, justified serial edges, join points, and handoff-loss decisions.
11. Execution trigger and handoff: match capabilities per lane, then define what user confirmation, tool permission, lifecycle, runtime, or lane handoff is required before production starts.
12. Verification: check final-deliverable acceptance, delivery-mode fit, upstream layer standards, unit gates, production-path risks, and capacity limits.
13. Change control: decide whether new information is a local correction, evidence supplement, expression adjustment, delivery-mode correction, tool-path correction, or contract change.

If the contract already exists and the user has just confirmed execution, start at step 10 and dispatch the next dependency-ready lane batch. Do not go back to step 1 unless a change trigger fires.

Use `references/task-types.md` only as an auxiliary intent map when the user's request is unclear. It helps infer whether the user is asking for truth, clarity, judgment, expression, execution, communication, learning, or revision. It does not override the final deliverable standard in the task contract.

## Task Contract Schema

Return this structure, keeping it short:

```text
任务契约 v0
- 最终交付物:
- 当前阶段交付物:
- 使用对象/场景:
- 交付场景:
- 主专业标准:
- 副专业标准:
- 复合任务链路:
- 最低可靠标准:
- 证据链:
- 证据分层:
- 生产路径:
- 容量边界:
- 不做什么:
- 关键假设:
- 阻塞问题:
- 第一阶段计划:
- 执行触发:
- 分工/交接建议:
- 验收方式:
- 变更触发:
```

If the task is small, compress the contract into 5-7 bullets. If the task is high-stakes, large, or client-facing, keep the full contract.

## Final vs Phase Deliverable

Do not confuse the artifact needed in the current reply with the true final deliverable.

- Final deliverable: the artifact that ultimately satisfies the user's real task, such as an updated Feishu document, deck, report, code change, contract redline, data workbook, script package, or production-ready asset.
- Current phase deliverable: the bounded artifact produced now, such as a task contract, source ledger, metric dictionary, outline, first batch, sample page, dry-run, test slice, or review memo.

If execution is intentionally paused, still name the final deliverable and explain how the current phase deliverable gates progress toward it.

## Execution Stop Rule

When this skill is explicitly named, cited, or requested as a planning step, the current response is planning-only by default.

Allowed in planning-only mode:

- Read the skill instructions and relevant references.
- Inspect a small read-only evidence packet when needed to make the contract credible.
- Output the task contract, object model, source/evidence ledger, unit contract, metric/chart matrix, production path, risk list, execution plan, or handoff brief.

Not allowed in planning-only mode:

- Create, overwrite, or upload final deliverables.
- Update Feishu/Google/Office documents, decks, spreadsheets, code, or customer-facing files.
- Generate final charts, final images, final PDFs, or final packages.
- Launch background sessions, background threads, automations, or external write operations.
- Run broad or irreversible processing beyond the stated first evidence packet.

Execution may start only when one of these is true:

- The user replies after the contract with explicit approval to execute the plan.
- A previously accepted workflow contract already grants a defined execution phase.

If the user asks for a skill review, failure diagnosis, boundary check, or "先梳理", stop after the contract and recommended next action.

## Post-Contract Execution Mode

Use this mode when a task contract has already been produced and the user now approves execution.

Before taking action, run a compact readiness check:

```text
执行就绪检查
- 已锁定契约:
- 本轮执行 lane:
- 输入:
- 输出:
- 写入边界:
- 禁止动作:
- 完成后是否继续下一 lane:
```

Rules:

- If the next lane is evidence, object/model, metric/chart, or product/experience, prefer read-only outputs and stop at a checkpoint unless the user approved a full lane sequence.
- If the next lane writes to Feishu/Base/docs/decks/workbooks/code or customer-facing artifacts, verify that all upstream lane gates required by the contract exist.
- If upstream gates are missing, do not write the final artifact. Produce the missing lane artifact instead and say what must pass before implementation.
- If the user explicitly approved a full execution package, continue lane by lane, but still preserve intermediate outputs and do not merge review into implementation.
- Before choosing Sessions or sequential execution for a composite task, compile a strict work orchestration plan. QA/review must depend on the decision, sample, or artifact it judges; high-loss design/production work stays together unless a concrete handoff contract exists.
- If mandatory distributed-execution rules are hit, first check native Codex Session tools. Under the Session-first policy, hand off the dependency-ready batch to visible Session workers rather than managed subagents or sequential current-thread lanes.
- Use sequential lanes only after recording that independent worker runtimes are unavailable, the user rejects background worker execution, or the turn is planning-only with no final write.
- End each execution response with one of: `当前 lane 完成，等待确认进入下一 lane`; `当前 lane 完成，已按已批准流程继续`; `最终交付物完成`; or `阻塞，缺少...`.

## Execution Handoff

After the contract is accepted, decide whether execution should stay in the current thread or be handed off.

Keep the main contract lightweight:

- Use single-thread execution for one owner, one artifact, low ambiguity, or a small change surface.
- Consider distributed execution when distinct evidence, data, writing, visual, product, implementation, or review lanes would reduce risk or rework.
- For high-standard composite tasks, do not leave handoff optional: provide an execution lane map, check whether worker tools are available, then recommend distributed execution or justify why the task does not hit mandatory split rules.
- If the user has already complained that prior execution failed because it did not split, later confirmations such as `继续`, `好`, `进执行`, `按这个做`, or `优化吧` count as approval to continue the split plan. Do not require the user to request workers again in the next turn.
- Do not dispatch workers or open sidebar-visible tasks during planning-only mode.
- Distributed execution proceeds only after the user confirms execution. The open-source distribution has no standing approval; list the planned Sessions, obtain task-scoped approval, and record it before dispatch.
- Read `../task-controller/references/work-orchestration.md` before producing any new composite lane map. If KY-TASK tools are active, call `task_controller_plan_orchestration` and clear every strict blocker before runtime selection.
- Read `references/execution-handoff.md` when recommending distributed execution, separate Codex threads, background workers, or detailed handoff prompts.

## Professional Lens Routing

Use professional lenses to define standards, not to add ceremony.

Common lenses:

- Data / spreadsheet / research analysis.
- Business / operating review / management reporting.
- Code / repository / system implementation.
- Deck / client-facing narrative / visual communication.
- Case / whitepaper / public-facing material supply.
- Script / screenplay / creative content.
- Contract / policy / legal-risk review.
- Marketing / KOC / content strategy.
- Operations / project execution / stakeholder coordination.

For high-standard tasks, state:

- Object model: entities, fields, files, metrics, pages, actors, or systems.
- Correctness criteria: what a professional would check first.
- Failure modes: what mistakes commonly create wrong results.
- Evidence chain: sources, scripts, formulas, samples, tests, or references.
- Acceptance checks: what must match across outputs before handoff.

If no listed lens fits, generate a provisional lens:

```text
专业判断形成
- 最终交付物要求的主标准:
- 依赖的副专业能力:
- 该领域最容易错的 3-5 件事:
- 本轮最低可靠标准:
- 第一轮证据/参考:
```

Read `references/domain-lenses.md` for data, code, deck/story, contract/policy, marketing/KOC, or operations planning. Read `references/case-whitepaper-materials.md` for case studies, whitepaper source packages, public-facing case supply drafts, or evidence-heavy case material curation. Read `references/ops-dashboard-prototype.md` for project management systems, Feishu/Base demos, operating dashboards, PM update flows, or management cockpit prototypes.

## Object Model Gate

Use an object model gate when professional correctness depends on stable categories.

State the task's core objects before planning execution. Examples:

- Data/reporting: metrics, source files, fields, filters, business lines, projects, time periods, charts, and output sections.
- Deck/document: sections, pages, claims, evidence assets, audiences, decisions, and required actions.
- Script/creative: audience, channel, speaker, scenes/beats, claims, brand facts, forbidden claims, and production constraints.
- Code/system: modules, APIs, schemas, state, callers, tests, and generated artifacts.

If the object model is missing or vague, do not proceed to polished production. Produce the object model as the current phase deliverable or make the first phase an evidence scan.

## Evidence Status Gate

Use an evidence status gate when the task depends on mixed materials, past projects, case files, drafts, templates, sales decks, screenshots, tables, or user-provided background.

Before polished production, classify important materials and claims:

```text
证据分层
- 可作为事实:
- 可作为结果数据:
- 可作为方法论启发:
- 仅后台参考:
- 禁用/不得进入正文:
- 需要用户确认:
```

Rules:

- Background context is not automatically final-output wording.
- Source presence is not permission to include it.
- Drafts, templates, sales materials, and unclosed proposals are not proof of delivered work.
- Internal source files can support judgment without appearing in the final artifact.
- If a claim is only inspired by a source, label it as method abstraction, not case fact.

If the task is public-facing, client-facing, or executive-facing, do not proceed from "material collection" to "final writing" until the evidence status gate exists.

## Composite Task Routing

Treat a task as composite when the final output depends on multiple professional layers, such as data analysis -> business judgment -> client-facing deck, repo discovery -> implementation -> test report, or contract review -> negotiation memo.

For composite tasks:

- Main acceptance criteria come from the final deliverable and its audience.
- Prerequisite acceptance criteria come from upstream evidence layers.
- Do not let an upstream layer dominate the task if it is only evidence for the final deliverable.
- Do not skip an upstream layer if the final deliverable would become unsupported without it.
- Build the primary semantic path first. Add prerequisite/supporting work only when its output is consumed by that path.
- Mark exactly one primary lane as semantic owner. A clean worker Session cannot repair missing or conflicting ownership.
- Independent lanes share a wave only when neither consumes the other, neither verifies the other's future output, and they have a declared downstream join point.

Every phase must name:

- Input.
- Output.
- Professional standard.
- Gate to proceed.
- Final-deliverable dependency.
- Contribution role and semantic authority.
- Output contract, downstream consumer, and dependency reason.

## Delivery Mode Gate

Use a delivery mode gate when the output will be read, watched, presented, operated, edited, packaged, or handed off.

State the primary mode:

- Live presentation or projection: speaker-led, screen-first, one screen one idea.
- Self-read document or web page: reader-led, scan-friendly, denser explanation allowed.
- External share package: portable, clean file structure, no QA leftovers, clear entry file.
- Working tool or interactive page: operator-led, task flow, controls, states, and error handling matter.
- Internal handoff or editable draft: reviewer-led, traceability and editability matter.

Then state:

- Consumption environment: projector, meeting room, desktop, mobile, print, async reading, or runtime.
- Primary interaction: speaker-led, reader-led, operator-led, reviewer-led, or automated.
- Format consequences: page density, navigation, visual hierarchy, asset packaging, responsiveness, editability, or runtime behavior.
- Mode-specific acceptance check: screenshot, preview, print, package listing, smoke test, or handoff checklist.

If multiple modes are possible, choose the primary mode and mark secondary modes as optional. If a later user message changes the primary mode, treat it as a contract change unless the existing artifact can be patched locally without changing the unit contract.

## Unit Contract

Use a unit contract when the final deliverable is made of repeatable units: slides, report sections, document chapters, script scenes, short-video beats, UI screens, chart assets, data tables, code modules, or workflow steps.

For each important unit, state:

```text
交付单元契约
- 单元:
- 单元任务:
- 主结论/功能:
- 必需证据/输入:
- 表达或实现方式:
- 不能说/不能做:
- 过关标准:
```

Do not produce polished final units before the unit contract exists when the task is high-standard, client-facing, evidence-heavy, or reference-driven.

For reports, decks, Feishu documents, scripts, or multi-section artifacts, do not merely promise a future unit contract. Output the important unit contracts before moving into execution.

If the user provides reference materials, first extract the reference logic:

- What structure or page task should be learned.
- What evidence pattern should be learned.
- What tone, density, or visual hierarchy should be learned.
- What must not be copied directly.

Reference materials calibrate structure and standards; they do not replace the task's own evidence and contract.

## Metric and Chart Matrix

Use a metric/chart matrix when the task contains numbers, tables, charts, dashboards, finance/business reporting, or quantified claims.

For each important metric or chart, state:

```text
指标/图表口径
- 名称:
- 指标定义:
- 来源文件/字段:
- 筛选规则:
- 分类规则:
- 是否纳入特殊调整:
- 是否排除:
- 输出位置:
- 验收检查:
```

Do not generate or update charts before their matrix exists when chart denominators, time ranges, categories, or source files are disputed or high-stakes.

## Production Path Contract

Use a production path contract when the task will create or modify artifacts, especially decks, reports, charts, images, scripts, data files, code, PDFs, or client-facing materials.

State:

- Source of truth: data table, script, raw asset, existing draft, reference material, repo source, or user-approved outline.
- Build path: deterministic script, manual edit, rendering/export chain, generative image/text step, or mixed pipeline.
- Tool boundary: what the chosen tool may change and what it must preserve.
- Fidelity risk: numbers, formulas, screenshots, quotes, layout, brand identity, legal wording, or executable behavior that cannot be invented.
- Review gate: the smallest preview, sample, diff, screenshot, render, or test that must pass before scaling.

If a requested tool conflicts with the professional standard, narrow its role instead of silently following the tool request. For example, use generative image tools for layout moodboards or visual drafts, but not as the source of truth for evidence-heavy pages containing exact charts, word clouds, screenshots, or quoted text.

Do not produce polished artifacts before the production path is compatible with the minimum reliable standard.

## Minimum Reliable Standard

Define the minimum reliable standard as professional bottom lines for this run, not an exhaustive ideal state.

Examples:

- Data analysis: metric dictionary, denominator checks, source lineage, one cross-output reconciliation.
- Client-facing strategy: each key claim has evidence, safe wording, audience relevance, and action implication.
- Script/creative output: target audience, channel, desired reaction/action, content mechanism, execution feasibility, and brand/safety boundary are clear.
- KOC/social analysis: volume, sentiment/NSR, topic, quote, interaction, search demand, and competitive benchmark are not mixed.
- Code work: relevant source inspection, change surface, tests or manual verification path, dirty worktree awareness.
- Contract/policy: exact clause reference, obligation/risk split, business vs legal judgment separation.

For high-standard outputs, use a small claim support check for the central claims only:

```text
关键结论校准
- 结论:
- 证据状态: 支持 / 部分支持 / 不支持
- 证据来源:
- 不能说:
- 安全表达:
- 需要的图表/样本/测试:
```

Do not run this for every sentence. Use it for the 3-5 claims that would shape the final deliverable.

For unit-based deliverables, attach the claim support check to the units that carry the central claims, not to every unit.

## Capacity Boundary

Task boundary = professional standard boundary + capacity boundary.

- Professional standard boundary decides what counts as correct or good.
- Capacity boundary decides how much can be handled in this run.

State concrete capacity drivers:

- Volume driver: files, rows, slides, records, modules, pages, stakeholders, or artifacts.
- Dependency driver: upstream sources, downstream outputs, tools, scripts, people, or systems.
- Context driver: how much must be read before the task can be done safely.
- Verification driver: how many checks or comparison surfaces are required.
- Runtime driver: long scans, exports, tests, renders, uploads, or review loops.

Read `references/capacity-boundary.md` for four execution modes and one-pass envelope guidance.

## Question Policy

Ask only for blocking unknowns. Everything else should become an assumption or an observation target.

Blocking unknown:
- Missing final deliverable, decision owner, required source, legal/financial/medical constraint, or non-negotiable standard.

Assumable unknown:
- Style preference, exact wording, minor format choice, incomplete examples, unless the final deliverable depends on them.

Observable unknown:
- Pattern, distribution, source quality, repo structure, sample quality, or data issue that can be inspected during the first evidence pass.

Prefer:
- "这个结果是给谁用的?"
- "这次要交付分析稿、执行清单、改稿，还是直接产物?"
- "有没有不能假设、不能改、必须查证的部分?"

Avoid:
- Asking cosmetic questions before the contract exists.
- Asking questions answerable from files, data, or repo context.
- Reopening the contract for details that fit inside the current contract.

## Evidence-First Planning

Before executing a high-standard task, inspect the smallest evidence packet needed to make the plan credible. If evidence is not available, make the first phase an evidence acquisition phase.

For data/client-facing analysis, this often means:

- Source ledger and time range.
- Field list and row counts.
- Metric formulas and denominators.
- Sample evidence for qualitative claims.
- Existing outputs that must remain consistent.

For script/creative output, this often means:

- Audience, channel, desired reaction/action, and usage context.
- Brand/product facts, constraints, and forbidden claims.
- Content form: short video, KOC口播, TVC, scene script, plot script, title set, poster copy, or campaign idea.
- Execution limits: length, format, production resources, platform style, and compliance risk.
- Reference examples only as logic/taste calibration, not as something to copy blindly.

For repo work, read `references/repo-risk-scan.md` and run a lightweight scan before committing to a substantial plan.

## Change Control

After `任务契约 v0` is locked, classify new information:

- Local correction: fix wording, label, formula display, or a small mismatch without changing the contract.
- Evidence supplement: add a source, sample, chart, or verification record without changing the deliverable.
- Expression adjustment: improve audience fit, story, tone, or page logic without changing the evidence base.
- Delivery-mode correction: adjust layout, density, navigation, packaging, or verification to match how the artifact will actually be used.
- Contract change: reopen only when the final deliverable changes, evidence disproves a core claim, a professional standard was wrong, a capacity limit is exceeded, or a user changes a non-negotiable constraint.

If it is not a contract change, do not restart the task. Patch locally and continue.

When KY-TASK state is active, direct user correction language such as “不对”, “我要的是”, or “按上一版” is still a controller event even before a worker reports it. Call `task_controller_record_correction` with a unique event ID, summary, category, affected requirement IDs, and required `recommendedInvalidFromLane`; then use `task_controller_revise_contract` to consume all open corrections before resuming registration, gates, or completion.

## Verification

Verify against three layers:

- Final deliverable: does the output serve the user, audience, and decision/action?
- Delivery mode: does it work in the actual use environment, such as projection, self-reading, external sharing, operation, or handoff?
- Professional standards: did the minimum reliable checks pass?
- Capacity boundary: did the run stay inside the promised one-pass envelope?

For composite tasks, verify every layer gate before handoff.

## Learning From Prior Runs

When the user cites a prior thread, failed run, or unsatisfactory skill use:

1. Read the referenced thread or use the pasted summary if direct reading is unavailable.
2. Extract the concrete miss: missing professional lens, weak task contract, wrong capacity estimate, missing layer gate, unsupported claim, poor change control, or weak verification.
3. Turn the miss into a compact reusable rule in this skill or its references.
4. Avoid storing long case history.

## Failure Policy

- If no workable contract can be formed, state exactly which contract field is blocking and ask for the minimum missing input.
- If professional lens is unclear, choose the likely lens and mark it as an assumption; do not proceed with only generic task-type labels.
- If delivery mode is ambiguous and likely changes layout, density, packaging, or verification, infer the likely primary mode and mark it as an assumption before production.
- If the task is composite but only one layer is planned, stop and map the missing layers.
- If composite lanes have no explicit semantic owner, dependency reasons, parallel waves, or join points, stop and compile the work orchestration plan before runtime selection.
- If QA/review precedes the artifact it judges, or implementation depends on that premature QA, reject and re-orchestrate the lane map.
- If design and production are split despite high handoff loss, combine them or define a concrete artifact handoff contract.
- If the final deliverable is unit-based but unit gates are missing, stop before polished production and create the unit contract.
- If the production path can corrupt the evidence, wording, layout, or executable behavior required by the professional standard, stop before polished production and define a safer path or a preview-only role for that tool.
- If a key claim is only partially supported, use safe wording or make evidence acquisition the next phase.
- If upstream evidence is sound but the final deliverable lacks audience fit, story, or actionability, the task is not complete.
- If capacity demand exceeds the one-pass envelope, split the work and name the next gate.
- If the user asks to proceed despite gaps, proceed only with explicit assumptions and change triggers.
