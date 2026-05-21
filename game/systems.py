import random
import time
from dataclasses import dataclass
from typing import Optional

from game.data import ITEMS, UPGRADE_RULES
from game.models import Player, InventoryItem


REST_SECONDS_PER_MISSING_HP = 5
REST_MIN_SECONDS = 30
REST_MAX_SECONDS = 900


@dataclass
class ActionResult:
    ok: bool
    title: str
    message: str


def xp_to_next(level: int) -> int:
    return 80 + (level - 1) * 45


def get_item(player: Player, item_id: int) -> Optional[InventoryItem]:
    for item in player.inventory:
        if item.uid == item_id:
            return item
    return None


def add_item(player: Player, key: str, quantity: int = 1, upgrade: int = 0) -> InventoryItem:
    item_type = ITEMS[key]["type"]

    if item_type in ["material", "consumable"] and upgrade == 0:
        for item in player.inventory:
            if item.key == key and item.upgrade == 0:
                item.quantity += quantity
                return item

    item = InventoryItem(
        uid=player.next_uid,
        key=key,
        quantity=quantity,
        upgrade=upgrade,
    )
    player.next_uid += 1
    player.inventory.append(item)
    return item


def remove_stack_item(player: Player, key: str, quantity: int) -> bool:
    for item in list(player.inventory):
        if item.key == key and item.upgrade == 0:
            if item.quantity < quantity:
                return False

            item.quantity -= quantity
            if item.quantity <= 0:
                player.inventory.remove(item)

            return True

    return False


def count_item(player: Player, key: str) -> int:
    return sum(
        item.quantity
        for item in player.inventory
        if item.key == key and item.upgrade == 0
    )


def roll_loot(player: Player, loot_table: list) -> list[str]:
    found = []

    for key, chance, min_qty, max_qty in loot_table:
        if random.random() <= chance:
            qty = random.randint(min_qty, max_qty)
            item = add_item(player, key, qty)

            if ITEMS[key]["type"] in ["material", "consumable"]:
                found.append(f"{ITEMS[key]['icon']} {ITEMS[key]['name']} x{qty}")
            else:
                found.append(f"`#{item.uid}` {ITEMS[key]['icon']} {ITEMS[key]['name']}")

    return found


def scaled_stat(item: InventoryItem, stat: str) -> int:
    base = ITEMS[item.key].get(stat, 0)
    if base <= 0:
        return 0
    return int(round(base * (1 + item.upgrade * 0.12)))


def equipment_items(player: Player) -> list[InventoryItem]:
    equipped_ids = {
        player.equipped_weapon,
        player.equipped_armor,
        player.equipped_ring,
    }

    return [
        item for item in player.inventory
        if item.uid in equipped_ids
    ]


def total_attack(player: Player) -> int:
    return player.attack + sum(scaled_stat(item, "attack") for item in equipment_items(player))


def total_defense(player: Player) -> int:
    return player.defense + sum(scaled_stat(item, "defense") for item in equipment_items(player))


def total_crit(player: Player) -> int:
    return min(60, player.crit + sum(scaled_stat(item, "crit") for item in equipment_items(player)))


def item_stat_text(item: InventoryItem) -> str:
    data = ITEMS[item.key]
    bits = []

    atk = scaled_stat(item, "attack")
    dfs = scaled_stat(item, "defense")
    crt = scaled_stat(item, "crit")

    if atk:
        bits.append(f"ATK +{atk}")
    if dfs:
        bits.append(f"DEF +{dfs}")
    if crt:
        bits.append(f"Crit +{crt}%")
    if data.get("heal"):
        bits.append(f"Hồi {data['heal']} HP")
    if data.get("heal_percent"):
        bits.append(f"Hồi {int(data['heal_percent'] * 100)}% HP")

    return ", ".join(bits) if bits else data.get("desc", "")


def level_up_if_needed(player: Player) -> list[str]:
    messages = []

    while player.xp >= xp_to_next(player.level):
        need = xp_to_next(player.level)
        player.xp -= need
        player.level += 1

        hp_gain = 8 + int(player.level * 1.4)
        st_gain = 4 + int(player.level * 0.8)
        atk_gain = 2 if player.level % 2 == 0 else 1
        def_gain = 1
        crit_gain = 1 if player.level % 4 == 0 else 0

        player.max_hp += hp_gain
        player.max_stamina += st_gain
        player.attack += atk_gain
        player.defense += def_gain
        player.crit += crit_gain
        player.hp = player.max_hp
        player.stamina = player.max_stamina

        messages.append(
            f"✨ **Lên level {player.level}!** HP +{hp_gain}, Stamina +{st_gain}, ATK +{atk_gain}, DEF +{def_gain}."
        )

    return messages


def equip_item(player: Player, item_id: int) -> ActionResult:
    item = get_item(player, item_id)

    if not item:
        return ActionResult(False, "Không tìm thấy item", "Item ID này không nằm trong túi đồ của bạn.")

    data = ITEMS[item.key]

    if data["type"] == "weapon":
        player.equipped_weapon = item.uid
    elif data["type"] == "armor":
        player.equipped_armor = item.uid
    elif data["type"] == "ring":
        player.equipped_ring = item.uid
    else:
        return ActionResult(False, "Không thể trang bị", "Chỉ vũ khí, giáp và nhẫn mới có thể trang bị.")

    return ActionResult(True, "Đã trang bị", f"Bạn đã trang bị {data['icon']} **{data['name']}**.")


def use_item(player: Player, item_id: int) -> ActionResult:
    item = get_item(player, item_id)

    if not item:
        return ActionResult(False, "Không tìm thấy item", "Item ID này không nằm trong túi đồ của bạn.")

    data = ITEMS[item.key]

    if data["type"] != "consumable":
        return ActionResult(False, "Không thể dùng", "Item này không phải vật phẩm tiêu hao.")

    if player.hp >= player.max_hp:
        return ActionResult(False, "HP đã đầy", "Bạn không cần hồi máu lúc này.")

    if item.key == "ember_flask":
        if player.flask_charges <= 0:
            return ActionResult(False, "Flask đã cạn", "Hãy nghỉ ngơi để nạp lại Ember Flask.")

        heal = int(player.max_hp * data.get("heal_percent", 0.4))
        player.flask_charges -= 1
    else:
        heal = data.get("heal", 0)
        item.quantity -= 1
        if item.quantity <= 0:
            player.inventory.remove(item)

    old_hp = player.hp
    player.hp = min(player.max_hp, player.hp + heal)
    healed = player.hp - old_hp

    return ActionResult(True, "Đã hồi máu", f"Bạn hồi **{healed} HP**.")


def start_rest(player: Player) -> ActionResult:
    if player.status == "resting":
        return ActionResult(False, "Đang nghỉ rồi", "Bạn đang nghỉ ngơi. Dùng `/checkrest` để kiểm tra.")

    missing_hp = player.max_hp - player.hp
    missing_stamina = player.max_stamina - player.stamina

    if missing_hp <= 0 and missing_stamina <= 0 and player.flask_charges >= player.max_flask_charges:
        return ActionResult(False, "Không cần nghỉ", "HP, stamina và flask của bạn đều đã đầy.")

    wait_seconds = min(
        max(missing_hp * REST_SECONDS_PER_MISSING_HP, REST_MIN_SECONDS),
        REST_MAX_SECONDS,
    )

    if missing_hp <= 0:
        wait_seconds = REST_MIN_SECONDS

    player.status = "resting"
    player.rest_start_time = time.time()
    player.rest_end_time = player.rest_start_time + wait_seconds
    player.rest_start_hp = player.hp
    player.rest_start_stamina = player.stamina

    return ActionResult(
        True,
        "Bắt đầu nghỉ ngơi",
        (
            f"HP hiện tại: **{player.hp}/{player.max_hp}**\n"
            f"Stamina hiện tại: **{player.stamina}/{player.max_stamina}**\n"
            f"Máu đã mất: **{missing_hp}**\n"
            f"Thời gian nghỉ: **{int(wait_seconds)} giây**"
        ),
    )


def check_rest(player: Player) -> ActionResult:
    if player.status != "resting":
        return ActionResult(False, "Không đang nghỉ", "Bạn hiện không ở trạng thái nghỉ ngơi.")

    now = time.time()

    if player.rest_end_time and now >= player.rest_end_time:
        player.hp = player.max_hp
        player.stamina = player.max_stamina
        player.flask_charges = player.max_flask_charges
        player.status = "idle"
        player.rest_start_time = None
        player.rest_end_time = None
        player.rest_start_hp = None
        player.rest_start_stamina = None

        return ActionResult(True, "Nghỉ xong", "🔥 Bạn đã hồi đầy HP, stamina và Ember Flask.")

    remaining = int(player.rest_end_time - now)
    return ActionResult(False, "Vẫn đang nghỉ", f"Bạn còn phải nghỉ **{remaining} giây**.")


def cancel_rest(player: Player) -> ActionResult:
    if player.status != "resting":
        return ActionResult(False, "Không đang nghỉ", "Bạn hiện không ở trạng thái nghỉ ngơi.")

    now = time.time()
    start_hp = player.rest_start_hp or player.hp
    start_stamina = player.rest_start_stamina or player.stamina
    start_time = player.rest_start_time or now
    end_time = player.rest_end_time or now
    total = max(1, end_time - start_time)
    elapsed = max(0, now - start_time)
    ratio = min(1, elapsed / total)

    player.hp = min(player.max_hp, int(start_hp + (player.max_hp - start_hp) * ratio))
    player.stamina = min(player.max_stamina, int(start_stamina + (player.max_stamina - start_stamina) * ratio))
    player.status = "idle"
    player.rest_start_time = None
    player.rest_end_time = None
    player.rest_start_hp = None
    player.rest_start_stamina = None

    return ActionResult(True, "Đã hủy nghỉ", f"Bạn rời ngọn lửa sớm.\nHP hiện tại: **{player.hp}/{player.max_hp}**")


def upgrade_item(player: Player, item_id: int) -> ActionResult:
    item = get_item(player, item_id)

    if not item:
        return ActionResult(False, "Không tìm thấy item", "Item ID này không nằm trong túi đồ của bạn.")

    data = ITEMS[item.key]

    if data["type"] not in ["weapon", "armor", "ring"]:
        return ActionResult(False, "Không thể merge", "Chỉ vũ khí, giáp và nhẫn mới có thể nâng cấp.")

    if item.locked:
        return ActionResult(False, "Item đang khóa", "Hãy dùng `/lockitem` để mở khóa trước.")

    next_level = item.upgrade + 1

    if next_level not in UPGRADE_RULES:
        return ActionResult(False, "Đã đạt giới hạn", "Bản hiện tại hỗ trợ nâng cấp đến +5.")

    rule = UPGRADE_RULES[next_level]

    if player.souls < rule["souls"]:
        return ActionResult(False, "Thiếu Souls", f"Bạn cần **{rule['souls']} Souls**.")

    missing = []
    for mat_key, qty in rule["materials"].items():
        have = count_item(player, mat_key)
        if have < qty:
            missing.append(f"{ITEMS[mat_key]['icon']} {ITEMS[mat_key]['name']} x{qty - have}")

    if missing:
        return ActionResult(False, "Thiếu nguyên liệu", "Bạn còn thiếu:\n" + "\n".join(missing))

    player.souls -= rule["souls"]

    for mat_key, qty in rule["materials"].items():
        remove_stack_item(player, mat_key, qty)

    if random.random() <= rule["chance"]:
        item.upgrade = next_level
        return ActionResult(True, "Merge thành công", f"{data['icon']} **{data['name']}** đã lên **+{next_level}**.")

    return ActionResult(False, "Merge thất bại", "Nguyên liệu và Souls đã mất, nhưng trang bị không bị phá hủy.")


def dismantle_item(player: Player, item_id: int) -> ActionResult:
    item = get_item(player, item_id)

    if not item:
        return ActionResult(False, "Không tìm thấy item", "Item ID này không nằm trong túi đồ của bạn.")

    if item.locked:
        return ActionResult(False, "Item đang khóa", "Không thể phân rã item đang khóa.")

    if item.uid in [player.equipped_weapon, player.equipped_armor, player.equipped_ring]:
        return ActionResult(False, "Đang trang bị", "Không thể phân rã item đang trang bị.")

    data = ITEMS[item.key]

    if data["type"] not in ["weapon", "armor", "ring"]:
        return ActionResult(False, "Không thể phân rã", "Bản hiện tại chỉ phân rã trang bị.")

    rarity = data.get("rarity", "common")

    rewards = []
    if rarity in ["common", "uncommon"]:
        qty = 1 + item.upgrade
        add_item(player, "iron_shard", qty)
        rewards.append(f"⛓️ Iron Shard x{qty}")
    elif rarity == "rare":
        qty = 1 + item.upgrade // 2
        add_item(player, "ember_stone", qty)
        rewards.append(f"🔥 Ember Stone x{qty}")
    else:
        add_item(player, "ancient_core", 1)
        rewards.append("💠 Ancient Core x1")

    gold = 5 + item.upgrade * 5
    player.gold += gold
    rewards.append(f"🪙 Gold +{gold}")

    player.inventory.remove(item)

    return ActionResult(True, "Đã phân rã", "Bạn nhận được:\n" + "\n".join(rewards))


def toggle_lock_item(player: Player, item_id: int) -> ActionResult:
    item = get_item(player, item_id)

    if not item:
        return ActionResult(False, "Không tìm thấy item", "Item ID này không nằm trong túi đồ của bạn.")

    item.locked = not item.locked
    state = "khóa" if item.locked else "mở khóa"

    return ActionResult(True, "Đã cập nhật", f"Item đã được **{state}**.")

# ============================================================
# v0.4 DAILY / QUEST / SHOP / DUNGEON SYSTEMS
# ============================================================

from datetime import datetime, timezone
from game.data import DAILY_REWARD, DAILY_QUEST_TEMPLATES, SHOP_ITEMS, DUNGEONS


def today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def ensure_player_runtime(player: Player) -> None:
    """Đảm bảo player cũ từ Firestore có đủ field mới."""
    if player.stats is None:
        player.stats = {}

    defaults = {
        "kills": 0,
        "bosses": 0,
        "explores": 0,
        "dungeons": 0,
        "deaths": 0,
        "merges": 0,
        "daily_claims": 0,
        "quests_claimed": 0,
    }
    for key, value in defaults.items():
        player.stats.setdefault(key, value)

    if player.daily_quests is None:
        player.daily_quests = []


def refresh_daily_quests(player: Player) -> None:
    ensure_player_runtime(player)
    today = today_key()

    if player.daily_quests_date == today and player.daily_quests:
        return

    # Chọn 3 quest đầu cho ổn định. Sau này có thể random theo seed ngày.
    quests = []
    for tpl in DAILY_QUEST_TEMPLATES[:3]:
        quest = dict(tpl)
        quest["progress"] = 0
        quest["claimed"] = False
        quests.append(quest)

    player.daily_quests_date = today
    player.daily_quests = quests


def update_quest_progress(player: Player, quest_type: str, amount: int = 1) -> list[str]:
    ensure_player_runtime(player)
    refresh_daily_quests(player)
    completed = []

    for quest in player.daily_quests:
        if quest.get("type") != quest_type or quest.get("claimed"):
            continue

        old_progress = int(quest.get("progress", 0))
        target = int(quest.get("target", 1))
        quest["progress"] = min(target, old_progress + amount)

        if old_progress < target and quest["progress"] >= target:
            completed.append(quest.get("name", "Daily Quest"))

    return completed


def claim_daily_reward(player: Player) -> ActionResult:
    ensure_player_runtime(player)
    today = today_key()

    if player.daily_claimed_date == today:
        return ActionResult(False, "Đã nhận daily", "Bạn đã nhận thưởng daily hôm nay rồi.")

    player.daily_claimed_date = today
    player.souls += DAILY_REWARD.get("souls", 0)
    player.gold += DAILY_REWARD.get("gold", 0)

    reward_lines = [
        f"💀 Souls +{DAILY_REWARD.get('souls', 0)}",
        f"🪙 Gold +{DAILY_REWARD.get('gold', 0)}",
    ]

    for key, qty in DAILY_REWARD.get("items", {}).items():
        add_item(player, key, qty)
        reward_lines.append(f"{ITEMS[key]['icon']} {ITEMS[key]['name']} x{qty}")

    player.stats["daily_claims"] = player.stats.get("daily_claims", 0) + 1
    refresh_daily_quests(player)

    return ActionResult(True, "Daily reward", "Bạn nhận được:\n" + "\n".join(reward_lines))


def claim_completed_quests(player: Player) -> ActionResult:
    ensure_player_runtime(player)
    refresh_daily_quests(player)

    claimed_any = False
    lines = []

    for quest in player.daily_quests:
        if quest.get("claimed"):
            continue

        progress = int(quest.get("progress", 0))
        target = int(quest.get("target", 1))
        if progress < target:
            continue

        quest["claimed"] = True
        claimed_any = True

        souls = int(quest.get("reward_souls", 0))
        gold = int(quest.get("reward_gold", 0))
        player.souls += souls
        player.gold += gold

        lines.append(f"✅ **{quest.get('name', 'Quest')}**")
        if souls:
            lines.append(f"└ 💀 Souls +{souls}")
        if gold:
            lines.append(f"└ 🪙 Gold +{gold}")

        for key, qty in quest.get("reward_items", {}).items():
            add_item(player, key, qty)
            lines.append(f"└ {ITEMS[key]['icon']} {ITEMS[key]['name']} x{qty}")

    if not claimed_any:
        return ActionResult(False, "Chưa có quest hoàn thành", "Bạn chưa có daily quest nào sẵn sàng nhận thưởng.")

    player.stats["quests_claimed"] = player.stats.get("quests_claimed", 0) + 1
    return ActionResult(True, "Đã nhận thưởng quest", "\n".join(lines))


def shop_item_by_id(shop_id: int) -> dict | None:
    for entry in SHOP_ITEMS:
        if entry["id"] == shop_id:
            return entry
    return None


def buy_shop_item(player: Player, shop_id: int, amount: int = 1) -> ActionResult:
    amount = max(1, min(20, amount))
    entry = shop_item_by_id(shop_id)

    if not entry:
        return ActionResult(False, "Không có món hàng", "Shop không có item ID này.")

    total_cost = entry["gold"] * amount
    if player.gold < total_cost:
        return ActionResult(False, "Thiếu Gold", f"Bạn cần **{total_cost} Gold** nhưng chỉ có **{player.gold}**.")

    key = entry["key"]
    qty = entry.get("quantity", 1) * amount
    player.gold -= total_cost
    add_item(player, key, qty)

    return ActionResult(
        True,
        "Đã mua",
        f"Bạn mua **{ITEMS[key]['icon']} {ITEMS[key]['name']} x{qty}** với **{total_cost} Gold**.",
    )


def item_sell_value(item: InventoryItem) -> int:
    rarity = ITEMS[item.key].get("rarity", "common")
    base = {
        "common": 8,
        "uncommon": 18,
        "rare": 45,
        "epic": 110,
        "legendary": 300,
        "mythic": 600,
    }.get(rarity, 8)

    if ITEMS[item.key]["type"] in ["material", "consumable"]:
        return max(1, base // 2) * item.quantity

    return base + item.upgrade * 15


def sell_item(player: Player, item_id: int) -> ActionResult:
    item = get_item(player, item_id)

    if not item:
        return ActionResult(False, "Không tìm thấy item", "Item ID này không nằm trong túi đồ của bạn.")

    if item.locked:
        return ActionResult(False, "Item đang khóa", "Không thể bán item đang khóa.")

    if item.uid in [player.equipped_weapon, player.equipped_armor, player.equipped_ring]:
        return ActionResult(False, "Đang trang bị", "Không thể bán item đang trang bị.")

    data = ITEMS[item.key]
    value = item_sell_value(item)
    player.gold += value
    player.inventory.remove(item)

    return ActionResult(True, "Đã bán item", f"Bạn bán {data['icon']} **{data['name']}** và nhận **{value} Gold**.")


def reset_dungeon_runs_if_needed(player: Player) -> None:
    today = today_key()
    if player.dungeon_runs_date != today:
        player.dungeon_runs_date = today
        player.dungeon_runs_used = 0


def available_dungeons(player: Player) -> list[tuple[str, dict]]:
    result = []
    for key, dungeon in DUNGEONS.items():
        required_area = dungeon.get("area")
        if required_area in player.unlocked_areas:
            result.append((key, dungeon))
    return result


def can_start_dungeon(player: Player, dungeon_key: str) -> ActionResult:
    reset_dungeon_runs_if_needed(player)

    if player.status != "idle":
        return ActionResult(False, "Bạn đang bận", "Bạn chỉ có thể vào dungeon khi đang rảnh.")

    if player.dungeon_runs_used >= 3:
        return ActionResult(False, "Hết lượt dungeon", "Bạn đã dùng hết 3 lượt dungeon hôm nay.")

    dungeon = DUNGEONS.get(dungeon_key)
    if not dungeon:
        return ActionResult(False, "Không tìm thấy dungeon", "Dungeon ID này không tồn tại.")

    if dungeon.get("area") not in player.unlocked_areas:
        return ActionResult(False, "Chưa mở khóa", "Bạn chưa mở khu vực yêu cầu cho dungeon này.")

    if player.level < dungeon.get("level", 1):
        return ActionResult(False, "Level chưa đủ", f"Dungeon này yêu cầu level {dungeon.get('level', 1)}.")

    if player.stamina < 15:
        return ActionResult(False, "Thiếu stamina", "Bạn cần ít nhất 15 stamina để vào dungeon.")

    return ActionResult(True, "Có thể vào dungeon", "Bạn có thể bắt đầu dungeon encounter.")


# Override use_item để hỗ trợ stamina_draught và camp_kit ở v0.4.
def use_item(player: Player, item_id: int) -> ActionResult:
    item = get_item(player, item_id)

    if not item:
        return ActionResult(False, "Không tìm thấy item", "Item ID này không nằm trong túi đồ của bạn.")

    data = ITEMS[item.key]

    if data["type"] != "consumable":
        return ActionResult(False, "Không thể dùng", "Item này không phải vật phẩm tiêu hao.")

    heal_hp = 0
    heal_stamina = 0
    consume_stack = item.key != "ember_flask"

    if item.key == "ember_flask":
        if player.flask_charges <= 0:
            return ActionResult(False, "Flask đã cạn", "Hãy nghỉ ngơi để nạp lại Ember Flask.")
        heal_hp = int(player.max_hp * data.get("heal_percent", 0.4))
        player.flask_charges -= 1
    else:
        heal_hp += int(data.get("heal", 0))
        heal_stamina += int(data.get("stamina", 0))
        if data.get("heal_percent"):
            heal_hp += int(player.max_hp * data.get("heal_percent"))
        if data.get("stamina_percent"):
            heal_stamina += int(player.max_stamina * data.get("stamina_percent"))

    if heal_hp <= 0 and heal_stamina <= 0:
        return ActionResult(False, "Không thể dùng", "Vật phẩm này chưa có hiệu ứng sử dụng trực tiếp.")

    if player.hp >= player.max_hp and player.stamina >= player.max_stamina:
        return ActionResult(False, "Đã đầy", "HP và stamina của bạn đều đã đầy.")

    old_hp = player.hp
    old_stamina = player.stamina
    player.hp = min(player.max_hp, player.hp + heal_hp)
    player.stamina = min(player.max_stamina, player.stamina + heal_stamina)

    if consume_stack:
        item.quantity -= 1
        if item.quantity <= 0:
            player.inventory.remove(item)

    hp_gained = player.hp - old_hp
    st_gained = player.stamina - old_stamina
    parts = []
    if hp_gained:
        parts.append(f"❤️ HP +{hp_gained}")
    if st_gained:
        parts.append(f"🟩 Stamina +{st_gained}")

    return ActionResult(True, "Đã dùng vật phẩm", "Bạn hồi " + ", ".join(parts) + ".")


# Override upgrade_item để daily quest merge có tiến trình.
def upgrade_item(player: Player, item_id: int) -> ActionResult:
    item = get_item(player, item_id)

    if not item:
        return ActionResult(False, "Không tìm thấy item", "Item ID này không nằm trong túi đồ của bạn.")

    data = ITEMS[item.key]

    if data["type"] not in ["weapon", "armor", "ring"]:
        return ActionResult(False, "Không thể merge", "Chỉ vũ khí, giáp và nhẫn mới có thể nâng cấp.")

    if item.locked:
        return ActionResult(False, "Item đang khóa", "Hãy dùng `/lockitem` để mở khóa trước.")

    next_level = item.upgrade + 1

    if next_level not in UPGRADE_RULES:
        return ActionResult(False, "Đã đạt giới hạn", "Bản hiện tại hỗ trợ nâng cấp đến +5.")

    rule = UPGRADE_RULES[next_level]

    if player.souls < rule["souls"]:
        return ActionResult(False, "Thiếu Souls", f"Bạn cần **{rule['souls']} Souls**.")

    missing = []
    for mat_key, qty in rule["materials"].items():
        have = count_item(player, mat_key)
        if have < qty:
            missing.append(f"{ITEMS[mat_key]['icon']} {ITEMS[mat_key]['name']} x{qty - have}")

    if missing:
        return ActionResult(False, "Thiếu nguyên liệu", "Bạn còn thiếu:\n" + "\n".join(missing))

    player.souls -= rule["souls"]

    for mat_key, qty in rule["materials"].items():
        remove_stack_item(player, mat_key, qty)

    ensure_player_runtime(player)
    player.stats["merges"] = player.stats.get("merges", 0) + 1
    update_quest_progress(player, "merge", 1)

    if random.random() <= rule["chance"]:
        item.upgrade = next_level
        return ActionResult(True, "Merge thành công", f"{data['icon']} **{data['name']}** đã lên **+{next_level}**.")

    return ActionResult(False, "Merge thất bại", "Nguyên liệu và Souls đã mất, nhưng trang bị không bị phá hủy.")
