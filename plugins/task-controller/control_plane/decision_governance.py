"""Deterministic authority, scenario-policy, and feedback classification.

The controller uses this module before runtime state exists.  It deliberately
contains no persistence or provider logic so the same policy can be exercised
by the Blueprint compiler, CLI helper, MCP adapter, and tests.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


POLICY_VERSION = "1.0"
AUTHORITIES = frozenset({"locked", "agent_may_decide", "propose_then_confirm"})
HIGH_IMPACT_CATEGORIES = frozenset({
    "pricing_structure",
    "billable_item",
    "budget_allocation",
    "kpi_binding",
    "scope_commitment",
    "contract_term",
    "commercial_scope",
})

_CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("billable_item", re.compile(r"收费项|计费项|节点费|服务费|单独收费|重复收费|不能收费|不该收费|billable|charge(?:d|s)?|fee item", re.I)),
    ("kpi_binding", re.compile(r"\bkpi\b|考核指标|指标绑定|扣款|赔付|达成率|绩效权重|deduction|penalt", re.I)),
    ("budget_allocation", re.compile(r"预算(?:分配|拆分|占比)?|费用占比|budget allocation|cost allocation", re.I)),
    ("pricing_structure", re.compile(r"报价结构|价格结构|计价方式|单价|报价|定价|pricing|price|rate card", re.I)),
    ("contract_term", re.compile(r"合同条款|付款条款|账期|结算方式|contract term|payment term", re.I)),
    ("scope_commitment", re.compile(r"交付范围|服务范围|承诺范围|增项|减项|scope commitment|delivery scope", re.I)),
)

_CORRECTION_TRIGGERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("不对", re.compile(r"不对|错了|有误|搞错")),
    ("我要的是", re.compile(r"我要的是|我说的是|不是这个|不是我要")),
    ("按上一版", re.compile(r"按上一版|恢复上一版|回到上一版|沿用原版")),
    ("目标变了", re.compile(r"目标变了|目标改为|改目标|用途变了")),
    ("来源换了", re.compile(r"来源换了|换(?:一份|个)?资料|资料版本不对|数据源不对")),
    ("不能收费", re.compile(r"不能收费|不该收费|不要收费|取消收费|重复收费|不单独收费")),
    ("不要改", re.compile(r"不要改这个|别改这个|保留原样|必须保留")),
    ("移除", re.compile(r"不要放|别放|删掉|删除|去掉|移除")),
)

_PRESERVE_UNMENTIONED = re.compile(r"其他(?:内容|部分)?(?:都)?不变|其余(?:内容|部分)?(?:都)?不变|保留其他|只改(?:这一|这)处")
_APPROVAL_ONLY = re.compile(r"^\s*(好|好的|可以|确认|通过|按这个|就这样|同意|ok|okay)[。！!\s]*$", re.I)


def _text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    return " ".join(
        str(item.get(field, "")).strip()
        for field in ("statement", "description", "title", "label", "id")
        if str(item.get(field, "")).strip()
    )


def _item_id(item: Any) -> str:
    return item.strip() if isinstance(item, str) else str(item.get("id", "")).strip()


def classify_decision_category(value: Any) -> str:
    """Return a stable commercial category, or ``general_change``."""
    if isinstance(value, dict):
        declared = value.get("category")
        if isinstance(declared, str) and declared.strip():
            return declared.strip()
    text = _text(value)
    for category, pattern in _CATEGORY_PATTERNS:
        if pattern.search(text):
            return category
    return "general_change"


def is_client_pricing_blueprint(blueprint: dict[str, Any]) -> bool:
    domains: set[str] = set()
    for field in ("domain", "domains"):
        value = blueprint.get(field, [])
        if isinstance(value, str):
            domains.add(value.lower())
        elif isinstance(value, list):
            domains.update(item.lower() for item in value if isinstance(item, str))
    artifact_values = {
        str(blueprint.get("artifactClass", "")).lower(),
        str(blueprint.get("deliverable", {}).get("artifactClass", "")).lower(),
        str(blueprint.get("deliverable", {}).get("kind", "")).lower(),
    }
    task_type = str(blueprint.get("taskType", "")).lower()
    audience = blueprint.get("deliverable", {}).get("audience", [])
    audience_values = {audience.lower()} if isinstance(audience, str) else {
        item.lower() for item in audience if isinstance(item, str)
    } if isinstance(audience, list) else set()
    explicit = bool(domains & {"client-pricing", "client_quote", "client-quote", "commercial-pricing"})
    pricing = bool(domains & {"pricing", "quote", "quotation"}) or bool(
        artifact_values & {"quote", "quotation", "pricing-workbook", "commercial-proposal"}
    )
    client_facing = any(token in task_type for token in ("client-facing", "client_facing", "client quote", "quotation")) or bool(
        audience_values & {"client", "customer", "客户", "甲方"}
    )
    return explicit or (pricing and client_facing)


def derive_decision_governance(
    blueprint: dict[str, Any], lane_definitions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compile change-policy items into explicit decision authority."""
    policy = blueprint.get("changePolicy", {})
    client_pricing = is_client_pricing_blueprint(blueprint)
    items: list[dict[str, str]] = []
    triggers: set[str] = {"client_pricing"} if client_pricing else set()
    for collection in ("preserve", "allowed", "forbidden"):
        for raw in policy.get(collection, []) if isinstance(policy, dict) else []:
            item_id = _item_id(raw)
            category = classify_decision_category(raw)
            declared = raw.get("authority") if isinstance(raw, dict) else None
            if collection in {"preserve", "forbidden"}:
                authority = "locked"
            elif isinstance(declared, str) and declared in AUTHORITIES:
                authority = declared
            elif category in HIGH_IMPACT_CATEGORIES or client_pricing:
                authority = "propose_then_confirm"
                if category == "general_change":
                    category = "commercial_scope"
            else:
                authority = "agent_may_decide"
            if category in HIGH_IMPACT_CATEGORIES:
                triggers.add(category)
            items.append({
                "id": item_id,
                "category": category,
                "authority": authority,
                "source": f"changePolicy.{collection}",
            })
    confirmation_items = [item for item in items if item["authority"] == "propose_then_confirm"]
    approval_gate = blueprint.get("approvals", {}).get("userApprovalGate", {})
    gate_present = isinstance(approval_gate, dict) and approval_gate.get("required") is True
    lane_names = {
        lane.get("name") for lane in (lane_definitions or []) if isinstance(lane, dict)
    }
    return {
        "policyVersion": POLICY_VERSION,
        "riskLevel": "high" if client_pricing or confirmation_items else "low",
        "confirmationRequired": bool(confirmation_items),
        "confirmationGatePresent": gate_present,
        "items": items,
        "confirmationItemIds": sorted(item["id"] for item in confirmation_items),
        "triggers": sorted(triggers),
        "laneCount": len(lane_names),
    }

def apply_scenario_policy(
    blueprint: dict[str, Any], scenario_pack: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return an effective Blueprint with declared scenario policy defaults.

    Only defaults explicitly checked into the selected scenario pack are
    applied.  The original input object is never mutated.
    """
    result = deepcopy(blueprint)
    applications: list[dict[str, Any]] = []
    defaults = scenario_pack.get("blueprintDefaults", {})
    governance = defaults.get("decisionGovernance", {}) if isinstance(defaults, dict) else {}
    if not isinstance(governance, dict):
        return result, applications

    required_case_ids = governance.get("requiredAcceptanceCaseIds", [])
    if not isinstance(required_case_ids, list):
        raise ValueError("Scenario decisionGovernance.requiredAcceptanceCaseIds must be an array")
    pack_cases = {
        case.get("id"): case for case in scenario_pack.get("acceptanceCases", []) if isinstance(case, dict)
    }
    existing_cases = {
        case.get("id"): case for case in result.get("acceptanceCases", []) if isinstance(case, dict)
    }
    for case_id in required_case_ids:
        if case_id not in pack_cases:
            raise ValueError(f"Scenario required AcceptanceCase is missing: {case_id}")
        canonical = deepcopy(pack_cases[case_id])
        existing = existing_cases.get(case_id)
        if existing is None:
            result.setdefault("acceptanceCases", []).append(canonical)
            existing_cases[case_id] = canonical
            applications.append({"type": "acceptance_case_injected", "id": case_id})
            continue
        protected_fields = (
            "version", "method", "procedure", "expected", "threshold",
            "evidenceSchema", "minimumAttestation", "required",
        )
        for field in protected_fields:
            if field in existing and field in canonical and existing[field] != canonical[field]:
                raise ValueError(f"Blueprint AcceptanceCase conflicts with scenario policy: {case_id}.{field}")
            if field not in existing and field in canonical:
                existing[field] = deepcopy(canonical[field])
        applications.append({"type": "acceptance_case_completed", "id": case_id})

    if governance.get("forceUserApproval") is True:
        gate = result.setdefault("approvals", {}).setdefault("userApprovalGate", {})
        artifact_id = governance.get("approvalArtifactId")
        blocks = governance.get("approvalBlocks")
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise ValueError("Scenario decisionGovernance.approvalArtifactId must be non-empty")
        if not isinstance(blocks, list) or not blocks:
            raise ValueError("Scenario decisionGovernance.approvalBlocks must be non-empty")
        gate.update({"required": True, "artifactId": artifact_id.strip(), "blocks": list(dict.fromkeys(blocks))})
        applications.append({
            "type": "user_approval_gate_enforced",
            "artifactId": artifact_id.strip(),
            "blocks": list(dict.fromkeys(blocks)),
        })
    return result, applications


def _suggest_lane(categories: list[str], lane_names: list[str]) -> str:
    if not lane_names:
        return "controller"
    joined = set(categories)
    preference: tuple[str, ...]
    if joined & {"billable_item", "pricing_structure", "budget_allocation", "kpi_binding", "commercial_scope"}:
        preference = ("pricing-model", "pricing_model", "commercial-model", "model", "pricing", "analysis")
    elif "source_change" in joined:
        preference = ("source-normalization", "source", "evidence", "research")
    elif "workbook_structure" in joined:
        preference = ("workbook-architecture", "architecture", "design", "product")
    else:
        preference = ("strategy", "model", "analysis", "evidence")
    for token in preference:
        for lane in lane_names:
            if lane == token or token in lane.lower():
                return lane
    for lane in lane_names:
        lowered = lane.lower()
        if not any(token in lowered for token in ("approval", "implementation", "production", "review", "final")):
            return lane
    return lane_names[0]


def classify_feedback(
    feedback: str,
    *,
    lane_names: list[str] | None = None,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify user feedback into an executable controller action."""
    text = feedback.strip() if isinstance(feedback, str) else ""
    if not text:
        raise ValueError("feedback must be a non-empty string")
    matched = [label for label, pattern in _CORRECTION_TRIGGERS if pattern.search(text)]
    categories: list[str] = []
    category = classify_decision_category(text)
    if category != "general_change":
        categories.append(category)
    if re.search(r"来源|资料|数据源|source", text, re.I):
        categories.append("source_change")
    if re.search(r"页签|工作表|表格结构|字段|sheet|workbook", text, re.I):
        categories.append("workbook_structure")
    categories = list(dict.fromkeys(categories))
    preserve_unmentioned = bool(_PRESERVE_UNMENTIONED.search(text))
    if _APPROVAL_ONLY.match(text):
        classification = "approval"
        action = "record_approval"
        revision = False
    elif matched:
        classification = "contract_correction"
        action = "record_correction"
        revision = True
    elif text.endswith(("?", "？")):
        classification = "question"
        action = "answer"
        revision = False
    else:
        classification = "local_edit"
        action = "continue_without_revision"
        revision = False

    names = [name for name in (lane_names or []) if isinstance(name, str) and name.strip()]
    suggested = _suggest_lane(categories, names) if revision else ""
    item_ids: list[str] = []
    if governance:
        for item in governance.get("items", []):
            if not isinstance(item, dict):
                continue
            if item.get("category") in categories or (
                not categories and item.get("authority") == "propose_then_confirm"
            ):
                item_id = item.get("id")
                if isinstance(item_id, str) and item_id:
                    item_ids.append(item_id)
    if revision and not item_ids:
        item_ids = [f"feedback:{categories[0] if categories else 'contract'}"]
    return {
        "classification": classification,
        "action": action,
        "requiresContractRevision": revision,
        "matchedTriggers": matched,
        "impactedCategories": categories,
        "impactedRequirementIds": sorted(set(item_ids)),
        "suggestedInvalidFromLane": suggested,
        "preserveUnmentioned": preserve_unmentioned,
        "reason": (
            "Feedback changes a locked or commercially material contract decision."
            if revision else
            "Feedback is an explicit approval." if classification == "approval" else
            "Feedback does not match a contract-correction trigger."
        ),
    }
