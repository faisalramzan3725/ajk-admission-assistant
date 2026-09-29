"""Spawn the JK Assistance MCP server over stdio and call a few tools with the official MCP client.

Usage: python scripts/mcp_smoke_test.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")


async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server" / "server.py")],
                                   env={**os.environ, "JK_DISABLE_LLM": "1", "PYTHONIOENCODING": "utf-8"})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("tools:", ", ".join(t.name for t in tools.tools))
            calls = [
                ("get_service", {"service_id": "must.clearance"}),
                ("advise_admission", {"group": "ics", "hssc_percent": 64, "interests": "computing"}),
                ("get_deadlines", {"institution": "uajk"}),
                ("evaluate_progression", {"semesters": [{"number": 1, "courses": [
                    {"code": "A", "credits": 3, "percent": 40}, {"code": "B", "credits": 3, "percent": 45},
                    {"code": "C", "credits": 3, "percent": 70}, {"code": "D", "credits": 3, "percent": 30}]}]}),
            ]
            for name, args in calls:
                res = await session.call_tool(name, args)
                text = res.content[0].text
                print(f"\n== {name} ->", json.dumps(json.loads(text), ensure_ascii=False)[:400])


asyncio.run(main())
