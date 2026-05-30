from .mqttbridge import MqttBridge


async def setup(bot):
    await bot.add_cog(MqttBridge(bot))
