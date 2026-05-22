import json
import os
from typing import Any

from game.ai_config import get_ai_config
from game.ai_validator import validate_area, validate_encounter, validate_enemy, validate_item
from game.data import AREAS

SYSTEM_PROMPT = """
You are the world-forge AI for Ashen RPG, a dark fantasy Discord text RPG inspired by Soulslike, DnD, Zelda-like exploration.
Create vivid, original, concise content. Return ONLY valid JSON. No markdown. No commentary.
Tone: dark fantasy, mysterious, poetic but readable.
Avoid modern objects, jokes, copyrighted names, explicit sexual content, hateful content, and real-world politics.
Do not invent overpowered stats. Stats will be assigned by the game engine.
""".strip()


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def _fallback_item(kind: str, theme: str, rarity: str, level: int) -> tuple[str, dict]:
    return validate_item({
        "name": f"Ashen {kind.title()}",
        "type": kind,
        "rarity": rarity,
        "icon": "✨",
        "effect": "none",
        "desc": f"Một vật phẩm sinh ra từ chủ đề {theme or 'ashen relic'}."
    }, level=level)


def _fallback_enemy(archetype: str, theme: str, level: int, area: str | None, is_boss: bool = False) -> tuple[str, dict]:
    return validate_enemy({
        "name": f"Ashen {archetype.title()}",
        "archetype": archetype,
        "icon": "☠️",
        "desc": f"Một sinh vật {archetype} được tạo từ tro và {theme or 'bóng tối'}.",
        "combat_intro": "Nó bước ra khỏi màn tro, im lặng như một lời nguyền."
    }, level=level, area=area, is_boss=is_boss)


def _call_openai_json(prompt: str) -> dict:
    cfg = get_ai_config()
    if not cfg.enabled:
        raise RuntimeError("AI chưa bật. Cần OPENAI_API_KEY và ASHEN_AI_ENABLED=true.")

    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("Thiếu thư viện openai. Hãy cài: python -m pip install openai") from e

    client = OpenAI(timeout=cfg.timeout_seconds)
    response = client.responses.create(
        model=cfg.model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_output_tokens=cfg.max_output_tokens,
    )
    return _extract_json(response.output_text)


async def generate_item(kind: str, rarity: str, theme: str, level: int, max_rarity: str = "epic") -> tuple[str, dict, str]:
    import asyncio
    kind = kind if kind in {"weapon", "armor", "ring", "consumable", "material"} else "weapon"
    prompt = f"""
Create one RPG item as JSON with keys:
name, icon, type, rarity, effect, desc.
Constraints:
- type must be {kind}
- rarity should be {rarity}
- theme: {theme}
- level context: {level}
- desc max 2 sentences, Vietnamese language.
- effect must be one of: none, bleed, burn, poison, frost, holy, shadow, lifesteal, soul_gain, drop_rate, boss_damage, undead_damage.
Return only JSON object.
""".strip()
    try:
        raw = await asyncio.to_thread(_call_openai_json, prompt)
        return (*validate_item(raw, level=level, max_rarity=max_rarity), prompt)
    except Exception:
        key, data = _fallback_item(kind, theme, rarity, level)
        data["ai_fallback"] = True
        return key, data, prompt


async def generate_enemy(archetype: str, theme: str, level: int, area: str | None, is_boss: bool = False) -> tuple[str, dict, str]:
    import asyncio
    prompt = f"""
Create one {'boss' if is_boss else 'enemy'} as JSON with keys:
name, icon, archetype, desc, combat_intro.
Constraints:
- archetype: {archetype}
- theme: {theme}
- area: {area}
- level context: {level}
- Vietnamese language.
- desc max 2 sentences.
- combat_intro max 1 sentence.
Return only JSON object.
""".strip()
    try:
        raw = await asyncio.to_thread(_call_openai_json, prompt)
        return (*validate_enemy(raw, level=level, area=area, is_boss=is_boss), prompt)
    except Exception:
        key, data = _fallback_enemy(archetype, theme, level, area, is_boss)
        data["ai_fallback"] = True
        return key, data, prompt


async def generate_area(theme: str, level: int) -> tuple[str, dict, str]:
    import asyncio
    prompt = f"""
Create one explorable dark fantasy area as JSON with keys:
name, icon, desc.
Constraints:
- theme: {theme}
- recommended level: {level}
- Vietnamese language.
- desc max 2 sentences.
Return only JSON object.
""".strip()
    try:
        raw = await asyncio.to_thread(_call_openai_json, prompt)
        return (*validate_area(raw, level=level), prompt)
    except Exception:
        key, data = validate_area({
            "name": f"Ashen {theme.title() if theme else 'Reach'}",
            "icon": "🗺️",
            "desc": f"Một vùng đất được tạo từ {theme or 'tro tàn'}, chưa được ghi trên bản đồ cũ."
        }, level=level)
        data["ai_fallback"] = True
        return key, data, prompt


async def generate_encounter(area_key: str, player_level: int, theme: str = "") -> tuple[dict, str]:
    import asyncio
    area = AREAS.get(area_key, {"name": area_key, "desc": "unknown"})
    prompt = f"""
Create one random explore encounter text as JSON with keys:
title, description, choice_hint, mood.
Context:
- area name: {area.get('name')}
- area description: {area.get('desc')}
- player level: {player_level}
- optional theme: {theme}
Constraints:
- Vietnamese language.
- description 3-5 sentences max.
- Do not decide rewards or damage.
Return only JSON object.
""".strip()
    try:
        raw = await asyncio.to_thread(_call_openai_json, prompt)
        return validate_encounter(raw), prompt
    except Exception:
        return validate_encounter({
            "title": "Tiếng Thì Thầm Trong Tro",
            "description": "Bạn nghe thấy một tiếng gọi rất nhỏ phía sau bức tường nứt. Tro bụi rơi xuống như tuyết xám, để lộ những vết móng tay cào sâu vào đá. Có thứ gì đó đang chờ bạn ở phía trước.",
            "choice_hint": "Bạn siết chặt vũ khí và bước tiếp.",
            "mood": "fallback"
        }), prompt
