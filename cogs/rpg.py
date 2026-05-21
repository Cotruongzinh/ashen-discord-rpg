import random

import discord
from discord import app_commands
from discord.ext import commands

from game.data import AREAS, BOSSES, CLASSES, ENEMIES, ITEMS, LORE_FRAGMENTS, DUNGEONS
from game.models import Player
from game.storage import delete_combat, get_combat, get_player, save_combat, save_player, list_players
from game import combat, systems, ui


def require_player(interaction: discord.Interaction) -> Player | None:
    return get_player(interaction.user.id)


def is_busy(player: Player) -> str | None:
    if player.status == "resting":
        return "🌙 Bạn đang nghỉ. Dùng `/checkrest` để kiểm tra."
    if player.status == "combat":
        return "⚔️ Bạn đang trong combat. Dùng `/combat` để tiếp tục."
    return None


class ClassSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=cls["name"],
                description=cls.get("desc", "Fantasy RPG class"),
                emoji=cls["icon"],
                value=key,
            )
            for key, cls in CLASSES.items()
        ]

        super().__init__(
            placeholder="Chọn class của bạn",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        old_player = get_player(interaction.user.id)
        if old_player:
            await interaction.response.send_message(
                "Bạn đã có nhân vật rồi. Dùng `/profile` để xem.",
                ephemeral=True,
            )
            return

        class_key = self.values[0]
        cls = CLASSES[class_key]

        player = Player(
            discord_id=interaction.user.id,
            name=interaction.user.display_name,
            class_key=class_key,
            hp=cls["max_hp"],
            max_hp=cls["max_hp"],
            stamina=cls["max_stamina"],
            max_stamina=cls["max_stamina"],
            attack=cls["attack"],
            defense=cls["defense"],
            crit=cls["crit"],
            area="forgotten_catacomb",
        )

        weapon = systems.add_item(player, cls["weapon"], 1)
        armor = systems.add_item(player, cls["armor"], 1)
        systems.add_item(player, "healing_herb", 3)
        systems.add_item(player, "ember_flask", 1)

        player.equipped_weapon = weapon.uid
        player.equipped_armor = armor.uid
        systems.ensure_player_runtime(player)
        systems.refresh_daily_quests(player)

        save_player(player)
        delete_combat(player.discord_id)

        embed = ui.profile_embed(player)
        embed.title = f"{cls['icon']} Nhân vật đã thức tỉnh"
        embed.description = (
            f"Bạn đã chọn **{cls['name']}**.\n"
            f"Bạn tỉnh dậy trong **Forgotten Catacomb**."
        )

        await interaction.response.edit_message(embed=embed, view=None)


class ClassSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(ClassSelect())


class InventoryView(discord.ui.View):
    def __init__(self, owner_id: int, player: Player):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.player = player

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Đây không phải inventory của bạn.", ephemeral=True)
            return False
        return True

    async def show(self, interaction: discord.Interaction, item_type: str | None):
        self.player = get_player(self.owner_id)
        await interaction.response.edit_message(
            embed=ui.inventory_embed(self.player, item_type),
            view=self,
        )

    @discord.ui.button(label="Tất cả", emoji="🎒", style=discord.ButtonStyle.secondary)
    async def all_items(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, None)

    @discord.ui.button(label="Vũ khí", emoji="⚔️", style=discord.ButtonStyle.primary)
    async def weapons(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, "weapon")

    @discord.ui.button(label="Giáp", emoji="🛡️", style=discord.ButtonStyle.primary)
    async def armor(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, "armor")

    @discord.ui.button(label="Vật phẩm", emoji="🧪", style=discord.ButtonStyle.success)
    async def consumables(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, "consumable")

    @discord.ui.button(label="Nguyên liệu", emoji="🔨", style=discord.ButtonStyle.secondary)
    async def materials(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, "material")


class TravelSelect(discord.ui.Select):
    def __init__(self, player: Player):
        options = []
        for key in player.unlocked_areas:
            area = AREAS.get(key)
            if not area:
                continue
            options.append(
                discord.SelectOption(
                    label=area["name"],
                    description=area["desc"][:90],
                    emoji=area["icon"],
                    value=key,
                )
            )

        super().__init__(
            placeholder="Chọn khu vực muốn di chuyển",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        player = get_player(interaction.user.id)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật.", ephemeral=True)
            return

        busy = is_busy(player)
        if busy:
            await interaction.response.send_message(busy, ephemeral=True)
            return

        area_key = self.values[0]

        if area_key not in player.unlocked_areas:
            await interaction.response.send_message("Bạn chưa mở khóa khu vực này.", ephemeral=True)
            return

        player.area = area_key
        save_player(player)

        area = AREAS[area_key]
        await interaction.response.edit_message(
            embed=ui.basic_embed(
                f"{area['icon']} Đã di chuyển",
                f"Bạn đã đến **{area['name']}**.\n{area['desc']}",
                discord.Color.green(),
            ),
            view=None,
        )


class TravelView(discord.ui.View):
    def __init__(self, player: Player):
        super().__init__(timeout=120)
        self.add_item(TravelSelect(player))


class CombatView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=600)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Đây không phải trận đấu của bạn.", ephemeral=True)
            return False
        return True

    async def do_action(self, interaction: discord.Interaction, action: str):
        player = get_player(self.owner_id)
        session = get_combat(self.owner_id)

        if not player or not session:
            await interaction.response.edit_message(
                embed=ui.basic_embed("Combat đã kết thúc", "Không tìm thấy trận đấu đang hoạt động.", discord.Color.orange()),
                view=None,
            )
            return

        result = combat.resolve_action(player, session, action)

        if result.ended:
            save_player(player)
            delete_combat(self.owner_id)
            await interaction.response.edit_message(
                embed=ui.combat_embed(player, session, result.title, result.message),
                view=None,
            )
            return

        save_player(player)
        save_combat(session)
        await interaction.response.edit_message(
            embed=ui.combat_embed(player, session),
            view=self,
        )

    @discord.ui.button(label="Attack", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def attack(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.do_action(interaction, "attack")

    @discord.ui.button(label="Skill", emoji="✨", style=discord.ButtonStyle.primary)
    async def skill(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.do_action(interaction, "skill")

    @discord.ui.button(label="Defend", emoji="🛡️", style=discord.ButtonStyle.secondary)
    async def defend(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.do_action(interaction, "defend")

    @discord.ui.button(label="Herb", emoji="🌿", style=discord.ButtonStyle.success)
    async def herb(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.do_action(interaction, "herb")

    @discord.ui.button(label="Flask", emoji="🧪", style=discord.ButtonStyle.success)
    async def flask(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.do_action(interaction, "flask")

    @discord.ui.button(label="Run", emoji="🏃", style=discord.ButtonStyle.secondary)
    async def run(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.do_action(interaction, "run")


class RPG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _start_combat_response(self, interaction: discord.Interaction, player: Player, enemy_key: str, is_boss: bool, source: str = "normal", dungeon_key: str | None = None):
        session = combat.start_combat(player, enemy_key, is_boss=is_boss, source=source, dungeon_key=dungeon_key)
        save_player(player)
        save_combat(session)
        await interaction.response.send_message(
            embed=ui.combat_embed(player, session),
            view=CombatView(player.discord_id),
        )

    @app_commands.command(name="start", description="Tạo nhân vật RPG")
    async def start(self, interaction: discord.Interaction):
        player = get_player(interaction.user.id)

        if player:
            await interaction.response.send_message(
                "Bạn đã có nhân vật rồi. Dùng `/profile` để xem.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🔥 Ashen RPG",
            description=(
                "Chọn class để bắt đầu hành trình.\n\n"
                "🛡️ **Knight** — máu cao, thủ tốt.\n"
                "🗡️ **Rogue** — nhanh, chí mạng cao.\n"
                "🔮 **Mage** — sát thương cao, phòng thủ yếu."
            ),
            color=discord.Color.dark_teal(),
        )

        await interaction.response.send_message(
            embed=embed,
            view=ClassSelectView(),
            ephemeral=True,
        )

    @app_commands.command(name="profile", description="Xem nhân vật của bạn")
    async def profile(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        await interaction.response.send_message(embed=ui.profile_embed(player))

    @app_commands.command(name="inventory", description="Xem túi đồ")
    async def inventory(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        await interaction.response.send_message(
            embed=ui.inventory_embed(player),
            view=InventoryView(interaction.user.id, player),
            ephemeral=True,
        )

    @app_commands.command(name="equip", description="Trang bị item bằng ID")
    async def equip(self, interaction: discord.Interaction, item_id: int):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        if player.status == "combat":
            await interaction.response.send_message("⚔️ Không thể đổi trang bị trong combat.", ephemeral=True)
            return

        result = systems.equip_item(player, item_id)
        if result.ok:
            save_player(player)

        await interaction.response.send_message(
            embed=ui.result_embed(result.title, result.message, result.ok),
            ephemeral=True,
        )

    @app_commands.command(name="useitem", description="Dùng vật phẩm tiêu hao bằng ID")
    async def useitem(self, interaction: discord.Interaction, item_id: int):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        if player.status == "combat":
            await interaction.response.send_message("⚔️ Trong combat hãy dùng button Herb/Flask.", ephemeral=True)
            return

        result = systems.use_item(player, item_id)
        if result.ok:
            save_player(player)

        await interaction.response.send_message(
            embed=ui.result_embed(result.title, result.message, result.ok),
            ephemeral=True,
        )

    @app_commands.command(name="rest", description="Nghỉ ngơi để hồi HP, stamina và flask")
    async def rest(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        if player.status == "combat":
            await interaction.response.send_message("⚔️ Không thể nghỉ khi đang combat. Dùng `/combat` để tiếp tục.", ephemeral=True)
            return

        result = systems.start_rest(player)
        if result.ok:
            save_player(player)

        await interaction.response.send_message(
            embed=ui.result_embed("🌙 " + result.title, result.message, result.ok)
        )

    @app_commands.command(name="checkrest", description="Kiểm tra trạng thái nghỉ ngơi")
    async def checkrest(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        result = systems.check_rest(player)
        if result.ok:
            save_player(player)

        await interaction.response.send_message(
            embed=ui.result_embed(result.title, result.message, result.ok),
            ephemeral=not result.ok,
        )

    @app_commands.command(name="cancelrest", description="Hủy nghỉ ngơi")
    async def cancelrest(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        result = systems.cancel_rest(player)
        if result.ok:
            save_player(player)

        await interaction.response.send_message(
            embed=ui.result_embed(result.title, result.message, result.ok),
            ephemeral=True,
        )

    @app_commands.command(name="explore", description="Khám phá khu vực hiện tại")
    async def explore(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        busy = is_busy(player)
        if busy:
            await interaction.response.send_message(busy, ephemeral=True)
            return

        area = AREAS[player.area]

        if not area["enemies"]:
            await interaction.response.send_message(
                embed=ui.basic_embed(
                    f"{area['icon']} {area['name']}",
                    "Nơi này khá yên bình. Bạn có thể nghỉ ngơi hoặc di chuyển.",
                    discord.Color.dark_blue(),
                )
            )
            return

        if player.stamina < 10:
            await interaction.response.send_message("🟩 Bạn không đủ stamina để khám phá. Hãy dùng `/rest`.", ephemeral=True)
            return

        player.stamina -= 10
        systems.ensure_player_runtime(player)
        player.stats["explores"] = player.stats.get("explores", 0) + 1
        systems.update_quest_progress(player, "explore", 1)
        roll = random.random()

        if roll < 0.60:
            enemy_key = random.choice(area["enemies"])
            await self._start_combat_response(interaction, player, enemy_key, is_boss=False)
            return

        if roll < 0.75:
            key = random.choice(["healing_herb", "iron_shard", "grave_bone", "ash_fang", "ring_of_embers"])
            qty = 1 if ITEMS[key]["type"] not in ["material", "consumable"] else random.randint(1, 3)
            systems.add_item(player, key, qty)
            save_player(player)

            await interaction.response.send_message(
                embed=ui.basic_embed(
                    "📦 Rương cũ",
                    f"Bạn tìm thấy **{ITEMS[key]['icon']} {ITEMS[key]['name']}** x{qty if ITEMS[key]['type'] in ['material', 'consumable'] else 1}.",
                    discord.Color.gold(),
                )
            )
            return

        if roll < 0.88:
            save_player(player)
            await interaction.response.send_message(
                embed=ui.basic_embed(
                    "📜 Lore Fragment",
                    random.choice(LORE_FRAGMENTS),
                    discord.Color.purple(),
                )
            )
            return

        damage = random.randint(8, 22)
        player.hp = max(1, player.hp - damage)
        save_player(player)

        await interaction.response.send_message(
            embed=ui.basic_embed(
                "🕳️ Bẫy cổ",
                f"Nền đá sụp xuống dưới chân bạn.\nBạn nhận **{damage} sát thương**.\nHP: **{player.hp}/{player.max_hp}**",
                discord.Color.red(),
            )
        )

    @app_commands.command(name="fight", description="Bắt đầu combat với quái ở khu vực hiện tại")
    async def fight(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        busy = is_busy(player)
        if busy:
            await interaction.response.send_message(busy, ephemeral=True)
            return

        area = AREAS[player.area]
        if not area["enemies"]:
            await interaction.response.send_message("Khu vực này không có quái thường.", ephemeral=True)
            return

        enemy_key = random.choice(area["enemies"])
        await self._start_combat_response(interaction, player, enemy_key, is_boss=False)

    @app_commands.command(name="combat", description="Tiếp tục combat đang diễn ra")
    async def active_combat(self, interaction: discord.Interaction):
        player = require_player(interaction)
        session = get_combat(interaction.user.id)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        if not session:
            if player.status == "combat":
                player.status = "idle"
                save_player(player)
            await interaction.response.send_message("Bạn không có combat đang diễn ra.", ephemeral=True)
            return

        await interaction.response.send_message(
            embed=ui.combat_embed(player, session),
            view=CombatView(player.discord_id),
        )

    @app_commands.command(name="boss", description="Thách đấu boss của khu vực hiện tại")
    async def boss(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        busy = is_busy(player)
        if busy:
            await interaction.response.send_message(busy, ephemeral=True)
            return

        area = AREAS[player.area]
        boss_key = area.get("boss")
        if not boss_key:
            await interaction.response.send_message("Khu vực này không có boss.", ephemeral=True)
            return

        await self._start_combat_response(interaction, player, boss_key, is_boss=True)

    @app_commands.command(name="merge", description="Merge/nâng cấp trang bị bằng ID")
    async def merge(self, interaction: discord.Interaction, item_id: int):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        if player.status == "combat":
            await interaction.response.send_message("⚔️ Không thể merge trong combat.", ephemeral=True)
            return

        result = systems.upgrade_item(player, item_id)
        save_player(player)

        await interaction.response.send_message(
            embed=ui.result_embed(result.title, result.message, result.ok),
            ephemeral=True,
        )

    @app_commands.command(name="dismantle", description="Phân rã trang bị bằng ID")
    async def dismantle(self, interaction: discord.Interaction, item_id: int):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        if player.status == "combat":
            await interaction.response.send_message("⚔️ Không thể phân rã trong combat.", ephemeral=True)
            return

        result = systems.dismantle_item(player, item_id)
        if result.ok:
            save_player(player)

        await interaction.response.send_message(
            embed=ui.result_embed(result.title, result.message, result.ok),
            ephemeral=True,
        )

    @app_commands.command(name="lockitem", description="Khóa/mở khóa item bằng ID")
    async def lockitem(self, interaction: discord.Interaction, item_id: int):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        result = systems.toggle_lock_item(player, item_id)
        if result.ok:
            save_player(player)

        await interaction.response.send_message(
            embed=ui.result_embed(result.title, result.message, result.ok),
            ephemeral=True,
        )

    @app_commands.command(name="map", description="Xem bản đồ thế giới")
    async def map(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        await interaction.response.send_message(embed=ui.map_embed(player), ephemeral=True)

    @app_commands.command(name="travel", description="Di chuyển sang khu vực đã mở khóa")
    async def travel(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        busy = is_busy(player)
        if busy:
            await interaction.response.send_message(busy, ephemeral=True)
            return

        await interaction.response.send_message(
            embed=ui.map_embed(player),
            view=TravelView(player),
            ephemeral=True,
        )

    @app_commands.command(name="recover", description="Thu hồi Echo of Death")
    async def recover(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        if player.death_echo_souls <= 0:
            await interaction.response.send_message("Bạn không có Echo of Death.", ephemeral=True)
            return

        if player.area != player.death_echo_area:
            area = AREAS.get(player.death_echo_area, {"name": player.death_echo_area})
            await interaction.response.send_message(
                f"Echo của bạn đang ở **{area['name']}**. Hãy `/travel` đến đó trước.",
                ephemeral=True,
            )
            return

        recovered = player.death_echo_souls
        player.souls += recovered
        player.death_echo_souls = 0
        player.death_echo_area = None
        save_player(player)

        await interaction.response.send_message(f"☠️ Bạn đã thu hồi **{recovered} Souls**.")

    @app_commands.command(name="daily", description="Nhận daily reward mỗi ngày")
    async def daily(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        result = systems.claim_daily_reward(player)
        save_player(player)
        await interaction.response.send_message(
            embed=ui.result_embed(result.title, result.message, result.ok),
            ephemeral=True,
        )

    @app_commands.command(name="quests", description="Xem daily quests")
    async def quests(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        systems.refresh_daily_quests(player)
        save_player(player)
        await interaction.response.send_message(embed=ui.quests_embed(player), ephemeral=True)

    @app_commands.command(name="claimquests", description="Nhận thưởng daily quests đã hoàn thành")
    async def claimquests(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        result = systems.claim_completed_quests(player)
        save_player(player)
        await interaction.response.send_message(
            embed=ui.result_embed(result.title, result.message, result.ok),
            ephemeral=True,
        )

    @app_commands.command(name="shop", description="Xem shop")
    async def shop(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        await interaction.response.send_message(embed=ui.shop_embed(player), ephemeral=True)

    @app_commands.command(name="buy", description="Mua item trong shop")
    async def buy(self, interaction: discord.Interaction, shop_id: int, amount: int = 1):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        busy = is_busy(player)
        if busy:
            await interaction.response.send_message(busy, ephemeral=True)
            return

        result = systems.buy_shop_item(player, shop_id, amount)
        if result.ok:
            save_player(player)

        await interaction.response.send_message(
            embed=ui.result_embed(result.title, result.message, result.ok),
            ephemeral=True,
        )

    @app_commands.command(name="sell", description="Bán item bằng ID")
    async def sell(self, interaction: discord.Interaction, item_id: int):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        busy = is_busy(player)
        if busy:
            await interaction.response.send_message(busy, ephemeral=True)
            return

        result = systems.sell_item(player, item_id)
        if result.ok:
            save_player(player)

        await interaction.response.send_message(
            embed=ui.result_embed(result.title, result.message, result.ok),
            ephemeral=True,
        )

    @app_commands.command(name="dungeons", description="Xem dungeon hiện có")
    async def dungeons(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        systems.reset_dungeon_runs_if_needed(player)
        save_player(player)
        await interaction.response.send_message(embed=ui.dungeon_embed(player), ephemeral=True)

    @app_commands.command(name="dungeon", description="Vào dungeon encounter")
    async def dungeon(self, interaction: discord.Interaction, dungeon_id: str):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        result = systems.can_start_dungeon(player, dungeon_id)
        if not result.ok:
            await interaction.response.send_message(
                embed=ui.result_embed(result.title, result.message, False),
                ephemeral=True,
            )
            return

        dungeon = DUNGEONS[dungeon_id]
        player.dungeon_runs_used += 1
        player.stamina -= 15
        enemy_key = random.choice(dungeon["enemies"])
        await self._start_combat_response(
            interaction,
            player,
            enemy_key,
            is_boss=False,
            source="dungeon",
            dungeon_key=dungeon_id,
        )

    @app_commands.command(name="leaderboard", description="Xem bảng xếp hạng")
    async def leaderboard(self, interaction: discord.Interaction, metric: str = "level"):
        allowed = {"level", "souls", "gold", "kills", "bosses", "dungeons"}
        if metric not in allowed:
            await interaction.response.send_message(
                "Metric hợp lệ: level, souls, gold, kills, bosses, dungeons",
                ephemeral=True,
            )
            return

        players = list_players(100)
        await interaction.response.send_message(embed=ui.leaderboard_embed(players, metric))

    @app_commands.command(name="devkit", description="Admin test: nhận tài nguyên để test nhanh")
    @app_commands.default_permissions(administrator=True)
    async def devkit(self, interaction: discord.Interaction):
        player = require_player(interaction)

        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return

        player.souls += 1500
        player.gold += 500
        systems.add_item(player, "iron_shard", 20)
        systems.add_item(player, "ember_stone", 8)
        systems.add_item(player, "ancient_core", 2)
        systems.add_item(player, "healing_herb", 10)
        systems.add_item(player, "stamina_draught", 5)
        systems.add_item(player, "camp_kit", 3)
        systems.add_item(player, "ashen_token", 3)
        systems.add_item(player, "ring_of_embers", 1)

        save_player(player)

        await interaction.response.send_message(
            embed=ui.result_embed(
                "Đã nhận Dev Kit",
                "Souls +1500\nGold +500\nIron Shard x20\nEmber Stone x8\nAncient Core x2\nHealing Herb x10\nRing of Embers x1",
                True,
            ),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(RPG(bot))
