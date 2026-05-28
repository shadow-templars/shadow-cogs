import json
from unittest.mock import AsyncMock, patch

import pytest


class TestRelay:
    async def test_publishes_correct_payload(self, cog, ctx):
        mock_client = AsyncMock()

        with patch("mqttrelay.mqttrelay.aiomqtt.Client") as mock_aiomqtt:
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

        with patch("mqttrelay.mqttrelay.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="status")

        published = mock_client.publish.call_args
        assert published[0][0] == "nexus/commands/inbound"
        assert published[1]["qos"] == 1

    async def test_reacts_hourglass_on_success(self, cog, ctx):
        mock_client = AsyncMock()

        with patch("mqttrelay.mqttrelay.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="whoami")

        ctx.message.add_reaction.assert_called_once_with("⏳")

    async def test_reacts_x_on_failure(self, cog, ctx):
        with patch("mqttrelay.mqttrelay.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.side_effect = Exception("Connection refused")

            await cog.relay(ctx, message="whoami")

        ctx.message.add_reaction.assert_called_once_with("❌")

    async def test_respects_channel_allowlist(self, cog, ctx):
        cog.config.allowed_channels = AsyncMock(return_value=[999999999])
        mock_client = AsyncMock()

        with patch("mqttrelay.mqttrelay.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="whoami")

        mock_client.publish.assert_not_called()
        ctx.message.add_reaction.assert_not_called()

    async def test_allows_when_channel_in_allowlist(self, cog, ctx):
        cog.config.allowed_channels = AsyncMock(return_value=[ctx.channel.id])
        mock_client = AsyncMock()

        with patch("mqttrelay.mqttrelay.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="whoami")

        mock_client.publish.assert_called_once()

    async def test_allows_when_no_channel_restrictions(self, cog, ctx):
        cog.config.allowed_channels = AsyncMock(return_value=[])
        mock_client = AsyncMock()

        with patch("mqttrelay.mqttrelay.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="whoami")

        mock_client.publish.assert_called_once()

    async def test_handles_command_with_no_args(self, cog, ctx):
        mock_client = AsyncMock()

        with patch("mqttrelay.mqttrelay.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="status")

        payload = json.loads(mock_client.publish.call_args[0][1])
        assert payload["command"] == "status"
        assert payload["args"] == []

    async def test_connects_with_configured_credentials(self, cog, ctx):
        mock_client = AsyncMock()

        with patch("mqttrelay.mqttrelay.aiomqtt.Client") as mock_aiomqtt:
            mock_aiomqtt.return_value.__aenter__.return_value = mock_client

            await cog.relay(ctx, message="whoami")

        call_kwargs = mock_aiomqtt.call_args[1]
        assert call_kwargs["hostname"] == "localhost"
        assert call_kwargs["port"] == 1883
        assert call_kwargs["username"] == "relay-cog"
        assert call_kwargs["password"] == "secret"
