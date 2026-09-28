import pytest

from finjev.core.gateway import FakeGateway
from finjev.core.models import ChoiceAnswer, NoulAnswer, Primitive, ScoreAnswer
from finjev.domain.research.models import (
    ClassifyFinancialEventInput,
    EvaluateSearchResultsInput,
    EvaluateSourceInput,
    Evidence,
    FinancialEvent,
    JudgeMaterialityInput,
    RerankSearchResultsInput,
    ResearchContext,
    SearchResult,
    ShouldContinueResearchInput,
    Source,
    VerifyEvidenceInput,
)
from finjev.domain.research.service import ResearchService


def fixture_answers(_state, questions, _context):
    answers = {}
    for key, question in questions.items():
        if question.primitive == Primitive.NOUL:
            value = 0.1 if "contradiction" in key else 0.9
            answers[key] = NoulAnswer(noul=value)
        elif question.primitive == Primitive.CHOICE:
            options = list(question.criteria)
            probabilities = {option: (1.0 if index == 0 else 0.0) for index, option in enumerate(options)}
            answers[key] = ChoiceAnswer(choice=options[0], probabilities=probabilities, confidence=0.95)
        else:
            levels = list(question.criteria)
            probabilities = {
                str(index): (1.0 if index == len(levels) - 1 else 0.0) for index, _level in enumerate(levels)
            }
            answers[key] = ScoreAnswer(
                score=float(len(levels) - 1),
                probabilities=probabilities,
                confidence=0.95,
                legend={str(index): level for index, level in enumerate(levels)},
            )
    return answers


@pytest.fixture
def service() -> ResearchService:
    return ResearchService(FakeGateway(fixture_answers))


def context() -> ResearchContext:
    return ResearchContext(
        company="Acme", question="Is Acme's margin improving?", known_claims=["Margin was stable"]
    )


@pytest.mark.asyncio
async def test_search_evaluation_and_reranking(service: ResearchService) -> None:
    results = [
        SearchResult(id="a", title="Acme reports annual results", snippet="Revenue and margin update."),
        SearchResult(id="b", title="Unrelated sports story", snippet="No financial information."),
    ]
    evaluated = await service.evaluate_search_results(
        EvaluateSearchResultsInput(query="Acme margin", results=results, research_context=context())
    )
    assert len(evaluated["evaluations"]) == 2
    assert evaluated["evaluations"][0]["policy"]["action"] == "ACCEPT"

    ranked = await service.rerank_search_results(
        RerankSearchResultsInput(query="Acme margin", results=results, research_context=context())
    )
    assert [item["rank"] for item in ranked["ranked"]] == [1, 2]


@pytest.mark.asyncio
async def test_source_evidence_event_materiality_and_continuation(service: ResearchService) -> None:
    source = Source(publisher="Acme IR", source_type="company_release")
    source_result = await service.evaluate_source(
        EvaluateSourceInput(source=source, claim="Acme raised guidance", research_context=context())
    )
    assert source_result["credibility"]["value"] > 0.5
    assert "rubric_versions" in source_result

    evidence_result = await service.verify_evidence(
        VerifyEvidenceInput(
            claim="Acme raised guidance",
            evidence=[Evidence(id="e1", text="The company increased full-year guidance.", source=source)],
            research_context=context(),
        )
    )
    assert evidence_result["findings"][0]["finding"] == "supports"

    event = FinancialEvent(
        headline="Acme announces annual earnings", content="Operating profit increased.", company="Acme"
    )
    event_result = await service.classify_financial_event(
        ClassifyFinancialEventInput(event=event, research_context=context())
    )
    assert event_result["judgments"]["event_type"]["choice"] == "earnings"
    assert event_result["materiality_decision"]["profile"] == "v2"
    assert event_result["decision_authority"] == "advisory_only"

    materiality_result = await service.judge_materiality(JudgeMaterialityInput(company="Acme", event=event))
    assert materiality_result["policy"]["action"] == "HUMAN_REVIEW"
    assert materiality_result["materiality_decision"]["profile"] == "v2"
    assert "missing denominators" in materiality_result["limitation"]

    continuation = await service.should_continue_research(
        ShouldContinueResearchInput(
            research_question="Is Acme's margin improving?",
            evidence_summary="One company release supports improvement.",
            information_gaps=["Independent confirmation"],
        )
    )
    assert continuation["policy"]["action"] in {"CONTINUE", "STOP", "VERIFY"}


@pytest.mark.asyncio
async def test_materiality_v2_uses_versioned_rubric_and_rule_floor() -> None:
    service = ResearchService(FakeGateway(fixture_answers), materiality_profile="v2")
    event = FinancialEvent(
        headline="审计师对财务报表发表保留意见",
        content="无法获取充分适当审计证据。",
        company="Acme",
    )
    result = await service.classify_financial_event(
        ClassifyFinancialEventInput(event=event, research_context=context())
    )

    assert result["materiality_decision"]["final"] == "critical"
    assert result["materiality_decision"]["rule_floor"] == "critical"
    assert "qualified_audit_opinion" in result["materiality_decision"]["rule_triggers"]
    assert result["rubric_versions"]["research.event-materiality-v2"] == ("research.event-materiality.v2")
    assert result["policy"]["action"] == "HUMAN_REVIEW"


@pytest.mark.asyncio
async def test_judge_materiality_uses_same_v2_rule_engine() -> None:
    service = ResearchService(FakeGateway(fixture_answers), materiality_profile="v2")
    event = FinancialEvent(
        headline="审计师对财务报表发表保留意见",
        content="审计师无法获取充分适当审计证据。",
        company="Acme",
    )
    result = await service.judge_materiality(JudgeMaterialityInput(company="Acme", event=event))

    assert result["materiality_decision"]["profile"] == "v2"
    assert result["materiality_decision"]["final"] == "critical"
    assert "qualified_audit_opinion" in result["materiality_decision"]["rule_triggers"]
    assert result["policy"]["action"] == "HUMAN_REVIEW"


@pytest.mark.asyncio
async def test_high_impact_headline_without_supporting_context_abstains() -> None:
    service = ResearchService(FakeGateway(fixture_answers), materiality_profile="v2")
    event = FinancialEvent(headline="Acme reports a potentially critical event", company="Acme")

    result = await service.judge_materiality(JudgeMaterialityInput(company="Acme", event=event))

    assert result["materiality_decision"]["final"] == "critical"
    assert result["policy"]["action"] == "ABSTAIN"
