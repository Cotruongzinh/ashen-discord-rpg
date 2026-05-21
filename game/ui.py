import discord

from game.data import AREAS, BOSSES, CLASSES, ENEMIES, ITEMS
from game.models import CombatSession, Player
from game import combat, systems


RARITY_COLOR = {
    "common": discord.Color.light_grey(),
    "uncommon": discord.Color.green(),
    "rare": discord.Color.blue(),
    "epic": discord.Color.purple(),
    "legendary": discord.Color.gold(),
    "mythic": discord.Color.red(),
}

RARITY_ICON = {
    "common": "⚪",
    "uncommon": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟡",
    "mythic": "🔴",
}


def bar(current: int, maximum: int, width: int = 10) -> str:
    if maximum <= 0:
        return "░" * width

    ratio = max(0, min(1, current / maximum))
    filled = round(ratio * width)

    return "█" * filled + "░" * (width - filled)


def item_name(item) -> str:
    data = ITEMS[item.key]
    rarity = data.get("rarity", "common")

    plus = ""
    if data["type"] in ["weapon", "armor", "ring"] and item.upgrade > 0:
        plus = f" +{item.upgrade}"

    qty = ""
    if data["type"] in ["material", "consumable"]:
        qty = f" x{item.quantity}"

    lock = "🔒 " if item.locked else ""

    return f"{lock}{RARITY_ICON.get(rarity, '⚪')} {data['icon']} **{data['name']}{plus}**{qty}"


def basic_embed(title: str, description: str, color: discord.Color = discord.Color.dark_teal()) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="Ashen RPG • Discord fantasy text RPG")
    return embed


def result_embed(title: str, message: str, ok: bool = True) -> discord.Embed:
    return basic_embed(
        title=("✅ " if ok else "⚠️ ") + title,
        description=message,
        color=discord.Color.green() if ok else discord.Color.orange(),
    )


def profile_embed(player: Player) -> discord.Embed:
    cls = CLASSES.get(player.class_key, {"name": player.class_key, "icon": "🔥"})
    area = AREAS.get(player.area, {"name": player.area, "icon": "📍"})

    status_map = {
        "idle": "✅ Sẵn sàng",
        "resting": "🌙 Đang nghỉ",
        "combat": "⚔️ Đang chiến đấu",
    }

    embed = discord.Embed(
        title=f"{cls['icon']} {player.name} — Level {player.level} {cls['name']}",
        description=(
            f"{area['icon']} Area: **{area['name']}**\n"
            f"Status: **{status_map.get(player.status, player.status)}**"
        ),
        color=discord.Color.dark_teal(),
    )

    embed.add_field(
        name="❤️ HP",
        value=f"**{player.hp}/{player.max_hp}**\n`{bar(player.hp, player.max_hp)}`",
        inline=True,
    )

    embed.add_field(
        name="🟩 Stamina",
        value=f"**{player.stamina}/{player.max_stamina}**\n`{bar(player.stamina, player.max_stamina)}`",
        inline=True,
    )

    need = systems.xp_to_next(player.level)
    embed.add_field(
        name="⭐ XP",
        value=f"**{player.xp}/{need}**\n`{bar(player.xp, need)}`",
        inline=True,
    )

    embed.add_field(
        name="⚔️ Combat",
        value=(
            f"ATK: **{systems.total_attack(player)}**\n"
            f"DEF: **{systems.total_defense(player)}**\n"
            f"Crit: **{systems.total_crit(player)}%**"
        ),
        inline=True,
    )

    embed.add_field(
        name="💰 Currency",
        value=(
            f"💀 Souls: **{player.souls}**\n"
            f"🪙 Gold: **{player.gold}**\n"
            f"🧪 Flask: **{player.flask_charges}/{player.max_flask_charges}**"
        ),
        inline=True,
    )

    equipment_lines = []
    for label, item_id in [
        ("Weapon", player.equipped_weapon),
        ("Armor", player.equipped_armor),
        ("Ring", player.equipped_ring),
    ]:
        item = systems.get_item(player, item_id) if item_id else None
        if item:
            equipment_lines.append(f"**{label}:** `#{item.uid}` {item_name(item)}")
        else:
            equipment_lines.append(f"**{label}:** Empty")

    embed.add_field(
        name="🎒 Equipment",
        value="\n".join(equipment_lines),
        inline=False,
    )

    if player.death_echo_souls > 0:
        echo_area = AREAS.get(player.death_echo_area, {"name": player.death_echo_area})
        embed.add_field(
            name="☠️ Echo of Death",
            value=f"Bạn còn **{player.death_echo_souls} Souls** rơi tại **{echo_area['name']}**.",
            inline=False,
        )

    embed.set_footer(text="Gợi ý: /explore • /fight • /inventory • /rest • /merge")
    return embed


def inventory_embed(player: Player, item_type: str | None = None) -> discord.Embed:
    type_names = {
        None: "Tất cả",
        "weapon": "Vũ khí",
        "armor": "Giáp",
        "ring": "Nhẫn",
        "consumable": "Vật phẩm",
        "material": "Nguyên liệu",
    }

    embed = discord.Embed(
        title=f"🎒 Inventory — {type_names.get(item_type, 'Tất cả')}",
        color=discord.Color.blurple(),
    )

    items = player.inventory
    if item_type:
        items = [item for item in items if ITEMS[item.key]["type"] == item_type]

    if not items:
        embed.description = "Không có item thuộc loại này."
        return embed

    lines = []

    for item in items[:25]:
        equipped = ""
        if item.uid in [player.equipped_weapon, player.equipped_armor, player.equipped_ring]:
            equipped = " — **Đang trang bị**"

        stats = systems.item_stat_text(item)
        lines.append(f"`#{item.uid}` {item_name(item)}{equipped}\n└ {stats}")

    embed.description = "\n".join(lines)
    embed.set_footer(text="Dùng /equip item_id • /useitem item_id • /merge item_id • /dismantle item_id")
    return embed


def map_embed(player: Player) -> discord.Embed:
    embed = discord.Embed(
        title="🗺️ World Map",
        description="Các khu vực hiện có trong bản prototype.",
        color=discord.Color.dark_gold(),
    )

    for key, area in AREAS.items():
        opened = key in player.unlocked_areas
        mark = "✅" if opened else "❔"
        current = " — **Bạn đang ở đây**" if key == player.area else ""
        embed.add_field(
            name=f"{mark} {area['icon']} {area['name']}{current}",
            value=(
                f"Lv.{area['level']} • {area['desc']}\n"
                f"{'Đã mở khóa' if opened else 'Điều kiện: ' + area.get('unlock', '???')}"
            ),
            inline=False,
        )

    embed.set_footer(text="Dùng /travel để di chuyển.")
    return embed


def combat_embed(player: Player, session: CombatSession, title: str | None = None, message: str | None = None) -> discord.Embed:
    enemy = BOSSES[session.enemy_key] if session.is_boss else ENEMIES[session.enemy_key]
    area = AREAS.get(session.area, {"name": session.area, "icon": "📍"})
    color = discord.Color.red() if session.is_boss else discord.Color.orange()

    embed = discord.Embed(
        title=title or f"{'👑 Boss' if session.is_boss else '⚔️ Combat'} — {enemy['icon']} {enemy['name']}",
        description=message or f"{area['icon']} **{area['name']}** • Turn **{session.turn}**",
        color=color,
    )

    embed.add_field(
        name=f"{enemy['icon']} {enemy['name']}",
        value=f"HP: **{max(0, session.enemy_hp)}/{session.enemy_max_hp}**\n`{bar(max(0, session.enemy_hp), session.enemy_max_hp)}`",
        inline=False,
    )

    embed.add_field(
        name="❤️ Bạn",
        value=f"HP: **{player.hp}/{player.max_hp}**\n`{bar(player.hp, player.max_hp)}`",
        inline=True,
    )

    embed.add_field(
        name="🟩 Stamina",
        value=f"**{player.stamina}/{player.max_stamina}**\n`{bar(player.stamina, player.max_stamina)}`",
        inline=True,
    )

    embed.add_field(
        name="⚔️ Stats",
        value=(
            f"ATK **{systems.total_attack(player)}**\n"
            f"DEF **{systems.total_defense(player)}**\n"
            f"Crit **{systems.total_crit(player)}%**"
        ),
        inline=True,
    )

    warning = combat.boss_warning(session)
    if warning:
        embed.add_field(name="⚠️ Cảnh báo", value=warning, inline=False)

    if session.log:
        embed.add_field(
            name="📜 Diễn biến",
            value="\n".join(session.log[-6:]),
            inline=False,
        )

    embed.set_footer(text="Dùng button bên dưới để đánh theo lượt.")
    return embed

# ============================================================
# v0.4 UI EMBEDS
# ============================================================

from game.data import SHOP_ITEMS, DAILY_REWARD, DUNGEONS


def daily_embed(player: Player) -> discord.Embed:
    systems.ensure_player_runtime(player)
    today = systems.today_key()
    claimed = player.daily_claimed_date == today
    status = "✅ Đã nhận hôm nay" if claimed else "🎁 Chưa nhận hôm nay"

    reward_lines = [
        f"💀 Souls +{DAILY_REWARD.get('souls', 0)}",
        f"🪙 Gold +{DAILY_REWARD.get('gold', 0)}",
    ]
    for key, qty in DAILY_REWARD.get("items", {}).items():
        reward_lines.append(f"{ITEMS[key]['icon']} {ITEMS[key]['name']} x{qty}")

    embed = basic_embed(
        "🎁 Daily Reward",
        f"Trạng thái: **{status}**\n\nPhần thưởng hôm nay:\n" + "\n".join(reward_lines),
        discord.Color.gold(),
    )
    embed.set_footer(text="Dùng /daily để nhận. Daily reset theo UTC.")
    return embed


def quests_embed(player: Player) -> discord.Embed:
    systems.ensure_player_runtime(player)
    systems.refresh_daily_quests(player)

    embed = discord.Embed(
        title="📜 Daily Quests",
        description="Hoàn thành nhiệm vụ mỗi ngày để nhận thêm tài nguyên.",
        color=discord.Color.purple(),
    )

    for quest in player.daily_quests:
        progress = int(quest.get("progress", 0))
        target = int(quest.get("target", 1))
        claimed = quest.get("claimed", False)
        mark = "✅" if claimed else ("🎁" if progress >= target else "⏳")
        reward = []
        if quest.get("reward_souls"):
            reward.append(f"💀 {quest['reward_souls']}")
        if quest.get("reward_gold"):
            reward.append(f"🪙 {quest['reward_gold']}")
        for key, qty in quest.get("reward_items", {}).items():
            reward.append(f"{ITEMS[key]['icon']} {ITEMS[key]['name']} x{qty}")

        embed.add_field(
            name=f"{mark} {quest.get('name', 'Quest')}",
            value=(
                f"{quest.get('desc', '')}\n"
                f"Tiến trình: **{progress}/{target}** `{bar(progress, target)}`\n"
                f"Thưởng: {', '.join(reward) if reward else 'Không có'}"
            ),
            inline=False,
        )

    embed.set_footer(text="Dùng /claimquests để nhận thưởng quest đã hoàn thành.")
    return embed


def shop_embed(player: Player) -> discord.Embed:
    embed = discord.Embed(
        title="🛒 Merchant Nara's Shop",
        description=f"Bạn đang có 🪙 **{player.gold} Gold**. Dùng `/buy shop_id amount` để mua.",
        color=discord.Color.dark_gold(),
    )

    for entry in SHOP_ITEMS:
        item = ITEMS[entry["key"]]
        embed.add_field(
            name=f"#{entry['id']} {item['icon']} {item['name']} x{entry.get('quantity', 1)}",
            value=f"Giá: **{entry['gold']} Gold** • {entry.get('label', item.get('desc', ''))}",
            inline=False,
        )

    embed.set_footer(text="Dùng /sell item_id để bán item không dùng nữa.")
    return embed


def dungeon_embed(player: Player) -> discord.Embed:
    systems.reset_dungeon_runs_if_needed(player)
    embed = discord.Embed(
        title="🏰 Dungeons",
        description=f"Lượt hôm nay: **{player.dungeon_runs_used}/3**. Dùng `/dungeon dungeon_id` để vào.",
        color=discord.Color.dark_red(),
    )

    for key, dungeon in DUNGEONS.items():
        opened = dungeon.get("area") in player.unlocked_areas
        mark = "✅" if opened else "🔒"
        embed.add_field(
            name=f"{mark} `{key}` {dungeon['icon']} {dungeon['name']}",
            value=(
                f"Lv.{dungeon.get('level', 1)} • {dungeon['desc']}\n"
                f"Bonus: 💀 +{dungeon.get('bonus_souls', 0)}, 🪙 +{dungeon.get('bonus_gold', 0)}"
            ),
            inline=False,
        )

    return embed


def leaderboard_embed(players: list[Player], metric: str) -> discord.Embed:
    labels = {
        "level": "Level",
        "souls": "Souls",
        "gold": "Gold",
        "kills": "Kills",
        "bosses": "Boss Kills",
        "dungeons": "Dungeon Clears",
    }
    label = labels.get(metric, "Level")

    def score(p: Player) -> int:
        systems.ensure_player_runtime(p)
        if metric in ["level", "souls", "gold"]:
            return int(getattr(p, metric, 0))
        return int(p.stats.get(metric, 0))

    ranked = sorted(players, key=score, reverse=True)[:10]
    lines = []
    for idx, p in enumerate(ranked, 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"`{idx}.`"
        lines.append(f"{medal} **{p.name}** — {label}: **{score(p)}**")

    embed = discord.Embed(
        title=f"🏆 Leaderboard — {label}",
        description="\n".join(lines) if lines else "Chưa có dữ liệu.",
        color=discord.Color.gold(),
    )
    embed.set_footer(text="Metric: level, souls, gold, kills, bosses, dungeons")
    return embed
