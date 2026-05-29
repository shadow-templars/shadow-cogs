import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

import aiomqtt
from redbot.core import Config, checks, commands

log = logging.getLogger("red.shadow-cogs.mqttrelay")


class MqttRelay(commands.Cog):
    """Relay Discord commands to an MQTT broker."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x5348414430575F4D515454)
        self.config.register_global(
            broker_host="localhost",
            broker_port=1883,
            username="",
            password="",
            topic="nexus/commands/inbound",
            allowed_channels=[],
        )

    @commands.group(name="mqttrelay")
    async def mqttrelay(self, ctx):
        """MQTT command relay."""

    @mqttrelay.command(name="relay")
    async def relay(self, ctx, *, message: str):
        """Relay a command via MQTT.

        Create an alias for convenience: [p]alias add nexus mqttrelay relay
        """
        allowed = await self.config.allowed_channels()
        if allowed and ctx.channel.id not in allowed:
            return

        parts = message.split()
        payload = {
            "version": 1,
            "id": str(uuid4()),
            "command": parts[0],
            "args": parts[1:],
            "raw": message,
            "context": {
                "guildId": str(ctx.guild.id) if ctx.guild else None,
                "channelId": str(ctx.channel.id),
                "userId": str(ctx.author.id),
                "messageId": str(ctx.message.id),
                "username": ctx.author.display_name,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }

        try:
            host = await self.config.broker_host()
            port = await self.config.broker_port()
            username = await self.config.username()
            password = await self.config.password()
            topic = await self.config.topic()

            async with aiomqtt.Client(
                hostname=host,
                port=port,
                username=username or None,
                password=password or None,
            ) as client:
                await client.publish(topic, json.dumps(payload), qos=1)

            await ctx.message.add_reaction("⏳")
        except Exception as e:
            log.error("Failed to publish MQTT message: %s", e)
            await ctx.message.add_reaction("❌")

    @mqttrelay.group(name="set")
    @checks.is_owner()
    async def mqttrelay_set(self, ctx):
        """Configure the MQTT relay."""

    @mqttrelay_set.command(name="broker")
    async def set_broker(self, ctx, host: str, port: int = 1883):
        """Set the MQTT broker host and port."""
        await self.config.broker_host.set(host)
        await self.config.broker_port.set(port)
        await ctx.tick()

    @mqttrelay_set.command(name="credentials")
    async def set_credentials(self, ctx, username: str, password: str):
        """Set MQTT broker credentials. Use in DMs to avoid leaking secrets."""
        await self.config.username.set(username)
        await self.config.password.set(password)
        await ctx.tick()
        if ctx.guild:
            try:
                await ctx.message.delete()
            except Exception:
                await ctx.send("⚠️ Delete your message — it contains credentials.")

    @mqttrelay_set.command(name="topic")
    async def set_topic(self, ctx, topic: str):
        """Set the MQTT topic to publish to."""
        await self.config.topic.set(topic)
        await ctx.tick()

    @mqttrelay_set.command(name="channel")
    async def set_channel(self, ctx, action: str, channel_id: int = None):
        """Manage allowed channels. Usage: channel add/remove <id> or channel list."""
        channels = await self.config.allowed_channels()
        if action == "add" and channel_id:
            if channel_id not in channels:
                channels.append(channel_id)
                await self.config.allowed_channels.set(channels)
            await ctx.tick()
        elif action == "remove" and channel_id:
            if channel_id in channels:
                channels.remove(channel_id)
                await self.config.allowed_channels.set(channels)
            await ctx.tick()
        elif action == "list":
            if channels:
                formatted = "\n".join(f"• <#{c}>" for c in channels)
                await ctx.send(f"Allowed channels:\n{formatted}")
            else:
                await ctx.send("No channel restrictions — relay works in all channels.")
        else:
            await ctx.send("Usage: `channel add|remove|list [channel_id]`")
