import re
import time
from typing import Any

from game.data import AREAS, ITEMS

ALLOWED_RARITIES = ["common", "uncommon", "rare", "epic", "legendary", "mythic"]
ALLOWED_ITEM_TYPES = ["weapon", "armor", "ring", "consumable", "material"]
ALLOWED_EFFECTS = [
    "none", "bleed", "burn", "poison", "frost", "holy", "shadow",
    "lifesteal", "soul_gain", "drop_rate", "boss_damage", "undead_damage",
]
ALLOWED_ARCHETYPES = [
    "undead", "beast", "spirit", "cultist", "plant", "construct", "drowned", "ash", "insect",
]
RARITY_ORDER = {name: i for i, name in enumerate(ALLOWED_RARITIES)}


def slugify(text: str, prefix: str = "ai") -> str:
    text = (text or "generated").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = "generated"
    return f"{prefix}_{text[:42]}_{int(time.time())}"


def clean_text(value: Any, max_len: int, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return fallback
    return value[:max_len]


def clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        value = int(value)
    except Exception:
        return default
    return max(low, min(high, value))


def normalize_rarity(raw: Any, max_rarity: str = "epic") -> str:
    rarity = str(raw or "common").lower().strip()
    if rarity not in ALLOWED_RARITIES:
        rarity = "common"
    if RARITY_ORDER[rarity] > RARITY_ORDER.get(max_rarity, 3):
        rarity = max_rarity
    return rarity


def normalize_effect(raw: Any) -> str:
    effect = str(raw or "none").lower().strip()
    return effect if effect in ALLOWED_EFFECTS else "none"


def item_budget(level: int, rarity: str, item_type: str) -> dict:
    rarity_mult = {
        "common": 1.00,
        "uncommon": 1.18,
        "rare": 1.40,
        "epic": 1.70,
        "legendary": 2.10,
        "mythic": 2.50,
    }.get(rarity, 1.0)
    level = max(1, min(60, level))
    if item_type == "weapon":
        return {
            "attack": max(2, int((5 + level * 2.2) * rarity_mult)),
            "defense": 0,
            "crit": max(0, int(2 + rarity_mult * 3)),
        }
    if item_type == "armor":
        return {
            "attack": 0,
            "defense": max(2, int((4 + level * 1.6) * rarity_mult)),
            "crit": max(0, int(rarity_mult * 2)),
        }
    if item_type == "ring":
        return {
            "attack": max(0, int((1 + level * 0.45) * rarity_mult)),
            "defense": max(0, int((1 + level * 0.45) * rarity_mult)),
            "crit": max(0, int(2 + rarity_mult * 2)),
        }
    return {"attack": 0, "defense": 0, "crit": 0}


def validate_item(raw: dict, *, level: int, max_rarity: str = "epic") -> tuple[str, dict]:
    raw = raw or {}
    item_type = str(raw.get("type") or "weapon").lower().strip()
    if item_type not in ALLOWED_ITEM_TYPES:
        item_type = "weapon"

    rarity = normalize_rarity(raw.get("rarity"), max_rarity=max_rarity)
    name = clean_text(raw.get("name"), 55, "Nameless Relic")
    key = slugify(name, "ai_item")
    effect = normalize_effect(raw.get("effect"))
    budget = item_budget(level, rarity, item_type)

    data = {
        "name": name,
        "icon": clean_text(raw.get("icon"), 4, "✨"),
        "type": item_type,
        "rarity": rarity,
        "attack": budget["attack"],
        "defense": budget["defense"],
        "crit": budget["crit"],
        "effect": effect,
        "desc": clean_text(raw.get("desc") or raw.get("description"), 240, "Một vật phẩm được sinh ra từ tro tàn."),
        "source": "ai",
        "level": max(1, min(60, int(level))),
    }

    if item_type == "consumable":
        data.update({
            "heal": clamp_int(raw.get("heal"), 10, 90, 30),
            "attack": 0,
            "defense": 0,
            "crit": 0,
        })
    if item_type == "material":
        data.update({"attack": 0, "defense": 0, "crit": 0})

    return key, data


def enemy_budget(level: int, archetype: str, is_boss: bool = False) -> dict:
    level = max(1, min(60, level))
    boss_mult = 3.0 if is_boss else 1.0
    return {
        "hp": int((28 + level * 11) * boss_mult),
        "attack": int((6 + level * 2.25) * (1.35 if is_boss else 1.0)),
        "defense": int(2 + level * 0.9),
        "xp": int((10 + level * 6) * (3.5 if is_boss else 1.0)),
        "souls": int((20 + level * 10) * (3.4 if is_boss else 1.0)),
        "gold": int((8 + level * 4) * (3.0 if is_boss else 1.0)),
    }


def validate_enemy(raw: dict, *, level: int, area: str | None = None, is_boss: bool = False) -> tuple[str, dict]:
    raw = raw or {}
    name = clean_text(raw.get("name"), 55, "Nameless Hollow")
    key = slugify(name, "ai_boss" if is_boss else "ai_enemy")
    archetype = str(raw.get("archetype") or "undead").lower().strip()
    if archetype not in ALLOWED_ARCHETYPES:
        archetype = "undead"
    stats = enemy_budget(level, archetype, is_boss=is_boss)

    loot = [("grave_bone", 0.35, 1, 2), ("healing_herb", 0.18, 1, 1)]
    if level >= 4:
        loot.append(("iron_shard", 0.25, 1, 2))
    if level >= 8:
        loot.append(("ember_stone", 0.08, 1, 1))

    data = {
        "name": name,
        "icon": clean_text(raw.get("icon"), 4, "☠️"),
        "archetype": archetype,
        "level": max(1, min(60, level)),
        "area": area,
        "desc": clean_text(raw.get("desc") or raw.get("description"), 260, "Một sinh vật lạ sinh ra từ bóng tối."),
        "combat_intro": clean_text(raw.get("combat_intro"), 220, "Nó bước ra khỏi bóng tối."),
        "hp": stats["hp"],
        "attack": stats["attack"],
        "defense": stats["defense"],
        "xp": stats["xp"],
        "souls": stats["souls"],
        "gold": stats["gold"],
        "loot": loot,
        "source": "ai",
    }
    if is_boss:
        data["unlock_area"] = None
        data["pattern"] = ["slash", "charge", "grave_cleave", "recover"]
    return key, data


def validate_area(raw: dict, *, level: int) -> tuple[str, dict]:
    raw = raw or {}
    name = clean_text(raw.get("name"), 55, "Nameless Reach")
    key = slugify(name, "ai_area")
    data = {
        "name": name,
        "icon": clean_text(raw.get("icon"), 4, "🗺️"),
        "level": max(1, min(60, level)),
        "desc": clean_text(raw.get("desc") or raw.get("description"), 260, "Một vùng đất lạ vừa được mở trong làn tro."),
        "enemies": [],
        "boss": None,
        "unlock": "Khu vực AI-generated. Admin có thể mở khóa bằng /aiunlockarea.",
        "source": "ai",
    }
    return key, data


def validate_encounter(raw: dict) -> dict:
    raw = raw or {}
    return {
        "title": clean_text(raw.get("title"), 80, "A Strange Encounter"),
        "description": clean_text(raw.get("description"), 700, "Bạn cảm thấy có điều gì đó đang chuyển động trong bóng tối."),
        "choice_hint": clean_text(raw.get("choice_hint"), 180, "Bạn siết chặt vũ khí và bước tiếp."),
        "mood": clean_text(raw.get("mood"), 40, "dark_fantasy"),
    }
