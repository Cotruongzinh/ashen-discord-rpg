import os
import random
import discord
from discord import app_commands
from discord.ext import commands, tasks

from game import ai_generator, ai_world, combat, systems, ui
from game.ai_content import apply_generated_payload, list_generated_content, mark_batch_status
from game.ai_world import generate_world_batch, get_ai_auto_config, get_cached_encounter, list_batches
from game.data import AREAS
from game.permissions import is_ai_admin, require_ai_admin
from game.storage import get_player, save_player, save_combat


def _result_lines(results: list[dict], max_lines: int = 12) -> str:
    if not results:
        return "Không có content nào được tạo."
    lines = []
    for row in results[:max_lines]:
        lines.append(
            f"`{row.get('doc_id')}`\n"
            f"└ **{row.get('name') or row.get('key')}** • `{row.get('content_type')}` • `{row.get('status')}`"
        )
    if len(results) > max_lines:
        lines.append(f"... và {len(results) - max_lines} nội dung khác.")
    return "\n".join(lines)


class AIWorldCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_cfg = get_ai_auto_config()
        if self.auto_cfg.enabled:
            self.auto_generate_loop.change_interval(minutes=self.auto_cfg.interval_minutes)
            self.auto_generate_loop.start()

    def cog_unload(self):
        if self.auto_generate_loop.is_running():
            self.auto_generate_loop.cancel()

    @tasks.loop(minutes=720)
    async def auto_generate_loop(self):
        cfg = get_ai_auto_config()
        if not cfg.enabled:
            return
        try:
            await generate_world_batch(
                created_by=0,
                theme=cfg.theme,
                level=cfg.level,
                area_key=cfg.area,
                item_count=cfg.items,
                enemy_count=cfg.enemies,
                area_count=0,
                encounter_count=cfg.encounters,
                auto_approve=cfg.auto_approve,
            )
            print("AI auto generation completed.")
        except Exception as e:
            print(f"AI auto generation failed: {e}")

    @auto_generate_loop.before_loop
    async def before_auto_generate_loop(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="ai_auto_status", description="Admin: xem trạng thái AI auto generation")
    @app_commands.default_permissions(administrator=True)
    async def ai_auto_status(self, interaction: discord.Interaction):
        cfg = get_ai_auto_config()
        embed = ui.basic_embed(
            "🧠 AI Auto Generation",
            (
                f"Enabled: **{cfg.enabled}**\n"
                f"Loop running: **{self.auto_generate_loop.is_running()}**\n"
                f"Interval: **{cfg.interval_minutes} phút**\n"
                f"Theme: **{cfg.theme}**\n"
                f"Area: `{cfg.area}`\n"
                f"Level: **{cfg.level}**\n"
                f"Items/Enemies/Encounters: **{cfg.items}/{cfg.enemies}/{cfg.encounters}**\n"
                f"Auto approve: **{cfg.auto_approve}**\n\n"
                "Mặc định nên để auto approve = False nếu server có nhiều người chơi."
            ),
            discord.Color.purple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ai_seed_world", description="Admin: AI tạo một gói nội dung thế giới mới")
    @app_commands.default_permissions(administrator=True)
    async def ai_seed_world(
        self,
        interaction: discord.Interaction,
        theme: str = "grave bell",
        level: int = 5,
        area: str = "forgotten_catacomb",
        items: int = 3,
        enemies: int = 3,
        areas: int = 0,
        encounters: int = 2,
        auto_approve: bool = False,
        unlock_area_for_you: bool = False,
    ):
        if not await require_ai_admin(interaction):
            return
        if not await require_ai_admin(interaction):
            return
        if area and area not in AREAS:
            await interaction.response.send_message(
                "Area không tồn tại. Để trống hoặc dùng area đang có, ví dụ `forgotten_catacomb`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            batch = await generate_world_batch(
                created_by=interaction.user.id,
                theme=theme,
                level=level,
                area_key=area,
                item_count=items,
                enemy_count=enemies,
                area_count=areas,
                encounter_count=encounters,
                auto_approve=auto_approve,
            )
        except Exception as e:
            await interaction.followup.send(f"AI seed world lỗi: `{e}`", ephemeral=True)
            return

        if auto_approve and unlock_area_for_you:
            player = get_player(interaction.user.id)
            if player:
                changed = False
                for row in batch.get("results", []):
                    if row.get("content_type") == "area" and row.get("key") not in player.unlocked_areas:
                        player.unlocked_areas.append(row.get("key"))
                        changed = True
                if changed:
                    save_player(player)

        embed = ui.basic_embed(
            "🧠 AI World Batch Created",
            (
                f"Batch ID: `{batch['batch_id']}`\n"
                f"Theme: **{batch['theme']}**\n"
                f"Status: **{batch['status']}**\n"
                f"Target area: `{batch['area_key']}`\n\n"
                f"{_result_lines(batch.get('results', []))}\n\n"
                "Nếu là draft, dùng `/ai_batch_approve batch_id:<id>` để duyệt cả batch."
            ),
            discord.Color.purple(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ai_batch_approve", description="Admin: duyệt toàn bộ AI batch và đưa vào runtime")
    @app_commands.default_permissions(administrator=True)
    async def ai_batch_approve(self, interaction: discord.Interaction, batch_id: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = mark_batch_status(batch_id, "approved")
        applied = {"ok": 0, "failed": 0}
        for payload in list_generated_content(status="approved", limit=300):
            if payload.get("batch_id") != batch_id:
                continue
            if apply_generated_payload(payload):
                applied["ok"] += 1
            else:
                applied["failed"] += 1
        await interaction.followup.send(
            embed=ui.result_embed(
                "AI batch approved",
                f"Batch `{batch_id}` đã duyệt **{result['updated']}** document. Applied runtime: `{applied}`",
                True,
            ),
            ephemeral=True,
        )

    @app_commands.command(name="ai_batch_reject", description="Admin: reject toàn bộ AI batch")
    @app_commands.default_permissions(administrator=True)
    async def ai_batch_reject(self, interaction: discord.Interaction, batch_id: str):
        result = mark_batch_status(batch_id, "rejected")
        await interaction.response.send_message(
            embed=ui.result_embed(
                "AI batch rejected",
                f"Batch `{batch_id}` đã reject **{result['updated']}** document.",
                True,
            ),
            ephemeral=True,
        )

    @app_commands.command(name="ai_batches", description="Admin: xem các AI batch gần đây")
    @app_commands.default_permissions(administrator=True)
    async def ai_batches(self, interaction: discord.Interaction):
        rows = list_batches(limit=8)
        if not rows:
            await interaction.response.send_message("Chưa có AI batch nào.", ephemeral=True)
            return
        lines = []
        for row in rows:
            counts = row.get("counts", {})
            lines.append(
                f"`{row['id']}`\n"
                f"└ **{row.get('theme')}** • `{row.get('status')}` • "
                f"A/I/E/X = {counts.get('areas', 0)}/{counts.get('items', 0)}/{counts.get('enemies', 0)}/{counts.get('encounters', 0)}"
            )
        await interaction.response.send_message(
            embed=ui.basic_embed("🧠 AI Batches", "\n".join(lines), discord.Color.purple()),
            ephemeral=True,
        )

    @app_commands.command(name="ai_cache_encounters", description="Admin: tạo sẵn AI encounter text để dùng nhanh")
    @app_commands.default_permissions(administrator=True)
    async def ai_cache_encounters(
        self,
        interaction: discord.Interaction,
        area: str = "forgotten_catacomb",
        theme: str = "grave bell",
        level: int = 5,
        count: int = 3,
        auto_approve: bool = True,
    ):
        if not await require_ai_admin(interaction):
            return
        if not await require_ai_admin(interaction):
            return
        if not await require_ai_admin(interaction):
            return
        if not await require_ai_admin(interaction):
            return
        if area not in AREAS:
            await interaction.response.send_message("Area không tồn tại.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        batch_id = f"encounter_batch_{int(discord.utils.utcnow().timestamp())}_{random.randint(1000, 9999)}"
        rows = await ai_world.generate_encounter_cache(
            created_by=interaction.user.id,
            area_key=area,
            theme=theme,
            level=level,
            count=count,
            auto_approve=auto_approve,
            batch_id=batch_id,
        )
        embed = ui.basic_embed(
            "🧠 AI Encounter Cache",
            _result_lines([
                {"doc_id": r["doc_id"], "content_type": "encounter", "key": r["key"], "name": r["data"].get("title"), "status": r["status"]}
                for r in rows
            ]),
            discord.Color.purple(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="aiexploreplus", description="Khám phá AI ưu tiên dùng cache để phản hồi nhanh hơn")
    async def aiexploreplus(self, interaction: discord.Interaction, theme: str = "", use_live_ai_if_empty: bool = False):
        # Người chơi thường được dùng approved/cache content.
        # Chỉ AI owner được bật live AI fallback để tránh ai cũng tiêu API.
        if use_live_ai_if_empty and not is_ai_admin(interaction.user.id):
            use_live_ai_if_empty = False

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
            await interaction.response.send_message("Khu vực này chưa có enemy để dựng encounter.", ephemeral=True)
            return
        if player.stamina < 10:
            await interaction.response.send_message("🟩 Bạn không đủ stamina để khám phá. Hãy dùng `/rest`.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        encounter = get_cached_encounter(player.area)
        source_text = "AI cache"
        if not encounter and use_live_ai_if_empty:
            encounter, _prompt = await ai_generator.generate_encounter(player.area, player.level, theme)
            source_text = "live AI"
        if not encounter:
            encounter = {
                "title": "Bóng tối chuyển động",
                "description": "Bạn tiến sâu vào khu vực trước mặt. Không khí lạnh đi, và một kẻ địch trồi ra từ màn sương.",
                "choice_hint": "Bạn siết chặt vũ khí.",
                "mood": "fallback",
            }
            source_text = "fallback"

        player.stamina -= 10
        systems.ensure_player_runtime(player)
        player.stats["explores"] = player.stats.get("explores", 0) + 1
        systems.update_quest_progress(player, "explore", 1)

        enemy_key = random.choice(area["enemies"])
        session = combat.start_combat(player, enemy_key, is_boss=False, source="explore")
        session.log.insert(0, f"🧠 {encounter.get('choice_hint', 'Bạn bước tiếp.')} ({source_text})")
        save_player(player)
        save_combat(session)

        encounter_embed = ui.basic_embed(
            f"🧠 {encounter.get('title', 'AI Encounter')}",
            encounter.get("description", "Bạn cảm thấy bóng tối đang chuyển động."),
            discord.Color.purple(),
        )
        encounter_embed.set_footer(text=f"Nguồn: {source_text}. Combat/reward vẫn do game engine kiểm soát.")
        await interaction.followup.send(embed=encounter_embed)

        from cogs.rpg import CombatView
        await interaction.followup.send(
            embed=ui.combat_embed(player, session),
            view=CombatView(player.discord_id),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AIWorldCog(bot))
