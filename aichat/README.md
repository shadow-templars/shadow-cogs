# AiChat

LLM-powered conversational AI for Red. The bot responds when mentioned (or when
you reply to one of its messages) and can call tools exposed by
[MCP](https://modelcontextprotocol.io/) servers via OpenAI function calling.

## Setup

### API key (global, set in DMs)

```
[p]aichat set apikey <openai_api_key>
```

> ⚠️ Run `set apikey` in DMs to avoid leaking the key. The message is
> auto-deleted if sent in a server.

### Model and prompt (global)

```
[p]aichat set model <model>          # default: gpt-4o-mini
[p]aichat set prompt <text>          # or attach a .txt file
```

## Usage

The bot replies when it is **addressed** — either mentioned directly, or when a
user replies to one of the bot's own messages. It pulls a short window of recent
channel messages (up to 10, within 5 minutes of the trigger) as conversation
context, then generates a response.

If any MCP tools are available, the model may call them; results are fed back and
the model continues until it produces a final reply.

### Channel restrictions (per-server)

By default the bot responds in any channel when addressed. Restrict it to
specific channels by running these in the target channel:

```
[p]aichat set channel enable
[p]aichat set channel disable
[p]aichat set channel list
```

When one or more channels are enabled, the bot only responds in those.

## Prompt templating

The system prompt supports context placeholders, substituted per message:

| Placeholder        | Replaced with                     |
| ------------------ | --------------------------------- |
| `{botname}`        | The bot's display name            |
| `{servername}`     | Current server name               |
| `{channelname}`    | Current channel name              |
| `{authorname}`     | Message author's display name     |
| `{authortoprole}`  | Author's top role (or `Member`)   |
| `{currentdate}`    | `YYYY-MM-DD` (UTC)                |
| `{currenttime}`    | `HH:MM UTC`                       |
| `{currentweekday}` | Day of week                       |

## MCP tool integration

AiChat connects to MCP servers over streamable HTTP (JSON-RPC, with SSE-formatted
responses supported) and exposes their tools to the model as OpenAI functions.

```
[p]aichat mcp add <name> <url>       # e.g. add my-server http://localhost:8000/mcp
[p]aichat mcp remove <name>
[p]aichat mcp list                   # servers + discovered tools
[p]aichat mcp reconnect              # reconnect to all servers
```

Point `<url>` at your MCP server's HTTP endpoint (the exact path depends on the
server). Servers are reconnected automatically on cog load. Tool names must be
unique across connected servers.

## Status

```
[p]aichat status
```

Shows the active model, number of MCP servers, total available tools, and channel
configuration for the current server.

## Requirements

- An OpenAI API key
- Optional: one or more MCP servers to expose tools

Python dependencies (installed with the cog): `openai`, `httpx`.
