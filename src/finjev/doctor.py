"""Check the installed stdio server without a paid model call by default."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

EXPECTED_TOOLS = {
    "evaluate_search_results", "rerank_search_results", "evaluate_source", "verify_evidence",
    "classify_financial_event", "judge_materiality", "should_continue_research",
}


async def check_server(command: str, env: dict[str, str], *, live: bool = False) -> dict:
    # An explicitly selected key file must win over a stale shell key.
    child_env = dict(os.environ)
    if "FINJEV_API_KEY_FILE" in env:
        child_env.pop("TYPESAFE_API_KEY", None)
    child_env.update(env)
    parameters = StdioServerParameters(command=command, args=[], env=child_env)
    async with asyncio.timeout(120 if live else 30):
        async with stdio_client(parameters) as streams:
            async with ClientSession(*streams) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
                prompts = await session.list_prompts()
                if {tool.name for tool in tools.tools} != EXPECTED_TOOLS:
                    raise RuntimeError("Installed server does not expose the seven expected tools.")
                if "financial_research_workflow" not in {p.name for p in prompts.prompts}:
                    raise RuntimeError("Installed server is missing the research workflow prompt.")
                workflow = await session.get_prompt(
                    "financial_research_workflow", arguments={"question": "Installation check"},
                )
                if not workflow.messages:
                    raise RuntimeError("Workflow prompt is empty.")
                report = {
                    "server": initialized.server_info.model_dump(mode="json"),
                    "tools": sorted(EXPECTED_TOOLS),
                    "prompts": [p.name for p in prompts.prompts],
                    "model_call": "not_requested",
                }
                if live:
                    # Synthetic protocol fixture, not a real company conclusion.
                    result = await session.call_tool("judge_materiality", {
                        "company": "Protocol Smoke Test Co",
                        "event": {
                            "headline": "审计师对财务报表发表保留意见",
                            "content": "审计师表示无法获取充分适当的审计证据。",
                            "company": "Protocol Smoke Test Co",
                            "source": {
                                "publisher": "Protocol Smoke Test Filing",
                                "source_type": "regulator_filing", "is_primary_source": True,
                            },
                        },
                    })
                    structured = result.structured_content or {}
                    if result.is_error or not structured.get("model"):
                        raise RuntimeError("Live Jev tool call failed or returned no model metadata.")
                    report["model_call"] = {
                        "model": structured.get("model"),
                        "action": (structured.get("policy") or {}).get("action"),
                        "decision_authority": structured.get("decision_authority"),
                    }
                return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", default=shutil.which("finjev-mcp"))
    parser.add_argument("--key-file", default=os.getenv("FINJEV_API_KEY_FILE"))
    parser.add_argument("--live", action="store_true", help="Make one billable Jev call with synthetic evidence")
    args = parser.parse_args()
    if not args.command:
        parser.error("finjev-mcp is not on PATH; pass --command with its absolute path.")
    env = {"FINJEV_MATERIALITY_PROFILE": "v2"}
    if args.key_file:
        env["FINJEV_API_KEY_FILE"] = str(Path(args.key_file).expanduser().resolve())
    try:
        report = asyncio.run(check_server(args.command, env, live=args.live))
    except Exception:
        print("MCP check failed. Check executable, credential file and network; no secrets printed.", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
