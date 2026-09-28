import pytest

from finjev.core.gateway import FakeGateway
from finjev.domain.research.service import ResearchService
from finjev.mcp_server import create_server


@pytest.mark.asyncio
async def test_mcp_exposes_only_the_v01_business_tools() -> None:
    server = create_server(ResearchService(FakeGateway({})))
    tools = await server.list_tools()
    assert [tool.name for tool in tools] == [
        "evaluate_search_results",
        "rerank_search_results",
        "evaluate_source",
        "verify_evidence",
        "classify_financial_event",
        "judge_materiality",
        "should_continue_research",
    ]
    assert all(tool.output_schema is not None for tool in tools)
