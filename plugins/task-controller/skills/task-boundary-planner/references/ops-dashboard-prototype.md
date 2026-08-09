# Operations Dashboard Prototype Reference

Use this reference for project management systems, Feishu/Base demos, PM update flows, operating dashboards, management cockpits, or any task where a user expects to inspect exceptions first and then drill into records.

## Core Principle

Do not start by building tables or charts. Start by defining the management question the first screen must answer.

A useful operating dashboard answers:

- What needs attention now?
- Why does it need attention?
- Who owns the next action?
- What is blocked?
- Where can I drill down?
- What changed this week?

## Required Planning Gates

Before execution, output these gates:

```text
经营看板原型闸门
- 首页使用路径:
- 首页必须回答的问题:
- P0/P1 关注规则:
- 下钻对象:
- 项目/商务/财务/交付/风险状态机:
- PM 输入到结构化字段映射:
- 看板单元契约:
- 干净 Demo 规则:
- 验收用例:
```

Planning gates are not the demo. They only authorize the next execution lane. A Feishu/Base prototype is not complete until implementation and review gates pass.

## Management User Path

Define the path before schema or charts:

1. Open dashboard.
2. See P0/P1 projects or issues first.
3. Read reason, owner, due date, money/risk impact, and next action.
4. Drill into project, business process, delivery task, PM update, or risk record.
5. Decide follow-up, escalation, or no action.

If the dashboard cannot support this path, it is a reporting page, not a management cockpit.

## Object Model

For project process management, define these objects before table creation:

- Project: standard project name, aliases, client, business line, owner, PM, stage, health, priority.
- PM update: source document, update date, project link, progress, next plan, issue, suggested field updates.
- Business/commercial process: quote, contract, project approval, billing, payment, settlement, closing.
- Delivery work: milestone, task, owner, progress, blocker, due date.
- Risk/issue/change: risk type, severity, owner, next action, due date, impact.
- Dashboard attention item: priority, reason, owner, next action, source record, status.

Do not merge all of these into one wide table unless the task is explicitly a one-table prototype.

## Status Machines

Fields must support management decisions, not just labels.

Typical status groups:

- Delivery: not started, starting, in delivery, stable, blocked, at risk, acceptance, closed.
- Commercial: not quoted, quoted, pending contract, contract signed, contract blocked, closed.
- Finance: not billed, billed, partly paid, pending payment, payment overdue, prepayment needed.
- Project approval/closing: not started, in process, blocked, complete, not applicable.
- PM update: not submitted, received, parsed, needs human check, written back, failed.

Every red/yellow status needs a reason and next action.

## Dashboard Unit Contract

For each dashboard block, state:

```text
看板单元契约
- 单元:
- 管理问题:
- 数据来源:
- 关注规则:
- 下钻目标:
- 通过标准:
```

Preferred first screen:

- P0 attention queue.
- P1 attention queue.
- Contract/commercial blockers.
- Payment/cash-flow blockers.
- Delivery blockers.
- Missing PM updates.
- This-week changes.

Distribution charts can appear after attention queues. Do not let pie charts or generic status counts lead the page when the user needs action.

## PM Input To Agent Writeback

Define the writeback path before implementation:

```text
PM 输入链路
- 来源: Feishu doc / project wiki / PM weekly report / IM summary
- 解析字段:
- 目标表:
- 目标字段:
- 自动写入:
- 需要人工确认:
- 冲突处理:
- 看板受影响单元:
```

At least one demo record should prove the full chain:

PM document -> parsed update row -> project status/risk/commercial field -> dashboard attention item.

## Clean Demo Rule

A demo intended for user evaluation must be clean:

- Prefer creating a fresh demo over copying an old one.
- If copying is necessary, remove or hide old dashboards, obsolete views, old examples, and old README links before delivery.
- Give the primary dashboard an unmistakable name such as `经营驾驶舱（先看这个）`.
- Do not leave v1/v2 or old entry points in the user-facing handoff unless the user asks for version comparison.
- Validate the user-visible entry, not only table counts and API success.

## Clean V3 Execution Sequence

When a previous dashboard/Base demo failed because it was table-first, chart-heavy, copied from an old version, or missing the PM update -> Agent writeback -> dashboard chain, use a clean-room sequence.

Do not modify the existing demo during planning. After execution is approved, run these lanes:

1. Evidence lane
   - Output: source ledger, source field inventory, sample project evidence, PM input source list, old-asset blocklist.
   - No Base writes.
   - Gate: each sample project has traceable business/commercial/finance/delivery/PM evidence or is marked as assumption.

2. Object/model lane
   - Output: table objects, field dictionary, relations, P0/P1 trigger rules, state machines, source-to-target mapping.
   - No Base writes.
   - Gate: every red/yellow state has reason, owner, next action, and source record.

3. Product/experience lane
   - Output: homepage layout, first-screen priority, dashboard unit contracts, drill-down paths, empty/conflict states.
   - No Base writes unless the user explicitly approved a visual-only mock.
   - Gate: the homepage answers who to watch, why, who owns it, next action, and money/contract/delivery blockage.

4. Implementation lane
   - Output: clean v3 Base, tables, fields, records, views, dashboard, and PM source records.
   - Writes allowed only to the approved clean v3 target.
   - Gate: one PM document chain changes a structured record and the dashboard attention item.

5. Review lane
   - Output: acceptance report, source reconciliation, user-path check, old-version contamination check.
   - Gate: required acceptance cases pass or unresolved risks are surfaced.

If the user confirms "execute" after the planning gates, start with Evidence lane. Do not jump to Implementation lane unless the upstream lane artifacts already exist and are accepted.

## Acceptance Cases

Before final handoff, verify these cases:

- Opening the dashboard shows what to look at first.
- A P0 item has reason, owner, due date, next action, and drill-down record.
- A commercial blocker appears in both the commercial table and dashboard.
- A PM update source can be traced to a structured update record.
- At least one dashboard number reconciles with its source table.
- No obsolete dashboard, copied artifact, or stale README entry competes with the main entry.
