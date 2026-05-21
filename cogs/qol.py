from __future__ import annotations

import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from game.storage import (
    delete_combat,
    get_combat,
    get_player,
    list_players,
    save_player,
)
from game import systems, ui
from game.data import AREAS

try:
    from game.delve import get_dungeon_run, delete_dungeon_run
except Exception:  # v0.8 vẫn chạy được nếu chưa cài v0.6 delve
    get_dungeon_run = None
    delete_dungeon_run = None


GUIDES: dict[str, dict[str, str]] = {
    "beginner": {
        "title": "🔥 Hướng dẫn người mới",
        "body": (
            "**Mục tiêu ban đầu:** tạo nhân vật, khám phá, kiếm loot, nghỉ hồi phục, nâng cấp đồ rồi đánh boss.\n\n"
            "**Flow khuyên dùng:**\n"
            "1. `/start` để tạo nhân vật.\n"
            "2. `/menu` để mở giao diện chính.\n"
            "3. `/explore` hoặc `/fight` để kiếm Souls, XP và loot.\n"
            "4. `/inventory` để xem item.\n"
            "5. `/equip` để trang bị đồ tốt hơn.\n"
            "6. `/merge` để nâng cấp trang bị.\n"
            "7. `/rest` khi HP hoặc stamina thấp.\n"
            "8. `/boss` khi đã đủ mạnh."
        ),
    },
    "combat": {
        "title": "⚔️ Hướng dẫn combat",
        "body": (
            "Combat dùng button theo lượt.\n\n"
            "**Attack**: sát thương ổn định, tốn ít stamina.\n"
            "**Skill**: sát thương cao hơn, tốn nhiều stamina.\n"
            "**Defend**: giảm sát thương nhận vào và hồi stamina.\n"
            "**Herb / Flask**: hồi máu trong combat.\n"
            "**Run**: có thể chạy khỏi quái thường, không hiệu quả với boss.\n\n"
            "Khi boss cảnh báo chuẩn bị tung đòn mạnh, hãy ưu tiên **Defend**."
        ),
    },
    "progression": {
        "title": "📈 Hướng phát triển nhân vật",
        "body": (
            "**Souls** dùng cho nâng cấp và một số hoạt động.\n"
            "**Gold** dùng để mua item, nghỉ trong dungeon, giao dịch.\n"
            "**XP** giúp lên level và tăng chỉ số gốc.\n\n"
            "Đừng bán hoặc phân rã nhầm item tốt. Dùng `/lockitem` để khóa item quan trọng.\n"
            "Farm nguyên liệu bằng `/explore`, `/fight`, `/dungeon` hoặc `/delve`."
        ),
    },
    "daily": {
        "title": "🎁 Daily / Quest / Dungeon",
        "body": (
            "**/daily**: nhận thưởng mỗi ngày.\n"
            "**/quests**: xem daily quest.\n"
            "**/claimquests**: nhận thưởng quest đã hoàn thành.\n"
            "**/dungeons** và **/dungeon**: dungeon nhanh, giới hạn lượt mỗi ngày.\n"
            "**/delves** và **/delve**: dungeon nhiều phòng có lựa chọn.\n\n"
            "Bạn cũng có thể dùng `/menu` để truy cập các mục này bằng button."
        ),
    },
    "commands": {
        "title": "⌨️ Danh sách lệnh chính",
        "body": (
            "**Cơ bản:** `/start`, `/menu`, `/profile`, `/status`, `/guide`\n"
            "**Hành động:** `/explore`, `/fight`, `/combat`, `/boss`, `/rest`, `/checkrest`\n"
            "**Item:** `/inventory`, `/equip`, `/useitem`, `/merge`, `/dismantle`, `/lockitem`\n"
            "**World:** `/map`, `/travel`, `/recover`\n"
            "**Daily/Shop:** `/daily`, `/quests`, `/claimquests`, `/shop`, `/buy`, `/sell`\n"
            "**Story:** `/npcs`, `/talk`, `/questlog`, `/acceptquest`, `/completequest`, `/lore`\n"
            "**Dungeon:** `/dungeons`, `/dungeon`, `/delves`, `/delve`, `/delvestatus`"
        ),
    },
}


def _area_name(area_key: Optional[str]) -> str:
    if not area_key:
        return "Unknown"
    return AREAS.get(area_key, {"name": area_key}).get("name", area_key)


def _status_line(player) -> str:
    now = time.time()
    status = getattr(player, "status", "idle")

    if status == "resting":
        end = getattr(player, "rest_end_time", None)
        if end:
            remaining = max(0, int(end - now))
            return f"🌙 Đang nghỉ • còn **{remaining}s**"
        return "🌙 Đang nghỉ"

    if status == "combat":
        return "⚔️ Đang chiến đấu"

    if status == "dungeon":
        return "🕯️ Đang trong dungeon run"

    return "✅ Sẵn sàng"


def _suggestions(player) -> list[str]:
    status = getattr(player, "status", "idle")
    suggestions: list[str] = []

    if status == "resting":
        suggestions.append("Dùng `/checkrest` để kiểm tra hoặc đợi thông báo nghỉ xong.")
        suggestions.append("Dùng `/cancelrest` nếu muốn hủy nghỉ sớm.")
        return suggestions

    if status == "combat":
        suggestions.append("Dùng `/combat` để mở lại trận đấu đang diễn ra.")
        suggestions.append("Nếu bị kẹt trạng thái, dùng `/repair`.")
        return suggestions

    if status == "dungeon":
        suggestions.append("Dùng `/delvestatus` để tiếp tục dungeon run.")
        suggestions.append("Dùng `/abandonrun` nếu muốn rút lui khỏi dungeon run.")
        return suggestions

    if player.hp <= max(1, int(player.max_hp * 0.35)):
        suggestions.append("HP thấp. Nên dùng `/rest` hoặc `/useitem`.")
    if player.stamina <= max(1, int(player.max_stamina * 0.25)):
        suggestions.append("Stamina thấp. Nên nghỉ trước khi đi tiếp.")
    if getattr(player, "death_echo_souls", 0) > 0:
        suggestions.append(f"Bạn có Echo of Death tại **{_area_name(player.death_echo_area)}**. Dùng `/recover` khi đến đúng khu vực.")

    suggestions.append("Dùng `/menu` để mở hub chính.")
    suggestions.append("Dùng `/guide topic:beginner` nếu cần hướng dẫn.")
    return suggestions[:5]


def _finish_rest_if_done(player) -> tuple[bool, str | None]:
    if getattr(player, "status", "idle") != "resting":
        return False, None

    end = getattr(player, "rest_end_time", None)
    if not end or time.time() < end:
        return False, None

    result = systems.check_rest(player)
    return True, result.message


def _repair_player(player, aggressive: bool = False) -> list[str]:
    """Sửa những trạng thái kẹt phổ biến mà không phá dữ liệu quan trọng."""
    systems.ensure_player_runtime(player)
    notes: list[str] = []

    rested, msg = _finish_rest_if_done(player)
    if rested:
        notes.append(msg or "Đã hoàn tất nghỉ ngơi.")

    if getattr(player, "status", "idle") == "combat":
        session = get_combat(player.discord_id)
        if not session:
            player.status = "idle"
            notes.append("Đã sửa trạng thái combat bị kẹt vì không tìm thấy combat session.")

    if getattr(player, "status", "idle") == "dungeon" and get_dungeon_run is not None:
        run = get_dungeon_run(player.discord_id)
        if not run:
            player.status = "idle"
            notes.append("Đã sửa trạng thái dungeon bị kẹt vì không tìm thấy dungeon run.")

    if aggressive:
        # Chỉ dùng khi người chơi yêu cầu: xóa combat/run nếu bot bị kẹt nặng.
        if get_combat(player.discord_id):
            delete_combat(player.discord_id)
            if player.status == "combat":
                player.status = "idle"
            notes.append("Đã xóa combat session hiện tại.")
        if delete_dungeon_run is not None and get_dungeon_run is not None:
            if get_dungeon_run(player.discord_id):
                delete_dungeon_run(player.discord_id)
                if player.status == "dungeon":
                    player.status = "idle"
                notes.append("Đã xóa dungeon run hiện tại.")

    return notes


def _status_embed(player, notes: Optional[list[str]] = None) -> discord.Embed:
    systems.ensure_player_runtime(player)
    area = AREAS.get(player.area, {"name": player.area, "icon": "📍", "desc": ""})
    notify_rest = player.stats.get("notify_rest", True)

    embed = discord.Embed(
        title=f"📌 Status — {player.name}",
        description=(
            f"{area.get('icon', '📍')} **{area.get('name', player.area)}**\n"
            f"{_status_line(player)}"
        ),
        color=discord.Color.dark_teal(),
    )

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
        value=f"💀 Souls: **{player.souls}**\n🪙 Gold: **{player.gold}**\n🧪 Flask: **{player.flask_charges}/{player.max_flask_charges}**",
        inline=True,
    )

    embed.add_field(
        name="📊 Thống kê",
        value=(
            f"Kills: **{player.stats.get('kills', 0)}**\n"
            f"Bosses: **{player.stats.get('bosses', 0)}**\n"
            f"Dungeons: **{player.stats.get('dungeons', 0)}**\n"
            f"Deaths: **{player.stats.get('deaths', 0)}**"
        ),
        inline=True,
    )
    embed.add_field(
        name="🔔 Thông báo",
        value=f"Rest notification: **{'Bật' if notify_rest else 'Tắt'}**\nDùng `/notifyrest` để đổi.",
        inline=True,
    )
    embed.add_field(
        name="💡 Gợi ý tiếp theo",
        value="\n".join(f"• {line}" for line in _suggestions(player)),
        inline=False,
    )

    if notes:
        embed.add_field(
            name="🛠️ Sửa tự động",
            value="\n".join(f"• {n}" for n in notes),
            inline=False,
        )

    embed.set_footer(text="Ashen RPG v0.8 • status / guide / repair / rest notification")
    return embed


class QuickStatusView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Đây không phải status menu của bạn.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=ui.basic_embed("Chưa có nhân vật", "Dùng `/start` trước.", discord.Color.orange()), view=None)
            return
        notes = _repair_player(player, aggressive=False)
        save_player(player)
        await interaction.response.edit_message(embed=_status_embed(player, notes), view=self)

    @discord.ui.button(label="Open Menu", emoji="🔥", style=discord.ButtonStyle.primary)
    async def open_menu_hint(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Dùng `/menu` để mở hub chính của game.", ephemeral=True)

    @discord.ui.button(label="Repair", emoji="🛠️", style=discord.ButtonStyle.danger)
    async def repair(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.edit_message(embed=ui.basic_embed("Chưa có nhân vật", "Dùng `/start` trước.", discord.Color.orange()), view=None)
            return
        notes = _repair_player(player, aggressive=True)
        if not notes:
            notes = ["Không phát hiện trạng thái kẹt nào."]
        save_player(player)
        await interaction.response.edit_message(embed=_status_embed(player, notes), view=self)


class QOL(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rest_notifier.start()

    def cog_unload(self):
        self.rest_notifier.cancel()

    @tasks.loop(seconds=60)
    async def rest_notifier(self):
        """Tự hoàn tất nghỉ và gửi DM nhẹ khi rest xong."""
        try:
            players = list_players(limit=300)
        except Exception as exc:
            print(f"[rest_notifier] list players failed: {exc}")
            return

        for player in players:
            try:
                systems.ensure_player_runtime(player)
                if getattr(player, "status", "idle") != "resting":
                    continue
                end = getattr(player, "rest_end_time", None)
                if not end or time.time() < end:
                    continue

                notify = player.stats.get("notify_rest", True)
                result = systems.check_rest(player)
                save_player(player)

                if notify:
                    try:
                        user = await self.bot.fetch_user(int(player.discord_id))
                        await user.send(
                            "🔥 **Ashen RPG:** Bạn đã nghỉ xong. HP, stamina và Ember Flask đã hồi đầy.\n"
                            "Dùng `/menu`, `/explore`, `/fight` hoặc `/delve` để tiếp tục."
                        )
                    except Exception:
                        # Không DM được thì thôi, state vẫn đã được cập nhật.
                        pass
            except Exception as exc:
                print(f"[rest_notifier] failed for {getattr(player, 'discord_id', 'unknown')}: {exc}")

    @rest_notifier.before_loop
    async def before_rest_notifier(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="status", description="Xem trạng thái hiện tại và gợi ý hành động tiếp theo")
    async def status(self, interaction: discord.Interaction):
        player = get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        notes = _repair_player(player, aggressive=False)
        save_player(player)
        await interaction.response.send_message(embed=_status_embed(player, notes), view=QuickStatusView(interaction.user.id), ephemeral=True)

    @app_commands.command(name="repair", description="Sửa trạng thái bị kẹt như combat/dungeon/rest session lỗi")
    @app_commands.describe(aggressive="Bật nếu muốn xóa combat/dungeon session hiện tại để thoát kẹt")
    async def repair(self, interaction: discord.Interaction, aggressive: bool = False):
        player = get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        notes = _repair_player(player, aggressive=aggressive)
        if not notes:
            notes = ["Không phát hiện trạng thái kẹt nào."]
        save_player(player)
        await interaction.response.send_message(embed=_status_embed(player, notes), ephemeral=True)

    @app_commands.command(name="notifyrest", description="Bật hoặc tắt thông báo DM khi nghỉ ngơi xong")
    @app_commands.describe(enabled="True để bật, False để tắt")
    async def notifyrest(self, interaction: discord.Interaction, enabled: bool):
        player = get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        systems.ensure_player_runtime(player)
        player.stats["notify_rest"] = bool(enabled)
        save_player(player)

        await interaction.response.send_message(
            f"🔔 Rest notification đã được **{'bật' if enabled else 'tắt'}**.",
            ephemeral=True,
        )

    @app_commands.command(name="guide", description="Hướng dẫn chơi Ashen RPG")
    @app_commands.describe(topic="Chọn chủ đề hướng dẫn")
    @app_commands.choices(topic=[
        app_commands.Choice(name="Người mới", value="beginner"),
        app_commands.Choice(name="Combat", value="combat"),
        app_commands.Choice(name="Phát triển nhân vật", value="progression"),
        app_commands.Choice(name="Daily / Quest / Dungeon", value="daily"),
        app_commands.Choice(name="Danh sách lệnh", value="commands"),
    ])
    async def guide(self, interaction: discord.Interaction, topic: app_commands.Choice[str] | None = None):
        key = topic.value if topic else "beginner"
        data = GUIDES.get(key, GUIDES["beginner"])
        embed = ui.basic_embed(data["title"], data["body"], discord.Color.blurple())
        embed.set_footer(text="Gợi ý: dùng /menu để chơi bằng button, /status để xem tình trạng hiện tại.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ping_rpg", description="Kiểm tra độ trễ và trạng thái bot")
    async def ping_rpg(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            embed=ui.basic_embed(
                "🏓 Pong",
                f"Bot latency: **{latency_ms}ms**\nFirebase/Firestore sẽ được kiểm tra khi bạn dùng các lệnh player như `/status` hoặc `/profile`.",
                discord.Color.green(),
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(QOL(bot))
