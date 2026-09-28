# Continuing The Working Agreement

Use on continuation, correction, recovery or controller handoff. The purpose is
to carry the user's intent into the next real action, not add more paperwork.

## One Execution Decision

This is the maintained source for mode selection. Other references specify how
to implement the selected mode, not additional reasons to force a split.

1. Restore an existing agreement before applying initial routing. Continue its
   ownership/runtime boundaries; a smaller next step is not a mode reset.
2. For new work, identify the outcome and required professional considerations.
   Separate responsibilities only when useful parallelism, incompatible authority
   or write boundaries, necessary independent review, or demonstrated context
   interference justifies the handoff cost. Domain names, three professional
   layers, a file write or a previous failure alone do not require workers.
3. Use `direct` for cohesive bounded work without an independent-worker requirement.
   Use `sequential-lanes` when intermediate evidence/checkpoints help one owner
   but independent workers add no value. Neither mode claims independent review.
4. Use `distributed` when the user explicitly requires independent execution or
   the task needs isolation/independent review that one owner cannot provide.
   It can also be selected for useful parallelism. Record mandatory requirements
   as such; do not label them optional to bypass admission. Keep tightly coupled
   definition and production together unless a reliable handoff preserves meaning.
5. After choosing distribution, apply the task's runtime policy and actual host
   authority. Session-first remains the default; no silent subagent substitution.
   Reuse compatible idle execution/review Sessions, creating only for a concrete
   isolation, parallelism or context need. No fixed team or Session count.

Verification scales with the consequence of being wrong. Ordinary checks do not
each need a reviewer Session; contract-required or consequential independent
review must remain independent. Existing commercial, sample, receipt and semantic
gates are not relaxed by this routing rule. Domain guidance supplies standards
and checks, not a compulsory team topology.

Checked-in scenario packs can impose additional graph/sample/commercial gates
once selected; those executable gates remain binding. Check that the actual
task fits the pack's scope and approval assumptions, not merely its domain name,
before adopting it. Use the existing generic orchestration route when no pack
fits; do not select a mismatched pack and then bypass its gates.

For a fresh direct request, do not initialize a full orchestration state merely
to document that it is direct. For an existing managed task, retain its evidence
and gates. Report only meaningful choices, progress and limitations to the user.

## User Decisions And Operating Envelope

Proceed through authorized internal checks without repeated plan approvals.
Ask only for missing authority, a material reserved preference/commitment, or an
explicit human gate. Investigate accessible factual uncertainty first. A previous
failure calls for diagnosis, not automatic extra approval rounds or more workers.

Before a work batch, define relevant usage/time/retry stopping conditions within
the user's authority. Concurrency is not a spending limit. Do not claim a hard
cost cap when the host cannot enforce or measure it; stop for a material budget
change or exhausted retry envelope instead of escalating models or looping.

Load current agreement, relevant evidence and the next worker's delta first.
Read historical context only to resolve a specific gap. When a Session's context
can no longer be maintained reliably, checkpoint decisions and unresolved issues
before replacement; disclose lost evidence that affects confidence. No fixed
token allowance or automatic context reset is promised by this plugin.

## Restore Before Acting

Read the current contract/policy and relevant worker status; for multi-turn
inquiry, read its checkpoint as described in `inquiry-ledger.md`. Recover:

- the result the user expects now and who will use or operate it;
- the controller's responsibility and the continuing implementation/review owners;
- the agreed runtime and the user-message evidence authorizing creation or
  coordination of visible conversations, including scope and any revocation;
- current write/spend/publication boundaries, unresolved material choices and
  the next useful action.

Keep these in existing contract/executionPolicy and inquiry understanding/evidence,
not a second ledger. Store source locators and concise decisions, not private
reasoning. A new controller needs this agreement, not just the last worker result.
Restore relevant records silently; tell the user only about substantive changes,
conflicts or missing authority. Do not make them approve unchanged arrangements.

An unchanged short follow-up inherits the existing role and runtime boundaries.
The small-task direct-execution exception is for genuinely direct work, not an
escape from an already assigned controller/worker separation. The controller
may inspect, synthesize and perform explicitly assigned delivery operations;
it must not quietly assume the implementation owner's writes.

## Choose The Outcome Before The Tool

Determine what the next action achieves before picking a capability or worker.
Distinguish preparing something for the user to operate from operating it on
their behalf. Ambiguity that changes cost, actor or deliverable warrants a
focused clarification, not an automatic test suite or new implementation.

Separate building a capability from activating paid or external effects.
Missing live-call authority does not by itself justify substituting a manual
workflow for requested automation. Develop and verify within existing authority;
leave activation disabled if appropriate. If a substitute materially changes
what the user gets or the work they must do, explain the tradeoff and obtain
the reserved choice before committing to that substitute.

## Runtime Admission

Check host permission, actual capability and the task's runtime policy separately.
Plugin defaults never authorize creating or messaging conversations. Explicit
task-scoped conversation coordination can remain valid over related turns; a
generic “continue” preserves that scope but does not invent or expand it.

For an authorized Session workflow, inspect compatible idle project Sessions
before creating another; follow `dispatch-and-recovery.md`. Neither short task
duration nor a correction is a reason to switch to a managed subagent. If the
host disallows the agreed route or authority is missing, stop only the affected
dispatch, state the exact issue and the minimal choice needed. Do not label a
permission conflict as missing tools or silently reinterpret the agreement.

Before every create, resume or follow-up dispatch, check current applicable
AGENTS instructions and host-supported model/reasoning options. Preserve explicit
user choices, resolve stale snapshots, and specify the selected model/reasoning,
task boundary, acceptance and usage stop conditions. Verify effective settings
where the host exposes them; if required settings cannot be confirmed, report
the limitation before dispatch. Do not embed a permanent model version here.

## Correct The Decision, Not Just The Last Action

When feedback exposes a role, runtime or purpose mismatch:

1. Stop the affected action within existing authority and preserve actual changes
   and running-work status. Do not erase evidence or assume a worker stopped.
2. Compare the actual action with the agreement: intended result, responsible
   actor, runtime, permissions and current evidence. Inspect related decisions
   likely affected by the same mistake, not every unrelated part of the project.
3. Distinguish a violated existing agreement from a changed agreement. For a
   violation, restore it and reconcile the host/state; for a material contract
   change, use existing correction/revision gates. Do not reset unrelated work
   or ask for permission already explicitly granted.
4. Resume through the agreed dispatch route only after the mismatch is resolved.
   An apology followed by a different unauthorized tool is not recovery.

If a worker or write bypassed KY-TASK, report it as untracked execution. Do not
fabricate earlier claims, permissions or callbacks to make it look compliant.
Inspect what actually happened, preserve useful artifacts as unverified inputs,
and re-enter a valid current attempt for remaining work and proportionate review.
State migration or a new checkpoint does not itself stop an active host worker.

## Review Actual Behavior

At handoff and after significant recovery, compare consequential claims with
host activity and artifact evidence: who actually wrote, which runtime actually
ran, whether the promised path is usable, and what remains unverified. Reuse
reliable evidence; do not rerun every check. A recorded pass or test count cannot
establish that the right task was chosen or the promised runtime was used.

For maintenance validation, use `../evals/controller-continuity.md`. Those
cases require observable multi-turn behavior; unit tests establish only the
specific state invariants they exercise.
