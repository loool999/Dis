# cogs/ping.py
from discord.ext import commands

class Ping(commands.Cog):
    """Simple ping command."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping", help="Check latency")
    async def ping(self, ctx):
        ms = round(self.bot.latency * 1000)
        await ctx.send(f"Pong! {ms}ms")

async def setup(bot):
    await bot.add_cog(Ping(bot))
