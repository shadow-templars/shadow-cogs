import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

import aiomqtt
from redbot.core import Config, checks, commands

log = logging.getLogger("red.shadow-cogs.mqttbridge")


class MqttBridge(commands.Cog):
    """Bridge Discord events and commands to an MQTT broker."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x5348414430575F4D515454)
        self.config.register_global(
            broker_host="localhost",
            broker_port=1883,
            username="",
            password="",
        )
        self.config.register_guild(
            topic="",
            events_topic="",
            enabled_events=[],
            allowed_channels=[],
        )

    async def _publish(self, topic: str, payload: dict) -> bool:
        try:
            host = await self.config.broker_host()
            port = await self.config.broker_port()
            username = await self.config.username()
            password = await self.config.password()

            async with aiomqtt.Client(
                hostname=host,
                port=port,
                username=username or None,
                password=password or None,
            ) as client:
                await client.publish(topic, json.dumps(payload), qos=1)

            return True
        except Exception as e:
            log.error("Failed to publish MQTT message: %s", e)
            return False

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        enabled = await self.config.guild(guild).enabled_events()
        if "member_join" not in enabled:
            return

        events_topic = await self.config.guild(guild).events_topic()
        if not events_topic:
            return

        payload = {
            "version": 1,
            "id": str(uuid4()),
            "event": "member_join",
            "context": {
                "guildId": str(guild.id),
                "userId": str(member.id),
                "username": member.display_name,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }

        await self._publish(events_topic, payload)

    @commands.group(name="mqttbridge")
    async def mqttbridge(self, ctx):
        """MQTT bridge for Discord."""

    @mqttbridge.command(name="relay")
    async def relay(self, ctx, *, message: str):
        """Relay a command via MQTT.

        Create an alias for convenience: [p]alias add mqtt mqttbridge relay
        """
        allowed = await self.config.guild(ctx.guild).allowed_channels()
        if not allowed or ctx.channel.id not in allowed:
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

        topic = await self.config.guild(ctx.guild).topic()
        if not topic:
            await ctx.send("No topic configured. Use `[p]mqttbridge set topic <topic>`.")
            return

        success = await self._publish(topic, payload)
        await ctx.message.add_reaction("⏳" if success else "❌")

    @mqttbridge.group(name="set")
    @checks.is_owner()
    async def mqttbridge_set(self, ctx):
        """Configure the MQTT bridge."""

    @mqttbridge_set.command(name="broker")
    async def set_broker(self, ctx, host: str, port: int = 1883):
        """Set the MQTT broker host and port."""
        await self.config.broker_host.set(host)
        await self.config.broker_port.set(port)
        await ctx.tick()

    @mqttbridge_set.command(name="credentials")
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

    @mqttbridge_set.command(name="topic")
    @commands.guild_only()
    async def set_topic(self, ctx, topic: str):
        """Set the MQTT topic for commands in this server."""
        await self.config.guild(ctx.guild).topic.set(topic)
        await ctx.tick()

    @mqttbridge_set.command(name="events_topic")
    @commands.guild_only()
    async def set_events_topic(self, ctx, topic: str):
        """Set the MQTT topic for events (join/leave) in this server."""
        await self.config.guild(ctx.guild).events_topic.set(topic)
        await ctx.tick()

    @mqttbridge_set.command(name="event")
    @commands.guild_only()
    async def set_event(self, ctx, action: str, event_name: str = None):
        """Manage enabled events. Usage: event enable|disable <name> or event list.

        Available events: member_join, member_leave
        """
        events = await self.config.guild(ctx.guild).enabled_events()
        if action == "enable" and event_name:
            if event_name not in events:
                events.append(event_name)
                await self.config.guild(ctx.guild).enabled_events.set(events)
            await ctx.tick()
        elif action == "disable" and event_name:
            if event_name in events:
                events.remove(event_name)
                await self.config.guild(ctx.guild).enabled_events.set(events)
            await ctx.tick()
        elif action == "list":
            if events:
                formatted = "\n".join(f"• {e}" for e in events)
                await ctx.send(f"Enabled events:\n{formatted}")
            else:
                await ctx.send("No events enabled.")
        else:
            await ctx.send("Usage: `event enable|disable <name>` or `event list`")

    @mqttbridge_set.command(name="channel")
    @commands.guild_only()
    async def set_channel(self, ctx, action: str):
        """Manage allowed channels. Run in the target channel.

        Usage: channel enable | channel disable | channel list
        """
        channels = await self.config.guild(ctx.guild).allowed_channels()
        if action == "enable":
            if ctx.channel.id not in channels:
                channels.append(ctx.channel.id)
                await self.config.guild(ctx.guild).allowed_channels.set(channels)
            await ctx.tick()
        elif action == "disable":
            if ctx.channel.id in channels:
                channels.remove(ctx.channel.id)
                await self.config.guild(ctx.guild).allowed_channels.set(channels)
            await ctx.tick()
        elif action == "list":
            if channels:
                formatted = "\n".join(f"• <#{c}>" for c in channels)
                await ctx.send(f"Enabled channels:\n{formatted}")
            else:
                await ctx.send(
                    "No channels configured — bridge is disabled. Use `channel enable` to enable."
                )
        else:
            await ctx.send("Usage: `channel enable|disable|list`")
