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
    from mqttrelay.mqttrelay import MqttRelay

    instance = MqttRelay.__new__(MqttRelay)
    instance.bot = bot

    mock_config = MagicMock()
    config_values = {
        "broker_host": "localhost",
        "broker_port": 1883,
        "username": "relay-cog",
        "password": "secret",
        "topic": "nexus/commands/inbound",
        "allowed_channels": [],
    }
    for key, value in config_values.items():
        setattr(mock_config, key, AsyncMock(return_value=value))
        getattr(mock_config, key).set = AsyncMock()

    instance.config = mock_config
    return instance
