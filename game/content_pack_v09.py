"""
Ashen RPG v0.9 content pack.

This file is additive: it updates game.data at runtime instead of overwriting your
existing data.py. That makes the patch safer with your current project.
"""

from __future__ import annotations

from typing import Iterable

from game import data


def _unique_extend(target: list, values: Iterable[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _setdefault_area(key: str, payload: dict) -> None:
    if key not in data.AREAS:
        data.AREAS[key] = payload
        return
    # Keep player-compatible existing area values, but add missing fields.
    for field_key, field_value in payload.items():
        if field_key not in data.AREAS[key]:
            data.AREAS[key][field_key] = field_value


def _patch_shop_items() -> None:
    """Add a few v0.9 items to shop if the project has a shop structure."""
    if not hasattr(data, "SHOP_ITEMS"):
        return

    shop = data.SHOP_ITEMS
    additions = [
        {"id": 9, "item_key": "moon_dew", "price": 85, "currency": "gold", "stock": 3},
        {"id": 10, "item_key": "waystone", "price": 120, "currency": "gold", "stock": 2},
        {"id": 11, "item_key": "ashen_charm", "price": 220, "currency": "gold", "stock": 1},
    ]

    if isinstance(shop, list):
        existing_ids = {entry.get("id") for entry in shop if isinstance(entry, dict)}
        existing_keys = {entry.get("item_key") for entry in shop if isinstance(entry, dict)}
        for entry in additions:
            if entry["id"] not in existing_ids and entry["item_key"] not in existing_keys:
                shop.append(entry)

    if isinstance(shop, dict):
        for entry in additions:
            shop.setdefault(str(entry["id"]), entry)


def apply_content_pack() -> dict:
    if getattr(data, "_ASHEN_CONTENT_PACK_V09_APPLIED", False):
        return {"already_applied": True}

    new_items = {
        # Weapons
        "bone_cleaver": {
            "name": "Bone Cleaver",
            "icon": "🪓",
            "type": "weapon",
            "rarity": "uncommon",
            "attack": 10,
            "defense": 0,
            "crit": 1,
            "desc": "Một chiếc rìu thô được ghép từ xương và sắt gỉ.",
        },
        "thorn_recurve": {
            "name": "Thorn Recurve",
            "icon": "🏹",
            "type": "weapon",
            "rarity": "rare",
            "attack": 14,
            "defense": 0,
            "crit": 8,
            "desc": "Cây cung cong như rễ cây, dây cung rỉ nhựa đen.",
        },
        "sunken_chime": {
            "name": "Sunken Chime",
            "icon": "🔔",
            "type": "weapon",
            "rarity": "epic",
            "attack": 19,
            "defense": 1,
            "crit": 4,
            "desc": "Chuông nguyện ướt lạnh, vang lên như tiếng cầu cứu dưới nước.",
        },
        # Armor / rings
        "gravewarden_mail": {
            "name": "Gravewarden Mail",
            "icon": "🛡️",
            "type": "armor",
            "rarity": "rare",
            "attack": 0,
            "defense": 11,
            "crit": 0,
            "desc": "Áo giáp của lính canh mộ không bao giờ được chôn cất.",
        },
        "veilrunner_boots": {
            "name": "Veilrunner Boots",
            "icon": "🥾",
            "type": "armor",
            "rarity": "uncommon",
            "attack": 0,
            "defense": 4,
            "crit": 3,
            "desc": "Đôi giày nhẹ cho những kẻ thích sống sót bằng khoảng cách.",
        },
        "ring_of_greed": {
            "name": "Ring of Greed",
            "icon": "💍",
            "type": "ring",
            "rarity": "rare",
            "attack": 1,
            "defense": 0,
            "crit": 4,
            "desc": "Chiếc nhẫn lạnh buốt, khiến chủ nhân nghe thấy tiếng vàng trong bóng tối.",
        },
        "ashen_charm": {
            "name": "Ashen Charm",
            "icon": "📿",
            "type": "ring",
            "rarity": "uncommon",
            "attack": 1,
            "defense": 2,
            "crit": 1,
            "desc": "Bùa tro nhỏ, thường được buộc vào cổ tay trẻ em vùng Ember Shrine.",
        },
        # Consumables / materials
        "moon_dew": {
            "name": "Moon Dew",
            "icon": "💧",
            "type": "consumable",
            "rarity": "uncommon",
            "heal": 55,
            "desc": "Giọt sương xanh nhạt, hồi 55 HP.",
        },
        "waystone": {
            "name": "Waystone",
            "icon": "🪨",
            "type": "consumable",
            "rarity": "rare",
            "desc": "Đá dẫn đường. Sau này có thể dùng để thoát dungeon hoặc quay về shrine.",
        },
        "chapel_sigil": {
            "name": "Chapel Sigil",
            "icon": "🔱",
            "type": "material",
            "rarity": "rare",
            "desc": "Dấu ấn chìm nước của Sunken Chapel.",
        },
        "drowned_silver": {
            "name": "Drowned Silver",
            "icon": "🥈",
            "type": "material",
            "rarity": "uncommon",
            "desc": "Bạc ngâm nước lâu ngày, dùng trong các công thức rèn sau này.",
        },
    }

    new_enemies = {
        "bone_marauder": {
            "name": "Bone Marauder",
            "icon": "☠️",
            "hp": 58,
            "attack": 14,
            "defense": 6,
            "xp": 28,
            "souls": 58,
            "gold": 20,
            "loot": [("grave_bone", 0.85, 1, 3), ("bone_cleaver", 0.08, 1, 1), ("iron_shard", 0.45, 1, 2)],
        },
        "ember_moth": {
            "name": "Ember Moth",
            "icon": "🦋",
            "hp": 36,
            "attack": 13,
            "defense": 2,
            "xp": 22,
            "souls": 44,
            "gold": 18,
            "loot": [("ember_stone", 0.10, 1, 1), ("moon_dew", 0.18, 1, 1)],
        },
        "bramble_knight": {
            "name": "Bramble Knight",
            "icon": "🌿",
            "hp": 88,
            "attack": 20,
            "defense": 11,
            "xp": 62,
            "souls": 128,
            "gold": 44,
            "loot": [("blackroot_leaf", 0.9, 2, 4), ("thorn_recurve", 0.07, 1, 1), ("gravewarden_mail", 0.05, 1, 1)],
        },
        "drowned_acolyte": {
            "name": "Drowned Acolyte",
            "icon": "🧎",
            "hp": 76,
            "attack": 22,
            "defense": 8,
            "xp": 70,
            "souls": 145,
            "gold": 58,
            "loot": [("drowned_silver", 0.75, 1, 3), ("chapel_sigil", 0.22, 1, 1), ("moon_dew", 0.25, 1, 1)],
        },
        "bell_wraithling": {
            "name": "Bell Wraithling",
            "icon": "👻",
            "hp": 84,
            "attack": 24,
            "defense": 6,
            "xp": 78,
            "souls": 162,
            "gold": 62,
            "loot": [("chapel_sigil", 0.30, 1, 1), ("sunken_chime", 0.04, 1, 1)],
        },
    }

    new_bosses = {
        "bell_wraith": {
            "name": "The Bell Wraith",
            "icon": "🔔",
            "hp": 560,
            "attack": 32,
            "defense": 14,
            "xp": 420,
            "souls": 980,
            "gold": 260,
            "unlock_area": None,
            "pattern": ["echo_slash", "drown", "charge", "bell_toll", "recover"],
            "loot": [("chapel_sigil", 1.0, 2, 4), ("sunken_chime", 0.35, 1, 1), ("ancient_core", 0.35, 1, 1)],
        }
    }

    data.ITEMS.update(new_items)
    data.ENEMIES.update(new_enemies)
    data.BOSSES.update(new_bosses)

    if "forgotten_catacomb" in data.AREAS:
        _unique_extend(data.AREAS["forgotten_catacomb"].setdefault("enemies", []), ["bone_marauder", "ember_moth"])

    if "blackroot_forest" in data.AREAS:
        _unique_extend(data.AREAS["blackroot_forest"].setdefault("enemies", []), ["bramble_knight"])
        # Let the forest boss open the next area if your current data allows it.
        if "weeping_treant" in data.BOSSES:
            data.BOSSES["weeping_treant"].setdefault("unlock_area", "sunken_chapel")
            if not data.BOSSES["weeping_treant"].get("unlock_area"):
                data.BOSSES["weeping_treant"]["unlock_area"] = "sunken_chapel"

    _setdefault_area(
        "sunken_chapel",
        {
            "name": "Sunken Chapel",
            "icon": "⛪",
            "level": 8,
            "desc": "Nhà nguyện chìm dưới bùn và nước đen. Tiếng chuông vẫn ngân, dù không còn ai kéo dây.",
            "enemies": ["drowned_acolyte", "bell_wraithling"],
            "boss": "bell_wraith",
            "unlock": "Đánh bại The Weeping Treant trong Blackroot Forest.",
        },
    )

    _patch_shop_items()

    data._ASHEN_CONTENT_PACK_V09_APPLIED = True

    return {
        "already_applied": False,
        "items": len(new_items),
        "enemies": len(new_enemies),
        "bosses": len(new_bosses),
        "areas": 1,
    }
