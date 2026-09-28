import pytest

from finjev import __version__
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


@pytest.mark.asyncio
async def test_agent_neutral_prompt_is_available_without_a_model_call() -> None:
    server = create_server(ResearchService(FakeGateway({})))
    prompts = await server.list_prompts()
    assert [prompt.name for prompt in prompts] == ["financial_research_workflow"]
    result = await server.get_prompt("financial_research_workflow", {"question": "研究某公司最新财报"})
    text = result.messages[0].content.text
    assert "研究某公司最新财报" in text
    assert "not a data provider" in text
    assert "ABSTAIN" in text and "HUMAN_REVIEW" in text
    assert "Write your own" in text
    assert server.version == __version__
