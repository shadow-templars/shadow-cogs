from .mqttrelay import MqttRelay


async def setup(bot):
    await bot.add_cog(MqttRelay(bot))
