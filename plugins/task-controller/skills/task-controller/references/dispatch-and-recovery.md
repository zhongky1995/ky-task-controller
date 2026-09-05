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
4. Only a response with `creationAction: create` permits a new host creation.
   Put the request ID in the narrow worker prompt so interrupted creation can
   be found later. Retain the returned `claimId`.
5. Create the Session with the locked project target. After its actual thread
   ID is available and project affinity is checked, register it with that
   `claimId`, `requestId`, runtime identity, and current packet/contract fields.
   A queued `clientThreadId` is not an actual `threadId`.
6. Continue through the admitted parallel frontier before waiting. Capacity
   can change after `ready-lanes`; if a claim is rejected, refresh the frontier.

New strict states require claims for independent workers. Existing states
without `dispatchAdmission: claims-v1` retain claim-free registration, but the
registration lock still enforces capacity and one current attempt per lane.

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
