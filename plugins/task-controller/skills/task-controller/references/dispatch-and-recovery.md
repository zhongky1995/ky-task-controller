# Dispatch Admission and Recovery

Read before creating/replacing a worker or recovering interrupted dispatch.
The host creates Sessions; KY-TASK owns the durable admission ledger. A ready
list is a scheduling snapshot, not a reservation or permission to create.

## Before Host Creation

1. Use the accepted strict plan, current contract revision, resolved project,
   and task-scoped approval. Bind exact `capabilityRequirements` per lane.
2. Check the host's callable skill/tool surface. A registry entry or active ID
   alone is not proof of availability. Planning reports `runtimeReady: false`
   for unknown availability even when `orchestrationExecutable: true` means the
   bound work graph is valid. Supply verified `runtimeAvailability` while
   planning, or `capabilityEvidence: {capabilityId: "concrete discovery result"}`
   when claiming. This is controller attestation, not a probe run by the plugin.
3. For each ready lane call `task_controller_claim_dispatch` with the same
   stable `requestId` that its worker will use. This atomically reserves the
   lane and one worker slot.
4. A response with `creationAction: create` admits a new dispatch attempt. It
   permits host creation when needed, but does not require a new Session.
   Put the request ID in the narrow worker prompt so interrupted creation can
   be found later. Retain the returned `claimId`.
5. Reuse a compatible idle Session (below), or create one with the locked project target. After its actual thread
   ID is available and project affinity is checked, register it with that
   `claimId`, `requestId`, runtime identity, and current packet/contract fields.
   A queued `clientThreadId` is not an actual `threadId`.
6. Continue through the admitted parallel frontier before waiting. Capacity
   can change after `ready-lanes`; if a claim is rejected, refresh the frontier.

New strict states require claims for independent workers. Existing states
without `dispatchAdmission: claims-v1` retain claim-free registration, but the
registration lock still enforces capacity and one current attempt per lane.

## Reuse Before Creation

Keep the work graph separate from the Session roster. Multiple serial lanes or
revisions may run in one continuing professional Session; independent parallel
jobs and independent reviewers still need different runtimes. Choose
`persistent + checkpoint_delta` when related follow-ups are expected. An
`ephemeral + packet_only` job with a genuine fresh-context requirement should
not be reused as if its conversation history had been erased.

Before reusing, verify the host Session is idle, in the locked project, has the
needed tools, and has compatible responsibility, authority and context. Check
for other controllers using it; the local ledger cannot detect cross-state or
host-side activity. Record this evidence and the reuse reason in registration
`notes`/`threadToolCheck`. Do not switch writer and reviewer roles to save a
window. A prior writer in this state cannot become its review worker, even after
supersession; a prior reviewer can continue later reviews of fresh artifacts.

For a new lane or revised attempt:

1. Finish/stop and reconcile the prior attempt. Close a passing lane normally;
   do not supersede valid evidence merely to free its Session. For failed work,
   decide bounded recovery; revise only if the contract actually changed.
2. Claim the ready lane with a new `requestId`, as for new creation.
3. Register a new unique `workerId` (an attempt ID, not necessarily the thread
   ID), retaining the same `threadId == runtimeHandle`. Use the new claim and
   current contract/packet identities; preserve the old worker/callback record.
4. After registration passes, send the current task packet and a compact delta
   to that existing Session. State which old conclusions are invalid, allowed
   actions, checks and stopping condition. Never replay old callbacks as new
   verification or blindly resend an uncertain dispatch.

For an ordinary clarification within a still-current attempt, continue that
attempt instead of inventing a replacement. Host messaging still requires the
user's authorized coordination scope. Reviewers must remain independent of all
subjects; reuse changes conversation allocation, not gates or permissions.

Revision changes evidence validity, not necessarily the required Session.
Rerunning a test with a corrected local environment, collecting an already
produced result, or fixing an in-scope defect is not by itself a new professional
responsibility. Binding a new attempt does not reset a conversation's context.
Create only for useful isolation, actual parallelism, unavailable/incompatible
prior workers, or context that can no longer be maintained reliably.

Behavioral checks (not a fixed team template):
- A producer corrects a draft and exports it: retain the producer Session;
  retain the independent reviewer at required checkpoints.
- A bounded data migration needs one environment retry: update the executing
  Session, do not create a separate evidence-collection Session by default.
- Independent source investigations can proceed together: separate Sessions
  remain useful; do not serialize them merely to reduce the count.
- A writer is relabeled as a reviewer, or an old run has not stopped: reject
  reuse regardless of a new worker ID or contract revision.

## Retry and Uncertain Creation

- Repeating a reserved request returns the same claim with
  `creationAction: reconcile-existing-creation`; do not create again.
- If it is already bound, `creationAction: already-registered` identifies the
  worker. Read its state instead of creating a replacement.
- Inspect host task/setup status for the request. If the Session exists, bind
  the original claim to its real identity. If setup is still pending or the
  outcome is unknown, keep the claim reserved and report that condition.
- Only after confirming **not created** or **stopped**, use
  `task_controller_release_dispatch` with `outcome: not-created | stopped` and
  concrete `evidence`. A timeout by itself is not evidence of non-creation.
- Released requests cannot be reused. A new attempt uses a new request ID.
- Revision or plan-digest changes prohibit binding an old claim to the new
  plan. Unbound claims survive revision until reconciled; no automatic expiry
  can silently create room for a possibly duplicated Session.

## Shared Scheduling States

`ready-lanes`, `next-lane`, and `finalize` use the same finalization check.

| State | Controller action |
|---|---|
| `pending` | Dispatch when dependencies and admission pass. |
| `stale` after an approved revision | Redo against current identities; stop/reconcile old execution first. |
| Live attempt or reserved creation | Wait or reconcile; do not create a second attempt. |
| Callback is done but lane is not complete | Validate evidence and call `complete-lane`; capacity may already be free. |
| `needs-work` / `blocked` | Resolve the named condition or revise the contract; no blind automatic retry. |
| `finalizable` | All lanes pass the final gate, with no live attempts or unbound claims. Call `finalize`. |
| `finalized` | Current revision is already closed. |

`activeWorkers` counts live attempts, not running-lane labels. Reservations
count separately as `reservedDispatches`; both consume `maxParallelWorkers`.
Default concurrency remains four; the explicit task ceiling is ten, with no
limit on total graph lanes. The host's own available capacity still applies.

Superseding a live worker (including by revision) invalidates its evidence but
does not prove its runtime stopped. It retains `runtimeStopPending: true` and
occupies capacity. After the host confirms termination/completion, retire it
with `task_controller_update_worker`, a terminal status, and
`runtimeStopEvidence`. Then a replacement may be admitted. Do not mark it
done/pass to make room. Terminal negative results can be explicitly superseded
after deciding a bounded retry, or revised when the contract itself changed.

The wait batches in `ready-lanes.waitCoordination` are only a coordination
plan. The controller calls host waits, carries each host cursor, rotates
batches of at most eight after progress or a bounded timeout, collects results,
and refreshes ready work. KY-TASK does not run an automatic host wait loop.
