from .healthcheck import HealthCheck


async def setup(bot):
    await bot.add_cog(HealthCheck(bot))
