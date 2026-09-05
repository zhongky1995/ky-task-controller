# Controller Protocol

Use this reference when a task needs a controller rather than a single uninterrupted execution.

## Controller Responsibilities

- Preserve the locked task contract.
- Decide which lanes exist and in what order.
- Keep lane outputs narrow and mergeable.
- Prevent unsupported evidence or assumptions from entering final artifacts.
- Ensure only the approved lane writes to external systems.
- Run final review against the original task, not against what happened to be built.

Before choosing a runtime, compile the lane map through
`work-orchestration.md`. The controller must distinguish decomposition from
orchestration: lane titles identify jobs, while the `OrchestrationPlan` proves
semantic ownership, parallel waves, justified serial edges, join points,
handoff cohesion, and lane-level capability bindings.

## Execution Modes

### Single-thread lanes

Use when worker tools are unavailable, the task is moderate, or consistency matters more than parallelism.

Rules:

- Run one lane at a time.
- Leave a visible checkpoint after each lane.
- Do not collapse evidence, model, product, implementation, and review into one long action.

### Distributed workers

Use when distinct lanes can work independently and reduce risk:

- evidence audit
- object/model design
- metric/chart design
- product/experience design
- implementation
- independent review

Rules:

- The controller keeps the contract.
- Workers receive only relevant inputs.
- Workers normally do not write final artifacts.
- One writer owns each final artifact.
- One reviewer checks the final artifact.

Runtime selection:

- Under the default `native_session_required` policy, use `native_thread_lane` for every distributed lane.
- Under `projectAffinityPolicy: inherit_or_resolve_required`, resolve and lock one saved Codex `targetProjectId` before native dispatch; every worker must report that project id.
- `ephemeral` lanes keep `contextPolicy: packet_only`; `persistent` lanes use `contextPolicy: checkpoint_delta`.
- Declare `dependsOn` for every new lane. Total Lane count is uncapped; dispatch the full ready frontier up to `maxParallelWorkers` (default four, explicit task maximum ten).
- When more than eight Sessions are active, coordinate them through stable wait batches of at most eight targets per host wait call.
- Both are real independent workers. `single_thread_section` and `thread_create_unavailable` are fallback records, not worker equivalents.
- If `splitRequirement` is `mandatory` and either real runtime is eligible, `mode` must be `distributed`. `multi_session` remains a legacy alias.

## Write Boundary Levels

- `read-only`: inspect sources and return analysis.
- `draft-file`: write intermediate files only.
- `approved-target`: write to the named final artifact or external system.
- `review-only`: inspect output and report pass/fail.

If a lane needs a higher write level than planned, stop and ask for confirmation or produce a revised controller contract.

## Schema V2 State Contract

Initialize with `goal`, optional `contract`, `laneDefinitions`, and `executionPolicy`. Each lane definition can set `name`, `kind`, `workerRequired`, `writeBoundary`, `workerLifecycle`, `contextPolicy`, and `runtimePreference`. Execution policy records `splitRequirement`, `mode`, `eligibleRuntimes`, `downgradeReason`, `requiredWorkerLanes`, `independentReviewRequired`, `nativeThreadUserApproved`, `projectAffinityPolicy`, `projectlessUserApproved`, `targetProjectId`, `targetProjectPath`, and `projectResolutionSource`.

The schema-v2 outer version does not change for semantic enforcement. New top-level fields are `enforcementMode`, `semanticDowngradeReason`, `contractSpec`, `contractDigest`, and `correctionEvents`. Risk tasks with an `approved-target` lane or independent review default to `semantic_strict`; an explicit `workflow_only` downgrade requires a reason. A newly inserted `review` or `review-only` lane is treated as review risk and requires the same existing downgrade reason in `workflow_only`, without automatically changing the locked `independentReviewRequired` policy. Legacy v2 state without the field remains read-only-compatible as warned `workflow_only` state.

Contract spec 2.x locks `interactionMode`, the business delivery shape, canonical-source priority, binding decisions, optional intent anchors, sample/user approval gates, and exact write policy. `discuss_only` and `plan_only` cannot authorize approved-target work. Canonical JSON SHA256 produces the deliverable fingerprint and a revision-bound contract digest.

Strict pass evidence is structured: non-empty `artifactManifest`, known unique `checkResults`, non-empty evidence, required-source coverage, and all applicable checks passing. Review additionally covers its configured semantic checks and the current workers in compiled `verificationSubjects`. Intermediate subjects come from produced `inputContracts`; final review covers final writers. Earlier-writer scope is retained only for legacy states. The final gate still requires every approved-target writer to have downstream review coverage.

`complete-lane --decision pass` is not a manual status flip. It requires a non-empty artifact, passing upstream lanes, and any required current-revision real worker plus accepted callback. Independent review additionally requires `reviewsWorkerIds` coverage and a reviewer `runtimeHandle` different from every implementation identity it reviews.

If the user changes the locked scope or acceptance criteria, call `revise-contract` with the earliest invalid lane. The revision keeps earlier valid lane outputs, clears affected current artifacts into audit history, marks affected lanes stale/pending, and makes all old worker callbacks unusable for the new revision.

Correction keywords are change-control input, not prose to absorb silently. Record them as `correctionEvents`; a callback containing events cannot pass, and open events block registration, gate, and completion. Revision must consume all open events and may not start later than the earliest recommended invalid lane. Strict revision includes the complete replacement `contractSpec`.

State writes use an advisory lock around the complete mutation and atomically replace the JSON file after fsync. `ready-lanes`, `next-lane`, and `finalize` share one finalization check: all lanes must pass, with no live attempts or unbound claims. Only `finalize` records the finalized revision. Revision-created `stale` work is schedulable again; `blocked` and `needs-work` require explicit resolution.

New strict states use `dispatchAdmission: claims-v1`. Reserve through `claim-dispatch` before host creation, then bind `claimId` at registration. Capacity includes live attempts and unbound reservations; one lane has one current attempt. Superseding a running worker retains capacity until `runtimeStopEvidence` confirms it stopped. Read `dispatch-and-recovery.md` for repeated requests, uncertain creation, and explicit release. New initialization never selects legacy because fields were omitted; compatibility imports must request it explicitly.

## TaskBlueprint and Shadow Routing

For blueprint-based state, `TaskBlueprint` is the canonical semantic decision. Once lane definitions are fixed, compile it with `compile-blueprint --task-blueprint --lane-definitions`; this produces the schema-v2 `contractSpec`, `blueprintDigest`, traceability map, and executable status. `init --task-blueprint` persists that lineage. A semantic-strict risk execution cannot initialize from a compilation with unresolved required content. If a hand-authored `contractSpec` is also supplied, normalize it and reject it unless it semantically equals the compiler projection.

Blueprint-backed semantic-strict corrections must revise through `revise-contract --task-blueprint`; do not replace the generated contract with a hand-authored one and discard blueprint lineage. States created solely with the legacy hand-authored `contractSpec` remain compatible with the existing revision flow.

`route-capabilities --task-blueprint --active-capability-ids` calls the checked-in registry router in shadow mode. Its output is advisory only: it does not register workers, select a runtime for execution, grant external-write authorization, or mutate state. A route suggestion must pass the normal controller contract and write gates before it influences execution.

## SolutionGraph Planning and Packets

`plan-orchestration --lane-definitions` is the generic read-only path. In strict mode it rejects missing semantic ownership, unexplained serialization, premature verification, lossy primary handoffs, shared parallel writers, and unavailable exact lane capabilities. It emits waves and join points before any Session/runtime choice.

`plan-blueprint --task-blueprint` is a pure read-only planning command. It compiles the blueprint contract, performs shadow routing, loads the selected checked-in scenario pack, builds a formal `SolutionGraph`, compiles its `OrchestrationPlan`, projects controller lanes, and compiles one `WorkerPacket` per graph node. Its result contains `routingDecision`, `solutionGraph`, `orchestrationPlan`, `laneProjection`, `workerPackets`, `planDigest`, `planExecutable`, and blockers. Planning never creates or dispatches workers.

Use `init --task-blueprint --auto-plan` to persist a graph-backed state. With no explicit `laneDefinitions`, the projected lane order, names, and boundaries become the state lanes. Explicit definitions must match that projection. The state stores the routing decision, graph and digest, node-indexed packets, and plan identity. A semantic-strict risk initialization fails when the plan is not executable.

For graph-backed state, `register-worker` requires `packetId` and `packetDigest`; its lane must equal the packet node/lane and every graph, blueprint, and contract digest must be current. `task` and `prompt` may be omitted because the helper stores the packet structure and rendered packet prompt. `record-callback` repeats the same packet identity and rejects stale or mismatched workers. Legacy non-graph state continues to use the prior task/prompt behavior.

## Structured-v1 Operation Protocol

New auto-planned `TaskBlueprint` / `SolutionGraph` state uses `structured-v1` as a hard protocol gate. Manual legacy states remain compatible with their documented callback contract. The mandatory order for an `approved-target` operation is:

1. Claim dispatch, create the host worker, and register it with its `claimId` and current `WorkerPacket` identity.
2. Use `task_controller_issue_operation_permit` to create an `OperationPermit` for the packet-allowlisted capability, target, action, payload, approval references, and readback plan.
3. Use `task_controller_dispatch_operation` to consume that permit. The restricted dispatcher creates the `OperationReceipt` and readback evidence.
4. If a persisted claim was interrupted, use `task_controller_reconcile_operation`. It performs the approved readback only and never repeats the write.
5. Record artifact-manifest-bound verification results with `task_controller_record_verification_result` or in `task_controller_record_callback`.
6. Record callback receipt IDs, artifact manifest/fingerprint, target version, and dispatcher readback fingerprint. Then run the independent review and final gate.

For an `approved-target` structured callback, `OperationPermit` + a dispatcher-generated consumed `OperationReceipt` + accepted verification results are mandatory. Free-text evidence, an unlogged write, or legacy `writeReceipt` does not satisfy the gate. `writeReceipt` is retained only for manual legacy state.

Semantic and business acceptance cases must declare an external verifier and cannot be self-attested. High-risk delivery requires independent review by a distinct worker/runtime before finalization. Permits, receipts, artifact manifest fingerprints, verification results, callbacks, and approvals are revision-bound; a contract revision makes old affected evidence unusable.

`MemoryTestAdapter` is only for tests and must never be used for production operations. The production `lark-cli` adapter accepts typed allowlisted descriptors with exactly `operation`, `identity`, `resource`, and `input`. It compiles fixed command prefixes and checks resource tokens against the approved target locator. It accepts no caller-supplied argv, shell, environment, working directory, executable, arbitrary command, or delete operation. Unsupported Lark operations must be added to the typed catalog before use.

The controller cannot prevent a caller from bypassing KY-TASK and directly using another external tool. That write has no valid permit, dispatcher receipt, or verification result, and therefore cannot pass KY-TASK callback, independent-review, gate, or finalization requirements.

Graph-backed `revise-contract --task-blueprint` regenerates routing, graph, projection, and packets with the stored planning availability inputs. This stage permits only the same ordered node IDs and lane boundaries; a topology change returns `replan_requires_new_state`. When topology is preserved, packet digests are replaced and every worker carrying an old packet digest is superseded.

The helper is a protocol guard, not an external-tool security boundary. It cannot intercept direct Feishu, browser, filesystem, or other writes made outside KY-TASK. It only fails closed for KY-TASK-managed dispatch, callback, gate, and completion.

## Merge Rules

- Merge evidence only if source and status are clear.
- Merge model changes only if they do not invalidate the user path.
- Merge product changes only if they keep the first-screen management question intact.
- Merge implementation only after source and user-path checks pass.
- Do not silently resolve conflicting lane outputs; surface the conflict.
