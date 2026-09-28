"""Deterministic materiality floors for auditable financial triggers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

MATERIALITY_ORDER = ("low", "medium", "high", "critical")


@dataclass(frozen=True)
class MaterialityRuleResult:
    floor: str | None
    triggers: tuple[str, ...]
    policy_version: str = "research.materiality-rules.v2"


def _percentages(text: str) -> list[float]:
    return [float(value) for value in re.findall(r"(-?\d+(?:\.\d+)?)\s*%", text)]


def _fact_numbers(event: Any) -> list[dict[str, Any]]:
    return list(getattr(event, "numeric_facts", None) or [])


def _change_for(facts: list[dict[str, Any]], *metric_fragments: str) -> list[float]:
    values: list[float] = []
    for fact in facts:
        metric = str(fact.get("metric") or "")
        if any(fragment in metric for fragment in metric_fragments):
            value = fact.get("change_pct")
            if isinstance(value, int | float):
                values.append(float(value))
    return values


def _normalized_for(facts: list[dict[str, Any]], *metric_fragments: str) -> list[float]:
    values: list[float] = []
    for fact in facts:
        metric = str(fact.get("metric") or "")
        if any(fragment in metric for fragment in metric_fragments):
            value = fact.get("normalized_value")
            if isinstance(value, int | float):
                values.append(float(value))
    return values


def evaluate_materiality_rules(event: Any) -> MaterialityRuleResult:
    text = " ".join(
        part
        for part in (str(getattr(event, "headline", "")), str(getattr(event, "content", "")))
        if part
    )
    facts = _fact_numbers(event)
    triggers: list[str] = []

    critical_phrases = {
        "持续经营存在重大不确定性": "going_concern_material_uncertainty",
        "否定意见": "adverse_audit_opinion",
        "无法表示意见": "disclaimer_audit_opinion",
        "重大缺陷": "material_internal_control_weakness",
    }
    triggers.extend(code for phrase, code in critical_phrases.items() if phrase in text)
    if "保留意见" in text and "无保留意见" not in text and "无保留审计意见" not in text:
        triggers.append("qualified_audit_opinion")

    percentages = _percentages(text)
    if "关键审计事项" in text and "收入" in text and any(value >= 80 for value in percentages):
        triggers.append("revenue_kam_over_80_percent")

    revenue_changes = _change_for(facts, "营业收入", "产品收入")
    profit_values = _normalized_for(facts, "净利润")
    if any(value <= -70 for value in revenue_changes) and (
        "亏损" in text or any(value < 0 for value in profit_values)
    ):
        triggers.append("revenue_collapse_with_loss")

    gross_margin_values = _normalized_for(facts, "毛利率")
    if any(value <= -70 for value in revenue_changes) and (
        any(value < 0 for value in gross_margin_values) or "毛利率为-" in text
    ):
        triggers.append("revenue_collapse_with_negative_margin")

    if triggers:
        return MaterialityRuleResult("critical", tuple(dict.fromkeys(triggers)))

    high_triggers: list[str] = []
    if "关键审计事项" in text:
        high_triggers.append("key_audit_matter")
    if "延期" in text:
        high_triggers.append("project_delay")
    if "担保" in text and any(value >= 5 for value in percentages):
        high_triggers.append("guarantee_over_5_percent")
    if "经营活动产生的现金流量净额" in text and any(
        value < 0 for value in _normalized_for(facts, "经营活动现金流量净额")
    ):
        high_triggers.append("negative_operating_cash_flow")
    if "合同资产" in text and any(value >= 100 for value in _change_for(facts, "合同资产")):
        high_triggers.append("contract_assets_over_100_percent_growth")
    if "短期借款" in text and any(value >= 100 for value in _change_for(facts, "短期借款")):
        high_triggers.append("short_term_debt_over_100_percent_growth")
    if "毛利率" in text and ("下降" in text or "减少" in text):
        high_triggers.append("margin_compression")
    return MaterialityRuleResult(
        "high" if high_triggers else None,
        tuple(dict.fromkeys(high_triggers)),
    )


def max_materiality(*levels: str | None) -> str:
    available = [level for level in levels if level is not None]
    if not available:
        return "low"
    return max(available, key=MATERIALITY_ORDER.index)
