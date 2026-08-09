from .aichat import AiChat


async def setup(bot):
    await bot.add_cog(AiChat(bot))
