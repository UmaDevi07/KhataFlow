"""Test the MCP endpoint: python client.py [url]   (default http://localhost:8000/mcp)"""
import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"
CALLS = [
    ("get_balance", {"customer": "Ravi", "session_id": "t1"}),
    ("record_payment", {"amount": 200, "mode": "cash", "session_id": "t1"}),  # no name: uses context
    ("summarize_book", {}),
    ("who_owes_most", {}),
]


async def main():
    async with streamablehttp_client(URL) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print("TOOLS:", [t.name for t in (await s.list_tools()).tools])
            for name, args in CALLS:
                res = await s.call_tool(name, args)
                print(f"\n{name} ->", res.content[0].text)


asyncio.run(main())
