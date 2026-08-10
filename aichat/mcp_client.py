import asyncio
import json
import logging

import httpx

log = logging.getLogger("red.shadow-cogs.aichat")


class MCPConnection:
    """A persistent connection to a single MCP server via SSE."""

    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url
        self.session_id: str | None = None
        self.tools: list[dict] = []
        self._client: httpx.AsyncClient | None = None
        self._post_client: httpx.AsyncClient | None = None
        self._response_stream = None
        self._sse_task: asyncio.Task | None = None
        self._connected = asyncio.Event()
        self._pending: dict[int, asyncio.Future] = {}
        self._request_id = 0

    async def connect(self):
        """Establish the SSE connection and discover tools."""
        self._client = httpx.AsyncClient(timeout=60.0)
        self._post_client = httpx.AsyncClient(timeout=60.0)
        self._sse_task = asyncio.create_task(self._maintain_sse())
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=10.0)
            self.tools = await self._discover_tools()
            log.info("Connected to MCP server '%s': %d tools", self.name, len(self.tools))
        except TimeoutError:
            log.error("Timeout connecting to MCP server '%s'", self.name)
            await self.close()
            raise

    async def close(self):
        """Close the connection."""
        if self._sse_task:
            self._sse_task.cancel()
            self._sse_task = None
        if self._response_stream:
            await self._response_stream.aclose()
            self._response_stream = None
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._post_client:
            await self._post_client.aclose()
            self._post_client = None
        self.session_id = None
        self._connected.clear()
        for future in self._pending.values():
            future.cancel()
        self._pending.clear()

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call a tool and return the text result."""
        result = await self._send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )
        if result:
            content = result.get("content", [])
            return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
        return "No result"

    async def _send_request(self, method: str, params: dict | None) -> dict | None:
        """Send a JSON-RPC request and wait for the response via SSE."""
        if not self.session_id or not self._post_client:
            raise RuntimeError(f"Not connected to {self.name}")

        self._request_id += 1
        request_id = self._request_id

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        base_url = self.url.rsplit("/sse", 1)[0]
        messages_url = f"{base_url}/messages/?session_id={self.session_id}"

        try:
            body = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
            }
            if params:
                body["params"] = params

            response = await self._post_client.post(messages_url, json=body)
            response.raise_for_status()

            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except TimeoutError:
            log.error("Timeout waiting for response to %s on '%s'", method, self.name)
            return None
        finally:
            self._pending.pop(request_id, None)

    async def _maintain_sse(self):
        """Keep the SSE stream open and dispatch responses."""
        try:
            self._response_stream = await self._client.send(
                self._client.build_request("GET", self.url),
                stream=True,
            )
            buffer = ""
            event_type = ""

            async for line in self._response_stream.aiter_lines():
                if line.startswith("event: "):
                    event_type = line[7:].strip()
                elif line.startswith("data: "):
                    buffer = line[6:]
                elif line == "" and buffer:
                    await self._handle_sse_event(event_type, buffer)
                    buffer = ""
                    event_type = ""
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("SSE connection to '%s' dropped", self.name)
        finally:
            self._connected.clear()
            self.session_id = None

    async def _handle_sse_event(self, event_type: str, data: str):
        """Handle an SSE event from the server."""
        if event_type == "endpoint":
            if "session_id=" in data:
                self.session_id = data.split("session_id=")[1].split("&")[0]
                self._connected.set()
        elif event_type == "message":
            try:
                msg = json.loads(data)
                request_id = msg.get("id")
                if request_id and request_id in self._pending:
                    future = self._pending[request_id]
                    if not future.done():
                        if "result" in msg:
                            future.set_result(msg["result"])
                        elif "error" in msg:
                            future.set_result(None)
                            log.error("MCP error from '%s': %s", self.name, msg["error"])
            except json.JSONDecodeError:
                pass

    async def _discover_tools(self) -> list[dict]:
        """Discover tools from the MCP server."""
        result = await self._send_request("tools/list", None)
        tools = result.get("tools", []) if result else []
        return [self._to_openai_format(t) for t in tools]

    @staticmethod
    def _to_openai_format(tool: dict) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
            },
        }


class MCPToolRouter:
    """Manages connections to multiple MCP servers and routes tool calls."""

    def __init__(self):
        self._connections: dict[str, MCPConnection] = {}

    async def connect(self, name: str, url: str):
        """Connect to an MCP server."""
        if name in self._connections:
            await self._connections[name].close()

        conn = MCPConnection(name, url)
        try:
            await conn.connect()
            self._connections[name] = conn
        except Exception:
            log.exception("Failed to connect to MCP server '%s'", name)

    async def disconnect(self, name: str):
        """Disconnect from an MCP server."""
        if name in self._connections:
            await self._connections[name].close()
            del self._connections[name]

    async def close(self):
        """Disconnect from all servers."""
        for conn in self._connections.values():
            await conn.close()
        self._connections.clear()

    async def get_openai_tools(self) -> list[dict]:
        """Get all available tools in OpenAI function calling format."""
        tools = []
        for conn in self._connections.values():
            tools.extend(conn.tools)
        return tools

    def get_tools_for_server(self, name: str) -> list[str]:
        """Get tool names for a specific server."""
        conn = self._connections.get(name)
        if not conn:
            return []
        return [t["function"]["name"] for t in conn.tools]

    async def call_tool(self, tool_name: str, arguments: str) -> str:
        """Call a tool on its MCP server and return the result."""
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            args = {}

        for conn in self._connections.values():
            tool_names = [t["function"]["name"] for t in conn.tools]
            if tool_name in tool_names:
                try:
                    return await conn.call_tool(tool_name, args)
                except Exception as e:
                    log.exception("Failed to call tool '%s'", tool_name)
                    return f"Tool call failed: {e}"

        return f"Unknown tool: {tool_name}"
