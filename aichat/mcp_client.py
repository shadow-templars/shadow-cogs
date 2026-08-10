import json
import logging

import httpx

log = logging.getLogger("red.shadow-cogs.aichat")


class MCPToolRouter:
    """Manages connections to MCP servers and routes tool calls via stateless HTTP."""

    def __init__(self):
        self._servers: dict[str, str] = {}
        self._sessions: dict[str, str] = {}
        self._tools: dict[str, dict] = {}
        self._tool_server_map: dict[str, str] = {}

    async def connect(self, name: str, url: str):
        """Connect to an MCP server and discover its tools."""
        self._servers[name] = url
        try:
            await self._initialize(name)
            tools = await self._discover_tools(name)
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
        self._sessions.pop(name, None)

    async def close(self):
        """Disconnect from all servers."""
        self._servers.clear()
        self._sessions.clear()
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

        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            args = {}

        try:
            result = await self._request(
                server_name,
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": args,
                },
            )
            if result:
                content = result.get("content", [])
                return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
            return "No result"
        except Exception as e:
            log.exception("Failed to call tool '%s'", tool_name)
            return f"Tool call failed: {e}"

    async def _initialize(self, server_name: str):
        """Send MCP initialize handshake."""
        await self._request(
            server_name,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "aichat", "version": "0.2.0"},
            },
        )

    async def _discover_tools(self, server_name: str) -> list[dict]:
        """Discover tools from an MCP server."""
        result = await self._request(server_name, "tools/list", None)
        tools = result.get("tools", []) if result else []
        return [self._to_openai_format(t) for t in tools]

    async def _request(self, server_name: str, method: str, params: dict | None) -> dict | None:
        """Send a JSON-RPC request to an MCP server."""
        url = self._servers[server_name]

        body: dict = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
        }
        if params:
            body["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        session_id = self._sessions.get(server_name)
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()

            # Store session ID from response
            if "mcp-session-id" in response.headers:
                self._sessions[server_name] = response.headers["mcp-session-id"]

            content_type = response.headers.get("content-type", "")

            # Handle JSON response directly
            if content_type.startswith("application/json"):
                data = response.json()
                if "error" in data:
                    log.error("MCP error from '%s': %s", server_name, data["error"])
                    return None
                return data.get("result")

            # Handle SSE-formatted response (text/event-stream)
            if content_type.startswith("text/event-stream"):
                for line in response.text.splitlines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if "error" in data:
                            log.error("MCP error from '%s': %s", server_name, data["error"])
                            return None
                        return data.get("result")

        return None

    @staticmethod
    def _to_openai_format(tool: dict) -> dict:
        """Convert an MCP tool definition to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
            },
        }
