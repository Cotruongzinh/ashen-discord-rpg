from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from game.storage import get_player, save_player
from game import story, ui


async def npc_autocomplete(interaction: discord.Interaction, current: str):
    player = get_player(interaction.user.id)
    if not player:
        return []
    choices = []
    current_lower = current.lower()
    for key, npc in story.available_npcs(player):
        label = f"{npc['name']} ({key})"
        if current_lower in key.lower() or current_lower in npc["name"].lower():
            choices.append(app_commands.Choice(name=label[:100], value=key))
    return choices[:25]


async def quest_autocomplete(interaction: discord.Interaction, current: str):
    player = get_player(interaction.user.id)
    if not player:
        return []
    story.ensure_story(player)
    current_lower = current.lower()
    choices = []
    for qid, quest in story.STORY_QUESTS.items():
        if current_lower in qid.lower() or current_lower in quest["name"].lower():
            state = story.get_quest_state(player, qid)
            choices.append(app_commands.Choice(name=f"{quest['name']} • {state}"[:100], value=qid))
    return choices[:25]


class Story(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="npcs", description="Xem NPC và quest cốt truyện có thể gặp")
    async def npcs(self, interaction: discord.Interaction):
        player = get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return
        story.ensure_story(player)
        save_player(player)
        await interaction.response.send_message(embed=story.npc_list_embed(player), ephemeral=True)

    @app_commands.command(name="talk", description="Nói chuyện với NPC")
    @app_commands.autocomplete(npc_id=npc_autocomplete)
    async def talk(self, interaction: discord.Interaction, npc_id: str):
        player = get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return
        if player.status == "resting":
            await interaction.response.send_message("🌙 Bạn đang nghỉ. Dùng `/checkrest` để kiểm tra.", ephemeral=True)
            return
        if player.status == "combat":
            await interaction.response.send_message("⚔️ Bạn đang trong combat. Dùng `/combat` để tiếp tục.", ephemeral=True)
            return
        available = {key for key, _ in story.available_npcs(player)}
        if npc_id not in available:
            await interaction.response.send_message("NPC này không có ở khu vực hiện tại hoặc chưa được mở khóa.", ephemeral=True)
            return
        embed = story.talk_embed(player, npc_id)
        save_player(player)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="questlog", description="Xem quest cốt truyện")
    async def questlog(self, interaction: discord.Interaction):
        player = get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return
        story.ensure_story(player)
        save_player(player)
        await interaction.response.send_message(embed=story.questlog_embed(player), ephemeral=True)

    @app_commands.command(name="acceptquest", description="Nhận story quest")
    @app_commands.autocomplete(quest_id=quest_autocomplete)
    async def acceptquest(self, interaction: discord.Interaction, quest_id: str):
        player = get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return
        if player.status in ["resting", "combat"]:
            await interaction.response.send_message("Bạn đang bận, chưa thể nhận quest.", ephemeral=True)
            return
        result = story.accept_quest(player, quest_id)
        if result.ok:
            save_player(player)
        await interaction.response.send_message(embed=ui.result_embed(result.title, result.message, result.ok), ephemeral=True)

    @app_commands.command(name="completequest", description="Trả story quest đã hoàn thành")
    @app_commands.autocomplete(quest_id=quest_autocomplete)
    async def completequest(self, interaction: discord.Interaction, quest_id: str):
        player = get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return
        if player.status in ["resting", "combat"]:
            await interaction.response.send_message("Bạn đang bận, chưa thể trả quest.", ephemeral=True)
            return
        result = story.complete_quest(player, quest_id)
        if result.ok:
            save_player(player)
        await interaction.response.send_message(embed=ui.result_embed(result.title, result.message, result.ok), ephemeral=True)

    @app_commands.command(name="lore", description="Xem Lore Codex đã mở khóa")
    async def lore(self, interaction: discord.Interaction):
        player = get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return
        story.ensure_story(player)
        save_player(player)
        await interaction.response.send_message(embed=story.lore_embed(player), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Story(bot))
