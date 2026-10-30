"""Versioned inquiry checkpoints; evidence-linked records, not a truth classifier."""
from copy import deepcopy
import hashlib
import json


def nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def validate_checkpoint(raw):
    if not isinstance(raw, dict):
        raise ValueError("checkpoint must be an object")
    required = {"originalIntent", "understanding", "evidence", "hypotheses", "questions", "nextAction"}
    if set(raw) != required:
        raise ValueError("checkpoint requires exactly: " + ", ".join(sorted(required)))
    result = deepcopy(raw)
    for key in ("originalIntent", "understanding", "nextAction"):
        result[key] = nonempty(raw[key], key)
    ids = set()
    for group in ("evidence", "hypotheses", "questions"):
        if not isinstance(raw[group], list):
            raise ValueError(f"{group} must be an array")
        for item in result[group]:
            if not isinstance(item, dict):
                raise ValueError(f"{group} items must be objects")
            item_id = nonempty(item.get("id"), "id")
            if item_id in ids:
                raise ValueError("duplicate inquiry ID")
            ids.add(item_id)
            item["id"] = item_id
            if group == "evidence":
                if set(item) != {"id", "source", "summary"}:
                    raise ValueError("evidence requires id/source/summary")
                nonempty(item["source"], "source")
                nonempty(item["summary"], "summary")
            else:
                if group == "hypotheses":
                    if set(item) != {"id", "claim", "status", "evidenceIds"}:
                        raise ValueError("hypothesis requires id/claim/status/evidenceIds")
                    nonempty(item["claim"], "claim")
                    statuses = {"untested", "supported", "refuted", "uncertain"}
                else:
                    required_question = {"id", "question", "status", "waitingOn", "answer", "evidenceIds"}
                    if not required_question <= set(item) or set(item) - required_question - {"completionImpact", "coreReason", "resolutionRevision"}:
                        raise ValueError("question requires id/question/status/waitingOn/answer/evidenceIds")
                    if item.get("completionImpact", "local") not in {"core", "local"}:
                        raise ValueError("invalid completionImpact")
                    if item.get("completionImpact") == "core":
                        nonempty(item.get("coreReason"), "coreReason")
                        if item["status"] != "open":
                            nonempty(item.get("answer"), "core resolution answer")
                            if type(item.get("resolutionRevision")) is not int or item["resolutionRevision"] < 0:
                                raise ValueError("closed core question requires resolutionRevision")
                    nonempty(item["question"], "question")
                    statuses = {"open", "answered", "withdrawn"}
                    if item["waitingOn"] not in {"controller", "user", "external", "none"}:
                        raise ValueError("invalid waitingOn")
                    if not isinstance(item["answer"], str):
                        raise ValueError("answer must be text")
                    if item["status"] == "answered":
                        nonempty(item["answer"], "answer")
                    if item["status"] != "open" and item["waitingOn"] != "none":
                        raise ValueError("closed question cannot wait for feedback")
                if item["status"] not in statuses:
                    raise ValueError("invalid inquiry status")
    evidence_ids = {item["id"] for item in result["evidence"]}
    for item in result["hypotheses"] + result["questions"]:
        refs = item["evidenceIds"]
        if not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in evidence_ids for ref in refs):
            raise ValueError("unknown evidence reference")
        if item["status"] in {"supported", "refuted", "answered"} and not refs:
            raise ValueError("resolved judgment requires evidence")
        if item.get("completionImpact") == "core" and not refs:
            raise ValueError("core question requires evidence")
    return result


def advance(ledger, *, event_id, expected_sequence, checkpoint, reason, evidence_ids, impact, timestamp, contract_revision, impact_target=None):
    checkpoint = validate_checkpoint(checkpoint)
    nonempty(event_id, "eventId")
    nonempty(reason, "reason")
    if impact not in {"none", "uncertain", "contract_change"}:
        raise ValueError("invalid impact")
    known = {item["id"] for item in checkpoint["evidence"]}
    if not isinstance(evidence_ids, list) or not evidence_ids or any(not isinstance(ref, str) or ref not in known for ref in evidence_ids):
        raise ValueError("update requires known evidenceIds")
    request = dict(checkpoint=checkpoint, reason=reason, evidenceIds=evidence_ids, impact=impact, impactTarget=impact_target)
    digest = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    previous = ledger or {"version": 1, "sequence": 0, "events": []}
    for event in previous["events"]:
        if event["eventId"] == event_id:
            if event["digest"] != digest:
                raise ValueError("eventId reused with different content")
            return deepcopy(previous), True
    if type(expected_sequence) is not int or expected_sequence != previous["sequence"]:
        raise ValueError("inquiry sequence conflict; read latest checkpoint")
    if previous["sequence"]:
        old = previous["current"]
        if checkpoint["originalIntent"] != old["originalIntent"]:
            raise ValueError("originalIntent is immutable; explain evolving goals in understanding")
        for group in ("evidence", "hypotheses", "questions"):
            current_items = {item["id"]: item for item in checkpoint[group]}
            for item in old[group]:
                if item["id"] not in current_items:
                    raise ValueError("retain prior inquiry items; resolve or withdraw instead of deleting")
                fields = {"evidence": ("source", "summary"), "hypotheses": ("claim",), "questions": ("question",)}[group]
                if any(item[field] != current_items[item["id"]][field] for field in fields):
                    raise ValueError("retain identity content; add a new ID for a changed claim/source")
    old_questions = {q["id"]: q for q in previous.get("current", {}).get("questions", [])}
    evidence_by_id = {e["id"]: e for e in checkpoint["evidence"]}
    for q in checkpoint["questions"]:
        old = old_questions.get(q["id"], {})
        if old.get("completionImpact") == "core":
            if q.get("completionImpact") != "core" or q.get("coreReason") != old.get("coreReason"):
                raise ValueError("core impact/reason cannot be downgraded; resolve or withdraw with evidence")
        if q.get("completionImpact") != "core":
            continue
        if old.get("completionImpact") != "core" and q["status"] != "open":
            raise ValueError("register a core question open before resolving it")
        if q["status"] != "open" and q != old:
            if q.get("resolutionRevision") != (contract_revision if contract_revision is not None else 0):
                raise ValueError("core resolution must bind the current contract revision")
            baseline = old
            if old.get("status") == "open":
                # Evidence may be gathered in earlier updates before closing.
                # Keep the opening finding stable throughout one open episode.
                was_open = False
                for event in previous["events"]:
                    historical = next((item for item in event["checkpoint"]["questions"] if item["id"] == q["id"]), {})
                    is_open = historical.get("completionImpact") == "core" and historical.get("status") == "open"
                    if is_open and not was_open:
                        baseline = historical
                    was_open = is_open
            baseline_content = {(evidence_by_id[ref]["source"], evidence_by_id[ref]["summary"]) for ref in baseline.get("evidenceIds", [])}
            if not any((evidence_by_id[ref]["source"], evidence_by_id[ref]["summary"]) not in baseline_content for ref in q["evidenceIds"]):
                raise ValueError("core resolution requires evidence beyond its opening finding or previous resolution")
    updated = deepcopy(previous)
    updated["sequence"] += 1
    updated["current"] = checkpoint
    updated["events"].append(dict(eventId=event_id, sequence=updated["sequence"], digest=digest,
                                  createdAt=timestamp, contractRevision=contract_revision, **request))
    return updated, False


def compact(ledger):
    if not ledger:
        return {"sequence": 0, "current": None, "lastChange": None}
    event = ledger["events"][-1]
    return {"sequence": ledger["sequence"], "current": ledger["current"],
            "lastChange": {key: event[key] for key in ("eventId", "reason", "evidenceIds", "impact", "contractRevision")}}


def completion_blockers(ledger, contract_revision):
    """Evidence bookkeeping only: this cannot judge whether a claim is true."""
    blockers = []
    for q in (ledger or {}).get("current", {}).get("questions", []):
        if q.get("completionImpact") != "core":
            continue
        revision = contract_revision if contract_revision is not None else 0
        if q["status"] == "open" or q.get("resolutionRevision") != revision:
            blockers.append(f"Unresolved core question {q['id']}: {q['question']} (completion reason: {q['coreReason']})")
    return blockers


def advance_patch(ledger, *, patch, **kwargs):
    """Merge sparse ID-based updates under the caller's state lock.

    Retain full historical checkpoints for compatibility. Replay compares the
    original patch, not a reapplication to newer state.
    """
    if not ledger or not ledger.get("sequence"):
        raise ValueError("patch requires an existing checkpoint")
    if not isinstance(patch, dict) or not patch:
        raise ValueError("patch must be a non-empty object")
    if set(patch) - {"understanding", "nextAction", "evidence", "hypotheses", "questions"}:
        raise ValueError("unknown or immutable patch field")
    request = {key: kwargs[key] for key in ("reason", "evidence_ids", "impact", "impact_target")}
    request["patch"] = patch
    for event in ledger["events"]:
        if event["eventId"] == kwargs["event_id"]:
            if event.get("patchRequest") != request:
                raise ValueError("eventId reused with different content")
            return deepcopy(ledger), True
    if type(kwargs["expected_sequence"]) is not int or kwargs["expected_sequence"] != ledger["sequence"]:
        raise ValueError("inquiry sequence conflict; read latest checkpoint")
    checkpoint = deepcopy(ledger["current"])
    for field, value in patch.items():
        if field in {"understanding", "nextAction"}:
            checkpoint[field] = value
            continue
        if not isinstance(value, list):
            raise ValueError(f"{field} patch must be an array")
        items = {item["id"]: item for item in checkpoint[field]}
        seen = set()
        for entry in value:
            if not isinstance(entry, dict):
                raise ValueError("patch entry must be an object")
            item_id = nonempty(entry.get("id"), "patch id")
            if item_id in seen:
                raise ValueError("duplicate patch ID")
            seen.add(item_id)
            merged = {**items.get(item_id, {}), **deepcopy(entry), "id": item_id}
            if item_id in items:
                checkpoint[field][checkpoint[field].index(items[item_id])] = merged
            else:
                checkpoint[field].append(merged)
    updated, replay = advance(ledger, checkpoint=checkpoint, **kwargs)
    updated["events"][-1]["patchRequest"] = deepcopy(request)
    return updated, replay
