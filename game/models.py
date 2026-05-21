from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InventoryItem:
    uid: int
    key: str
    quantity: int = 1
    upgrade: int = 0
    locked: bool = False


@dataclass
class Player:
    discord_id: int
    name: str
    class_key: str

    level: int = 1
    xp: int = 0

    hp: int = 100
    max_hp: int = 100

    stamina: int = 100
    max_stamina: int = 100

    # Chỉ số gốc. Chỉ số tổng được cộng thêm từ trang bị trong systems.py.
    attack: int = 10
    defense: int = 5
    crit: int = 5

    souls: int = 0
    gold: int = 0

    area: str = "forgotten_catacomb"
    unlocked_areas: list[str] = field(
        default_factory=lambda: ["ember_shrine", "forgotten_catacomb"]
    )

    inventory: list[InventoryItem] = field(default_factory=list)

    equipped_weapon: Optional[int] = None
    equipped_armor: Optional[int] = None
    equipped_ring: Optional[int] = None

    next_uid: int = 1

    status: str = "idle"  # idle | resting | combat
    rest_start_time: Optional[float] = None
    rest_end_time: Optional[float] = None
    rest_start_hp: Optional[int] = None
    rest_start_stamina: Optional[int] = None

    flask_charges: int = 3
    max_flask_charges: int = 3

    death_echo_souls: int = 0
    death_echo_area: Optional[str] = None

    defeated_bosses: list[str] = field(default_factory=list)

    # v0.4: long-term loop data
    daily_claimed_date: Optional[str] = None
    daily_quests_date: Optional[str] = None
    daily_quests: list[dict] = field(default_factory=list)
    dungeon_runs_date: Optional[str] = None
    dungeon_runs_used: int = 0
    stats: dict = field(default_factory=dict)


@dataclass
class CombatSession:
    owner_id: int
    enemy_key: str
    enemy_hp: int
    enemy_max_hp: int
    area: str
    is_boss: bool = False
    turn: int = 1
    created_at: float = 0.0
    log: list[str] = field(default_factory=list)

    # v0.4: source can be normal | explore | dungeon | boss
    source: str = "normal"
    dungeon_key: Optional[str] = None
