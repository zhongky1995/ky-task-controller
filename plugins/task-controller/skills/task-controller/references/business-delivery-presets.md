# Business Delivery Presets

These presets constrain the business shape of the final artifact. Use them with
`contractSpec.specVersion: "2.0"`; they do not replace task-specific acceptance checks.

Apply only the preset relevant to the actual deliverable. Sample/structure
approval below is conditional on a user-requested checkpoint or a material choice
reserved to the user; it is not triggered merely because the author must make a
professional design decision. When structure or expression is delegated, the
owner may develop and check it without a new approval phase. Existing recorded
approval gates, mandatory gates from the selected scenario pack (including those
not yet recorded in state), and the commercial-pricing approval chain remain binding; this
guidance does not clear them or change an active contract.

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
- Approval: when the user requests a sample checkpoint or reserves a material presentation choice, obtain representative-sample approval before the affected production pages; otherwise develop and check the pages within delegated authority.
- Forbidden: internal paths, page-production notes, worker/process language, unsupported claims, and references that require the client to open internal source files.

## 证据型分析

- Audience and use mode: decision owner reviewing findings, confidence, and recommended action.
- Units: findings, claims, tables, charts, or report sections with stable IDs.
- Source priority: authoritative primary data, approved business definitions, reproducible calculations, then contextual references.
- Standalone delivery: expose source role, applicability, methodology limits, and evidence for each material conclusion; include an entrypoint summary when self-contained packaging is required.
- Approval: ask about claim/evidence treatment only when it entails an unresolved choice reserved to the user; ordinary analytical treatment remains the professional owner’s responsibility.
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
- Approval: seek sample view/page approval when it fixes a material operating choice reserved to the user; delegated information design may proceed within the approved write policy.
- Write policy: list exact Base/Wiki targets and allowed actions. Every approved-target callback returns the exact locator, before/after version, readback evidence, and idempotency key.
- Forbidden: writing during discussion/planning, creating adjacent unapproved objects, leaking internal IDs/paths into visible copy, and claiming completion from local drafts.

## 现有文档修订

- Audience and use mode: the document's real recipient and the handoff/editing context.
- Units: sections, clauses, pages, or named content blocks affected by the revision.
- Source priority: current approved document, explicit user corrections, binding decisions, then supplementary references.
- Standalone delivery: preserve surrounding context, navigation, formatting conventions, and document identity; provide one entrypoint to the revised document or package.
- Approval: clarify unresolved preservation authority or a material preference reserved to the user. Uncertainty about delegated tone or structure calls for professional judgment, not automatic sample approval; explicit sample checkpoints remain binding.
- Write policy: target the exact existing document and distinguish update from destructive replace/delete actions.
- Forbidden: broad rewrites outside allowed changes, loss of preserved content, internal revision commentary in the clean copy, and stale approval reuse after a correction.
