from game.models import Player, InventoryItem
from game.storage import save_player, get_player


test_player = Player(
    discord_id=123456789,
    name="Test Emberborn",
    class_key="knight",
    level=1,
    hp=120,
    max_hp=120,
    stamina=80,
    max_stamina=80,
    attack=12,
    defense=9,
    crit=5,
)

test_player.inventory.append(
    InventoryItem(
        uid=1,
        key="rusty_sword",
        quantity=1,
        upgrade=0,
    )
)

test_player.equipped_weapon = 1
test_player.next_uid = 2

save_player(test_player)

loaded = get_player(123456789)

print("Đã lưu và đọc lại player:")
print(loaded)