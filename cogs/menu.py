from __future__ import annotations

import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from game.data import AREAS, ITEMS
from game.storage import get_player, save_player
from game import systems, ui


def safe_area_name(area_key: Optional[str]) -> str:
    if not area_key:
        return "Unknown"
    return AREAS.get(area_key, {"name": area_key}).get("name", area_key)


def status_label(player) -> str:
    status = getattr(player, "status", "idle")
    if status == "idle":
        return "✅ Sẵn sàng"
    if status == "resting":
        end = getattr(player, "rest_end_time", None)
        if end:
            remaining = max(0, int(end - time.time()))
            return f"🌙 Đang nghỉ • còn {remaining}s"
        return "🌙 Đang nghỉ"
    if status == "combat":
        return "⚔️ Đang chiến đấu"
    if status == "dungeon":
        return "🕯️ Đang trong dungeon"
    return f"⏳ {status}"


def make_hub_embed(interaction: discord.Interaction) -> discord.Embed:
    player = get_player(interaction.user.id)

    if not player:
        embed = discord.Embed(
            title="🔥 Ashen RPG — Main Menu",
            description=(
                "Bạn chưa có nhân vật.\n\n"
                "Dùng **/start** để tạo nhân vật trước, sau đó quay lại **/menu** để chơi bằng giao diện button."
            ),
            color=discord.Color.orange(),
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text="Ashen RPG v0.7 • UI Hub")
        return embed

    systems.ensure_player_runtime(player)
    area = AREAS.get(player.area, {"name": player.area, "icon": "📍", "desc": ""})
    need = systems.xp_to_next(player.level)

    tips = []
    if getattr(player, "status", "idle") == "resting":
        tips.append("🌙 Bạn đang nghỉ. Mở tab **Rest** để kiểm tra hoặc hủy nghỉ.")
    elif getattr(player, "status", "idle") == "combat":
        tips.append("⚔️ Bạn đang trong combat. Dùng **/combat** để mở lại trận đấu.")
    elif getattr(player, "status", "idle") == "dungeon":
        tips.append("🕯️ Bạn đang trong dungeon. Dùng **/delvestatus** để mở lại dungeon run.")
    else:
        if player.hp <= max(1, int(player.max_hp * 0.35)):
            tips.append("❤️ HP thấp. Nên nghỉ hoặc dùng vật phẩm hồi máu.")
        if player.stamina <= max(1, int(player.max_stamina * 0.30)):
            tips.append("🟩 Stamina thấp. Nghỉ ngơi sẽ giúp bạn hồi phục.")
        if not tips:
            tips.append("🗺️ Gợi ý: Explore, Fight, Delve hoặc làm quest để farm tài nguyên.")

    embed = discord.Embed(
        title=f"🔥 Ashen RPG — {player.name}",
        description=(
            f"{area.get('icon', '📍')} **{area['name']}**\n"
            f"{area.get('desc', '')}\n\n"
            f"Trạng thái: **{status_label(player)}**\n"
            f"Level: **{player.level}** • XP: **{player.xp}/{need}** `{ui.bar(player.xp, need)}`"
        ),
        color=discord.Color.dark_teal(),
    )
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    embed.add_field(
        name="❤️ HP",
        value=f"**{player.hp}/{player.max_hp}**\n`{ui.bar(player.hp, player.max_hp)}`",
        inline=True,
    )
    embed.add_field(
        name="🟩 Stamina",
        value=f"**{player.stamina}/{player.max_stamina}**\n`{ui.bar(player.stamina, player.max_stamina)}`",
        inline=True,
    )
    embed.add_field(
        name="💰 Tài nguyên",
        value=f"💀 **{player.souls}** Souls\n🪙 **{player.gold}** Gold",
        inline=True,
    )
    embed.add_field(name="🧭 Gợi ý hiện tại", value="\n".join(tips), inline=False)
    embed.set_footer(text="Dùng các button bên dưới để mở nhanh menu. Slash command vẫn dùng bình thường.")
    return embed


class OwnerView(discord.ui.View):
    def __init__(self, owner_id: int, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("🔒 Đây không phải menu của bạn.", ephemeral=True)
            return False
        return True

    async def back_to_hub(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=make_hub_embed(interaction), view=MainMenuView(self.owner_id))


class MainMenuView(OwnerView):
    def __init__(self, owner_id: int):
        super().__init__(owner_id, timeout=600)

    @discord.ui.button(label="Profile", emoji="👤", style=discord.ButtonStyle.primary, row=0)
    async def profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=make_hub_embed(interaction), view=self)
            return
        await interaction.response.edit_message(embed=ui.profile_embed(player), view=self)

    @discord.ui.button(label="Inventory", emoji="🎒", style=discord.ButtonStyle.primary, row=0)
    async def inventory(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=make_hub_embed(interaction), view=self)
            return
        await interaction.response.edit_message(embed=ui.inventory_embed(player), view=InventoryMenuView(self.owner_id))

    @discord.ui.button(label="Map", emoji="🗺️", style=discord.ButtonStyle.secondary, row=0)
    async def map(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=make_hub_embed(interaction), view=self)
            return
        await interaction.response.edit_message(embed=ui.map_embed(player), view=MapMenuView(self.owner_id, player))

    @discord.ui.button(label="Rest", emoji="🌙", style=discord.ButtonStyle.success, row=0)
    async def rest(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=make_hub_embed(interaction), view=self)
            return
        await interaction.response.edit_message(embed=rest_embed(player), view=RestMenuView(self.owner_id))

    @discord.ui.button(label="Adventure", emoji="⚔️", style=discord.ButtonStyle.danger, row=1)
    async def adventure(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=adventure_embed(interaction), view=BackOnlyView(self.owner_id))

    @discord.ui.button(label="Quests", emoji="📜", style=discord.ButtonStyle.secondary, row=1)
    async def quests(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=make_hub_embed(interaction), view=self)
            return
        systems.ensure_player_runtime(player)
        systems.refresh_daily_quests(player)
        save_player(player)
        await interaction.response.edit_message(embed=ui.quests_embed(player), view=QuestMenuView(self.owner_id))

    @discord.ui.button(label="Shop", emoji="🛒", style=discord.ButtonStyle.secondary, row=1)
    async def shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=make_hub_embed(interaction), view=self)
            return
        await interaction.response.edit_message(embed=ui.shop_embed(player), view=BackOnlyView(self.owner_id))

    @discord.ui.button(label="Daily", emoji="🎁", style=discord.ButtonStyle.success, row=1)
    async def daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=make_hub_embed(interaction), view=self)
            return
        await interaction.response.edit_message(embed=ui.daily_embed(player), view=DailyMenuView(self.owner_id))

    @discord.ui.button(label="Help", emoji="❔", style=discord.ButtonStyle.secondary, row=2)
    async def help(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=help_embed(), view=BackOnlyView(self.owner_id))

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=2)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=make_hub_embed(interaction), view=self)


class BackOnlyView(OwnerView):
    @discord.ui.button(label="Quay lại Menu", emoji="⬅️", style=discord.ButtonStyle.primary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_hub(interaction)


class InventoryMenuView(OwnerView):
    async def show(self, interaction: discord.Interaction, item_type: str | None):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=make_hub_embed(interaction), view=MainMenuView(self.owner_id))
            return
        await interaction.response.edit_message(embed=ui.inventory_embed(player, item_type), view=self)

    @discord.ui.button(label="Tất cả", emoji="🎒", style=discord.ButtonStyle.secondary, row=0)
    async def all_items(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, None)

    @discord.ui.button(label="Vũ khí", emoji="⚔️", style=discord.ButtonStyle.primary, row=0)
    async def weapons(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, "weapon")

    @discord.ui.button(label="Giáp", emoji="🛡️", style=discord.ButtonStyle.primary, row=0)
    async def armor(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, "armor")

    @discord.ui.button(label="Nhẫn", emoji="💍", style=discord.ButtonStyle.primary, row=1)
    async def rings(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, "ring")

    @discord.ui.button(label="Vật phẩm", emoji="🧪", style=discord.ButtonStyle.success, row=1)
    async def consumables(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, "consumable")

    @discord.ui.button(label="Nguyên liệu", emoji="🔨", style=discord.ButtonStyle.secondary, row=1)
    async def materials(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, "material")

    @discord.ui.button(label="Quay lại", emoji="⬅️", style=discord.ButtonStyle.secondary, row=2)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_hub(interaction)


class TravelSelect(discord.ui.Select):
    def __init__(self, player):
        options: list[discord.SelectOption] = []
        for key in getattr(player, "unlocked_areas", ["forgotten_catacomb"]):
            area = AREAS.get(key)
            if not area:
                continue
            options.append(discord.SelectOption(
                label=area["name"][:100],
                description=area.get("desc", "")[:100],
                emoji=area.get("icon", "📍"),
                value=key,
                default=(key == player.area),
            ))
        if not options:
            options.append(discord.SelectOption(label="Forgotten Catacomb", value="forgotten_catacomb", emoji="🪦"))
        super().__init__(placeholder="Di chuyển đến khu vực đã mở khóa", min_values=1, max_values=1, options=options[:25], row=0)

    async def callback(self, interaction: discord.Interaction):
        player = get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật.", ephemeral=True)
            return
        if getattr(player, "status", "idle") != "idle":
            await interaction.response.send_message("Bạn chỉ có thể travel khi đang rảnh.", ephemeral=True)
            return
        target = self.values[0]
        if target not in getattr(player, "unlocked_areas", []):
            await interaction.response.send_message("Bạn chưa mở khóa khu vực này.", ephemeral=True)
            return
        player.area = target
        save_player(player)
        await interaction.response.edit_message(embed=ui.map_embed(player), view=MapMenuView(interaction.user.id, player))


class MapMenuView(OwnerView):
    def __init__(self, owner_id: int, player):
        super().__init__(owner_id, timeout=300)
        self.add_item(TravelSelect(player))

    @discord.ui.button(label="Quay lại", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_hub(interaction)


class RestMenuView(OwnerView):
    @discord.ui.button(label="Bắt đầu nghỉ", emoji="🌙", style=discord.ButtonStyle.success, row=0)
    async def start_rest(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=make_hub_embed(interaction), view=MainMenuView(self.owner_id))
            return
        if getattr(player, "status", "idle") not in ["idle", "resting"]:
            embed = ui.result_embed("Bạn đang bận", "Bạn chỉ có thể nghỉ khi không combat hoặc dungeon.", False)
            await interaction.response.edit_message(embed=embed, view=self)
            return
        result = systems.start_rest(player)
        save_player(player)
        embed = ui.result_embed(result.title, result.message, result.ok)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Kiểm tra", emoji="🔎", style=discord.ButtonStyle.primary, row=0)
    async def check_rest(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=make_hub_embed(interaction), view=MainMenuView(self.owner_id))
            return
        result = systems.check_rest(player)
        save_player(player)
        await interaction.response.edit_message(embed=ui.result_embed(result.title, result.message, result.ok), view=self)

    @discord.ui.button(label="Hủy nghỉ", emoji="❌", style=discord.ButtonStyle.danger, row=0)
    async def cancel_rest(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=make_hub_embed(interaction), view=MainMenuView(self.owner_id))
            return
        result = systems.cancel_rest(player)
        save_player(player)
        await interaction.response.edit_message(embed=ui.result_embed(result.title, result.message, result.ok), view=self)

    @discord.ui.button(label="Quay lại", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_hub(interaction)


class DailyMenuView(OwnerView):
    @discord.ui.button(label="Nhận Daily", emoji="🎁", style=discord.ButtonStyle.success)
    async def claim_daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=make_hub_embed(interaction), view=MainMenuView(self.owner_id))
            return
        result = systems.claim_daily_reward(player)
        save_player(player)
        await interaction.response.edit_message(embed=ui.result_embed(result.title, result.message, result.ok), view=self)

    @discord.ui.button(label="Quay lại", emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_hub(interaction)


class QuestMenuView(OwnerView):
    @discord.ui.button(label="Nhận thưởng quest", emoji="🎁", style=discord.ButtonStyle.success)
    async def claim_quests(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=make_hub_embed(interaction), view=MainMenuView(self.owner_id))
            return
        result = systems.claim_completed_quests(player)
        save_player(player)
        await interaction.response.edit_message(embed=ui.result_embed(result.title, result.message, result.ok), view=self)

    @discord.ui.button(label="Làm mới", emoji="🔄", style=discord.ButtonStyle.primary)
    async def refresh_quests(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        systems.ensure_player_runtime(player)
        systems.refresh_daily_quests(player)
        save_player(player)
        await interaction.response.edit_message(embed=ui.quests_embed(player), view=self)

    @discord.ui.button(label="Quay lại", emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_hub(interaction)


def rest_embed(player) -> discord.Embed:
    missing_hp = max(0, player.max_hp - player.hp)
    missing_st = max(0, player.max_stamina - player.stamina)
    status = status_label(player)
    embed = discord.Embed(
        title="🌙 Rest Menu",
        description=(
            f"Trạng thái: **{status}**\n\n"
            f"❤️ HP: **{player.hp}/{player.max_hp}** `{ui.bar(player.hp, player.max_hp)}`\n"
            f"🟩 Stamina: **{player.stamina}/{player.max_stamina}** `{ui.bar(player.stamina, player.max_stamina)}`\n"
            f"🧪 Flask: **{player.flask_charges}/{player.max_flask_charges}**\n\n"
            f"Máu đã mất: **{missing_hp}** • Stamina đã mất: **{missing_st}**"
        ),
        color=discord.Color.dark_blue(),
    )
    embed.set_footer(text="Nghỉ ngơi hồi đầy HP/Stamina/Flask sau thời gian chờ.")
    return embed


def adventure_embed(interaction: discord.Interaction) -> discord.Embed:
    player = get_player(interaction.user.id)
    area_text = "Chưa có nhân vật. Dùng /start trước."
    if player:
        area = AREAS.get(player.area, {"name": player.area, "icon": "📍"})
        area_text = f"{area.get('icon', '📍')} Bạn đang ở **{area['name']}** • {status_label(player)}"
    embed = discord.Embed(
        title="⚔️ Adventure Hub",
        description=(
            f"{area_text}\n\n"
            "Các lệnh phiêu lưu chính:\n"
            "`/explore` — khám phá khu vực, gặp event/quái/rương.\n"
            "`/fight` — bắt đầu combat với quái thường.\n"
            "`/combat` — mở lại combat đang diễn ra.\n"
            "`/boss` — thách đấu boss khu vực.\n"
            "`/delves` — xem dungeon nhiều phòng.\n"
            "`/delve dungeon_id:grave_trial` — vào dungeon nhiều phòng.\n"
            "`/delvestatus` — mở lại dungeon run."
        ),
        color=discord.Color.red(),
    )
    embed.set_footer(text="v0.7 chưa tự bấm thay slash command cho combat/delve để tránh xung đột session.")
    return embed


def help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="❔ Ashen RPG Help",
        description=(
            "**Core**\n"
            "`/start`, `/menu`, `/profile`, `/inventory`, `/map`, `/travel`\n\n"
            "**Combat / Adventure**\n"
            "`/explore`, `/fight`, `/combat`, `/boss`, `/recover`\n\n"
            "**Items**\n"
            "`/equip`, `/useitem`, `/merge`, `/dismantle`, `/lockitem`\n\n"
            "**Loop hằng ngày**\n"
            "`/daily`, `/quests`, `/claimquests`, `/shop`, `/buy`, `/sell`, `/leaderboard`\n\n"
            "**Story / Dungeon**\n"
            "`/npcs`, `/talk`, `/questlog`, `/acceptquest`, `/completequest`, `/lore`\n"
            "`/delves`, `/delve`, `/delvestatus`, `/abandonrun`"
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Mẹo: dùng /menu để mở UI tổng hợp thay vì nhớ toàn bộ lệnh.")
    return embed


class Menu(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="menu", description="Mở menu tổng hợp để chơi Ashen RPG dễ hơn")
    @app_commands.describe(private="Bật để chỉ bạn thấy menu, tắt để gửi công khai trong kênh")
    async def menu(self, interaction: discord.Interaction, private: bool = True):
        await interaction.response.send_message(
            embed=make_hub_embed(interaction),
            view=MainMenuView(interaction.user.id),
            ephemeral=private,
        )

    @app_commands.command(name="help_rpg", description="Xem hướng dẫn lệnh Ashen RPG")
    async def help_rpg(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=help_embed(), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Menu(bot))
