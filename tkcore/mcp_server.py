"""MCP server for the four agent tools (MCP spec 2026-07-28, Python SDK 2.x): typed outputSchema and
structuredContent on every tool, plus one resource per kural. Read-only and deterministic.

  python -m tkcore.mcp_server        stdio; register it in an MCP client's mcpServers config with this command
"""
import json
from typing import Optional

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import agent_tools as at
from .release import VERSION

server = MCPServer(
    name="thirukkural", title="Thirukkural", version=VERSION,
    instructions="Canonical Thirukkural text with provenance. Never quote a kural from memory: call find_kural or "
                 "get_kural and quote the returned text exactly, and run verify_quote on any kural a model wrote.")
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)


@server.tool(description=at.TOOLS["find_kural"][3], annotations=READ_ONLY)
def find_kural(quote: str, limit: int = 5) -> at.Candidates:
    return at.find_kural(**at.FindKuralIn(quote=quote, limit=limit).model_dump())


@server.tool(description=at.TOOLS["get_kural"][3], annotations=READ_ONLY)
def get_kural(number: int, layers: Optional[list[at.Layer]] = None) -> at.Kural:
    args = {"number": number} if layers is None else {"number": number, "layers": layers}
    return at.get_kural(**at.GetKuralIn(**args).model_dump())


@server.tool(description=at.TOOLS["verify_quote"][3], annotations=READ_ONLY)
def verify_quote(quote: str, number: Optional[int] = None) -> at.Verdict:
    return at.verify_quote(**at.VerifyQuoteIn(quote=quote, number=number).model_dump())


@server.tool(description=at.TOOLS["search_english"][3], annotations=READ_ONLY)
def search_english(query: str, limit: int = 5) -> at.Candidates:
    return at.search_english(**at.SearchEnglishIn(query=query, limit=limit).model_dump())


@server.resource("kural://{number}", name="kural", mime_type="application/json",
                 description="One kural with its Pope and Drew/Lazarus translations and its Merkle proof.")
def kural_resource(number: str) -> str:
    return json.dumps(at.get_kural(int(number)).model_dump(mode="json"), ensure_ascii=False)


if __name__ == "__main__":
    server.run()
