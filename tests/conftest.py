import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_group_decorator(*args, **kwargs):
    def decorator(func):
        func.command = lambda *a, **kw: lambda f: f
        func.group = lambda *a, **kw: _make_group_decorator(*a, **kw)
        return func

    return decorator


# Stub redbot.core before importing the cog
_core = MagicMock()
_core.Config.get_conf = MagicMock(return_value=MagicMock())
_core.commands.Cog = object
_core.commands.group = _make_group_decorator
_core.commands.command = lambda *a, **kw: lambda f: f
_core.checks.is_owner = lambda: lambda f: f

sys.modules["redbot"] = MagicMock()
sys.modules["redbot.core"] = _core


@pytest.fixture
def bot():
    return MagicMock()


@pytest.fixture
def ctx():
    ctx = AsyncMock()
    ctx.guild.id = 123456789
    ctx.channel.id = 987654321
    ctx.author.id = 111222333
    ctx.author.display_name = "TestUser"
    ctx.message.id = 444555666
    ctx.message.add_reaction = AsyncMock()
    ctx.message.delete = AsyncMock()
    ctx.tick = AsyncMock()
    ctx.send = AsyncMock()
    return ctx


@pytest.fixture
def cog(bot):
    from mqttbridge.mqttbridge import MqttBridge

    instance = MqttBridge.__new__(MqttBridge)
    instance.bot = bot

    mock_config = MagicMock()
    global_values = {
        "broker_host": "localhost",
        "broker_port": 1883,
        "username": "relay-cog",
        "password": "secret",
    }
    guild_values = {
        "topic": "nexus/commands/inbound",
        "allowed_channels": [987654321],
    }
    for key, value in global_values.items():
        setattr(mock_config, key, AsyncMock(return_value=value))
        getattr(mock_config, key).set = AsyncMock()

    mock_guild = MagicMock()
    for key, value in guild_values.items():
        setattr(mock_guild, key, AsyncMock(return_value=value))
        getattr(mock_guild, key).set = AsyncMock()

    mock_config.guild = MagicMock(return_value=mock_guild)

    instance.config = mock_config
    return instance
