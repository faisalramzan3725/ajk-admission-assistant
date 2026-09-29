"""Spawn the JK Assistance MCP server over stdio and call its admission tools with the official MCP client.

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

CALLS = [
    ("get_test", {"test_id": "mdcat"}),
    ("check_admission", {"group": "pre_med", "hssc_obtained": 946, "hssc_total": 1100, "ssc_obtained": 1010, "ssc_total": 1100,
                         "mdcat_obtained": 140, "interests": "medicine"}),
    ("check_admission", {"group": "pre_eng", "hssc_obtained": 80, "ecat_obtained": 210, "interests": "engineering"}),
    ("how_to_apply", {"institution": "jac"}),
    ("admission_dates", {"institution": "uajk"}),
]


async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server" / "server.py")],
                                   env={**os.environ, "JK_DISABLE_LLM": "1", "PYTHONIOENCODING": "utf-8"})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("tools:", ", ".join(t.name for t in (await session.list_tools()).tools))
            for name, args in CALLS:
                res = await session.call_tool(name, args)
                print(f"\n== {name} ->", json.dumps(json.loads(res.content[0].text), ensure_ascii=False)[:400])


if __name__ == "__main__":
    asyncio.run(main())
