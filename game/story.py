"""
v0.5 Story / NPC / Story Quest systems.

File này không cần thêm field mới vào Player model. Toàn bộ dữ liệu story được lưu trong
player.stats để tương thích với dữ liệu Firestore cũ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import discord

from game.data import AREAS, ITEMS
from game.models import Player
from game import systems


NPCS = {
    "blind_pilgrim": {
        "name": "The Blind Pilgrim",
        "icon": "🧓",
        "area": "ember_shrine",
        "role": "Lore Keeper",
        "short": "Một kẻ hành hương mù luôn ngồi cạnh tro tàn.",
        "greeting": "Ngọn lửa không chết, Emberborn. Nó chỉ học cách nói dối.",
        "talk": [
            "Ta nghe thấy tiếng chuông dưới hầm mộ. Nó không gọi người sống. Nó gọi những thứ chưa chịu chết.",
            "Nếu ngươi tìm thấy xương cũ trong mộ, hãy lắng nghe. Xương nhớ nhiều hơn thịt.",
            "Keeper of the First Grave không canh giữ người chết. Hắn canh giữ bí mật đầu tiên.",
        ],
        "quests": ["bell_under_graves"],
    },
    "kael_smith": {
        "name": "Kael, Ashen Smith",
        "icon": "🔨",
        "area": "ember_shrine",
        "role": "Blacksmith",
        "short": "Người thợ rèn cụt một tay, giữ lò lửa dưới đền thờ.",
        "greeting": "Thép không sợ bóng tối. Chỉ có người cầm nó là run tay.",
        "talk": [
            "Mang ta sắt. Mang ta tro. Ta sẽ dạy vũ khí của ngươi cách sống lâu hơn chủ nhân.",
            "Một thanh kiếm tốt không cần hét. Nó chỉ cần sống sót sau cú va chạm đầu tiên.",
            "Nếu ngươi định đi sâu hơn, đừng tiếc nguyên liệu. Người chết không dùng được Iron Shard.",
        ],
        "quests": ["smiths_first_flame"],
    },
    "merchant_nara": {
        "name": "Merchant Nara",
        "icon": "🧺",
        "area": "ember_shrine",
        "role": "Merchant",
        "short": "Một thương nhân khoác áo choàng bụi, luôn cười khi nghe tiếng tiền.",
        "greeting": "Mua bán là hình thức cầu nguyện thực tế nhất, bạn của ta.",
        "talk": [
            "Đừng xuống hầm mộ với túi rỗng. Người chết rất thích lấy những gì ngươi chưa kịp dùng.",
            "Ta từng bán bản đồ cho một hiệp sĩ. Hắn quay lại không có đầu, nhưng bản đồ thì còn nguyên.",
            "Nếu thấy token phủ tro, giữ lấy. Sau này có người sẽ đổi chúng lấy thứ tốt hơn vàng.",
        ],
        "quests": ["naras_supply_run"],
    },
    "silent_knight": {
        "name": "The Silent Knight",
        "icon": "🗡️",
        "area": "blackroot_forest",
        "role": "Wounded Knight",
        "short": "Một hiệp sĩ im lặng đứng giữa rừng, giáp bị rễ cây xuyên qua.",
        "greeting": "...",
        "talk": [
            "Hiệp sĩ đặt tay lên ngực giáp. Có tiếng rễ cây chuyển động bên trong.",
            "Hắn chỉ về phía sâu trong rừng. Có thứ gì đó đang khóc dưới tán cây.",
            "Trên lưỡi kiếm của hắn có khắc: 'Đừng tin khu rừng khi nó gọi tên ngươi.'",
        ],
        "quests": ["blackroot_last_oath"],
    },
}


STORY_QUESTS = {
    "bell_under_graves": {
        "name": "Tiếng Chuông Dưới Hầm Mộ",
        "icon": "🔔",
        "giver": "blind_pilgrim",
        "area": "ember_shrine",
        "desc": "The Blind Pilgrim nghe thấy tiếng chuông vọng lên từ Forgotten Catacomb.",
        "accept_text": "Hãy mang về dấu vết của những kẻ không chịu yên nghỉ.",
        "objectives": [
            {"type": "item", "key": "grave_bone", "qty": 5, "consume": True},
            {"type": "level", "level": 2},
        ],
        "rewards": {
            "souls": 180,
            "gold": 80,
            "items": {"ember_stone": 1},
            "lore": "bell_fragment",
        },
    },
    "smiths_first_flame": {
        "name": "Ngọn Lửa Đầu Tiên Của Thợ Rèn",
        "icon": "🔥",
        "giver": "kael_smith",
        "area": "ember_shrine",
        "desc": "Kael muốn thử độ bền của thép trong tay bạn.",
        "accept_text": "Mang nguyên liệu đến. Ta sẽ rèn cho ngươi một bài học.",
        "objectives": [
            {"type": "item", "key": "iron_shard", "qty": 6, "consume": True},
            {"type": "souls", "qty": 120, "consume": True},
        ],
        "rewards": {
            "souls": 60,
            "gold": 120,
            "items": {"ember_stone": 1, "ashen_token": 1},
            "lore": "smith_fragment",
        },
    },
    "naras_supply_run": {
        "name": "Chuyến Hàng Qua Tro",
        "icon": "🧺",
        "giver": "merchant_nara",
        "area": "ember_shrine",
        "desc": "Nara cần vật liệu để đổi lấy hàng hóa mới.",
        "accept_text": "Không phải mọi cuộc phiêu lưu đều cần máu. Một số chỉ cần túi đủ nặng.",
        "objectives": [
            {"type": "item", "key": "ash_fang", "qty": 3, "consume": True},
            {"type": "item", "key": "iron_shard", "qty": 3, "consume": True},
        ],
        "rewards": {
            "souls": 120,
            "gold": 180,
            "items": {"camp_kit": 1, "stamina_draught": 2},
            "lore": "merchant_fragment",
        },
    },
    "keeper_first_secret": {
        "name": "Bí Mật Của Kẻ Giữ Mộ",
        "icon": "👑",
        "giver": "blind_pilgrim",
        "area": "ember_shrine",
        "desc": "The Blind Pilgrim muốn biết điều gì được canh giữ sau cái chết của Keeper.",
        "accept_text": "Nếu ngươi đã hạ Keeper, vậy hãy mang sự im lặng của hắn về đây.",
        "requirements": {"boss_defeated": "keeper_first_grave"},
        "objectives": [
            {"type": "boss_defeated", "key": "keeper_first_grave"},
            {"type": "item", "key": "keeper_core", "qty": 1, "consume": True},
        ],
        "rewards": {
            "souls": 420,
            "gold": 160,
            "items": {"ring_of_embers": 1, "ashen_token": 2},
            "lore": "keeper_secret",
        },
    },
    "blackroot_last_oath": {
        "name": "Lời Thề Cuối Của Rừng Đen",
        "icon": "🌲",
        "giver": "silent_knight",
        "area": "blackroot_forest",
        "desc": "The Silent Knight chỉ vào sâu trong Blackroot Forest, nơi có tiếng khóc cổ xưa.",
        "accept_text": "Hiệp sĩ không nói. Nhưng nhiệm vụ thì đã rõ.",
        "requirements": {"area_unlocked": "blackroot_forest"},
        "objectives": [
            {"type": "area_unlocked", "key": "blackroot_forest"},
            {"type": "item", "key": "blackroot_leaf", "qty": 6, "consume": True},
        ],
        "rewards": {
            "souls": 520,
            "gold": 220,
            "items": {"ancient_core": 1, "ashen_token": 2},
            "lore": "blackroot_oath",
        },
    },
}


LORE_CODEX = {
    "bell_fragment": {
        "title": "Mảnh Chuông Câm",
        "text": "Chiếc chuông dưới mộ không tạo âm thanh. Nó tạo ký ức. Những ai nghe nó quá lâu sẽ nhớ những cái chết không thuộc về mình.",
    },
    "smith_fragment": {
        "title": "Bài Học Của Kael",
        "text": "Kael từng rèn vũ khí cho một vị vua vô danh. Khi nhà vua mất trí, chỉ có thanh kiếm là còn nhận ra chủ nhân cũ.",
    },
    "merchant_fragment": {
        "title": "Sổ Nợ Của Nara",
        "text": "Trong sổ của Nara có tên của nhiều người đã chết. Một số vẫn tiếp tục trả nợ sau khi được chôn.",
    },
    "keeper_secret": {
        "title": "Bí Mật Đầu Tiên",
        "text": "Keeper of the First Grave không canh giữ mộ đầu tiên. Hắn canh giữ người đầu tiên được hồi sinh từ tro.",
    },
    "blackroot_oath": {
        "title": "Lời Thề Của Rễ Cây",
        "text": "Các hiệp sĩ trong Blackroot không chết. Họ mọc rễ, và rễ cây học cách mặc giáp của họ.",
    },
}


@dataclass
class StoryResult:
    ok: bool
    title: str
    message: str


def ensure_story(player: Player) -> None:
    systems.ensure_player_runtime(player)
    player.stats.setdefault("story_quests", {})
    player.stats.setdefault("lore_codex", [])
    player.stats.setdefault("story_completed", 0)
    player.stats.setdefault("npcs_talked", 0)


def get_quest_state(player: Player, quest_id: str) -> str:
    ensure_story(player)
    quest_data = player.stats["story_quests"].get(quest_id)
    if not quest_data:
        return "available"
    return quest_data.get("status", "available")


def _requirement_met(player: Player, req_type: str, value: str) -> bool:
    if req_type == "area_unlocked":
        return value in player.unlocked_areas
    if req_type == "boss_defeated":
        return value in player.defeated_bosses
    return True


def requirements_met(player: Player, quest_id: str) -> tuple[bool, str]:
    quest = STORY_QUESTS[quest_id]
    reqs = quest.get("requirements", {})
    for req_type, value in reqs.items():
        if not _requirement_met(player, req_type, value):
            if req_type == "area_unlocked":
                area = AREAS.get(value, {"name": value})
                return False, f"Bạn cần mở khóa **{area['name']}** trước."
            if req_type == "boss_defeated":
                return False, "Bạn cần đánh bại boss liên quan trước."
    return True, ""


def accept_quest(player: Player, quest_id: str) -> StoryResult:
    ensure_story(player)

    if quest_id not in STORY_QUESTS:
        return StoryResult(False, "Không tìm thấy quest", "Quest ID này không tồn tại.")

    state = get_quest_state(player, quest_id)
    if state == "active":
        return StoryResult(False, "Quest đang hoạt động", "Bạn đã nhận quest này rồi. Dùng `/questlog` để xem.")
    if state == "completed":
        return StoryResult(False, "Quest đã hoàn thành", "Bạn đã hoàn thành quest này rồi.")

    ok, reason = requirements_met(player, quest_id)
    if not ok:
        return StoryResult(False, "Chưa đủ điều kiện", reason)

    quest = STORY_QUESTS[quest_id]
    player.stats["story_quests"][quest_id] = {
        "status": "active",
        "accepted_at_area": player.area,
    }

    return StoryResult(True, "Đã nhận quest", f"**{quest['icon']} {quest['name']}**\n{quest['accept_text']}")


def objective_status(player: Player, objective: dict) -> tuple[bool, str]:
    typ = objective["type"]

    if typ == "item":
        key = objective["key"]
        need = int(objective.get("qty", 1))
        have = systems.count_item(player, key)
        item = ITEMS[key]
        return have >= need, f"{item['icon']} {item['name']}: **{have}/{need}**"

    if typ == "souls":
        need = int(objective.get("qty", 0))
        return player.souls >= need, f"💀 Souls: **{player.souls}/{need}**"

    if typ == "level":
        need = int(objective.get("level", 1))
        return player.level >= need, f"⭐ Level: **{player.level}/{need}**"

    if typ == "boss_defeated":
        key = objective["key"]
        done = key in player.defeated_bosses
        return done, f"👑 Đánh bại boss: **{'Hoàn thành' if done else 'Chưa'}**"

    if typ == "area_unlocked":
        key = objective["key"]
        area = AREAS.get(key, {"name": key, "icon": "📍"})
        done = key in player.unlocked_areas
        return done, f"{area['icon']} Mở khóa {area['name']}: **{'Hoàn thành' if done else 'Chưa'}**"

    return True, "Mục tiêu không xác định."


def quest_ready(player: Player, quest_id: str) -> tuple[bool, list[str]]:
    quest = STORY_QUESTS[quest_id]
    lines = []
    all_done = True
    for obj in quest.get("objectives", []):
        done, text = objective_status(player, obj)
        all_done = all_done and done
        mark = "✅" if done else "⬜"
        lines.append(f"{mark} {text}")
    return all_done, lines


def complete_quest(player: Player, quest_id: str) -> StoryResult:
    ensure_story(player)

    if quest_id not in STORY_QUESTS:
        return StoryResult(False, "Không tìm thấy quest", "Quest ID này không tồn tại.")

    state = get_quest_state(player, quest_id)
    if state != "active":
        return StoryResult(False, "Quest chưa hoạt động", "Bạn cần `/acceptquest` trước hoặc quest này đã hoàn thành.")

    ready, lines = quest_ready(player, quest_id)
    if not ready:
        return StoryResult(False, "Chưa hoàn thành", "Bạn còn thiếu:\n" + "\n".join(lines))

    quest = STORY_QUESTS[quest_id]

    # Consume objectives after final check.
    for obj in quest.get("objectives", []):
        if obj["type"] == "item" and obj.get("consume", False):
            systems.remove_stack_item(player, obj["key"], int(obj.get("qty", 1)))
        if obj["type"] == "souls" and obj.get("consume", False):
            player.souls -= int(obj.get("qty", 0))

    rewards = quest.get("rewards", {})
    player.souls += int(rewards.get("souls", 0))
    player.gold += int(rewards.get("gold", 0))

    reward_lines = []
    if rewards.get("souls"):
        reward_lines.append(f"💀 Souls +{rewards['souls']}")
    if rewards.get("gold"):
        reward_lines.append(f"🪙 Gold +{rewards['gold']}")

    for item_key, qty in rewards.get("items", {}).items():
        systems.add_item(player, item_key, qty)
        item = ITEMS[item_key]
        reward_lines.append(f"{item['icon']} {item['name']} x{qty}")

    lore_key = rewards.get("lore")
    if lore_key and lore_key not in player.stats["lore_codex"]:
        player.stats["lore_codex"].append(lore_key)
        lore = LORE_CODEX[lore_key]
        reward_lines.append(f"📜 Lore mở khóa: **{lore['title']}**")

    player.stats["story_quests"][quest_id]["status"] = "completed"
    player.stats["story_completed"] = player.stats.get("story_completed", 0) + 1

    return StoryResult(True, "Quest hoàn thành", f"**{quest['icon']} {quest['name']}**\n" + "\n".join(reward_lines))


def available_npcs(player: Player) -> list[tuple[str, dict]]:
    ensure_story(player)
    result = []
    for key, npc in NPCS.items():
        npc_area = npc.get("area")
        if npc_area == player.area or npc_area == "ember_shrine":
            # Ember Shrine NPCs are accessible as a hub. Silent Knight appears only in forest.
            if npc_area == "blackroot_forest" and "blackroot_forest" not in player.unlocked_areas:
                continue
            result.append((key, npc))
    return result


def npc_list_embed(player: Player) -> discord.Embed:
    ensure_story(player)
    area = AREAS.get(player.area, {"name": player.area, "icon": "📍"})
    embed = discord.Embed(
        title="🧑‍🤝‍🧑 NPCs & Story",
        description=f"{area['icon']} Khu vực hiện tại: **{area['name']}**\nDùng `/talk npc_id:<id>` để nói chuyện.",
        color=discord.Color.dark_teal(),
    )
    lines = []
    for key, npc in available_npcs(player):
        quest_bits = []
        for qid in npc.get("quests", []):
            state = get_quest_state(player, qid)
            q = STORY_QUESTS[qid]
            icon = "✅" if state == "completed" else "📌" if state == "active" else "❔"
            quest_bits.append(f"{icon} `{qid}` {q['name']}")
        quest_text = "\n".join(quest_bits) if quest_bits else "Không có quest."
        lines.append(f"`{key}` {npc['icon']} **{npc['name']}** — {npc['role']}\n└ {npc['short']}\n└ Quest: {quest_text}")
    embed.add_field(name="Nhân vật có thể gặp", value="\n\n".join(lines) if lines else "Không có NPC ở đây.", inline=False)
    embed.set_footer(text="Ashen RPG v0.5 • Story NPC system")
    return embed


def talk_embed(player: Player, npc_id: str) -> discord.Embed:
    ensure_story(player)
    npc = NPCS[npc_id]
    player.stats["npcs_talked"] = player.stats.get("npcs_talked", 0) + 1

    line_index = player.stats["npcs_talked"] % max(1, len(npc.get("talk", [])))
    line = npc.get("talk", [npc.get("greeting", "...")])[line_index]

    embed = discord.Embed(
        title=f"{npc['icon']} {npc['name']}",
        description=f"*{npc['greeting']}*\n\n{line}",
        color=discord.Color.blurple(),
    )

    quest_lines = []
    for qid in npc.get("quests", []):
        quest = STORY_QUESTS[qid]
        state = get_quest_state(player, qid)
        ready, obj_lines = quest_ready(player, qid) if state == "active" else (False, [])
        state_text = {
            "available": "Có thể nhận",
            "active": "Đang làm" + (" • Sẵn sàng hoàn thành" if ready else ""),
            "completed": "Đã hoàn thành",
        }.get(state, state)
        quest_lines.append(f"`{qid}` {quest['icon']} **{quest['name']}** — {state_text}")

    if quest_lines:
        embed.add_field(name="Quest", value="\n".join(quest_lines), inline=False)
        embed.add_field(
            name="Lệnh",
            value="`/acceptquest quest_id:<id>` để nhận quest\n`/completequest quest_id:<id>` để trả quest",
            inline=False,
        )

    embed.set_footer(text="Ashen RPG v0.5 • NPC dialogue")
    return embed


def questlog_embed(player: Player) -> discord.Embed:
    ensure_story(player)
    embed = discord.Embed(
        title="📜 Story Quest Log",
        description="Quest cốt truyện không reset mỗi ngày. Chúng dùng để mở lore và phần thưởng dài hạn.",
        color=discord.Color.purple(),
    )

    active_lines = []
    completed_lines = []
    available_lines = []

    for qid, quest in STORY_QUESTS.items():
        state = get_quest_state(player, qid)
        ready, obj_lines = quest_ready(player, qid)
        block = f"`{qid}` {quest['icon']} **{quest['name']}**\n└ {quest['desc']}"
        if state == "active":
            block += "\n" + "\n".join(obj_lines)
            if ready:
                block += "\n✅ Có thể hoàn thành bằng `/completequest`."
            active_lines.append(block)
        elif state == "completed":
            completed_lines.append(block)
        else:
            ok, _ = requirements_met(player, qid)
            if ok:
                available_lines.append(block)

    embed.add_field(name="📌 Đang làm", value="\n\n".join(active_lines) if active_lines else "Không có.", inline=False)
    embed.add_field(name="❔ Có thể nhận", value="\n\n".join(available_lines[:5]) if available_lines else "Không có.", inline=False)
    embed.add_field(name="✅ Đã xong", value="\n".join(completed_lines[:6]) if completed_lines else "Chưa có.", inline=False)
    embed.set_footer(text="Ashen RPG v0.5 • Story quests")
    return embed


def lore_embed(player: Player) -> discord.Embed:
    ensure_story(player)
    codex = player.stats.get("lore_codex", [])
    embed = discord.Embed(
        title="📚 Lore Codex",
        description="Các mảnh lore được mở khóa qua story quest.",
        color=discord.Color.dark_magenta(),
    )
    if not codex:
        embed.add_field(name="Trống", value="Bạn chưa mở khóa lore nào. Hãy nói chuyện với NPC và làm story quest.", inline=False)
    else:
        for key in codex[:10]:
            lore = LORE_CODEX.get(key)
            if lore:
                embed.add_field(name=f"📜 {lore['title']}", value=lore["text"], inline=False)
    embed.set_footer(text="Ashen RPG v0.5 • Lore Codex")
    return embed
