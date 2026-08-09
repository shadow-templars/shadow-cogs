import json
import logging

import httpx

log = logging.getLogger("red.shadow-cogs.aichat")


class MCPToolRouter:
    """Manages connections to MCP servers and routes tool calls."""

    def __init__(self):
        self._servers: dict[str, str] = {}
        self._tools: dict[str, dict] = {}
        self._tool_server_map: dict[str, str] = {}

    async def connect(self, name: str, url: str):
        """Connect to an MCP server and discover its tools."""
        self._servers[name] = url
        try:
            tools = await self._discover_tools(url)
            for tool in tools:
                tool_name = tool["function"]["name"]
                self._tools[tool_name] = tool
                self._tool_server_map[tool_name] = name
            log.info("Connected to MCP server '%s': %d tools", name, len(tools))
        except Exception:
            log.exception("Failed to connect to MCP server '%s' at %s", name, url)

    async def disconnect(self, name: str):
        """Disconnect from an MCP server and remove its tools."""
        tools_to_remove = [t for t, s in self._tool_server_map.items() if s == name]
        for tool_name in tools_to_remove:
            del self._tools[tool_name]
            del self._tool_server_map[tool_name]
        self._servers.pop(name, None)

    async def close(self):
        """Disconnect from all servers."""
        self._servers.clear()
        self._tools.clear()
        self._tool_server_map.clear()

    async def get_openai_tools(self) -> list[dict]:
        """Get all available tools in OpenAI function calling format."""
        return list(self._tools.values())

    def get_tools_for_server(self, name: str) -> list[str]:
        """Get tool names for a specific server."""
        return [t for t, s in self._tool_server_map.items() if s == name]

    async def call_tool(self, tool_name: str, arguments: str) -> str:
        """Call a tool on its MCP server and return the result."""
        server_name = self._tool_server_map.get(tool_name)
        if not server_name:
            return f"Unknown tool: {tool_name}"

        url = self._servers[server_name]
        base_url = url.rsplit("/sse", 1)[0]

        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            args = {}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{base_url}/messages/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": args},
                    },
                )
                response.raise_for_status()
                result = response.json()

                if "result" in result:
                    content = result["result"].get("content", [])
                    return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
                elif "error" in result:
                    return f"Tool error: {result['error'].get('message', 'Unknown error')}"
                return "No result"
        except Exception as e:
            log.exception("Failed to call tool '%s'", tool_name)
            return f"Tool call failed: {e}"

    async def _discover_tools(self, url: str) -> list[dict]:
        """Discover tools from an MCP server and convert to OpenAI format."""
        base_url = url.rsplit("/sse", 1)[0]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/messages/",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                },
            )
            response.raise_for_status()
            result = response.json()

        tools = result.get("result", {}).get("tools", [])
        return [self._mcp_tool_to_openai(tool) for tool in tools]

    @staticmethod
    def _mcp_tool_to_openai(tool: dict) -> dict:
        """Convert an MCP tool definition to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
            },
        }
