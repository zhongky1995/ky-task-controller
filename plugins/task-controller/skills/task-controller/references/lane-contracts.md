# Lane Contracts

Use these templates to run or dispatch lanes.

These are output-contract examples, not an orchestration template. Before using
one, the accepted `OrchestrationPlan` must already declare the lane's
`contributionRole`, `semanticAuthority`, `semanticOwner`, `dependsOn`,
`dependencyReasons`, input/output contracts, handoff policy, and lane-level
capability requirement.

Gates below are internal quality checks unless the accepted contract explicitly
requires a user decision. Passing a gate should advance authorized work, not
generate another confirmation request. For uncertain inputs, include the premise
to verify, evidence that would change it, and the downstream decision in the
existing input/output contract; see `continuous-execution.md`.

## Delegate an outcome and its decisions

Use the original request, audience/use and relevant source artifacts to explain the
problem. Identify hard constraints and their basis separately from controller
interpretations, candidate explanations and optional suggestions. Verified facts
are evidence, not automatically instructions. A suggestion becomes binding only
through an authorized decision, not repetition in a handoff or acceptance list.

State which professional decisions the owner may make: for example structure,
argument, examples and expression in a proposal, or implementation approach inside
an agreed software interface. The owner may reject a controller hypothesis with
evidence and continue within delegated authority. Preserve exact constraints where
the user, compatibility, permissions or correctness require them. This freedom
does not waive recorded contracts: if a proposed change affects a binding term,
return the concrete conflict through the existing correction/revision protocol;
continue only unaffected work until it is resolved.

Give enough context to solve the work, not an exhaustive recipe. Include necessary
research, production, integration and self-review in the responsibility; do not
require a fresh controller decision at each internal step. A missing input that
can be investigated within scope is work to do, not automatically a blocker.
Stop at actual permission limits or unresolved reserved decisions. Keep required
runtime, credential and callback metadata in a separate operational section or
linked packet; it remains binding but should not dominate the substantive brief.
These are distinctions in the existing handoff, not new mandatory schema fields,
forms, word limits, sample phases or approval gates.

For example, a proposal owner can receive the audience, business objective,
original brief, research, confirmed commitments and delivery target, with authority
to determine the argument, structure and examples and complete a usable proposal.
Do not turn the controller's preferred table of contents or example count into
acceptance criteria without a task-specific reason. For an exact API migration,
the interface and compatibility tests can remain fixed while the implementation
approach is delegated.

Reviewers receive original intent, relevant sources, constraints and the actual
artifact. For quality judgments, read/use the artifact and form an independent
assessment before consulting author self-assessments or controller repair lists.
Then reconcile all required checks. Report material failures with location,
evidence and effect on intended use; optional preferences are not failure gates.
A reviewer may challenge the adequacy of the brief itself without silently
changing acceptance or authorizing writes.

## Evidence Lane

```text
Evidence lane
- 输入:
- 任务:
- 输出: source ledger, field inventory, sample evidence, blocked/forbidden assumptions
- 写入边界: read-only or draft-file
- 禁止: final artifact writes, broad inference, unsupported consolidation
- gate: each important claim/object has a source status
```

## Object / Model Lane

```text
Object/model lane
- 输入:
- 任务:
- 输出: objects, fields, relations, status machines, source-to-target mapping
- 写入边界: read-only or draft-file
- 禁止: implementation, dashboard creation, final schema writes
- gate: every red/yellow state has reason, owner, next action, and source record
```

## Metric / Chart Lane

```text
Metric/chart lane
- 输入:
- 任务:
- 输出: metric dictionary, chart matrix, denominators, filters, reconciliation checks
- 写入边界: read-only or draft-file
- 禁止: final chart generation when denominator/source is unresolved
- gate: every metric can reconcile to a source table or declared assumption
```

## Product / Experience Lane

```text
Product/experience lane
- 输入:
- 任务:
- 输出: user path, first-screen priority, unit/dashboard contracts, drill-down path, empty/conflict states
- 写入边界: read-only or draft-file unless visual mock is approved
- 禁止: generic chart dumping, implementation before user path
- gate: the first screen answers what to watch, why, owner, next action, and blockage
```

## Implementation Lane

```text
Implementation lane
- 输入:
- 任务:
- 输出: approved final artifact or prototype
- 写入边界: approved-target only
- 禁止: old-version contamination, unapproved schema changes, unsupported data writes
- gate: smoke test and at least one end-to-end chain pass
- lifecycle: prefer persistent + checkpoint_delta for related production and corrections; use ephemeral + packet_only when task isolation is useful, following the Session reuse policy
- runtime: native_thread_lane for every distributed lane under the Session-first policy
- project identity: projectTargetType is project; projectId equals executionPolicy.targetProjectId; projectEnvironment is local or worktree
- dependsOn: explicit upstream lane names; [] means parallel-ready
- identity: unique requestId and runtimeHandle for the current contractRevision
- semantic identity: current contractDigest and deliverableFingerprint
- legacy strict callback: non-empty artifactManifest plus complete checkResults; retained only for manual non-graph checkpoints
- structured-v1 callback: dispatcher-generated operationReceiptIds plus a manifest entry matching each receipt target, targetVersion, and operationArtifactFingerprint
- business delivery: every declared unitId is covered; self-contained packages expose the configured entrypoint
- write evidence: approved-target pass references controller-ledger OperationReceipts created from current-revision OperationPermits; free-form writeReceipt cannot satisfy structured-v1
```

## Review Lane

```text
Review lane
- 输入:
- 任务:
- 输出: acceptance report, source reconciliation, user-path check, contamination check
- 写入边界: review-only; return corrections to the author. An explicitly reassigned reviewer who writes becomes a writer and cannot independently review that artifact; obtain a different reviewer.
- 禁止: redefining acceptance to fit the built output
- gate: required acceptance cases pass or unresolved risks are explicit
- structured verification: semantic/business results come from the registered review worker, whose runtime and verifier capability match its WorkerPacket; reviewsWorkerIds and manifest entries must cover applicable writers in the compiled verificationSubjects and their exact receipt-bound artifacts
- identity: runtimeHandle must differ from every covered writer runtime
- project identity: the review Session uses the same locked projectId as the writers it reviews
- coverage: reviewsWorkerIds covers the compiled verificationSubjects; intermediate review covers producers of its inputContracts, final review covers final writers. Legacy states retain their earlier-writer scope.
- semantic gate: checkResults covers each preserve, allowedChanges, forbidden, and acceptance ID with passing evidence
```

## Semantic Strict Lane Packet

Every strict lane handoff includes:

```text
contractRevision:
contractDigest:
deliverableFingerprint:
applicable canonicalSource IDs:
applicable preserve / allowedChanges / forbidden / acceptance IDs:
sampleGate status and acceptanceIds:
userApprovalGate status, artifactId, and current approval fingerprint:
artifactManifest shape:
checkResults shape: [{id, status: pass, evidence}]
writeReceipt shape: {targetId, targetLocator, action, beforeVersion, afterVersion, readbackEvidence, idempotencyKey}
correctionEvents shape: [{id?, reason, recommendedInvalidFromLane, keywords?}]
contributionRole / semanticAuthority / semanticOwner:
dependsOn / dependencyReasons:
inputContracts / outputContracts:
handoffRisk / handoffMode / handoffContract:
capabilityRequirements:
```

Unknown, duplicate, missing, failed, or evidence-free check results cannot satisfy a pass. If correction language changes target, source, preservation, permission, or acceptance, return a correction event and `needs-work`; do not keep a pass recommendation.

## Contract Revision Rule

When the user changes scope, sources, acceptance, or write permission, identify the earliest affected lane and call `task_controller_revise_contract`. Outputs from that lane onward become stale or pending, their current artifact values are cleared into audit history, and old callbacks cannot satisfy the new revision. Re-run affected workers and review with new attempt/request identities and current contract/packet identities. A compatible reconciled Session may retain its runtimeHandle under `dispatch-and-recovery.md`; prior evidence cannot be reused as a fresh result.
