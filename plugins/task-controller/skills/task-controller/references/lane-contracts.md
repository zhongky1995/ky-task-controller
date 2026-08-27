# Lane Contracts

Use these templates to run or dispatch lanes.

These are output-contract examples, not an orchestration template. Before using
one, the accepted `OrchestrationPlan` must already declare the lane's
`contributionRole`, `semanticAuthority`, `semanticOwner`, `dependsOn`,
`dependencyReasons`, input/output contracts, handoff policy, and lane-level
capability requirement.

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
- lifecycle: normally ephemeral + packet_only; persistent + checkpoint_delta only for an ongoing workbench
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
- 写入边界: review-only unless minor local correction is approved
- 禁止: redefining acceptance to fit the built output
- gate: required acceptance cases pass or unresolved risks are explicit
- structured verification: semantic/business results come from the registered review worker, whose runtime and verifier capability match its WorkerPacket; reviewedWorkerIds and manifest entries must cover the preceding approved-target writers and their exact receipt-bound artifacts
- identity: runtimeHandle must differ from every covered writer runtime
- project identity: the review Session uses the same locked projectId as the writers it reviews
- coverage: reviewsWorkerIds must cover every current approved-target writer in an earlier lane, regardless of lane kind; later writers are checked by downstream reviews and the final gate
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

When the user changes scope, sources, acceptance, or write permission, identify the earliest affected lane and call `task_controller_revise_contract`. Outputs from that lane onward become stale or pending, their current artifact values are cleared into audit history, and old callbacks cannot satisfy the new revision. Re-run affected workers and review with new request/runtime identities.
