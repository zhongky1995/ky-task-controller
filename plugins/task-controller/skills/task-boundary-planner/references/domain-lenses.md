# Domain Lens Reference

Use this reference when the task has a high professional standard. Pick only the relevant lens; do not load every domain into the response.

## Data / Spreadsheet / Research Analysis

Use for CSV/XLSX analysis, metric correction, social listening, research reports, dashboards, and any task where numbers become client-facing claims.

Professional standard boundary:
- Source ledger: input files, time range, platform/scope, row counts, included/excluded records.
- Metric dictionary: each metric's numerator, denominator, unit, and whether it counts records, unique IDs, brand hits, users, interactions, or samples.
- Lineage: source -> cleaning rule -> intermediate output -> final table/chart/report.
- Reconciliation: compare totals across source files, cleaned samples, summaries, charts, and narrative.
- Evidence: representative samples for qualitative claims; formulas or scripts for quantitative claims.

Common failure modes:
- Mixing raw volume, cleaned sample size, and final metric.
- Mixing all-platform, focus-platform, and single-platform denominators.
- Treating multi-brand hits as unique content counts.
- Reusing internal platform labels as client-facing definitions.
- Generating charts from a different denominator than the report text.
- Using interaction subfields to recompute a total when a source total field already exists.

Minimum evidence packet:
- Field list and row counts.
- Time range and source description.
- Deduplication key and duplicate handling.
- Filtering rules and excluded-category rationale.
- Metric formulas, especially share/SOV, sentiment, NSR, interaction, search index, and bid price.
- Metric/chart matrix when outputs include multiple charts, disputed categories, special adjustments, or cross-source reconciliation.
- One cross-output consistency check.

Acceptance checks:
- Every chart denominator matches its title and data scope.
- Every narrative number can be traced to a table, script, or source file.
- Report, chart assets, Excel sheets, and README use the same metric names.
- If user-facing wording changes, generated scripts are updated so reruns do not recreate old terms.

When data analysis supports a client-facing recommendation, treat data as the evidence layer, not the final deliverable. Add a judgment layer and a production layer before handoff.

## Business / Operating Review / Management Reporting

Use for business reviews, semiannual/quarterly reports, operating updates, subsidiary reporting, revenue or delivery summaries, management asks, and documents where numbers become internal decisions.

Professional standard boundary:
- Reporting object model: metrics, business lines, projects, owners, time periods, pipeline stages, and decision audiences.
- Metric dictionary: business scale, new signing, delivery amount, recognized revenue, cash collection, pipeline, forecast, and target must not be mixed.
- Business taxonomy: the same business-line names and order must be used across actuals, forecast, pipeline, and action plans.
- Audience split: execution-side collaboration requests and management/resource asks must be separated.
- Specificity: each business-line claim needs project names, amount/status, business meaning, issue/opportunity, and next action.

Common failure modes:
- Treating project count as business scale.
- Mixing signed business, delivery amount, pipeline, forecast, and cash flow.
- Using one-off user corrections as hidden special cases instead of explicit metric rules.
- Combining new businesses with the existing core business base without labeling them as separate forecasts.
- Writing generic capability statements without project evidence, operational bottlenecks, or resource asks.
- Changing business-line order between H1 review and H2 plan.

Minimum evidence packet:
- Source ledger for every workbook or document.
- Metric/chart matrix before charts are generated.
- Business-line classification rules and special split rules.
- Current output structure and any user-edited latest document.
- A section/unit contract for every major report section.

Acceptance checks:
- Every headline number appears in a traceable table with source, filter, and classification rule.
- Every chart title states metric, scope, time range, and whether it is actual, delivery, pipeline, or forecast.
- H1 actuals and H2 plan use the same business-line taxonomy and order unless a new business is explicitly separated.
- Collaboration requests name execution-side process bottlenecks; management asks name resource, authority, cash-flow, or strategic alignment needs.
- Final document, local backup, chart data, and chart images use the same wording and totals.

## Code / Repository / System Implementation

Use for repository changes, product code, scripts, data pipelines, tests, and automation.

Professional standard boundary:
- Architecture map: entry points, relevant modules, data flow, external dependencies.
- Change surface: files likely touched and files explicitly out of scope.
- Contract: APIs, schemas, CLI flags, file formats, env vars, tests, and compatibility expectations.
- Verification: existing tests, new tests, manual checks, logs, screenshots, or data diffs.

Common failure modes:
- Guessing architecture from names instead of source files.
- Editing shared code without finding callers.
- Running broad commands without checking scripts and env.
- Ignoring dirty worktree changes.
- Treating generated output as source of truth.

Minimum evidence packet:
- Manifest/docs, entry points, nearby code, tests, and git status.
- Relevant search results for symbols, routes, schemas, or file formats.
- Verification command list before editing.

## Deck / Client-Facing Narrative / Visual Communication

Use for PPT, strategy narratives, client reports, visual charts, and analysis-to-presentation work.

Professional standard boundary:
- Audience and decision: who needs to believe or decide what.
- Delivery mode: live presentation, projection HTML, self-read handout, external package, editable deck, or client report.
- Story spine: context -> evidence -> judgment -> implication -> action.
- Page task: each page's job, not just its topic.
- Evidence fit: every claim has a chart, quote, source, or example.
- Wording standard: precise, non-overclaimed, client-safe.

Common failure modes:
- Turning analysis into page decoration without a decision point.
- Mixing chart scopes or metric names across pages.
- Copying a reference page's form while missing its logic.
- Producing claims stronger than the data supports.
- Treating a projected presentation as a scrolling web handout or information card wall.
- Verifying only browser correctness while missing projection readability, page rhythm, or speaker flow.
- Choosing a production path that corrupts evidence, such as generative redraws of exact charts, word clouds, user screenshots, or quoted text.
- Cropping or restyling evidence assets until the proof becomes unreadable or incomplete.

Minimum evidence packet:
- Target audience, intended use, delivery mode, source data, must-have claims, reference examples, forbidden claims, available assets, and production constraints.

Analysis-to-output bridge:
- Convert data points into page tasks: diagnosis, comparison, proof, implication, or action.
- For each page or section, require a claim, supporting evidence, interpretation, and next-step implication.
- Reject pages that only display charts without a decision-relevant message.
- Check that terminology and metric scope match the data layer.
- When reference pages are provided, extract their page task, evidence pattern, information density, and hierarchy before producing new pages.
- For evidence-heavy decks, define a page-level evidence contract before visual polish.
- For projection or live presentation, require one screen one idea, large readable type, visual structures such as flowcharts or maps when they carry logic better than cards, and a speaker route.
- Choose the production route before visual polish: exact-data pages need deterministic charts/assets; generative tools may provide moodboards or layout references but must not become the source of truth for exact evidence.
- Before scaling a deck, review a contact sheet or representative pages against page task, delivery mode, evidence fidelity, brand markers, and readability.

## Script / Screenplay / Creative Content

Use for short video scripts, KOC口播, 小红书文案, ad scripts, campaign ideas, titles, poster copy, speeches, story scripts, and creative concepts.

Professional standard boundary:
- Audience and context: who should watch/read it, where, and in what state of mind.
- Desired effect: attention, trust, emotion, memory, search, comment, conversion, internal alignment, or brand preference.
- Content mechanism: hook, scenario, conflict, insight, proof, twist, payoff, CTA, or repeatable creative device.
- Format constraints: channel, length, rhythm, structure, platform language, production resources, and compliance boundaries.
- Brand fit: message, tone, facts, forbidden claims, risk words, and what must remain recognizable.

Common failure modes:
- Writing polished sentences without a communication mechanism.
- Copying a reference style while missing audience, channel, or brand logic.
- Piling up selling points without scene, conflict, emotion, or proof.
- Producing a concept that is memorable but not connected to the brand.
- Writing scripts that sound good but cannot be filmed, performed, posted, or approved.
- Using platform-inappropriate language, such as TVC tone for 小红书 or brand-ad tone for KOC.
- Overclaiming product effects, discounts, medical/health benefits, performance, or user outcomes.

Minimum evidence packet:
- Final content form and channel.
- Target audience and desired reaction/action.
- Brand/product facts and non-negotiable constraints.
- Reference examples, if provided, with explicit note of what to learn from them.
- Execution limits: length, talent, scene, budget, format, approval, or production constraints.

Acceptance checks:
- The first moment has a reason to keep watching or reading.
- One core idea leads the content; secondary points support it instead of competing.
- The content has a working mechanism: scene, conflict, proof, emotion, or action.
- The voice fits the speaker/publisher, especially for KOC or first-person content.
- The output can be executed under the stated channel and production constraints.
- Risky claims are avoided or softened.

## Contract / Policy / Legal-Risk Review

Use for contracts, terms, policies, compliance, and risk reviews.

Professional standard boundary:
- Jurisdiction or governing framework if known.
- Clause inventory and obligations by party.
- Risk severity, likelihood, and negotiation priority.
- Exact text references; separate legal judgment from business judgment.

Common failure modes:
- Giving legal certainty without jurisdiction or counsel context.
- Missing cross-references and definitions.
- Rewriting clauses without preserving commercial intent.

Minimum evidence packet:
- Contract version, target clauses, governing law if available, business goal, non-negotiables.

## Marketing / KOC / Content Strategy

Use for KOC analysis, social listening, content plans, search/grass-planting strategy, and campaign diagnosis.

Professional standard boundary:
- Business goal: awareness, trust, search capture, conversion, reputation repair, or community operation.
- Funnel location: exposure, search, evaluation, interaction, conversion, loyalty.
- Evidence split: volume, sentiment/NSR, topic, quote, interaction, platform search demand, and competitive benchmark.
- Platform logic: do not mix social mention volume with search index, ad bid, or conversion proxy.

Common failure modes:
- Treating volume as persuasion.
- Treating main posts as the whole user conversation.
- Quoting noisy high-interaction posts as user insight.
- Mixing KOC content opportunity with paid keyword opportunity.

Minimum evidence packet:
- Platform scope, brand set, metric formulas, topic taxonomy, representative quotes, interaction evidence, search/bid source if used.

Output bridge:
- Turn evidence into a client-facing argument: current gap, why it matters, what to strengthen, where to act, and how to measure.
- Distinguish content strategy, KOC seeding, search occupation, paid keyword opportunity, and interaction operation.
- Tie each recommendation to a funnel role and one supporting evidence type.

## Operations / Project Execution / Stakeholder Coordination

Use for plans, schedules, operating mechanisms, procurement, internal collaboration, and cross-team delivery.

Professional standard boundary:
- Goal, owner, dependencies, timeline, deliverables, risks, and decision gates.
- Stakeholder map and escalation path.
- Definition of done for each phase.

Common failure modes:
- Listing activities without owners or gates.
- Ignoring blocking dependencies.
- Treating communication as optional after execution starts.

Minimum evidence packet:
- Deadline, decision owner, constraints, available resources, current blockers, required outputs.
