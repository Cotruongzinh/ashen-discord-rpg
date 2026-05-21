import discord
from discord import app_commands
from discord.ext import commands

from game.content_pack_v09 import apply_content_pack


class ContentPackCog(commands.Cog):
    def __init__(self, bot: commands.Bot, summary: dict):
        self.bot = bot
        self.summary = summary

    @app_commands.command(name="contentpack", description="Xem content pack đang được load")
    async def contentpack(self, interaction: discord.Interaction):
        if self.summary.get("already_applied"):
            desc = "Content pack v0.9 đã được áp dụng trước đó."
        else:
            desc = (
                "**Ashen RPG Content Pack v0.9** đã được load.\n\n"
                f"⚔️ Items mới: **{self.summary.get('items', 0)}**\n"
                f"☠️ Enemies mới: **{self.summary.get('enemies', 0)}**\n"
                f"👑 Boss mới: **{self.summary.get('bosses', 0)}**\n"
                f"🗺️ Area mới: **{self.summary.get('areas', 0)}**"
            )

        embed = discord.Embed(
            title="📦 Content Pack",
            description=desc,
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    summary = apply_content_pack()
    print(f"Applied content pack v0.9: {summary}")
    await bot.add_cog(ContentPackCog(bot, summary))
