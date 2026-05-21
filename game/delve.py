"""
Ashen RPG v0.6 — Multi-room dungeon / delve system.
This module is intentionally additive: it uses its own Firestore collection
and does not require changing the existing Player model.
"""

from __future__ import annotations

import math
import random
import time
from typing import Any, Optional

from game.data import AREAS, BOSSES, ENEMIES, ITEMS
from game.firebase_client import get_firestore_client
from game.models import InventoryItem, Player
from game.storage import get_player, save_player

RUNS_COLLECTION = "dungeon_runs"

DELVE_DUNGEONS: dict[str, dict[str, Any]] = {
    "grave_trial": {
        "name": "Trial of the Forgotten Grave",
        "icon": "🪦",
        "area": "forgotten_catacomb",
        "min_level": 1,
        "rooms": 5,
        "stamina_cost": 18,
        "entry_souls": 0,
        "enemies": ["hollow_rat", "grave_skeleton", "hollow_soldier", "ash_hound"],
        "boss": "keeper_first_grave",
        "bonus_souls": 160,
        "bonus_gold": 55,
        "bonus_loot": [("iron_shard", 1.00, 2, 4), ("ember_stone", 0.35, 1, 1)],
        "description": "Một chuỗi hầm mộ ngắn với bẫy, rương cũ và tiếng chuông bên dưới đá.",
    },
    "blackroot_depths": {
        "name": "Blackroot Depths",
        "icon": "🌲",
        "area": "blackroot_forest",
        "min_level": 4,
        "rooms": 6,
        "stamina_cost": 24,
        "entry_souls": 80,
        "enemies": ["thorn_wolf", "lost_hunter", "root_witch"],
        "boss": "weeping_treant",
        "bonus_souls": 360,
        "bonus_gold": 120,
        "bonus_loot": [("blackroot_leaf", 1.00, 3, 6), ("ember_stone", 0.65, 1, 2), ("ancient_core", 0.18, 1, 1)],
        "description": "Lối sâu dưới rừng đen, nơi rễ cây mọc qua xương và máu khô.",
    },
}


def get_dungeon_run(user_id: int) -> Optional[dict[str, Any]]:
    db = get_firestore_client()
    doc = db.collection(RUNS_COLLECTION).document(str(user_id)).get()
    if not doc.exists:
        return None
    return doc.to_dict()


def save_dungeon_run(user_id: int, run: dict[str, Any]) -> None:
    db = get_firestore_client()
    db.collection(RUNS_COLLECTION).document(str(user_id)).set(run)


def delete_dungeon_run(user_id: int) -> None:
    db = get_firestore_client()
    db.collection(RUNS_COLLECTION).document(str(user_id)).delete()


def player_unlocked_areas(player: Player) -> list[str]:
    value = getattr(player, "unlocked_areas", None)
    if isinstance(value, list):
        return value
    return ["ember_shrine", "forgotten_catacomb"]


def ensure_player_runtime_fields(player: Player) -> None:
    # dataclasses without slots accept runtime attributes; save_player will only persist
    # declared fields, but recent patches include these fields. This keeps old players safe.
    if not hasattr(player, "unlocked_areas") or not isinstance(getattr(player, "unlocked_areas"), list):
        setattr(player, "unlocked_areas", ["ember_shrine", "forgotten_catacomb"])
    if not hasattr(player, "stats") or not isinstance(getattr(player, "stats"), dict):
        setattr(player, "stats", {})
    if not hasattr(player, "death_echo_souls"):
        setattr(player, "death_echo_souls", 0)
    if not hasattr(player, "death_echo_area"):
        setattr(player, "death_echo_area", None)


def add_stat(player: Player, key: str, amount: int = 1) -> None:
    ensure_player_runtime_fields(player)
    if isinstance(getattr(player, "stats", None), dict):
        player.stats[key] = int(player.stats.get(key, 0)) + amount


def give_item(player: Player, key: str, quantity: int = 1, upgrade: int = 0) -> InventoryItem:
    item_type = ITEMS[key]["type"]
    if item_type in ["material", "consumable"] and upgrade == 0:
        for item in player.inventory:
            if item.key == key and item.upgrade == 0:
                item.quantity += quantity
                return item

    item = InventoryItem(uid=player.next_uid, key=key, quantity=quantity, upgrade=upgrade)
    player.next_uid += 1
    player.inventory.append(item)
    return item


def roll_loot(player: Player, loot_table: list[tuple[str, float, int, int]]) -> list[str]:
    found: list[str] = []
    for key, chance, min_qty, max_qty in loot_table:
        if key not in ITEMS:
            continue
        if random.random() <= chance:
            qty = random.randint(min_qty, max_qty)
            item = give_item(player, key, qty)
            if ITEMS[key]["type"] in ["material", "consumable"]:
                found.append(f"{ITEMS[key]['icon']} {ITEMS[key]['name']} x{qty}")
            else:
                found.append(f"`#{item.uid}` {ITEMS[key]['icon']} {ITEMS[key]['name']}")
    return found


def start_dungeon_run(user_id: int, dungeon_id: str) -> tuple[bool, str, Optional[dict[str, Any]]]:
    player = get_player(user_id)
    if not player:
        return False, "Bạn chưa có nhân vật. Dùng `/start` trước.", None

    ensure_player_runtime_fields(player)

    if dungeon_id not in DELVE_DUNGEONS:
        return False, "Dungeon không tồn tại.", None

    existing = get_dungeon_run(user_id)
    if existing:
        return False, "Bạn đang ở trong một dungeon run khác. Dùng `/delvestatus` để tiếp tục hoặc `/abandonrun` để rút lui.", existing

    dungeon = DELVE_DUNGEONS[dungeon_id]

    if player.level < dungeon["min_level"]:
        return False, f"Bạn cần level {dungeon['min_level']} để vào dungeon này.", None

    if dungeon["area"] not in player_unlocked_areas(player):
        area_name = AREAS.get(dungeon["area"], {}).get("name", dungeon["area"])
        return False, f"Bạn chưa mở khóa khu vực **{area_name}**.", None

    if getattr(player, "status", "idle") == "resting":
        return False, "Bạn đang nghỉ ngơi. Hãy `/checkrest` trước.", None

    if player.stamina < dungeon["stamina_cost"]:
        return False, f"Bạn cần {dungeon['stamina_cost']} stamina để vào dungeon này.", None

    if player.souls < dungeon["entry_souls"]:
        return False, f"Bạn cần {dungeon['entry_souls']} Souls để mở lối vào.", None

    player.stamina -= dungeon["stamina_cost"]
    player.souls -= dungeon["entry_souls"]
    player.status = "dungeon"
    save_player(player)

    run = {
        "user_id": user_id,
        "dungeon_id": dungeon_id,
        "room": 0,
        "max_rooms": dungeon["rooms"],
        "started_at": int(time.time()),
        "updated_at": int(time.time()),
        "banked_souls": 0,
        "banked_gold": 0,
        "cleared": False,
        "last_event": "Bạn bước qua cổng đá. Không khí lạnh tràn vào phổi.",
    }
    save_dungeon_run(user_id, run)
    return True, "Dungeon run đã bắt đầu.", run


def abandon_dungeon_run(user_id: int) -> tuple[bool, str]:
    player = get_player(user_id)
    run = get_dungeon_run(user_id)
    if not player or not run:
        return False, "Bạn không ở trong dungeon run nào."

    keep_souls = int(run.get("banked_souls", 0) * 0.45)
    keep_gold = int(run.get("banked_gold", 0) * 0.45)
    player.souls += keep_souls
    player.gold += keep_gold
    player.status = "idle"
    save_player(player)
    delete_dungeon_run(user_id)
    return True, f"Bạn rút lui khỏi dungeon và giữ lại 💀 **{keep_souls} Souls**, 🪙 **{keep_gold} Gold**."


def short_rest_in_dungeon(user_id: int) -> tuple[bool, str, Optional[dict[str, Any]]]:
    player = get_player(user_id)
    run = get_dungeon_run(user_id)
    if not player or not run:
        return False, "Bạn không ở trong dungeon run nào.", None

    cost_gold = 25 + run.get("room", 0) * 10
    if player.gold < cost_gold:
        return False, f"Bạn cần {cost_gold} Gold để dựng trại ngắn trong dungeon.", run

    player.gold -= cost_gold
    heal = max(12, int(player.max_hp * 0.28))
    st = max(10, int(player.max_stamina * 0.22))
    old_hp = player.hp
    old_st = player.stamina
    player.hp = min(player.max_hp, player.hp + heal)
    player.stamina = min(player.max_stamina, player.stamina + st)

    # Small ambush risk.
    ambush = random.random() < 0.22
    text = f"🌙 Bạn nghỉ ngắn trong góc tối. HP +{player.hp - old_hp}, Stamina +{player.stamina - old_st}."
    if ambush:
        dmg = max(1, random.randint(6, 18) - int(player.defense * 0.25))
        player.hp -= dmg
        text += f"\n⚠️ Một bóng đen phục kích khi bạn đang nghỉ. Bạn mất **{dmg} HP**."
        if player.hp <= 0:
            return dungeon_death(user_id, "Bạn bị hạ gục trong lúc nghỉ ngắn.")

    save_player(player)
    run["updated_at"] = int(time.time())
    run["last_event"] = text
    save_dungeon_run(user_id, run)
    return True, text, run


def search_current_room(user_id: int) -> tuple[bool, str, Optional[dict[str, Any]]]:
    player = get_player(user_id)
    run = get_dungeon_run(user_id)
    if not player or not run:
        return False, "Bạn không ở trong dungeon run nào.", None

    if player.stamina < 6:
        return False, "Bạn cần ít nhất 6 stamina để lục soát căn phòng.", run

    player.stamina -= 6
    roll = random.random()
    if roll < 0.48:
        dungeon = DELVE_DUNGEONS[run["dungeon_id"]]
        pool = ["healing_herb", "iron_shard", "grave_bone"]
        if run["dungeon_id"] == "blackroot_depths":
            pool.append("blackroot_leaf")
        key = random.choice([k for k in pool if k in ITEMS])
        qty = random.randint(1, 3)
        give_item(player, key, qty)
        text = f"🔎 Bạn lục soát căn phòng và tìm thấy {ITEMS[key]['icon']} **{ITEMS[key]['name']} x{qty}**."
    elif roll < 0.72:
        souls = random.randint(18, 45) + run.get("room", 0) * 6
        run["banked_souls"] = run.get("banked_souls", 0) + souls
        text = f"💀 Bạn tìm thấy dấu vết của một kẻ đã chết. Tạm giữ **{souls} Souls** trong dungeon reward."
    else:
        dmg = max(1, random.randint(8, 24) - int(player.defense * 0.3))
        player.hp -= dmg
        text = f"🕳️ Bạn đạp trúng bẫy khi lục soát. Mất **{dmg} HP**."
        if player.hp <= 0:
            return dungeon_death(user_id, "Bạn chết vì một cái bẫy cũ trong dungeon.")

    run["last_event"] = text
    run["updated_at"] = int(time.time())
    save_player(player)
    save_dungeon_run(user_id, run)
    return True, text, run


def proceed_next_room(user_id: int) -> tuple[bool, str, Optional[dict[str, Any]]]:
    player = get_player(user_id)
    run = get_dungeon_run(user_id)
    if not player or not run:
        return False, "Bạn không ở trong dungeon run nào.", None

    dungeon = DELVE_DUNGEONS[run["dungeon_id"]]
    next_room = int(run.get("room", 0)) + 1
    run["room"] = next_room
    run["updated_at"] = int(time.time())

    if next_room >= int(run["max_rooms"]):
        ok, text, run = resolve_boss_room(player, run, dungeon)
    else:
        room_type = random.choices(
            ["enemy", "chest", "trap", "shrine", "lore"],
            weights=[48, 18, 15, 11, 8],
            k=1,
        )[0]
        if room_type == "enemy":
            ok, text, run = resolve_enemy_room(player, run, dungeon)
        elif room_type == "chest":
            ok, text, run = resolve_chest_room(player, run, dungeon)
        elif room_type == "trap":
            ok, text, run = resolve_trap_room(player, run)
        elif room_type == "shrine":
            ok, text, run = resolve_shrine_room(player, run)
        else:
            ok, text, run = resolve_lore_room(player, run)

    if player.hp <= 0:
        return dungeon_death(user_id, "Bạn gục xuống trước khi tìm được lối ra.")

    save_player(player)
    if run:
        save_dungeon_run(user_id, run)
    return ok, text, run


def resolve_enemy_room(player: Player, run: dict[str, Any], dungeon: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    enemy_key = random.choice(dungeon["enemies"])
    enemy = ENEMIES[enemy_key]

    player_hit = max(1, int(player.attack * random.uniform(0.85, 1.35)) - int(enemy["defense"] * 0.45))
    rounds = max(1, min(5, math.ceil(enemy["hp"] / player_hit)))
    incoming = max(1, int(enemy["attack"] * random.uniform(0.75, 1.25)) - int(player.defense * 0.42))
    taken = incoming * rounds
    if random.random() < player.crit / 100:
        rounds = max(1, rounds - 1)
        taken = max(1, incoming * rounds)

    player.hp -= taken
    reward_souls = enemy["souls"] + random.randint(0, 18)
    reward_gold = enemy["gold"] + random.randint(0, 10)
    run["banked_souls"] = run.get("banked_souls", 0) + reward_souls
    run["banked_gold"] = run.get("banked_gold", 0) + reward_gold
    add_stat(player, "kills", 1)

    loot = roll_loot(player, enemy.get("loot", []))
    text = (
        f"⚔️ **Room {run['room']}** — {enemy['icon']} **{enemy['name']}** xuất hiện.\n"
        f"Bạn giao chiến trong **{rounds} lượt**, nhận **{taken} sát thương**.\n"
        f"Tạm giữ: 💀 **{reward_souls} Souls**, 🪙 **{reward_gold} Gold**."
    )
    if loot:
        text += "\n🎁 Loot: " + ", ".join(loot)
    run["last_event"] = text
    return True, text, run


def resolve_chest_room(player: Player, run: dict[str, Any], dungeon: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    loot_pool = [("healing_herb", 0.80, 1, 2), ("iron_shard", 0.75, 1, 3), ("ember_stone", 0.25, 1, 1)]
    if run["dungeon_id"] == "blackroot_depths":
        loot_pool.append(("blackroot_leaf", 0.75, 2, 4))
    loot = roll_loot(player, loot_pool)
    souls = random.randint(25, 80)
    run["banked_souls"] = run.get("banked_souls", 0) + souls
    text = f"📦 **Room {run['room']}** — Bạn mở một chiếc rương cũ.\n💀 Tạm giữ **{souls} Souls**."
    if loot:
        text += "\n🎁 Loot: " + ", ".join(loot)
    run["last_event"] = text
    return True, text, run


def resolve_trap_room(player: Player, run: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    dmg = max(1, random.randint(12, 36) - int(player.defense * 0.35))
    player.hp -= dmg
    text = f"🕳️ **Room {run['room']}** — Bẫy cổ kích hoạt. Bạn mất **{dmg} HP**."
    run["last_event"] = text
    return True, text, run


def resolve_shrine_room(player: Player, run: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    hp_heal = max(10, int(player.max_hp * 0.22))
    st_heal = max(10, int(player.max_stamina * 0.28))
    old_hp = player.hp
    old_st = player.stamina
    player.hp = min(player.max_hp, player.hp + hp_heal)
    player.stamina = min(player.max_stamina, player.stamina + st_heal)
    text = (
        f"🕯️ **Room {run['room']}** — Bạn tìm thấy một bàn thờ nứt vỡ.\n"
        f"HP +{player.hp - old_hp}, Stamina +{player.stamina - old_st}."
    )
    run["last_event"] = text
    return True, text, run


def resolve_lore_room(player: Player, run: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    lore = random.choice([
        "'Ngọn lửa không soi đường. Nó chỉ làm bóng tối có hình dạng.'",
        "'Kẻ giữ mộ đầu tiên không được chôn ở đây. Hắn được xây thành chính hầm mộ này.'",
        "'Rễ cây trong Blackroot không tìm nước. Chúng tìm ký ức.'",
        "'Nếu nghe thấy chuông, đừng trả lời.'",
    ])
    if hasattr(player, "stats") and isinstance(player.stats, dict):
        codex = player.stats.get("lore_codex", [])
        if isinstance(codex, list) and lore not in codex:
            codex.append(lore)
            player.stats["lore_codex"] = codex
    text = f"📜 **Room {run['room']}** — Bạn tìm thấy một mảnh văn khắc:\n*{lore}*"
    run["last_event"] = text
    return True, text, run


def resolve_boss_room(player: Player, run: dict[str, Any], dungeon: dict[str, Any]) -> tuple[bool, str, Optional[dict[str, Any]]]:
    boss_key = dungeon.get("boss")
    boss = BOSSES.get(boss_key) if boss_key else None
    if not boss:
        return complete_dungeon(player, run, dungeon, "Bạn tìm thấy lối ra cuối cùng.")

    player_hit = max(1, int(player.attack * random.uniform(1.05, 1.65)) - int(boss["defense"] * 0.50))
    rounds = max(3, min(8, math.ceil(boss["hp"] / max(1, player_hit * 3))))
    incoming = max(2, int(boss["attack"] * random.uniform(0.90, 1.35)) - int(player.defense * 0.42))
    taken = incoming * rounds
    if random.random() < player.crit / 100:
        taken = int(taken * 0.82)

    player.hp -= taken
    if player.hp <= 0:
        return dungeon_death(int(run["user_id"]), f"👑 {boss['name']} nghiền nát bạn ở phòng cuối.")

    run["banked_souls"] = run.get("banked_souls", 0) + boss.get("souls", 0)
    run["banked_gold"] = run.get("banked_gold", 0) + boss.get("gold", 0)
    roll_loot(player, boss.get("loot", []))
    add_stat(player, "bosses", 1)
    return complete_dungeon(
        player,
        run,
        dungeon,
        f"👑 **Final Room** — Bạn đánh bại {boss['icon']} **{boss['name']}** sau {rounds} pha giao chiến và mất **{taken} HP**.",
    )


def complete_dungeon(player: Player, run: dict[str, Any], dungeon: dict[str, Any], intro: str) -> tuple[bool, str, None]:
    bonus_souls = dungeon.get("bonus_souls", 0)
    bonus_gold = dungeon.get("bonus_gold", 0)
    total_souls = run.get("banked_souls", 0) + bonus_souls
    total_gold = run.get("banked_gold", 0) + bonus_gold
    player.souls += total_souls
    player.gold += total_gold
    player.status = "idle"
    loot = roll_loot(player, dungeon.get("bonus_loot", []))
    add_stat(player, "dungeons", 1)

    # Optional daily quest compatibility.
    add_stat(player, "daily_dungeon", 1)

    save_player(player)
    delete_dungeon_run(int(run["user_id"]))
    text = (
        f"{intro}\n\n"
        f"✅ **Dungeon cleared:** {dungeon['icon']} **{dungeon['name']}**\n"
        f"Nhận: 💀 **{total_souls} Souls**, 🪙 **{total_gold} Gold**."
    )
    if loot:
        text += "\n🎁 Clear loot: " + ", ".join(loot)
    return True, text, None


def dungeon_death(user_id: int, reason: str) -> tuple[bool, str, None]:
    player = get_player(user_id)
    run = get_dungeon_run(user_id)
    if not player:
        delete_dungeon_run(user_id)
        return False, reason, None

    ensure_player_runtime_fields(player)
    lost_carried = int(player.souls * (0.20 if player.level <= 5 else 0.55))
    player.souls = max(0, player.souls - lost_carried)

    # Banked dungeon rewards are lost on death; carried souls create echo if supported.
    if hasattr(player, "death_echo_souls"):
        player.death_echo_souls = int(getattr(player, "death_echo_souls", 0)) + lost_carried
        player.death_echo_area = run.get("dungeon_id", "dungeon") if run else "dungeon"

    player.hp = max(1, int(player.max_hp * 0.5))
    player.stamina = player.max_stamina
    player.status = "idle"
    save_player(player)
    delete_dungeon_run(user_id)
    text = (
        f"☠️ **YOU DIED**\n{reason}\n\n"
        f"Bạn tỉnh lại với **{player.hp}/{player.max_hp} HP**.\n"
        f"Dungeon reward chưa nhận đã mất. Carried Souls mất: **{lost_carried}**."
    )
    return False, text, None


def dungeon_status_text(player: Player, run: dict[str, Any]) -> str:
    dungeon = DELVE_DUNGEONS[run["dungeon_id"]]
    return (
        f"{dungeon['icon']} **{dungeon['name']}**\n"
        f"Phòng: **{run.get('room', 0)}/{run.get('max_rooms', dungeon['rooms'])}**\n"
        f"❤️ HP: **{player.hp}/{player.max_hp}**\n"
        f"🟩 Stamina: **{player.stamina}/{player.max_stamina}**\n"
        f"Tạm giữ trong dungeon: 💀 **{run.get('banked_souls', 0)}**, 🪙 **{run.get('banked_gold', 0)}**\n\n"
        f"{run.get('last_event', 'Bạn đang đứng trong bóng tối.')}"
    )
