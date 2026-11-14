"""Minimal official-SDK stdio MCP server used by the live integration test."""

from mcp.server.fastmcp import FastMCP

server = FastMCP("govagent-live-test")


@server.tool(name="lookup")
def lookup(query: str) -> str:
    return f"records matching {query}"


if __name__ == "__main__":
    server.run(transport="stdio")
