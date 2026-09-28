"""Exercise the installed FinJev process through the real MCP stdio protocol."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def run(call_tool: bool) -> None:
    child_env = {
        key: value
        for key in (
            "TYPESAFE_API_KEY",
            "FINJEV_API_KEY_FILE",
            "TYPESAFE_MODEL",
            "FINJEV_MATERIALITY_PROFILE",
        )
        if (value := os.getenv(key))
    }
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "finjev.mcp_server"],
        env=child_env,
        cwd=os.getcwd(),
    )
    async with stdio_client(parameters) as streams:
        async with ClientSession(*streams) as session:
            initialized = await session.initialize()
            listed = await session.list_tools()
            report: dict[str, object] = {
                "server": initialized.server_info.model_dump(mode="json"),
                "tools": [tool.name for tool in listed.tools],
            }
            if call_tool:
                result = await session.call_tool(
                    "judge_materiality",
                    {
                        "company": "Protocol Smoke Test Co",
                        "event": {
                            "headline": "审计师对财务报表发表保留意见",
                            "content": "审计师表示无法获取充分适当的审计证据。",
                            "company": "Protocol Smoke Test Co",
                            "source": {
                                "publisher": "Protocol Smoke Test Filing",
                                "source_type": "regulator_filing",
                                "is_primary_source": True,
                            },
                        },
                    },
                )
                structured = result.structured_content or {}
                report["call"] = {
                    "is_error": result.is_error,
                    "model": structured.get("model"),
                    "profile": (structured.get("materiality_decision") or {}).get("profile"),
                    "final_materiality": (structured.get("materiality_decision") or {}).get("final"),
                    "action": (structured.get("policy") or {}).get("action"),
                    "decision_authority": structured.get("decision_authority"),
                }
            print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-tool", action="store_true", help="Make one real Jev-backed tool call")
    args = parser.parse_args()
    asyncio.run(run(args.call_tool))


if __name__ == "__main__":
    main()
