from dataclasses import asdict, fields
from typing import Optional

from game.firebase_client import get_firestore_client
from game.models import Player, InventoryItem, CombatSession


PLAYERS_COLLECTION = "players"
COMBAT_COLLECTION = "combat_sessions"


def player_to_dict(player: Player) -> dict:
    data = asdict(player)
    data["inventory"] = [asdict(item) for item in player.inventory]
    return data


def dict_to_player(data: dict) -> Player:
    data = dict(data)

    inventory = [
        InventoryItem(**item)
        for item in data.get("inventory", [])
    ]

    data["inventory"] = inventory

    # Giúp dữ liệu cũ trên Firestore không crash khi model thay đổi.
    valid_fields = {field.name for field in fields(Player)}
    clean_data = {key: value for key, value in data.items() if key in valid_fields}

    return Player(**clean_data)


def get_player(discord_id: int) -> Optional[Player]:
    db = get_firestore_client()

    doc = (
        db.collection(PLAYERS_COLLECTION)
        .document(str(discord_id))
        .get()
    )

    if not doc.exists:
        return None

    return dict_to_player(doc.to_dict())


def save_player(player: Player) -> None:
    db = get_firestore_client()

    (
        db.collection(PLAYERS_COLLECTION)
        .document(str(player.discord_id))
        .set(player_to_dict(player))
    )


def delete_player(discord_id: int) -> None:
    db = get_firestore_client()

    (
        db.collection(PLAYERS_COLLECTION)
        .document(str(discord_id))
        .delete()
    )


def combat_to_dict(session: CombatSession) -> dict:
    return asdict(session)


def dict_to_combat(data: dict) -> CombatSession:
    data = dict(data)
    valid_fields = {field.name for field in fields(CombatSession)}
    clean_data = {key: value for key, value in data.items() if key in valid_fields}
    return CombatSession(**clean_data)


def get_combat(owner_id: int) -> Optional[CombatSession]:
    db = get_firestore_client()

    doc = (
        db.collection(COMBAT_COLLECTION)
        .document(str(owner_id))
        .get()
    )

    if not doc.exists:
        return None

    return dict_to_combat(doc.to_dict())


def save_combat(session: CombatSession) -> None:
    db = get_firestore_client()

    (
        db.collection(COMBAT_COLLECTION)
        .document(str(session.owner_id))
        .set(combat_to_dict(session))
    )


def delete_combat(owner_id: int) -> None:
    db = get_firestore_client()

    (
        db.collection(COMBAT_COLLECTION)
        .document(str(owner_id))
        .delete()
    )


def list_players(limit: int = 100) -> list[Player]:
    """
    Lấy danh sách player để làm leaderboard nhỏ.
    Với server lớn, sau này nên chuyển sang query/index riêng.
    """
    db = get_firestore_client()
    players: list[Player] = []

    docs = db.collection(PLAYERS_COLLECTION).limit(limit).stream()
    for doc in docs:
        if doc.exists:
            try:
                players.append(dict_to_player(doc.to_dict()))
            except Exception:
                # Bỏ qua document lỗi để leaderboard không làm bot crash.
                continue

    return players
