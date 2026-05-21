import random
import time
from dataclasses import dataclass
from typing import Optional

from game.data import BOSSES, ENEMIES, ITEMS
from game.models import CombatSession, Player, InventoryItem
from game import systems


@dataclass
class CombatResult:
    ok: bool
    title: str
    message: str
    ended: bool = False
    victory: bool = False
    death: bool = False


def get_enemy_data(session: CombatSession) -> dict:
    return BOSSES[session.enemy_key] if session.is_boss else ENEMIES[session.enemy_key]


def start_combat(
    player: Player,
    enemy_key: str,
    is_boss: bool = False,
    source: str = "normal",
    dungeon_key: str | None = None,
) -> CombatSession:
    enemy = BOSSES[enemy_key] if is_boss else ENEMIES[enemy_key]
    player.status = "combat"

    return CombatSession(
        owner_id=player.discord_id,
        enemy_key=enemy_key,
        enemy_hp=enemy["hp"],
        enemy_max_hp=enemy["hp"],
        area=player.area,
        is_boss=is_boss,
        turn=1,
        created_at=time.time(),
        log=[f"{enemy['icon']} **{enemy['name']}** xuất hiện."],
        source=source,
        dungeon_key=dungeon_key,
    )


def _append_log(session: CombatSession, *lines: str) -> None:
    for line in lines:
        if line:
            session.log.append(line)
    session.log = session.log[-8:]


def _find_item(player: Player, key: str) -> Optional[InventoryItem]:
    for item in player.inventory:
        if item.key == key:
            return item
    return None


def _player_attack_damage(player: Player, session: CombatSession, multiplier: float = 1.0) -> tuple[int, bool]:
    enemy = get_enemy_data(session)
    base = systems.total_attack(player) * multiplier
    damage = max(1, int(base + random.randint(-2, 7) - enemy["defense"] * 0.55))
    crit = random.random() < systems.total_crit(player) / 100
    if crit:
        damage = int(damage * 1.75)
    return damage, crit


def _enemy_raw_damage(session: CombatSession, defending: bool = False) -> tuple[int, str, Optional[str]]:
    enemy = get_enemy_data(session)
    base = enemy["attack"]
    move_text = "phản công"
    warning = None
    multiplier = 1.0

    if session.is_boss:
        pattern = enemy.get("pattern", [])
        move = pattern[(session.turn - 1) % len(pattern)] if pattern else "slash"

        if move in ["slash", "root_lash"]:
            multiplier = 1.0
            move_text = "tung đòn chém"
        elif move in ["summon", "poison_mist"]:
            multiplier = 0.75
            move_text = "gọi bóng tối phụ trợ"
        elif move == "charge":
            multiplier = 0.40
            move_text = "tụ lực"
            warning = "Boss đang tụ lực. Lượt sau có thể rất nguy hiểm."
        elif move in ["grave_cleave", "crushing_branch"]:
            multiplier = 1.85
            move_text = "tung đại chiêu"
        elif move == "recover":
            multiplier = 0.25
            move_text = "lùi lại hồi sức"

    raw = int(base * multiplier + random.randint(-2, 4))
    if defending:
        raw = int(raw * 0.35)
    return max(0, raw), move_text, warning


def _enemy_turn(player: Player, session: CombatSession, defending: bool = False) -> None:
    enemy = get_enemy_data(session)
    raw, move_text, warning = _enemy_raw_damage(session, defending)
    taken = max(0, int(raw - systems.total_defense(player) * 0.45))

    if taken <= 0:
        _append_log(session, f"{enemy['icon']} {enemy['name']} {move_text}, nhưng bạn chặn được hoàn toàn.")
    else:
        player.hp -= taken
        _append_log(session, f"{enemy['icon']} {enemy['name']} {move_text}, gây **{taken} sát thương**.")

    if warning:
        _append_log(session, f"⚠️ {warning}")


def _victory(player: Player, session: CombatSession) -> CombatResult:
    enemy = get_enemy_data(session)
    player.status = "idle"
    player.xp += enemy["xp"]
    player.souls += enemy["souls"]
    player.gold += enemy["gold"]
    player.stamina = min(player.max_stamina, player.stamina + 12)

    systems.ensure_player_runtime(player)
    player.stats["kills"] = player.stats.get("kills", 0) + 1
    systems.update_quest_progress(player, "kill", 1)

    loot = systems.roll_loot(player, enemy["loot"])
    level_msgs = systems.level_up_if_needed(player)
    extra = []

    if session.source == "dungeon" and session.dungeon_key:
        from game.data import DUNGEONS
        dungeon = DUNGEONS.get(session.dungeon_key)
        if dungeon:
            bonus_souls = dungeon.get("bonus_souls", 0)
            bonus_gold = dungeon.get("bonus_gold", 0)
            player.souls += bonus_souls
            player.gold += bonus_gold
            bonus_loot = systems.roll_loot(player, dungeon.get("bonus_loot", []))
            player.stats["dungeons"] = player.stats.get("dungeons", 0) + 1
            systems.update_quest_progress(player, "dungeon", 1)
            extra.append(f"🏰 Dungeon bonus: 💀 +{bonus_souls}, 🪙 +{bonus_gold}")
            if bonus_loot:
                extra.append("🎁 Dungeon loot: " + ", ".join(bonus_loot))

    if session.is_boss:
        player.stats["bosses"] = player.stats.get("bosses", 0) + 1
        systems.update_quest_progress(player, "boss", 1)
        if session.enemy_key not in player.defeated_bosses:
            player.defeated_bosses.append(session.enemy_key)

        unlock = enemy.get("unlock_area")
        if unlock and unlock not in player.unlocked_areas:
            player.unlocked_areas.append(unlock)
            extra.append("🗺️ Một khu vực mới đã được mở khóa.")

    reward = (
        f"💀 Souls +**{enemy['souls']}**\n"
        f"🪙 Gold +**{enemy['gold']}**\n"
        f"⭐ XP +**{enemy['xp']}**"
    )

    if loot:
        reward += "\n🎁 Loot: " + ", ".join(loot)

    if level_msgs:
        reward += "\n" + "\n".join(level_msgs)

    if extra:
        reward += "\n" + "\n".join(extra)

    _append_log(session, f"✅ Bạn đã đánh bại **{enemy['name']}**.")

    return CombatResult(
        ok=True,
        title="Chiến thắng",
        message=reward,
        ended=True,
        victory=True,
    )


def _death(player: Player, session: CombatSession) -> CombatResult:
    loss_rate = 0.20 if player.level <= 5 else 0.70
    lost_souls = int(player.souls * loss_rate)

    player.souls -= lost_souls
    systems.ensure_player_runtime(player)
    player.stats["deaths"] = player.stats.get("deaths", 0) + 1
    player.death_echo_souls = lost_souls
    player.death_echo_area = session.area
    player.hp = max(1, player.max_hp // 2)
    player.stamina = player.max_stamina
    player.status = "idle"
    player.area = "ember_shrine"

    _append_log(session, "☠️ **Bạn đã gục ngã.**")

    msg = (
        "Bạn tỉnh lại tại **Ember Shrine**.\n"
        f"Bạn đánh rơi **{lost_souls} Souls** tại khu vực vừa chết.\n"
        "Hãy quay lại khu vực đó và dùng `/recover` để thu hồi."
    )

    return CombatResult(False, "YOU DIED", msg, ended=True, death=True)


def resolve_action(player: Player, session: CombatSession, action: str) -> CombatResult:
    enemy = get_enemy_data(session)

    if player.status == "resting":
        return CombatResult(False, "Bạn đang nghỉ", "Bạn không thể chiến đấu khi đang nghỉ ngơi.")

    if action == "run":
        if session.is_boss:
            _append_log(session, "🏃 Bạn không thể chạy khỏi boss.")
        elif random.random() < 0.72:
            player.status = "idle"
            _append_log(session, "🏃 Bạn đã rút lui khỏi trận đấu.")
            return CombatResult(True, "Đã rút lui", "Bạn biến mất vào bóng tối trước khi kẻ địch kịp đuổi theo.", ended=True)
        else:
            _append_log(session, "⚠️ Bạn cố chạy nhưng bị chặn lại.")

    elif action == "defend":
        player.stamina = min(player.max_stamina, player.stamina + 8)
        _append_log(session, "🛡️ Bạn thủ thế. Sát thương nhận vào giảm mạnh và hồi 8 stamina.")
        _enemy_turn(player, session, defending=True)

        if player.hp <= 0:
            return _death(player, session)

        session.turn += 1
        return CombatResult(True, "Bạn đã đỡ", "Bạn giữ vững thế thủ.")

    elif action == "herb":
        herb = _find_item(player, "healing_herb")
        if not herb:
            _append_log(session, "⚠️ Bạn không có Healing Herb.")
        else:
            result = systems.use_item(player, herb.uid)
            _append_log(session, f"🌿 {result.message}")

    elif action == "flask":
        flask = _find_item(player, "ember_flask")
        if not flask:
            _append_log(session, "⚠️ Bạn không có Ember Flask.")
        else:
            result = systems.use_item(player, flask.uid)
            _append_log(session, f"🧪 {result.message}")

    elif action == "skill":
        cost = 18
        if player.stamina < cost:
            _append_log(session, f"⚠️ Không đủ stamina để dùng kỹ năng. Cần {cost} stamina.")
        else:
            player.stamina -= cost
            damage, crit = _player_attack_damage(player, session, multiplier=1.65)
            session.enemy_hp -= damage
            crit_text = " chí mạng" if crit else ""
            _append_log(session, f"✨ Bạn dùng kỹ năng gây **{damage} sát thương{crit_text}**.")

    else:  # attack
        cost = 8
        if player.stamina >= cost:
            player.stamina -= cost
            damage, crit = _player_attack_damage(player, session, multiplier=1.0)
        else:
            damage, crit = _player_attack_damage(player, session, multiplier=0.55)
            _append_log(session, "⚠️ Bạn quá mệt, đòn đánh yếu đi.")

        session.enemy_hp -= damage
        crit_text = " chí mạng" if crit else ""
        _append_log(session, f"⚔️ Bạn gây **{damage} sát thương{crit_text}**.")

    if session.enemy_hp <= 0:
        return _victory(player, session)

    # Nếu action dùng item/run thất bại/attack/skill thì kẻ địch phản công.
    if action != "defend":
        _enemy_turn(player, session, defending=False)

    if player.hp <= 0:
        return _death(player, session)

    player.stamina = min(player.max_stamina, player.stamina + 4)
    session.turn += 1

    return CombatResult(True, "Tiếp tục chiến đấu", "Trận đấu vẫn chưa kết thúc.")


def boss_warning(session: CombatSession) -> Optional[str]:
    if not session.is_boss:
        return None

    enemy = get_enemy_data(session)
    pattern = enemy.get("pattern", [])
    if not pattern:
        return None

    move = pattern[(session.turn - 1) % len(pattern)]
    if move in ["grave_cleave", "crushing_branch"]:
        return "Boss chuẩn bị tung đòn cực mạnh. Nên dùng 🛡️ Đỡ."
    if move == "charge":
        return "Boss đang tụ lực. Lượt sau có thể rất nguy hiểm."
    return None
