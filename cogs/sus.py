# cogs/sus.py
import discord
from discord.ext import commands
from discord import app_commands

class sus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sus", help="sus")
    async def sus_prefix(self, ctx, *, text: str):
        await ctx.send(text)

async def setup(bot):
    await bot.add_cog(sus(bot))

# --- Slash command (one input parameter) ---
@app_commands.command(name="sus", description="sus")
@app_commands.describe(text="sus")
async def sus_slash(interaction: discord.Interaction, text: str):
    # Respond to the slash with the provided text
    await interaction.response.send_message(f"e {text}")

# Export to the loader so main.py can register it
APP_COMMANDS = [sus_slash]
# Optional: for fast dev, restrict to a guild:
# APP_COMMAND_GUILD_ID = 123456789012345678
