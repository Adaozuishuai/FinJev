from __future__ import annotations

from typing import Any

from pydantic import Field

from ...core.models import StrictModel


class Source(StrictModel):
    publisher: str = Field(min_length=1)
    source_type: str | None = None
    url: str | None = None
    publication_date: str | None = None
    is_primary_source: bool | None = None


class SearchResult(StrictModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    snippet: str | None = None
    url: str | None = None
    publisher: str | None = None
    source_type: str | None = None
    publication_date: str | None = None


class ResearchContext(StrictModel):
    company: str | None = None
    question: str = Field(min_length=1)
    known_claims: list[str] | None = None
    as_of: str | None = None


class EvaluateSearchResultsInput(StrictModel):
    query: str = Field(min_length=1)
    results: list[SearchResult] = Field(min_length=1, max_length=25)
    research_context: ResearchContext | None = None


class ProvidedSearchEvaluation(StrictModel):
    result_id: str = Field(min_length=1)
    relevance: float = Field(ge=0, le=1)
    new_information: float = Field(ge=0, le=1)
    worth_fetching: float = Field(ge=0, le=1)
    information_value: float = Field(ge=0, le=1)


class RerankSearchResultsInput(EvaluateSearchResultsInput):
    evaluations: list[ProvidedSearchEvaluation] | None = Field(default=None, max_length=25)


class EvaluateSourceInput(StrictModel):
    source: Source
    claim: str = Field(min_length=1)
    research_context: ResearchContext | None = None


class Evidence(StrictModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source: Source | None = None
    publication_date: str | None = None


class VerifyEvidenceInput(StrictModel):
    claim: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1, max_length=15)
    research_context: ResearchContext | None = None


class FinancialEvent(StrictModel):
    headline: str = Field(min_length=1)
    content: str | None = None
    company: str | None = None
    publication_date: str | None = None
    source: Source | None = None
    related_entities: list[str] | None = Field(default=None, max_length=30)
    numeric_facts: list[dict[str, Any]] | None = Field(default=None, max_length=50)


class ClassifyFinancialEventInput(StrictModel):
    event: FinancialEvent
    research_context: ResearchContext | None = None


class FinancialContext(StrictModel):
    revenue: float | None = Field(default=None, ge=0)
    assets: float | None = Field(default=None, ge=0)
    market_cap: float | None = Field(default=None, ge=0)
    known_materiality_threshold: float | None = Field(default=None, ge=0)
    currency: str | None = None


class JudgeMaterialityInput(StrictModel):
    company: str = Field(min_length=1)
    event: FinancialEvent
    financial_context: FinancialContext | None = None


class ShouldContinueResearchInput(StrictModel):
    research_question: str = Field(min_length=1)
    evidence_summary: str = Field(min_length=1)
    information_gaps: list[str] = Field(max_length=30)
    research_rounds: int = Field(default=0, ge=0, le=100)
