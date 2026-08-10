import json
import logging

import httpx

log = logging.getLogger("red.shadow-cogs.aichat")


class MCPToolRouter:
    """Manages connections to MCP servers and routes tool calls."""

    def __init__(self):
        self._servers: dict[str, str] = {}
        self._sessions: dict[str, str] = {}
        self._tools: dict[str, dict] = {}
        self._tool_server_map: dict[str, str] = {}

    async def connect(self, name: str, url: str):
        """Connect to an MCP server and discover its tools."""
        self._servers[name] = url
        try:
            session_id = await self._establish_session(url)
            self._sessions[name] = session_id
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
            result = await self._send_request(
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

    async def _establish_session(self, url: str) -> str:
        """Connect to the SSE endpoint to get a session ID."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            async with client.stream("GET", url) as response:
                async for line in response.aiter_lines():
                    if line.startswith("event: endpoint"):
                        continue
                    if line.startswith("data: "):
                        endpoint = line[6:].strip()
                        if "session_id=" in endpoint:
                            session_id = endpoint.split("session_id=")[1].split("&")[0]
                            return session_id
        raise RuntimeError(f"Failed to establish session with {url}")

    async def _send_request(self, server_name: str, method: str, params: dict) -> dict | None:
        """Send a JSON-RPC request to an MCP server."""
        url = self._servers[server_name]
        session_id = self._sessions.get(server_name)

        if not session_id:
            session_id = await self._establish_session(url)
            self._sessions[server_name] = session_id

        base_url = url.rsplit("/sse", 1)[0]
        messages_url = f"{base_url}/messages/?session_id={session_id}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                messages_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params,
                },
            )

            if response.status_code == 400 and "session_id" in response.text:
                session_id = await self._establish_session(url)
                self._sessions[server_name] = session_id
                messages_url = f"{base_url}/messages/?session_id={session_id}"
                response = await client.post(
                    messages_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": method,
                        "params": params,
                    },
                )

            response.raise_for_status()

            if response.headers.get("content-type", "").startswith("application/json"):
                result = response.json()
                return result.get("result")

            return None

    async def _discover_tools(self, server_name: str) -> list[dict]:
        """Discover tools from an MCP server and convert to OpenAI format."""
        result = await self._send_request(server_name, "tools/list", {})
        tools = result.get("tools", []) if result else []
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
