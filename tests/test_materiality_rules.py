from finjev.domain.research.materiality import evaluate_materiality_rules, max_materiality
from finjev.domain.research.models import FinancialEvent


def test_nonstandard_audit_opinion_sets_critical_floor() -> None:
    result = evaluate_materiality_rules(
        FinancialEvent(headline="审计师因证据不足发表保留意见", company="Acme")
    )
    assert result.floor == "critical"
    assert result.triggers == ("qualified_audit_opinion",)


def test_standard_unqualified_opinion_does_not_match_qualified_opinion() -> None:
    result = evaluate_materiality_rules(
        FinancialEvent(headline="会计师事务所发表标准无保留意见", company="Acme")
    )
    assert result.floor is None
    assert "qualified_audit_opinion" not in result.triggers


def test_guarantee_over_five_percent_sets_high_floor() -> None:
    result = evaluate_materiality_rules(
        FinancialEvent(headline="担保余额占公司净资产8.62%", company="Acme")
    )
    assert result.floor == "high"
    assert result.triggers == ("guarantee_over_5_percent",)


def test_max_materiality_never_downgrades_semantic_result() -> None:
    assert max_materiality("critical", "high") == "critical"
    assert max_materiality("medium", "high") == "high"


def test_asset_preservation_without_denominator_does_not_force_high() -> None:
    result = evaluate_materiality_rules(
        FinancialEvent(headline="法院裁定执行财产保全，部分银行存款受限", company="Acme")
    )
    assert result.floor is None
