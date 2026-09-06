# Durable Collaborative Inquiry

Use for consequential multi-turn investigation or handoff, not every simple Q&A.
The controller maintains this ledger; the user does not fill forms or approve each
update. It records how understanding changes, not a user ability profile.

## Lifecycle

1. Read `task_controller_inquiry_status(statePath)` when resuming. It returns the
   current checkpoint, sequence, last change, current contract revision, and open
   corrections. Request `history: true` only to inspect earlier reasoning changes.
2. At a meaningful new observation, user preference, experiment, or change of
   direction, call `task_controller_update_inquiry`. Supply a unique eventId and
   the expectedSequence from the read (0 for a new ledger). No need to write for
   every message or repeat an unchanged checkpoint to demonstrate activity.
3. For a new path, this creates an `inquiry-only` file. No full production graph
   or execution permission is needed. Only read/updates and eventual init are
   allowed; creating the file grants no host or external-write authority.
4. When a bounded execution contract is supported and authorized, call normal
   init at the same path without force. It retains inquiry history. Resolve a
   precontract `uncertain`/`contract_change` impact through another evidence-backed
   checkpoint with impact `none` before init; the resulting contract establishes
   the execution baseline, not implicit user approval.
5. Existing task states accept the ledger on first update. Contract revisions
   retain history; read results distinguish the current contract revision from
   the revision at which the last inquiry change was recorded.

## Checkpoint And Evidence

`checkpoint` is a complete current snapshot with these fields:

- `originalIntent`: immutable original concern. Evolving goals belong in
  `understanding` with an explicit reason; do not silently replace the concern.
- `understanding`: present interpretation, including uncertainty and relevant
  decisions. Describe what is retained or revised, not private chain-of-thought.
- `evidence`: `{id, source, summary}` entries. Source locators can identify a
  user message, material, test or tool result. Preserve provenance; a user's
  approval proves preference/authority, not technical correctness.
- `hypotheses`: `{id, claim, status, evidenceIds}`. Status is `untested`,
  `supported`, `refuted`, or `uncertain`; supported/refuted requires evidence.
- `questions`: `{id, question, status, waitingOn, answer, evidenceIds}`. Status
  is `open`, `answered`, or `withdrawn`; waitingOn is `controller`, `user`,
  `external`, or `none`. Closed questions use `none`; answered questions require
  an answer and evidence. Do not fabricate an answer to clear a dependency.
- `nextAction`: next useful action and what it should distinguish or achieve.

Each update also requires `reason`, its supporting `evidenceIds`, and `impact`.
Record actual evidence, not an assumed agreement. Retain prior item IDs; change
status or add a new claim/source ID instead of overwriting identity content.
Earlier complete snapshots remain in immutable event history. Replays with the
same ID/content are no-ops; conflicting IDs or stale sequences are rejected.
Read latest and reconcile instead of blindly retrying a conflicting write.

## Link To Execution

- `impact: none`: supplemental understanding or in-scope choice; no new user
  approval, correction, or automatic lane invalidation.
- `impact: uncertain`: a material execution premise may be wrong. Investigate,
  do not classify this as ordinary uncertainty about an unrelated question.
- `impact: contract_change`: evidence or explicit user direction changes the
  accepted contract. In an execution state, both non-none values require
  `requirementIds` and `recommendedInvalidFromLane` and atomically open an
  `inquiry:<eventId>` correction with the checkpoint. Current approvals/finalization
  are invalidated through the existing mechanism.

Open corrections still block execution globally in this runtime. Investigation
and ledger updates remain possible; an update with `impact: none` does not clear
an open correction. Resolve through revise-contract consuming the event ID, even
if investigation disproves the concern and the replacement contract is unchanged.
Do not ask for a ritual user confirmation of an internally resolved uncertainty.
Changed permissions or reserved choices still need actual user authority.

Before dispatch, read current understanding and pass only lane-relevant evidence,
premises and open questions through the existing artifact/packet handoff. Worker
registration records `inquirySequence` for traceability, not as an approval or a
substitute for contract/packet digests. The controller must collect worker findings
and update the ledger when they change the interpretation. It must also reconcile
obsolete host work using dispatch-and-recovery; writing a checkpoint does not
send messages, stop workers, or revoke already-running external actions.

This is structured persistence and gate integration, not automatic semantic truth
verification. The controller still judges impact and evidence relevance. The
keyword feedback classifier and ordered-suffix invalidation remain unchanged.
Do not claim selective branch pausing or automatically verified user feedback.
