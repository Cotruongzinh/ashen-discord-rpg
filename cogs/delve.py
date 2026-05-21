from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from game.delve import (
    DELVE_DUNGEONS,
    abandon_dungeon_run,
    delete_dungeon_run,
    dungeon_status_text,
    get_dungeon_run,
    proceed_next_room,
    search_current_room,
    short_rest_in_dungeon,
    start_dungeon_run,
)
from game.storage import get_player


def delve_embed(user: discord.abc.User, title: str, description: str, color: discord.Color | None = None) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color or discord.Color.dark_teal(),
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.set_footer(text="Ashen RPG • Multi-room Dungeon v0.6")
    return embed


class DelveView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=600)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("🔒 Đây không phải dungeon run của bạn.", ephemeral=True)
            return False
        return True

    async def refresh(self, interaction: discord.Interaction, title: str, text: str, color: discord.Color | None = None):
        player = get_player(self.owner_id)
        run = get_dungeon_run(self.owner_id)
        if not player or not run:
            await interaction.response.edit_message(
                embed=delve_embed(interaction.user, title, text, color or discord.Color.green()),
                view=None,
            )
            return

        desc = f"{text}\n\n---\n{dungeon_status_text(player, run)}"
        await interaction.response.edit_message(
            embed=delve_embed(interaction.user, title, desc, color or discord.Color.dark_teal()),
            view=self,
        )

    @discord.ui.button(label="Tiến tiếp", emoji="🚪", style=discord.ButtonStyle.primary)
    async def next_room(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok, text, run = proceed_next_room(self.owner_id)
        color = discord.Color.green() if run is None and ok else discord.Color.orange()
        if run is None:
            await interaction.response.edit_message(
                embed=delve_embed(interaction.user, "Dungeon kết thúc", text, color),
                view=None,
            )
            return
        await self.refresh(interaction, "🚪 Bạn tiến sâu hơn", text, color)

    @discord.ui.button(label="Lục soát", emoji="🔎", style=discord.ButtonStyle.secondary)
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok, text, run = search_current_room(self.owner_id)
        color = discord.Color.red() if run is None and not ok else discord.Color.blurple()
        if run is None:
            await interaction.response.edit_message(
                embed=delve_embed(interaction.user, "Dungeon kết thúc", text, color),
                view=None,
            )
            return
        await self.refresh(interaction, "🔎 Lục soát căn phòng", text, color)

    @discord.ui.button(label="Nghỉ ngắn", emoji="🌙", style=discord.ButtonStyle.success)
    async def short_rest(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok, text, run = short_rest_in_dungeon(self.owner_id)
        color = discord.Color.red() if run is None and not ok else discord.Color.green()
        if run is None:
            await interaction.response.edit_message(
                embed=delve_embed(interaction.user, "Dungeon kết thúc", text, color),
                view=None,
            )
            return
        await self.refresh(interaction, "🌙 Nghỉ ngắn", text, color)

    @discord.ui.button(label="Rút lui", emoji="🏃", style=discord.ButtonStyle.danger)
    async def retreat(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok, text = abandon_dungeon_run(self.owner_id)
        await interaction.response.edit_message(
            embed=delve_embed(interaction.user, "🏃 Rút lui khỏi dungeon", text, discord.Color.orange()),
            view=None,
        )


async def dungeon_autocomplete(interaction: discord.Interaction, current: str):
    current = current.lower()
    result = []
    for dungeon_id, dungeon in DELVE_DUNGEONS.items():
        label = f"{dungeon['icon']} {dungeon['name']}"
        if current in dungeon_id.lower() or current in dungeon["name"].lower():
            result.append(app_commands.Choice(name=label[:100], value=dungeon_id))
    return result[:25]


class Delve(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="delves", description="Xem các dungeon nhiều phòng có thể khám phá")
    async def delves(self, interaction: discord.Interaction):
        player = get_player(interaction.user.id)
        lines = []
        for dungeon_id, dungeon in DELVE_DUNGEONS.items():
            status = "✅ Có thể thử" if player and player.level >= dungeon["min_level"] else f"🔒 Cần Lv.{dungeon['min_level']}"
            lines.append(
                f"{dungeon['icon']} **{dungeon['name']}** `/{dungeon_id}`\n"
                f"{status} • {dungeon['rooms']} phòng • Cost: 🟩 {dungeon['stamina_cost']} stamina, 💀 {dungeon['entry_souls']} Souls\n"
                f"{dungeon['description']}"
            )
        await interaction.response.send_message(
            embed=delve_embed(interaction.user, "🕯️ Delve Dungeons", "\n\n".join(lines), discord.Color.dark_purple()),
            ephemeral=True,
        )

    @app_commands.command(name="delve", description="Bắt đầu một dungeon nhiều phòng")
    @app_commands.autocomplete(dungeon_id=dungeon_autocomplete)
    async def delve(self, interaction: discord.Interaction, dungeon_id: str):
        ok, text, run = start_dungeon_run(interaction.user.id, dungeon_id)
        if not ok:
            await interaction.response.send_message(
                embed=delve_embed(interaction.user, "Không thể bắt đầu dungeon", text, discord.Color.orange()),
                ephemeral=True,
            )
            return

        player = get_player(interaction.user.id)
        desc = text
        if player and run:
            desc += f"\n\n---\n{dungeon_status_text(player, run)}"
        await interaction.response.send_message(
            embed=delve_embed(interaction.user, "🕯️ Dungeon run bắt đầu", desc, discord.Color.dark_teal()),
            view=DelveView(interaction.user.id),
        )

    @app_commands.command(name="delvestatus", description="Mở lại dungeon run đang diễn ra")
    async def delvestatus(self, interaction: discord.Interaction):
        player = get_player(interaction.user.id)
        run = get_dungeon_run(interaction.user.id)
        if not player or not run:
            await interaction.response.send_message("Bạn không có dungeon run đang diễn ra.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=delve_embed(interaction.user, "🕯️ Dungeon Run", dungeon_status_text(player, run), discord.Color.dark_teal()),
            view=DelveView(interaction.user.id),
        )

    @app_commands.command(name="abandonrun", description="Rút lui khỏi dungeon run hiện tại")
    async def abandonrun(self, interaction: discord.Interaction):
        ok, text = abandon_dungeon_run(interaction.user.id)
        await interaction.response.send_message(
            embed=delve_embed(interaction.user, "🏃 Rút lui", text, discord.Color.orange()),
            ephemeral=not ok,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Delve(bot))
