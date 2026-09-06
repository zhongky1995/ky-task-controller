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
                    if set(item) != {"id", "question", "status", "waitingOn", "answer", "evidenceIds"}:
                        raise ValueError("question requires id/question/status/waitingOn/answer/evidenceIds")
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
