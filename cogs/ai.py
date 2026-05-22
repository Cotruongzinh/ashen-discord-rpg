import random
import discord
from discord import app_commands
from discord.ext import commands

from game import ai_generator, systems, ui, combat
from game.ai_config import get_ai_config
from game.ai_content import (
    apply_generated_payload,
    get_generated_content,
    list_generated_content,
    mark_content_status,
    save_generated_content,
)
from game.ai_runtime import load_ai_content_on_startup
from game.data import AREAS, ENEMIES, ITEMS
from game.permissions import require_ai_admin
from game.storage import get_player, save_player, save_combat


VALID_ITEM_TYPES = ["weapon", "armor", "ring", "consumable", "material"]
VALID_RARITIES = ["common", "uncommon", "rare", "epic", "legendary", "mythic"]
VALID_CONTENT_TYPES = ["item", "enemy", "boss", "area"]
VALID_STATUSES = ["draft", "approved", "rejected"]


def _short_dict_summary(data: dict) -> str:
    parts = []
    for key in ["name", "type", "rarity", "level", "archetype", "area"]:
        if key in data and data[key] is not None:
            parts.append(f"**{key}:** {data[key]}")
    desc = data.get("desc") or data.get("description")
    if desc:
        parts.append(f"**desc:** {str(desc)[:180]}")
    return "\n".join(parts) if parts else "Không có mô tả."


class AICog(commands.Cog):
    def __init__(self, bot: commands.Bot, startup_summary: dict):
        self.bot = bot
        self.startup_summary = startup_summary

    @app_commands.command(name="ai_status", description="Xem trạng thái AI generator")
    async def ai_status(self, interaction: discord.Interaction):
        cfg = get_ai_config()
        embed = ui.basic_embed(
            "🧠 AI Generator Status",
            (
                f"Enabled: **{cfg.enabled}**\n"
                f"Model: **{cfg.model}**\n"
                f"Max output tokens: **{cfg.max_output_tokens}**\n"
                f"Startup applied content: `{self.startup_summary}`\n\n"
                "AI có quyền tạo item/enemy/area/encounter, nhưng stat/reward được game engine chuẩn hóa."
            ),
            discord.Color.purple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="aigen_item", description="Admin: AI tạo item mới có kiểm soát")
    @app_commands.default_permissions(administrator=True)
    async def aigen_item(
        self,
        interaction: discord.Interaction,
        kind: str = "weapon",
        rarity: str = "rare",
        theme: str = "grave bell",
        level: int = 5,
        auto_approve: bool = False,
        give_to_you: bool = False,
    ):
        if not await require_ai_admin(interaction):
            return
        if kind not in VALID_ITEM_TYPES:
            await interaction.response.send_message(f"kind hợp lệ: {', '.join(VALID_ITEM_TYPES)}", ephemeral=True)
            return
        if rarity not in VALID_RARITIES:
            await interaction.response.send_message(f"rarity hợp lệ: {', '.join(VALID_RARITIES)}", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        key, data, prompt = await ai_generator.generate_item(kind, rarity, theme, level)
        status = "approved" if auto_approve else "draft"
        doc_id = save_generated_content(
            content_type="item",
            key=key,
            data=data,
            created_by=interaction.user.id,
            status=status,
            prompt=prompt,
        )
        if auto_approve:
            apply_generated_payload({"content_type": "item", "key": key, "data": data})

        give_text = ""
        if give_to_you and auto_approve:
            player = get_player(interaction.user.id)
            if player:
                item = systems.add_item(player, key, 1)
                save_player(player)
                give_text = f"\n🎁 Đã thêm vào inventory của bạn: `#{item.uid}` **{data['name']}**"

        embed = ui.basic_embed(
            "🧠 AI Item Generated",
            (
                f"Document: `{doc_id}`\n"
                f"Key: `{key}`\n"
                f"Status: **{status}**\n\n"
                f"{_short_dict_summary(data)}"
                f"{give_text}\n\n"
                "Nếu là draft, dùng `/ai_approve doc_id:<id>` để đưa vào game."
            ),
            discord.Color.purple(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="aigen_enemy", description="Admin: AI tạo quái hoặc boss mới có kiểm soát")
    @app_commands.default_permissions(administrator=True)
    async def aigen_enemy(
        self,
        interaction: discord.Interaction,
        archetype: str = "undead",
        theme: str = "grave bell",
        level: int = 5,
        area: str = "forgotten_catacomb",
        is_boss: bool = False,
        auto_approve: bool = False,
    ):
        if not await require_ai_admin(interaction):
            return
        if area not in AREAS:
            await interaction.response.send_message("Area không tồn tại trong runtime data.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        key, data, prompt = await ai_generator.generate_enemy(archetype, theme, level, area, is_boss=is_boss)
        content_type = "boss" if is_boss else "enemy"
        status = "approved" if auto_approve else "draft"
        doc_id = save_generated_content(
            content_type=content_type,
            key=key,
            data=data,
            created_by=interaction.user.id,
            status=status,
            prompt=prompt,
        )
        if auto_approve:
            apply_generated_payload({"content_type": content_type, "key": key, "data": data})

        embed = ui.basic_embed(
            "🧠 AI Enemy Generated",
            (
                f"Document: `{doc_id}`\n"
                f"Key: `{key}`\n"
                f"Status: **{status}**\n\n"
                f"{_short_dict_summary(data)}\n\n"
                f"HP **{data['hp']}** • ATK **{data['attack']}** • DEF **{data['defense']}**\n"
                "Nếu approved, enemy sẽ được gắn vào area tương ứng và có thể gặp trong /fight hoặc /explore."
            ),
            discord.Color.red() if is_boss else discord.Color.orange(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="aigen_area", description="Admin: AI tạo khu vực mới có kiểm soát")
    @app_commands.default_permissions(administrator=True)
    async def aigen_area(
        self,
        interaction: discord.Interaction,
        theme: str = "haunted lake",
        level: int = 8,
        auto_approve: bool = False,
        unlock_for_you: bool = True,
    ):
        if not await require_ai_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        key, data, prompt = await ai_generator.generate_area(theme, level)
        status = "approved" if auto_approve else "draft"
        doc_id = save_generated_content(
            content_type="area",
            key=key,
            data=data,
            created_by=interaction.user.id,
            status=status,
            prompt=prompt,
        )
        if auto_approve:
            apply_generated_payload({"content_type": "area", "key": key, "data": data})
            if unlock_for_you:
                player = get_player(interaction.user.id)
                if player and key not in player.unlocked_areas:
                    player.unlocked_areas.append(key)
                    save_player(player)

        embed = ui.basic_embed(
            "🧠 AI Area Generated",
            (
                f"Document: `{doc_id}`\n"
                f"Area key: `{key}`\n"
                f"Status: **{status}**\n\n"
                f"{_short_dict_summary(data)}\n\n"
                "Lưu ý: area mới cần enemy. Hãy dùng `/aigen_enemy area:<area_key> auto_approve:True`."
            ),
            discord.Color.dark_gold(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ai_content", description="Admin: xem AI content đã sinh")
    @app_commands.default_permissions(administrator=True)
    async def ai_content(self, interaction: discord.Interaction, content_type: str = "item", status: str = "draft"):
        if not await require_ai_admin(interaction):
            return
        if content_type not in VALID_CONTENT_TYPES:
            await interaction.response.send_message(f"content_type hợp lệ: {', '.join(VALID_CONTENT_TYPES)}", ephemeral=True)
            return
        if status not in VALID_STATUSES:
            await interaction.response.send_message(f"status hợp lệ: {', '.join(VALID_STATUSES)}", ephemeral=True)
            return
        items = list_generated_content(content_type=content_type, status=status, limit=10)
        if not items:
            await interaction.response.send_message("Không có content phù hợp.", ephemeral=True)
            return
        lines = []
        for payload in items:
            data = payload.get("data") or {}
            lines.append(f"`{payload['id']}`\n└ **{data.get('name', payload.get('key'))}** • `{payload.get('status')}`")
        embed = ui.basic_embed(
            "🧠 AI Content Library",
            "\n".join(lines),
            discord.Color.purple(),
        )
        embed.set_footer(text="Dùng /ai_approve doc_id hoặc /ai_reject doc_id")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ai_approve", description="Admin: duyệt AI content và đưa vào runtime game")
    @app_commands.default_permissions(administrator=True)
    async def ai_approve(self, interaction: discord.Interaction, doc_id: str):
        if not await require_ai_admin(interaction):
            return
        payload = mark_content_status(doc_id, "approved")
        if not payload:
            await interaction.response.send_message("Không tìm thấy document AI content.", ephemeral=True)
            return
        applied = apply_generated_payload(payload)
        await interaction.response.send_message(
            embed=ui.result_embed(
                "AI content approved",
                f"Document `{doc_id}` đã được duyệt. Applied runtime: **{applied}**",
                applied,
            ),
            ephemeral=True,
        )

    @app_commands.command(name="ai_reject", description="Admin: từ chối AI content")
    @app_commands.default_permissions(administrator=True)
    async def ai_reject(self, interaction: discord.Interaction, doc_id: str):
        if not await require_ai_admin(interaction):
            return
        payload = mark_content_status(doc_id, "rejected")
        if not payload:
            await interaction.response.send_message("Không tìm thấy document AI content.", ephemeral=True)
            return
        await interaction.response.send_message(f"Đã reject `{doc_id}`.", ephemeral=True)

    @app_commands.command(name="aiunlockarea", description="Admin: mở khóa area cho chính bạn")
    @app_commands.default_permissions(administrator=True)
    async def aiunlockarea(self, interaction: discord.Interaction, area_key: str):
        if not await require_ai_admin(interaction):
            return
        player = get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật.", ephemeral=True)
            return
        if area_key not in AREAS:
            await interaction.response.send_message("Area key không tồn tại trong runtime. Hãy approve area trước.", ephemeral=True)
            return
        if area_key not in player.unlocked_areas:
            player.unlocked_areas.append(area_key)
            save_player(player)
        await interaction.response.send_message(f"Đã mở khóa area `{area_key}` cho bạn.", ephemeral=True)

    @app_commands.command(name="aiexplore", description="Khám phá bằng AI encounter text có kiểm soát")
    async def aiexplore(self, interaction: discord.Interaction, theme: str = ""):
        if not await require_ai_admin(interaction):
            return
        player = get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return
        if player.status == "resting":
            await interaction.response.send_message("🌙 Bạn đang nghỉ. Dùng `/checkrest` để kiểm tra.", ephemeral=True)
            return
        if player.status == "combat":
            await interaction.response.send_message("⚔️ Bạn đang combat. Dùng `/combat` để tiếp tục.", ephemeral=True)
            return
        area = AREAS.get(player.area)
        if not area or not area.get("enemies"):
            await interaction.response.send_message("Khu vực này chưa có enemy để AI dựng encounter.", ephemeral=True)
            return
        if player.stamina < 10:
            await interaction.response.send_message("🟩 Bạn không đủ stamina để khám phá. Hãy dùng `/rest`.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        encounter, _prompt = await ai_generator.generate_encounter(player.area, player.level, theme)
        player.stamina -= 10
        systems.ensure_player_runtime(player)
        player.stats["explores"] = player.stats.get("explores", 0) + 1
        systems.update_quest_progress(player, "explore", 1)

        enemy_key = random.choice(area["enemies"])
        session = combat.start_combat(player, enemy_key, is_boss=False, source="explore")
        session.log.insert(0, f"🧠 {encounter['choice_hint']}")
        save_player(player)
        save_combat(session)

        encounter_embed = ui.basic_embed(
            f"🧠 {encounter['title']}",
            encounter["description"],
            discord.Color.purple(),
        )
        encounter_embed.set_footer(text="AI tạo tình huống; combat/reward vẫn do game engine kiểm soát.")
        await interaction.followup.send(embed=encounter_embed)

        from cogs.rpg import CombatView
        await interaction.followup.send(
            embed=ui.combat_embed(player, session),
            view=CombatView(player.discord_id),
        )


async def setup(bot: commands.Bot):
    summary = load_ai_content_on_startup()
    print(f"Loaded AI approved content: {summary}")
    await bot.add_cog(AICog(bot, summary))
