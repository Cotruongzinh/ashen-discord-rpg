import os
import random
import time
from dataclasses import dataclass
from typing import Any

from game import ai_generator
from game.ai_config import get_ai_config
from game.ai_content import (
    apply_generated_payload,
    list_generated_content,
    save_generated_content,
)
from game.data import AREAS

BATCH_COLLECTION = "ai_generation_batches"

ITEM_KINDS = ["weapon", "armor", "ring", "consumable", "material"]
ENEMY_ARCHETYPES = ["undead", "beast", "spirit", "cultist", "plant", "construct", "drowned", "ash", "insect"]
RARITY_BY_LEVEL = [
    (1, ["common", "common", "uncommon"]),
    (5, ["common", "uncommon", "uncommon", "rare"]),
    (10, ["uncommon", "rare", "rare", "epic"]),
    (20, ["rare", "epic", "epic", "legendary"]),
]


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class AIAutoConfig:
    enabled: bool
    interval_minutes: int
    theme: str
    items: int
    enemies: int
    encounters: int
    auto_approve: bool
    area: str
    level: int


def get_ai_auto_config() -> AIAutoConfig:
    return AIAutoConfig(
        enabled=bool_env("ASHEN_AI_AUTO_GENERATE", False),
        interval_minutes=max(15, int(os.getenv("ASHEN_AI_AUTO_INTERVAL_MINUTES", "720"))),
        theme=os.getenv("ASHEN_AI_AUTO_THEME", "grave bell"),
        items=max(0, min(10, int(os.getenv("ASHEN_AI_AUTO_ITEMS", "2")))),
        enemies=max(0, min(10, int(os.getenv("ASHEN_AI_AUTO_ENEMIES", "2")))),
        encounters=max(0, min(10, int(os.getenv("ASHEN_AI_AUTO_ENCOUNTERS", "2")))),
        auto_approve=bool_env("ASHEN_AI_AUTO_APPROVE", False),
        area=os.getenv("ASHEN_AI_AUTO_AREA", "forgotten_catacomb"),
        level=max(1, min(60, int(os.getenv("ASHEN_AI_AUTO_LEVEL", "5")))),
    )


def choose_rarity(level: int) -> str:
    choices = ["common", "uncommon"]
    for min_level, values in RARITY_BY_LEVEL:
        if level >= min_level:
            choices = values
    return random.choice(choices)


def save_batch_record(batch_id: str, payload: dict) -> None:
    from game.firebase_client import get_firestore_client

    db = get_firestore_client()
    db.collection(BATCH_COLLECTION).document(batch_id).set(payload)


def list_batches(limit: int = 10) -> list[dict]:
    from game.firebase_client import get_firestore_client

    db = get_firestore_client()
    docs = db.collection(BATCH_COLLECTION).limit(100).stream()
    rows = []
    for doc in docs:
        data = doc.to_dict() or {}
        data["id"] = doc.id
        rows.append(data)
    rows.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return rows[:limit]


async def generate_encounter_cache(
    *,
    created_by: int,
    area_key: str,
    theme: str,
    level: int,
    count: int,
    auto_approve: bool = False,
    batch_id: str | None = None,
) -> list[dict]:
    results = []
    status = "approved" if auto_approve else "draft"
    for _ in range(max(0, min(10, count))):
        data, prompt = await ai_generator.generate_encounter(area_key, level, theme)
        key = f"{area_key}_{int(time.time())}_{random.randint(1000, 9999)}"
        data["area_key"] = area_key
        data["source"] = "ai"
        doc_id = save_generated_content(
            content_type="encounter",
            key=key,
            data=data,
            created_by=created_by,
            status=status,
            prompt=prompt,
            batch_id=batch_id,
        )
        results.append({"doc_id": doc_id, "content_type": "encounter", "key": key, "data": data, "status": status})
    return results


async def generate_world_batch(
    *,
    created_by: int,
    theme: str,
    level: int,
    area_key: str | None = None,
    item_count: int = 3,
    enemy_count: int = 3,
    area_count: int = 0,
    encounter_count: int = 0,
    auto_approve: bool = False,
) -> dict:
    cfg = get_ai_config()
    if not cfg.enabled:
        raise RuntimeError("AI chưa bật. Cần OPENAI_API_KEY và ASHEN_AI_ENABLED=true.")

    batch_id = f"batch_{int(time.time())}_{random.randint(1000, 9999)}"
    status = "approved" if auto_approve else "draft"
    results: list[dict[str, Any]] = []
    generated_area_keys: list[str] = []

    area_count = max(0, min(3, area_count))
    item_count = max(0, min(15, item_count))
    enemy_count = max(0, min(15, enemy_count))
    encounter_count = max(0, min(15, encounter_count))
    level = max(1, min(60, level))

    for _ in range(area_count):
        key, data, prompt = await ai_generator.generate_area(theme, level)
        doc_id = save_generated_content(
            content_type="area",
            key=key,
            data=data,
            created_by=created_by,
            status=status,
            prompt=prompt,
            batch_id=batch_id,
        )
        if auto_approve:
            apply_generated_payload({"content_type": "area", "key": key, "data": data})
        generated_area_keys.append(key)
        results.append({"doc_id": doc_id, "content_type": "area", "key": key, "name": data.get("name"), "status": status})

    target_area = area_key if area_key in AREAS else None
    if not target_area and generated_area_keys:
        target_area = generated_area_keys[0]
    if not target_area:
        target_area = "forgotten_catacomb" if "forgotten_catacomb" in AREAS else next(iter(AREAS.keys()))

    for _ in range(item_count):
        kind = random.choice(ITEM_KINDS)
        rarity = choose_rarity(level)
        key, data, prompt = await ai_generator.generate_item(kind, rarity, theme, level)
        doc_id = save_generated_content(
            content_type="item",
            key=key,
            data=data,
            created_by=created_by,
            status=status,
            prompt=prompt,
            batch_id=batch_id,
        )
        if auto_approve:
            apply_generated_payload({"content_type": "item", "key": key, "data": data})
        results.append({"doc_id": doc_id, "content_type": "item", "key": key, "name": data.get("name"), "status": status})

    for _ in range(enemy_count):
        archetype = random.choice(ENEMY_ARCHETYPES)
        key, data, prompt = await ai_generator.generate_enemy(archetype, theme, level, target_area, is_boss=False)
        doc_id = save_generated_content(
            content_type="enemy",
            key=key,
            data=data,
            created_by=created_by,
            status=status,
            prompt=prompt,
            batch_id=batch_id,
        )
        if auto_approve:
            apply_generated_payload({"content_type": "enemy", "key": key, "data": data})
        results.append({"doc_id": doc_id, "content_type": "enemy", "key": key, "name": data.get("name"), "status": status})

    if encounter_count:
        encounter_rows = await generate_encounter_cache(
            created_by=created_by,
            area_key=target_area,
            theme=theme,
            level=level,
            count=encounter_count,
            auto_approve=auto_approve,
            batch_id=batch_id,
        )
        for row in encounter_rows:
            results.append({"doc_id": row["doc_id"], "content_type": "encounter", "key": row["key"], "name": row["data"].get("title"), "status": status})

    payload = {
        "batch_id": batch_id,
        "theme": theme,
        "level": level,
        "area_key": target_area,
        "status": status,
        "auto_approve": auto_approve,
        "created_by": created_by,
        "created_at": time.time(),
        "counts": {
            "areas": area_count,
            "items": item_count,
            "enemies": enemy_count,
            "encounters": encounter_count,
        },
        "results": results[:80],
    }
    save_batch_record(batch_id, payload)
    return payload


def get_cached_encounter(area_key: str) -> dict | None:
    rows = list_generated_content(content_type="encounter", status="approved", limit=80)
    candidates = []
    for row in rows:
        data = row.get("data") or {}
        if data.get("area_key") in {area_key, None, ""}:
            candidates.append(data)
    if not candidates:
        return None
    return random.choice(candidates)
