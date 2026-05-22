import json
import time
from typing import Optional

from game.firebase_client import get_firestore_client
from game.data import ITEMS, ENEMIES, AREAS, BOSSES


AI_COLLECTION = "ai_generated_content"
BATCH_COLLECTION = "ai_generation_batches"


def _now() -> float:
    return time.time()


def _encode_data(data: dict) -> str:
    """
    Firestore không lưu tốt nested array như:
    loot = [["iron_shard", 0.5, 1, 2]]
    nên data AI được encode thành JSON string.
    """
    return json.dumps(data or {}, ensure_ascii=False)


def _decode_payload(payload: dict) -> dict:
    """
    Hỗ trợ cả document mới dùng data_json
    và document cũ dùng data.
    """
    if not payload:
        return payload

    if "data_json" in payload:
        try:
            payload["data"] = json.loads(payload.get("data_json") or "{}")
        except Exception:
            payload["data"] = {}
    else:
        payload["data"] = payload.get("data") or {}

    return payload


def save_generated_content(
    *,
    content_type: str,
    key: str,
    data: dict,
    created_by: int,
    status: str = "draft",
    prompt: str = "",
    batch_id: str | None = None,
) -> str:
    """
    Lưu AI content vào Firestore.

    Quan trọng:
    - Không lưu field data trực tiếp để tránh lỗi invalid nested entity.
    - Lưu data_json thay thế.
    """
    db = get_firestore_client()

    safe_key = str(key).strip().lower().replace(" ", "_")
    doc_id = f"{content_type}_{safe_key}"

    payload = {
        "content_type": content_type,
        "key": safe_key,
        "status": status,
        "created_by": str(created_by),
        "created_at": _now(),
        "updated_at": _now(),
        "prompt": str(prompt or "")[:800],
        "batch_id": batch_id,
        "data_json": _encode_data(data),

        # Các field preview để dễ xem trong Firebase
        "name": data.get("name") or data.get("title") or data.get("area_name") or safe_key,
        "theme": data.get("theme", ""),
        "rarity": data.get("rarity", ""),
        "level": int(data.get("level", data.get("recommended_level", 1)) or 1),
    }

    db.collection(AI_COLLECTION).document(doc_id).set(payload)
    return doc_id


def get_generated_content(doc_id: str) -> Optional[dict]:
    db = get_firestore_client()

    doc = db.collection(AI_COLLECTION).document(doc_id).get()

    if not doc.exists:
        return None

    payload = doc.to_dict() or {}
    payload["id"] = doc.id
    return _decode_payload(payload)


def list_generated_content(
    content_type: str | None = None,
    status: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    List AI content.

    Để tránh lỗi composite index, mình query rộng hơn rồi filter/sort local.
    """
    db = get_firestore_client()

    # Nếu có status thì query theo status trước.
    # Nếu không thì query toàn bộ collection có limit cao hơn.
    query = db.collection(AI_COLLECTION)

    if status:
        query = query.where("status", "==", status)

    docs = query.limit(max(limit, 300)).stream()

    rows = []
    for doc in docs:
        payload = doc.to_dict() or {}
        payload["id"] = doc.id
        payload = _decode_payload(payload)

        if content_type and payload.get("content_type") != content_type:
            continue

        rows.append(payload)

    rows.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return rows[:limit]


def mark_content_status(doc_id: str, status: str) -> Optional[dict]:
    db = get_firestore_client()

    ref = db.collection(AI_COLLECTION).document(doc_id)
    doc = ref.get()

    if not doc.exists:
        return None

    ref.update(
        {
            "status": status,
            "updated_at": _now(),
        }
    )

    payload = doc.to_dict() or {}
    payload["id"] = doc.id
    payload["status"] = status

    return _decode_payload(payload)


def apply_generated_payload(payload: dict) -> bool:
    """
    Đưa AI content đã duyệt vào runtime data của game.

    AI có quyền tạo content, nhưng dữ liệu đã qua validator/balance trước đó.
    """
    payload = _decode_payload(payload)

    content_type = payload.get("content_type")
    key = payload.get("key")
    data = payload.get("data") or {}

    if not key or not isinstance(data, dict):
        return False

    if content_type == "item":
        ITEMS[key] = data
        return True

    if content_type == "enemy":
        ENEMIES[key] = data

        area_key = data.get("area")
        if area_key in AREAS:
            AREAS[area_key].setdefault("enemies", [])
            if key not in AREAS[area_key]["enemies"]:
                AREAS[area_key]["enemies"].append(key)

        return True

    if content_type == "boss":
        BOSSES[key] = data
        return True

    if content_type == "area":
        AREAS[key] = data
        AREAS[key].setdefault("enemies", [])
        return True

    if content_type == "encounter":
        # Encounter không cần đưa vào data.py.
        # Nó được đọc trực tiếp từ Firebase cache.
        return True

    return False


def apply_approved_content(limit: int = 300) -> dict:
    """
    Load toàn bộ AI content đã approved vào runtime khi bot start.
    """
    applied = {
        "item": 0,
        "enemy": 0,
        "boss": 0,
        "area": 0,
        "encounter": 0,
        "failed": 0,
    }

    for payload in list_generated_content(status="approved", limit=limit):
        ok = apply_generated_payload(payload)

        if ok:
            content_type = payload.get("content_type", "failed")
            applied[content_type] = applied.get(content_type, 0) + 1
        else:
            applied["failed"] += 1

    return applied


def save_batch_record(batch_id: str, payload: dict) -> None:
    """
    Lưu batch record.
    Batch payload không nên chứa nested arrays phức tạp.
    """
    db = get_firestore_client()

    safe_payload = dict(payload)
    safe_payload["updated_at"] = _now()

    db.collection(BATCH_COLLECTION).document(batch_id).set(safe_payload)


def get_batch_record(batch_id: str) -> Optional[dict]:
    db = get_firestore_client()

    doc = db.collection(BATCH_COLLECTION).document(batch_id).get()

    if not doc.exists:
        return None

    payload = doc.to_dict() or {}
    payload["id"] = doc.id
    return payload


def list_batch_records(limit: int = 10) -> list[dict]:
    db = get_firestore_client()

    docs = db.collection(BATCH_COLLECTION).limit(max(limit, 100)).stream()

    rows = []
    for doc in docs:
        payload = doc.to_dict() or {}
        payload["id"] = doc.id
        rows.append(payload)

    rows.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return rows[:limit]


def mark_batch_status(batch_id: str, status: str) -> dict:
    """
    Đổi status cho batch và toàn bộ content thuộc batch đó.
    Dùng trong /ai_batch_approve và /ai_batch_reject.
    """
    db = get_firestore_client()

    batch_ref = db.collection(BATCH_COLLECTION).document(batch_id)
    batch_doc = batch_ref.get()

    if batch_doc.exists:
        batch_ref.update(
            {
                "status": status,
                "updated_at": _now(),
            }
        )

    updated = 0

    docs = (
        db.collection(AI_COLLECTION)
        .where("batch_id", "==", batch_id)
        .limit(500)
        .stream()
    )

    for doc in docs:
        db.collection(AI_COLLECTION).document(doc.id).update(
            {
                "status": status,
                "updated_at": _now(),
            }
        )
        updated += 1

    return {
        "batch_id": batch_id,
        "status": status,
        "updated": updated,
    }