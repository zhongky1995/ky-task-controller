# Task Type Reference

Use this reference only as an auxiliary intent map when the user's request is unclear. It helps infer the user's core ask, but it does not set the final acceptance standard. In the main skill, the final deliverable and professional lens define the task contract.

## 求真型

Core question: facts 到底是什么?

Typical tasks: company checks, prospectuses, contracts, policies, financial reports, product parameters.

Acceptance criteria:
- Separate verified facts from inference.
- Cite or name the evidence source when external or document-based facts matter.
- Flag stale, conflicting, missing, or low-confidence facts.
- Avoid filling factual gaps with plausible narrative.

Process notes:
- Verify current or high-stakes facts before using them.
- Prefer primary sources: official docs, filings, original files, repo source, contracts, datasets.

## 求清型

Core question: 混乱信息怎么理清?

Typical tasks: meeting notes, requirements cleanup, file organization, customer needs understanding.

Acceptance criteria:
- Group related items under stable categories.
- Remove duplicates and separate facts, decisions, open questions, and actions.
- Preserve source meaning without inventing unsupported conclusions.
- Output is easy to continue from: owners, priorities, next steps, or unresolved issues are visible when relevant.

## 求判型

Core question: 应该怎么判断和取舍?

Typical tasks: resume evaluation, contract risk, cooperation judgment, strategic choice.

Acceptance criteria:
- State the decision frame and evaluation dimensions.
- Show tradeoffs, risks, and uncertainty.
- Give a clear recommendation or decision path.
- Explain what evidence would change the judgment.

## 求好型

Core question: 怎样表达才有效?

Typical tasks: scripts, copy, titles, posters, PPT pages, public-facing writing.

Acceptance criteria:
- Match the audience, channel, tone, and intended action.
- Make the main message visible and memorable.
- Remove generic phrasing and unsupported exaggeration.
- Preserve required facts, brand constraints, and legal/compliance boundaries.

## 求成型

Core question: 怎么把事情做成?

Typical tasks: marketing plans, operations plans, KOC execution, project scheduling, implementation plans.

Acceptance criteria:
- Translate the goal into concrete actions, owners, timeline, dependencies, and deliverables.
- Sequence work by priority and blocking relationships.
- Include resource assumptions and risk responses.
- Define measurable checkpoints, not just activities.

## 求通型

Core question: 怎么和人沟通并推进?

Typical tasks: procurement communication, client communication, interviews, internal collaboration.

Acceptance criteria:
- Identify stakeholders, positions, likely concerns, and desired next step.
- Reduce ambiguity and conflict without losing necessary firmness.
- Produce usable communication artifacts when needed: message, agenda, talk track, follow-up note.
- Make the next ask or decision clear.

## 求学型

Core question: 我怎么进入一个陌生领域?

Typical tasks: learning new concepts, understanding an industry, building a knowledge map.

Acceptance criteria:
- Build a map before detail: concepts, actors, mechanisms, vocabulary, common questions.
- Distinguish fundamentals from edge cases.
- Explain enough to support transfer to the user's task.
- Suggest next learning path or practical exercises when useful.

## 求改型

Core question: 如何精准修改现有产物?

Typical tasks: revise PPT, edit images, fix data, amend contract clauses, polish drafts.

Acceptance criteria:
- Preserve what should not change.
- Make targeted improvements tied to the user's goal.
- Show or summarize meaningful before/after differences.
- Verify format, references, formulas, layout, tests, or constraints depending on artifact type.

## Mixed-Type Rule

Use the primary type to infer the user's core intent. Use secondary types to identify supporting workflow needs. Do not let this override the final deliverable, professional lens, or task contract.

Examples:
- "整理会议纪要给客户确认需求": primary 求通, secondary 求清.
- "看合同能不能签": primary 求判, secondary 求真.
- "改 PPT 让老板觉得方案更有说服力": primary 求好, secondary 求改.
- "做运营方案但输入很散": primary 求成, secondary 求清.
