# Business Delivery Presets

These presets constrain the business shape of the final artifact. Use them with
`contractSpec.specVersion: "2.0"`; they do not replace task-specific acceptance checks.

## Shared High-Risk Rules

- High-risk, client-facing, executive-facing, or durable-write work should define non-empty `intentAnchors`.
- Order `canonicalSources.priority` from the controlling source to supporting evidence; lower numbers take precedence. Record source `role` and `appliesTo` when only part of the deliverable is governed.
- Put every settled user choice in `decisionLedger`; use `status: binding` while it remains mandatory.
- Set `deliverable.standalone: true` when the receiver must understand the result without controller chat, repository context, or an internal walkthrough.
- Final artifacts must not expose internal file paths, worker/lane names, prompt language, controller process notes, unfinished placeholders, or phrases such as “本轮先做”“后续补充”“根据内部材料”.
- Use `sampleGate` for machine-verifiable sample quality and `userApprovalGate` for explicit human approval. They are independent gates.
- `interactionMode: discuss_only` and `plan_only` never authorize an `approved-target` lane. Durable writes require `execute`, a matching `writePolicy`, and a verified `writeReceipt`.

## 逐P对客稿

- Audience and use mode: named client stakeholders; live presentation, direct circulation, or both.
- Units: one unit per page. The strict manifest must cover every page ID.
- Source priority: signed brief and approved client facts, approved sample/style, current source materials, then non-binding references.
- Standalone delivery: each page must carry enough claim, evidence, and context to be read outside the production conversation; the package has one visible entrypoint.
- Approval: require a representative sample page and explicit user approval before blocking production pages.
- Forbidden: internal paths, page-production notes, worker/process language, unsupported claims, and references that require the client to open internal source files.

## 证据型分析

- Audience and use mode: decision owner reviewing findings, confidence, and recommended action.
- Units: findings, claims, tables, charts, or report sections with stable IDs.
- Source priority: authoritative primary data, approved business definitions, reproducible calculations, then contextual references.
- Standalone delivery: expose source role, applicability, methodology limits, and evidence for each material conclusion; include an entrypoint summary when self-contained packaging is required.
- Approval: use user approval when a sample claim/evidence treatment determines the rest of the report.
- Forbidden: converting background reference into fact, hiding evidence gaps, internal analysis paths, and process narration in the final report.

## 客户报价 / 商业预算

- Audience and use mode: client decision-makers approving what they buy, what it costs, and how delivery is judged.
- Decision authority: presentation and layout choices may be `agent_may_decide`; pricing structure, billable items, budget allocation, KPI binding, scope commitments, and contract terms default to `propose_then_confirm` unless the user explicitly grants a different authority.
- Required graph: `source-normalization -> pricing-model -> commercial-review -> user-approval -> workbook-architecture -> implementation -> final-review`. Workbook architecture must not run in parallel with an unapproved pricing model.
- Commercial review: every charge item must show independent deliverable value, purchase reason, overlap decision, removal impact, and source reference. Pairwise overlap, KPI causality, budget rationale, and the client purchase hierarchy require artifact-bound evidence.
- Approval: bind user approval to the fingerprinted `commercial-pricing-model` artifact produced by the independent commercial review. Approval blocks workbook architecture, implementation, and final review; a later correction makes it stale.
- Forbidden: duplicate node charges, filler fees used only to force a target total, internal execution steps presented as first-level client purchase modules, unverifiable KPI deductions, and a reviewer assertion without evidence references.

## 飞书 Base / 驾驶舱 / Wiki

- Audience and use mode: named operators and managers using the artifact repeatedly, not merely reviewing a prototype.
- Units: tables, views, dashboards, Wiki nodes, forms, workflows, and navigation entrypoints.
- Source priority: approved operating rules and field definitions, current production structure, verified source data, then visual references.
- Standalone delivery: define the first operational entrypoint, role-specific paths, and the maximum required opens; readback evidence must prove the written object can be found and used.
- Approval: require user approval for a sample view/page when it fixes the information hierarchy or operating path.
- Write policy: list exact Base/Wiki targets and allowed actions. Every approved-target callback returns the exact locator, before/after version, readback evidence, and idempotency key.
- Forbidden: writing during discussion/planning, creating adjacent unapproved objects, leaking internal IDs/paths into visible copy, and claiming completion from local drafts.

## 现有文档修订

- Audience and use mode: the document's real recipient and the handoff/editing context.
- Units: sections, clauses, pages, or named content blocks affected by the revision.
- Source priority: current approved document, explicit user corrections, binding decisions, then supplementary references.
- Standalone delivery: preserve surrounding context, navigation, formatting conventions, and document identity; provide one entrypoint to the revised document or package.
- Approval: require explicit sample approval when tone, redline style, structure, or preservation policy is uncertain.
- Write policy: target the exact existing document and distinguish update from destructive replace/delete actions.
- Forbidden: broad rewrites outside allowed changes, loss of preserved content, internal revision commentary in the clean copy, and stale approval reuse after a correction.
