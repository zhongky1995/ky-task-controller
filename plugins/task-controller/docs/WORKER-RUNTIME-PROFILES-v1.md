# KY-TASK Worker Runtime Profiles v1

## Outcome

KY-TASK now selects worker runtimes by declared capabilities instead of making
the central state machine decide directly from runtime names.

This is an internal extensibility seam, not a change to the installed default:

- distributed work still uses `native_session_required`;
- the selected worker must be independent, user-visible, and project-capable;
- native Session creation still requires per-task user approval;
- project affinity still defaults to `inherit_or_resolve_required`;
- at most four dependency-ready workers run concurrently by default;
- unavailable native Session tooling still blocks instead of silently falling
  back to a managed Sub Agent.

## Before and after

| Decision | Before | After |
|---|---|---|
| Known worker runtimes | duplicated string lists in Python and MCP | one checked-in runtime profile registry |
| Runtime selection | ordered `if runtime == ...` branches | capability requirements plus explicit priority |
| Persistent worker | hard-coded to one runtime name | requires `supportsPersistent: true` |
| Session-first worker | hard-coded to one runtime name | requires independent + user-visible + project scope |
| Identity validation | runtime-name branch | `identityBinding` from the selected profile |
| Callback default | runtime-name branch | `defaultCallbackMode` from the selected profile |
| Audit trail | `laneRuntime` and handle | profile version and SHA-256 fingerprint are also stored |
| Adding a future adapter | edit central selector branches | add a validated profile, then implement its host adapter |

## Registry contract

The source of truth is
`config/worker-runtime-profiles.json`. Python and MCP both load it and fail
closed when it is missing or malformed.

Each profile declares:

- `runtimeId` and `profileVersion`;
- whether the worker is independent and user-visible;
- whether it supports persistent workbenches;
- whether explicit approval is required;
- the execution-policy field that records that approval;
- runtime-handle identity binding;
- supported project/projectless scope kinds;
- supported and default callback modes;
- whether active thread routing identities are required;
- deterministic selection priority.

The registry and each selected profile receive a canonical SHA-256
fingerprint. Worker registration stores
`runtimeRegistryVersion`, `runtimeProfileVersion`, and
`runtimeProfileFingerprint`, binding the worker record to the capabilities that
authorized it.

## Selection rules

`native_session_required` compiles to this capability requirement:

```text
independent = true
userVisible = true
scope includes project
persistent = lane.workerLifecycle == persistent
explicit approval satisfied when required
```

`lane_lifecycle` keeps the compatibility behavior. For an ephemeral `auto`
lane, `managed_agent_worker` retains the lower selection priority and is chosen
first. This policy must still be an explicit task-level override; it is not a
fallback from Session-first execution.

An explicit lane `runtimePreference` is treated as a filter, not permission to
bypass capability or approval checks.

## Adapter boundary

The profile registry does not execute arbitrary commands or HTTP requests. A
future runtime adapter still needs a concrete, reviewed host implementation for
worker creation, messaging, waiting, cancellation, and identity attestation.

Scope resolution remains outside the adapter: the controller resolves and
locks the target Codex project first, then passes that resolved target to the
host runtime. External-write authorization also remains in the existing permit
and dispatcher layer.

The contract test includes a second synthetic project-capable adapter and
proves it can satisfy the selector without a new runtime-name branch in the
controller. It does not make that synthetic adapter available in production.
