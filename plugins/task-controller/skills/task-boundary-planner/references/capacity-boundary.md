# Capacity Boundary Reference

Use this reference when a task may be too large, too professional, or too uncertain to complete reliably in one pass.

## Two Boundaries

Task boundary has two parts:

- Professional standard boundary: what counts as correct or good.
- Capacity boundary: what can be handled in this run.

Unknowns are acceptable. Unbounded work is not.

## Professional Standard Boundary

Assess the standard as high when the task requires any of these:

- Domain judgment: legal, finance, architecture, strategy, policy, medical, research, data interpretation.
- High consequence: wrong output may cause business, compliance, reputation, security, or production risk.
- Strict artifact quality: client-facing deck, contract, final copy, production code, published analysis.
- External truth: current facts, source verification, citations, traceability.
- Expert taste: design quality, narrative quality, executive-facing judgment.

Assess the standard as low when the task mostly needs routine transformation, formatting, extraction, cleanup, or obvious execution.

## Capacity Boundary

Assess capacity demand as high when the task has any of these:

- Many files, pages, rows, slides, records, stakeholders, requirements, or systems.
- Large repository or unclear architecture.
- Multiple deliverables or a long chain of dependent decisions.
- More information than can be safely inspected or summarized in one pass.
- Verification requires multiple tools, tests, sources, or review rounds.
- The user expects both diagnosis and execution across a broad scope.

Assess capacity demand as low when the object is small, the deliverable is singular, and verification is straightforward.

Do not report capacity as a label only. State the concrete drivers:

- Volume driver: files, rows, slides, records, modules, pages, stakeholders, or artifacts.
- Dependency driver: upstream sources, downstream outputs, tools, scripts, people, or systems.
- Context driver: how much must be read before the task can be done safely.
- Verification driver: how many checks or comparison surfaces are required.
- Runtime driver: long scans, exports, tests, renders, uploads, or review loops.

For high-capacity tasks, define a one-pass envelope:

- What can be completed in this run.
- What must be sampled, batched, or deferred.
- What artifact proves progress.
- What gate decides whether to scale.

## Four Execution Modes

### Direct Execution

Low professional standard + low capacity demand.

Use when the task is routine and bounded.

Behavior:
- Execute directly after a short boundary checkpoint.
- Ask no questions unless a required object or deliverable is missing.
- Verify with a simple completion check.

Examples: rename a section, summarize a short note, format a small list.

### Batch Organization

Low professional standard + high capacity demand.

Use when there is a lot to process but the standard is routine.

Behavior:
- Chunk the work by file, topic, row range, folder, date, stakeholder, or batch.
- Define batch size and progress markers.
- Produce an index, inventory, or representative first batch before scaling.

Examples: organize folders, clean many meeting notes, classify large keyword lists.

### Professional Calibration

High professional standard + low capacity demand.

Use when the object is small but correctness or quality standards matter.

Behavior:
- Define the evaluation criteria before final output.
- Verify source material or domain assumptions.
- Produce a small calibrated answer, sample, rubric, or decision frame.
- Ask for confirmation only on criteria that change the result.

Examples: contract clause judgment, executive headline rewrite, strategic recommendation from a short brief.

### Project Decomposition

High professional standard + high capacity demand.

Use when both judgment and volume are high.

Behavior:
- Do not promise a complete one-pass answer.
- Split the work into phases with gates: discovery, calibration, execution, verification, handoff.
- Identify what can be completed now and what must become a later batch or subtask.
- Use samples, test slices, or subsystem plans before broad execution.

Examples: refactor a large repo, rebuild a deck, analyze many documents for a business decision, produce a full campaign plan from scattered materials.

## Output Additions

When this reference applies, include:

- Execution mode.
- Standard risk: low/medium/high.
- Capacity risk: low/medium/high.
- Concrete capacity drivers.
- Artifact graph when multiple files/outputs are involved.
- One-pass limit: what can be completed now.
- Decomposition trigger: what would require batching, sampling, or a separate phase.

Keep the output compact unless the user explicitly asks for a full planning document.
