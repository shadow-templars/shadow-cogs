import logging
from datetime import UTC, datetime

import openai
from redbot.core import Config, checks, commands

from .mcp_client import MCPToolRouter

log = logging.getLogger("red.shadow-cogs.aichat")

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."


class AiChat(commands.Cog):
    """LLM-powered conversational AI with MCP tool integration."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x41494348415400)
        self.config.register_global(
            openai_api_key="",
            model="gpt-4o-mini",
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            mcp_servers={},
        )
        self.config.register_guild(
            enabled_channels=[],
        )
        self.tool_router = MCPToolRouter()
        self.bot.loop.create_task(self._connect_mcp_servers())

    async def _connect_mcp_servers(self):
        """Connect to all configured MCP servers on startup."""
        await self.bot.wait_until_ready()
        servers = await self.config.mcp_servers()
        for name, url in servers.items():
            await self.tool_router.connect(name, url)

    async def cog_unload(self):
        await self.tool_router.close()

    def _is_addressed(self, message) -> bool:
        if self.bot.user in message.mentions:
            return True
        if message.reference and message.reference.resolved:
            return message.reference.resolved.author == self.bot.user
        return False

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if not self._is_addressed(message):
            return

        enabled = await self.config.guild(message.guild).enabled_channels()
        if enabled and message.channel.id not in enabled:
            return

        async with message.channel.typing():
            response = await self._generate_response(message)

        if response:
            await message.reply(response, mention_author=False)

    async def _generate_response(self, message) -> str | None:
        api_key = await self.config.openai_api_key()
        if not api_key:
            log.warning("No OpenAI API key configured")
            return None

        model = await self.config.model()
        system_prompt = await self.config.system_prompt()
        system_prompt = self._inject_context(system_prompt, message)

        tools = await self.tool_router.get_openai_tools()

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(await self._build_conversation_history(message))

        client = openai.AsyncOpenAI(api_key=api_key)

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools if tools else openai.NOT_GIVEN,
            )

            choice = response.choices[0]

            # Tool calling loop
            while choice.finish_reason == "tool_calls":
                messages.append(choice.message.model_dump())

                for tool_call in choice.message.tool_calls:
                    result = await self.tool_router.call_tool(
                        tool_call.function.name, tool_call.function.arguments
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                    )

                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools if tools else openai.NOT_GIVEN,
                )
                choice = response.choices[0]

            return choice.message.content

        except Exception:
            log.exception("Failed to generate response")
            return None

    def _inject_context(self, prompt: str, message) -> str:
        now = datetime.now(UTC)
        replacements = {
            "{botname}": self.bot.user.display_name,
            "{servername}": message.guild.name,
            "{channelname}": message.channel.name,
            "{authorname}": message.author.display_name,
            "{authortoprole}": message.author.top_role.name
            if message.author.top_role
            else "Member",
            "{currentdate}": now.strftime("%Y-%m-%d"),
            "{currenttime}": now.strftime("%H:%M UTC"),
            "{currentweekday}": now.strftime("%A"),
        }
        for key, value in replacements.items():
            prompt = prompt.replace(key, value)
        return prompt

    async def _build_conversation_history(self, trigger_message) -> list[dict]:
        """Fetch recent channel messages and build conversation context.

        Looks back up to 10 messages within a 5-minute window before the
        trigger message. Maps bot messages to assistant role, everything
        else to user role with the author's name.
        """
        history = []
        max_gap_seconds = 300

        async for msg in trigger_message.channel.history(
            limit=10, before=trigger_message, oldest_first=False
        ):
            gap = (trigger_message.created_at - msg.created_at).total_seconds()
            if gap > max_gap_seconds:
                break

            if msg.author == self.bot.user:
                history.append({"role": "assistant", "content": msg.content})
            elif not msg.author.bot:
                content = f"{msg.author.display_name}: {msg.content}" if msg.content else None
                if content:
                    history.append({"role": "user", "content": content})

        history.reverse()
        history.append({"role": "user", "content": trigger_message.content})
        return history

    # --- Commands ---

    @commands.group(name="aichat")
    @checks.is_owner()
    async def aichat(self, ctx):
        """AI chat configuration."""

    @aichat.group(name="set")
    async def aichat_set(self, ctx):
        """Configure AI chat settings."""

    @aichat_set.command(name="apikey")
    async def set_apikey(self, ctx, api_key: str):
        """Set the OpenAI API key. Use in DMs."""
        await self.config.openai_api_key.set(api_key)
        await ctx.tick()
        if ctx.guild:
            try:
                await ctx.message.delete()
            except Exception:
                await ctx.send("⚠️ Delete your message — it contains credentials.")

    @aichat_set.command(name="model")
    async def set_model(self, ctx, model: str):
        """Set the LLM model for responses."""
        await self.config.model.set(model)
        await ctx.tick()

    @aichat_set.command(name="prompt")
    async def set_prompt(self, ctx, *, prompt: str = None):
        """Set the system prompt. Attach a .txt file or provide inline."""
        if ctx.message.attachments:
            content = (await ctx.message.attachments[0].read()).decode("utf-8")
            await self.config.system_prompt.set(content)
        elif prompt:
            await self.config.system_prompt.set(prompt)
        else:
            await ctx.send("Provide a prompt or attach a .txt file.")
            return
        await ctx.tick()

    @aichat_set.command(name="channel")
    @commands.guild_only()
    async def set_channel(self, ctx, action: str):
        """Manage enabled channels. Run in the target channel.

        Usage: channel enable | channel disable | channel list
        """
        channels = await self.config.guild(ctx.guild).enabled_channels()
        if action == "enable":
            if ctx.channel.id not in channels:
                channels.append(ctx.channel.id)
                await self.config.guild(ctx.guild).enabled_channels.set(channels)
            await ctx.tick()
        elif action == "disable":
            if ctx.channel.id in channels:
                channels.remove(ctx.channel.id)
                await self.config.guild(ctx.guild).enabled_channels.set(channels)
            await ctx.tick()
        elif action == "list":
            if channels:
                formatted = "\n".join(f"• <#{c}>" for c in channels)
                await ctx.send(f"Enabled channels:\n{formatted}")
            else:
                await ctx.send("No channels configured — responds everywhere when addressed.")
        else:
            await ctx.send("Usage: `channel enable|disable|list`")

    @aichat.group(name="mcp")
    async def aichat_mcp(self, ctx):
        """Manage MCP server connections."""

    @aichat_mcp.command(name="add")
    async def mcp_add(self, ctx, name: str, url: str):
        """Add an MCP server. Example: [p]aichat mcp add my-server http://localhost:8000/sse"""
        servers = await self.config.mcp_servers()
        servers[name] = url
        await self.config.mcp_servers.set(servers)
        await self.tool_router.connect(name, url)
        await ctx.tick()

    @aichat_mcp.command(name="remove")
    async def mcp_remove(self, ctx, name: str):
        """Remove an MCP server."""
        servers = await self.config.mcp_servers()
        if name in servers:
            del servers[name]
            await self.config.mcp_servers.set(servers)
            await self.tool_router.disconnect(name)
        await ctx.tick()

    @aichat_mcp.command(name="list")
    async def mcp_list(self, ctx):
        """List configured MCP servers and their tools."""
        servers = await self.config.mcp_servers()
        if not servers:
            await ctx.send("No MCP servers configured.")
            return

        lines = []
        for name, url in servers.items():
            tools = self.tool_router.get_tools_for_server(name)
            tool_names = ", ".join(tools) if tools else "not connected"
            lines.append(f"• **{name}** — `{url}`\n  Tools: {tool_names}")
        await ctx.send("\n".join(lines))

    @aichat_mcp.command(name="reconnect")
    async def mcp_reconnect(self, ctx):
        """Reconnect to all configured MCP servers."""
        servers = await self.config.mcp_servers()
        await self.tool_router.close()
        for name, url in servers.items():
            await self.tool_router.connect(name, url)
        await ctx.tick()

    @aichat.command(name="status")
    async def status(self, ctx):
        """Show AI chat status."""
        model = await self.config.model()
        servers = await self.config.mcp_servers()
        total_tools = len(await self.tool_router.get_openai_tools())
        channels = await self.config.guild(ctx.guild).enabled_channels()

        lines = [
            f"**Model:** {model}",
            f"**MCP Servers:** {len(servers)}",
            f"**Available Tools:** {total_tools}",
            f"**Channels:** {'all (when addressed)' if not channels else len(channels)}",
        ]
        await ctx.send("\n".join(lines))
