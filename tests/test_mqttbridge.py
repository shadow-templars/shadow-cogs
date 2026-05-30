import json
from unittest.mock import AsyncMock, patch


class TestRelay:
    async def test_publishes_correct_payload(self, cog, ctx):
        mock_client = AsyncMock()

        with patch("mqttbridge.mqttbridge.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="whoami arg1 arg2")

        published = mock_client.publish.call_args
        payload = json.loads(published[0][1])

        assert payload["version"] == 1
        assert payload["command"] == "whoami"
        assert payload["args"] == ["arg1", "arg2"]
        assert payload["raw"] == "whoami arg1 arg2"
        assert payload["context"]["guildId"] == str(ctx.guild.id)
        assert payload["context"]["channelId"] == str(ctx.channel.id)
        assert payload["context"]["userId"] == str(ctx.author.id)
        assert payload["context"]["messageId"] == str(ctx.message.id)
        assert payload["context"]["username"] == "TestUser"
        assert "id" in payload
        assert "timestamp" in payload["context"]

    async def test_publishes_to_configured_topic(self, cog, ctx):
        mock_client = AsyncMock()

        with patch("mqttbridge.mqttbridge.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="status")

        published = mock_client.publish.call_args
        assert published[0][0] == "nexus/commands/inbound"
        assert published[1]["qos"] == 1

    async def test_reacts_hourglass_on_success(self, cog, ctx):
        mock_client = AsyncMock()

        with patch("mqttbridge.mqttbridge.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="whoami")

        ctx.message.add_reaction.assert_called_once_with("⏳")

    async def test_reacts_x_on_failure(self, cog, ctx):
        with patch("mqttbridge.mqttbridge.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.side_effect = Exception("Connection refused")

            await cog.relay(ctx, message="whoami")

        ctx.message.add_reaction.assert_called_once_with("❌")

    async def test_respects_channel_allowlist(self, cog, ctx):
        cog.config.guild.return_value.allowed_channels = AsyncMock(return_value=[999999999])
        mock_client = AsyncMock()

        with patch("mqttbridge.mqttbridge.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="whoami")

        mock_client.publish.assert_not_called()
        ctx.message.add_reaction.assert_not_called()

    async def test_allows_when_channel_in_allowlist(self, cog, ctx):
        cog.config.guild.return_value.allowed_channels = AsyncMock(return_value=[ctx.channel.id])
        mock_client = AsyncMock()

        with patch("mqttbridge.mqttbridge.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="whoami")

        mock_client.publish.assert_called_once()

    async def test_blocked_when_no_channels_configured(self, cog, ctx):
        cog.config.guild.return_value.allowed_channels = AsyncMock(return_value=[])
        mock_client = AsyncMock()

        with patch("mqttbridge.mqttbridge.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="whoami")

        mock_client.publish.assert_not_called()

    async def test_handles_command_with_no_args(self, cog, ctx):
        mock_client = AsyncMock()

        with patch("mqttbridge.mqttbridge.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="status")

        payload = json.loads(mock_client.publish.call_args[0][1])
        assert payload["command"] == "status"
        assert payload["args"] == []

    async def test_connects_with_configured_credentials(self, cog, ctx):
        mock_client = AsyncMock()

        with patch("mqttbridge.mqttbridge.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="whoami")

        call_kwargs = mock_aiomqtt.call_args[1]
        assert call_kwargs["hostname"] == "localhost"
        assert call_kwargs["port"] == 1883
        assert call_kwargs["username"] == "relay-cog"
        assert call_kwargs["password"] == "secret"


class TestConfig:
    async def test_set_broker(self, cog, ctx):
        await cog.set_broker(ctx, host="mqtt.example.com", port=8883)

        cog.config.broker_host.set.assert_called_once_with("mqtt.example.com")
        cog.config.broker_port.set.assert_called_once_with(8883)
        ctx.tick.assert_called_once()

    async def test_set_credentials(self, cog, ctx):
        ctx.guild = None

        await cog.set_credentials(ctx, username="user", password="pass")

        cog.config.username.set.assert_called_once_with("user")
        cog.config.password.set.assert_called_once_with("pass")
        ctx.tick.assert_called_once()

    async def test_set_credentials_deletes_message_in_guild(self, cog, ctx):
        await cog.set_credentials(ctx, username="user", password="pass")

        ctx.message.delete.assert_called_once()

    async def test_set_topic(self, cog, ctx):
        await cog.set_topic(ctx, topic="custom/topic")

        cog.config.guild.return_value.topic.set.assert_called_once_with("custom/topic")
        ctx.tick.assert_called_once()

    async def test_channel_enable(self, cog, ctx):
        cog.config.guild.return_value.allowed_channels = AsyncMock(return_value=[])
        cog.config.guild.return_value.allowed_channels.set = AsyncMock()

        await cog.set_channel(ctx, action="enable")

        cog.config.guild.return_value.allowed_channels.set.assert_called_once_with([ctx.channel.id])
        ctx.tick.assert_called_once()

    async def test_channel_enable_no_duplicates(self, cog, ctx):
        cog.config.guild.return_value.allowed_channels = AsyncMock(return_value=[ctx.channel.id])
        cog.config.guild.return_value.allowed_channels.set = AsyncMock()

        await cog.set_channel(ctx, action="enable")

        cog.config.guild.return_value.allowed_channels.set.assert_not_called()

    async def test_channel_disable(self, cog, ctx):
        cog.config.guild.return_value.allowed_channels = AsyncMock(
            return_value=[ctx.channel.id, 456]
        )
        cog.config.guild.return_value.allowed_channels.set = AsyncMock()

        await cog.set_channel(ctx, action="disable")

        cog.config.guild.return_value.allowed_channels.set.assert_called_once_with([456])
        ctx.tick.assert_called_once()

    async def test_channel_list(self, cog, ctx):
        cog.config.guild.return_value.allowed_channels = AsyncMock(return_value=[123, 456])

        await cog.set_channel(ctx, action="list")

        ctx.send.assert_called_once()
        assert "123" in ctx.send.call_args[0][0]

    async def test_channel_list_empty(self, cog, ctx):
        cog.config.guild.return_value.allowed_channels = AsyncMock(return_value=[])

        await cog.set_channel(ctx, action="list")

        ctx.send.assert_called_once()
        assert "No channels configured" in ctx.send.call_args[0][0]


class TestEvents:
    async def test_member_join_publishes_event(self, cog, ctx):
        cog.config.guild.return_value.events_topic = AsyncMock(return_value="nexus/events/inbound")
        cog.config.guild.return_value.enabled_events = AsyncMock(return_value=["member_join"])
        mock_client = AsyncMock()

        member = AsyncMock()
        member.guild = ctx.guild
        member.id = 111222333
        member.display_name = "NewMember"

        with patch("mqttbridge.mqttbridge.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.on_member_join(member)

        payload = json.loads(mock_client.publish.call_args[0][1])
        assert payload["version"] == 1
        assert payload["event"] == "member_join"
        assert payload["context"]["userId"] == "111222333"
        assert payload["context"]["username"] == "NewMember"

    async def test_member_join_skipped_when_no_events_topic(self, cog, ctx):
        cog.config.guild.return_value.enabled_events = AsyncMock(return_value=["member_join"])
        cog.config.guild.return_value.events_topic = AsyncMock(return_value="")
        mock_client = AsyncMock()

        member = AsyncMock()
        member.guild = ctx.guild

        with patch("mqttbridge.mqttbridge.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.on_member_join(member)

        mock_client.publish.assert_not_called()

    async def test_member_join_skipped_when_event_not_enabled(self, cog, ctx):
        cog.config.guild.return_value.enabled_events = AsyncMock(return_value=[])
        mock_client = AsyncMock()

        member = AsyncMock()
        member.guild = ctx.guild

        with patch("mqttbridge.mqttbridge.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.on_member_join(member)

        mock_client.publish.assert_not_called()
