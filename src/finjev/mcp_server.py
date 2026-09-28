from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import __version__
from .core.gateway import TypeSafeGateway
from .domain.research.models import (
    ClassifyFinancialEventInput,
    EvaluateSearchResultsInput,
    EvaluateSourceInput,
    Evidence,
    FinancialContext,
    FinancialEvent,
    JudgeMaterialityInput,
    RerankSearchResultsInput,
    ResearchContext,
    SearchResult,
    ShouldContinueResearchInput,
    Source,
    VerifyEvidenceInput,
)
from .domain.research.service import ResearchService
from .workflow import RESEARCH_INSTRUCTIONS, research_workflow

SERVER_VERSION = __version__


def resolve_materiality_profile() -> str:
    profile = os.getenv("FINJEV_MATERIALITY_PROFILE", "v2").strip().lower()
    if profile not in {"v1", "v2"}:
        raise RuntimeError("FINJEV_MATERIALITY_PROFILE must be 'v1' or 'v2'.")
    return profile


def create_server(service: ResearchService, *, close_gateway: bool = False) -> MCPServer:
    @asynccontextmanager
    async def lifespan(_server: MCPServer):
        try:
            yield None
        finally:
            await service.gateway.aclose()  # type: ignore[attr-defined]

    server = MCPServer(
        name="finjev",
        version=SERVER_VERSION,
        description="Financial Judgment Infrastructure for MCP-compatible agents.",
        instructions=RESEARCH_INSTRUCTIONS,
        lifespan=lifespan if close_gateway else None,
    )

    @server.prompt(
        name="financial_research_workflow",
        description="Retrieve cited financial evidence, obtain Jev judgments, then synthesize your own answer.",
    )
    def financial_research_workflow(question: str, language: str = "zh-CN") -> str:
        return research_workflow(question, language)

    @server.tool(
        name="evaluate_search_results",
        description="Evaluate search results on relevance, novelty, fetch worthiness, and expected information value.",
        structured_output=True,
    )
    async def evaluate_search_results(
        query: str,
        results: list[SearchResult],
        research_context: ResearchContext | None = None,
    ) -> dict[str, Any]:
        return await service.evaluate_search_results(
            EvaluateSearchResultsInput(query=query, results=results, research_context=research_context)
        )

    @server.tool(
        name="rerank_search_results",
        description="Rerank search results using deterministic composition of atomic research judgments.",
        structured_output=True,
    )
    async def rerank_search_results(
        query: str,
        results: list[SearchResult],
        research_context: ResearchContext | None = None,
        evaluations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return await service.rerank_search_results(
            RerankSearchResultsInput(
                query=query,
                results=results,
                research_context=research_context,
                evaluations=evaluations,
            )
        )

    @server.tool(
        name="evaluate_source",
        description="Evaluate source type, primary-source status, authority, directness, independence, and cross-validation need.",
        structured_output=True,
    )
    async def evaluate_source(
        source: Source,
        claim: str,
        research_context: ResearchContext | None = None,
    ) -> dict[str, Any]:
        return await service.evaluate_source(
            EvaluateSourceInput(source=source, claim=claim, research_context=research_context)
        )

    @server.tool(
        name="verify_evidence",
        description="Evaluate whether evidence supports or contradicts a financial claim and how strong it is.",
        structured_output=True,
    )
    async def verify_evidence(
        claim: str,
        evidence: list[Evidence],
        research_context: ResearchContext | None = None,
    ) -> dict[str, Any]:
        return await service.verify_evidence(
            VerifyEvidenceInput(claim=claim, evidence=evidence, research_context=research_context)
        )

    @server.tool(
        name="classify_financial_event",
        description="Classify a financial event and judge relevance, materiality, fundamental impact, novelty, and follow-up need.",
        structured_output=True,
    )
    async def classify_financial_event(
        event: FinancialEvent,
        research_context: ResearchContext | None = None,
    ) -> dict[str, Any]:
        return await service.classify_financial_event(
            ClassifyFinancialEventInput(event=event, research_context=research_context)
        )

    @server.tool(
        name="judge_materiality",
        description="Judge semantic financial materiality; numeric threshold checks remain ordinary code responsibilities.",
        structured_output=True,
    )
    async def judge_materiality(
        company: str,
        event: FinancialEvent,
        financial_context: FinancialContext | None = None,
    ) -> dict[str, Any]:
        return await service.judge_materiality(
            JudgeMaterialityInput(company=company, event=event, financial_context=financial_context)
        )

    @server.tool(
        name="should_continue_research",
        description="Decide whether code should continue, stop, or verify before another research round.",
        structured_output=True,
    )
    async def should_continue_research(
        research_question: str,
        evidence_summary: str,
        information_gaps: list[str],
        research_rounds: int = 0,
    ) -> dict[str, Any]:
        return await service.should_continue_research(
            ShouldContinueResearchInput(
                research_question=research_question,
                evidence_summary=evidence_summary,
                information_gaps=information_gaps,
                research_rounds=research_rounds,
            )
        )

    return server


def main() -> None:
    if os.getenv("FINJEV_PROVIDER", "typesafe") != "typesafe":
        raise RuntimeError("Only FINJEV_PROVIDER=typesafe is supported by the production MCP entrypoint.")
    profile = resolve_materiality_profile()
    gateway = TypeSafeGateway()
    create_server(
        ResearchService(gateway, materiality_profile=profile),
        close_gateway=True,
    ).run("stdio")


if __name__ == "__main__":
    main()
