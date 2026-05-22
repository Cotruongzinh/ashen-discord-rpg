import discord
from discord import app_commands
from discord.ext import commands

from game.permissions import is_ai_admin
from game.ai_content import (
    list_generated_content,
    get_generated_content,
    mark_content_status,
    apply_generated_payload,
    list_batch_records,
    mark_batch_status,
)


def _is_admin(interaction: discord.Interaction) -> bool:
    return is_ai_admin(interaction.user.id)


def _short(text: str, limit: int = 220) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _content_title(payload: dict) -> str:
    data = payload.get("data") or {}
    return (
        data.get("name")
        or data.get("title")
        or data.get("area_name")
        or payload.get("name")
        or payload.get("key")
        or payload.get("id")
        or "Untitled"
    )


def _content_description(payload: dict) -> str:
    data = payload.get("data") or {}
    pieces = []

    for field in ["description", "lore", "intro", "combat_intro", "hook", "summary", "flavor"]:
        if data.get(field):
            pieces.append(f"**{field}:** {_short(data.get(field), 260)}")

    if not pieces:
        pieces.append(_short(str(data), 500))

    return "\n".join(pieces)


def build_content_embed(payload: dict, index: int = 1, total: int = 1) -> discord.Embed:
    data = payload.get("data") or {}
    content_type = payload.get("content_type", "unknown")
    status = payload.get("status", "unknown")
    key = payload.get("key", payload.get("id", "unknown"))
    title = _content_title(payload)

    color = {
        "draft": discord.Color.orange(),
        "approved": discord.Color.green(),
        "rejected": discord.Color.red(),
    }.get(status, discord.Color.blurple())

    embed = discord.Embed(
        title=f"🧠 AI Review [{index}/{total}] — {title}",
        description=_content_description(payload),
        color=color,
    )

    embed.add_field(name="Doc ID", value=f"`{payload.get('id', 'unknown')}`", inline=False)
    embed.add_field(name="Type", value=f"`{content_type}`", inline=True)
    embed.add_field(name="Status", value=f"`{status}`", inline=True)
    embed.add_field(name="Key", value=f"`{key}`", inline=True)

    if data.get("rarity"):
        embed.add_field(name="Rarity", value=str(data.get("rarity")), inline=True)
    if data.get("level") or data.get("recommended_level"):
        embed.add_field(name="Level", value=str(data.get("level") or data.get("recommended_level")), inline=True)
    if data.get("theme"):
        embed.add_field(name="Theme", value=str(data.get("theme")), inline=True)
    if data.get("area"):
        embed.add_field(name="Area", value=str(data.get("area")), inline=True)

    stats = []
    for field in ["attack", "defense", "crit", "hp", "xp", "souls", "gold"]:
        if field in data:
            stats.append(f"{field.upper()}: **{data[field]}**")
    if stats:
        embed.add_field(name="Game Stats", value="\n".join(stats), inline=False)

    if payload.get("batch_id"):
        embed.add_field(name="Batch", value=f"`{payload.get('batch_id')}`", inline=False)

    embed.set_footer(text="Approve để đưa content vào runtime game. Reject nếu nội dung không ổn.")
    return embed


class AIReviewView(discord.ui.View):
    def __init__(self, owner_id: int, content_type: str | None, status: str, page: int = 0):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.content_type = None if content_type in [None, "all"] else content_type
        self.status = status
        self.page = max(0, page)
        self.items = list_generated_content(
            content_type=self.content_type,
            status=self.status,
            limit=25,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("🔒 Menu review này không phải của bạn.", ephemeral=True)
            return False
        if not _is_admin(interaction):
            await interaction.response.send_message("Chỉ AI owner trong AI_ADMIN_IDS mới dùng được AI Review.", ephemeral=True)
            return False
        return True

    def current(self) -> dict | None:
        if not self.items:
            return None
        self.page = max(0, min(self.page, len(self.items) - 1))
        return self.items[self.page]

    def render(self) -> tuple[discord.Embed, "AIReviewView"]:
        payload = self.current()
        if not payload:
            embed = discord.Embed(
                title="🧠 AI Review",
                description=f"Không có content nào với status `{self.status}`.",
                color=discord.Color.dark_grey(),
            )
            return embed, self

        return build_content_embed(payload, self.page + 1, len(self.items)), self

    @discord.ui.button(label="Prev", emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.items:
            self.page = (self.page - 1) % len(self.items)
        embed, view = self.render()
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Next", emoji="➡️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.items:
            self.page = (self.page + 1) % len(self.items)
        embed, view = self.render()
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Approve", emoji="✅", style=discord.ButtonStyle.success)
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        payload = self.current()
        if not payload:
            await interaction.response.send_message("Không có content để approve.", ephemeral=True)
            return

        updated = mark_content_status(payload["id"], "approved")
        if updated:
            apply_generated_payload(updated)

        self.items = list_generated_content(
            content_type=self.content_type,
            status=self.status,
            limit=25,
        )
        if self.page >= len(self.items):
            self.page = max(0, len(self.items) - 1)

        if self.items:
            embed, view = self.render()
            embed.add_field(name="✅ Approved", value=f"Đã duyệt `{payload['id']}`.", inline=False)
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            embed = discord.Embed(
                title="✅ Approved",
                description=f"Đã duyệt `{payload['id']}`. Không còn content draft nào.",
                color=discord.Color.green(),
            )
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Reject", emoji="❌", style=discord.ButtonStyle.danger)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        payload = self.current()
        if not payload:
            await interaction.response.send_message("Không có content để reject.", ephemeral=True)
            return

        mark_content_status(payload["id"], "rejected")

        self.items = list_generated_content(
            content_type=self.content_type,
            status=self.status,
            limit=25,
        )
        if self.page >= len(self.items):
            self.page = max(0, len(self.items) - 1)

        if self.items:
            embed, view = self.render()
            embed.add_field(name="❌ Rejected", value=f"Đã reject `{payload['id']}`.", inline=False)
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            embed = discord.Embed(
                title="❌ Rejected",
                description=f"Đã reject `{payload['id']}`. Không còn content draft nào.",
                color=discord.Color.red(),
            )
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.primary)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.items = list_generated_content(
            content_type=self.content_type,
            status=self.status,
            limit=25,
        )
        embed, view = self.render()
        await interaction.response.edit_message(embed=embed, view=view)


class AIBatchReviewView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.page = 0
        self.batches = list_batch_records(limit=25)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("🔒 Menu batch này không phải của bạn.", ephemeral=True)
            return False
        if not _is_admin(interaction):
            await interaction.response.send_message("Chỉ AI owner trong AI_ADMIN_IDS mới dùng được AI Batch Review.", ephemeral=True)
            return False
        return True

    def current(self) -> dict | None:
        if not self.batches:
            return None
        self.page = max(0, min(self.page, len(self.batches) - 1))
        return self.batches[self.page]

    def render(self) -> tuple[discord.Embed, "AIBatchReviewView"]:
        batch = self.current()
        if not batch:
            embed = discord.Embed(
                title="🧠 AI Batch Review",
                description="Chưa có batch nào.",
                color=discord.Color.dark_grey(),
            )
            return embed, self

        status = batch.get("status", "unknown")
        color = {
            "draft": discord.Color.orange(),
            "approved": discord.Color.green(),
            "rejected": discord.Color.red(),
        }.get(status, discord.Color.blurple())

        embed = discord.Embed(
            title=f"🧠 AI Batch [{self.page + 1}/{len(self.batches)}]",
            description=(
                f"Batch ID: `{batch.get('id')}`\n"
                f"Theme: **{batch.get('theme', 'unknown')}**\n"
                f"Area: `{batch.get('area', 'unknown')}`\n"
                f"Level: `{batch.get('level', 'unknown')}`\n"
                f"Status: `{status}`"
            ),
            color=color,
        )

        for field in ["item_ids", "enemy_ids", "area_ids", "encounter_ids"]:
            values = batch.get(field) or []
            if values:
                embed.add_field(
                    name=field,
                    value="\n".join(f"`{x}`" for x in values[:8]) + (f"\n...+{len(values)-8}" if len(values) > 8 else ""),
                    inline=False,
                )

        embed.set_footer(text="Approve batch để duyệt tất cả content trong batch.")
        return embed, self

    @discord.ui.button(label="Prev", emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.batches:
            self.page = (self.page - 1) % len(self.batches)
        embed, view = self.render()
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Next", emoji="➡️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.batches:
            self.page = (self.page + 1) % len(self.batches)
        embed, view = self.render()
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Approve Batch", emoji="✅", style=discord.ButtonStyle.success)
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        batch = self.current()
        if not batch:
            await interaction.response.send_message("Không có batch để approve.", ephemeral=True)
            return

        result = mark_batch_status(batch["id"], "approved")

        approved_content = list_generated_content(status="approved", limit=300)
        applied = 0
        for payload in approved_content:
            if payload.get("batch_id") == batch["id"]:
                if apply_generated_payload(payload):
                    applied += 1

        self.batches = list_batch_records(limit=25)
        embed, view = self.render()
        embed.add_field(
            name="✅ Batch Approved",
            value=f"Updated: **{result.get('updated', 0)}** content\nApplied runtime: **{applied}**",
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Reject Batch", emoji="❌", style=discord.ButtonStyle.danger)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        batch = self.current()
        if not batch:
            await interaction.response.send_message("Không có batch để reject.", ephemeral=True)
            return

        result = mark_batch_status(batch["id"], "rejected")

        self.batches = list_batch_records(limit=25)
        embed, view = self.render()
        embed.add_field(
            name="❌ Batch Rejected",
            value=f"Updated: **{result.get('updated', 0)}** content",
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.primary)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.batches = list_batch_records(limit=25)
        embed, view = self.render()
        await interaction.response.edit_message(embed=embed, view=view)


class AIReview(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ai_review", description="Review AI generated content bằng button")
    @app_commands.describe(
        content_type="Loại content cần review",
        status="Trạng thái content",
        private="Chỉ bạn thấy menu review"
    )
    @app_commands.choices(
        content_type=[
            app_commands.Choice(name="All", value="all"),
            app_commands.Choice(name="Item", value="item"),
            app_commands.Choice(name="Enemy", value="enemy"),
            app_commands.Choice(name="Area", value="area"),
            app_commands.Choice(name="Boss", value="boss"),
            app_commands.Choice(name="Encounter", value="encounter"),
        ],
        status=[
            app_commands.Choice(name="Draft", value="draft"),
            app_commands.Choice(name="Approved", value="approved"),
            app_commands.Choice(name="Rejected", value="rejected"),
        ],
    )
    async def ai_review(
        self,
        interaction: discord.Interaction,
        content_type: app_commands.Choice[str] = None,
        status: app_commands.Choice[str] = None,
        private: bool = True,
    ):
        if not _is_admin(interaction):
            await interaction.response.send_message("Chỉ AI owner trong AI_ADMIN_IDS mới dùng được lệnh này.", ephemeral=True)
            return

        ct = content_type.value if content_type else "all"
        st = status.value if status else "draft"

        view = AIReviewView(interaction.user.id, ct, st)
        embed, view = view.render()

        await interaction.response.send_message(embed=embed, view=view, ephemeral=private)

    @app_commands.command(name="ai_review_batches", description="Review AI generation batches bằng button")
    @app_commands.describe(private="Chỉ bạn thấy menu review")
    async def ai_review_batches(self, interaction: discord.Interaction, private: bool = True):
        if not _is_admin(interaction):
            await interaction.response.send_message("Chỉ AI owner trong AI_ADMIN_IDS mới dùng được lệnh này.", ephemeral=True)
            return

        view = AIBatchReviewView(interaction.user.id)
        embed, view = view.render()

        await interaction.response.send_message(embed=embed, view=view, ephemeral=private)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIReview(bot))
