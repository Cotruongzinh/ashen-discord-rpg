import discord
from discord import app_commands
from discord.ext import commands

from game.firebase_client import get_firestore_client
from game.storage import get_player
from game.ui import profile_embed


KNOWN_SESSION_COLLECTIONS = [
    "combat_sessions",
    "dungeon_runs",
]


async def delete_character_data(discord_id: int) -> None:
    """Delete player and known active sessions from Firestore."""
    db = get_firestore_client()
    user_doc_id = str(discord_id)

    # Delete main player document.
    db.collection("players").document(user_doc_id).delete()

    # Delete active combat/dungeon sessions if they exist.
    for collection in KNOWN_SESSION_COLLECTIONS:
        db.collection(collection).document(user_doc_id).delete()


class DeleteCharacterModal(discord.ui.Modal, title="Xác nhận xóa nhân vật"):
    confirm = discord.ui.TextInput(
        label="Gõ XOA để xác nhận",
        placeholder="XOA",
        required=True,
        max_length=20,
    )

    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Đây không phải yêu cầu xóa nhân vật của bạn.",
                ephemeral=True,
            )
            return

        value = str(self.confirm.value).strip().upper()
        if value not in {"XOA", "DELETE"}:
            await interaction.response.send_message(
                "❌ Xác nhận sai. Nhân vật **chưa bị xóa**. Hãy gõ `XOA` nếu thật sự muốn xóa.",
                ephemeral=True,
            )
            return

        player = get_player(self.owner_id)
        if not player:
            await interaction.response.send_message(
                "Bạn hiện không có nhân vật để xóa.",
                ephemeral=True,
            )
            return

        await delete_character_data(self.owner_id)

        embed = discord.Embed(
            title="🗑️ Nhân vật đã bị xóa",
            description=(
                f"Nhân vật **{player.name}** đã được xóa khỏi Firebase.\n\n"
                "Bạn có thể tạo lại nhân vật mới bằng `/start`."
            ),
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AccountView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Menu này không phải của bạn.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Xem Profile", emoji="👤", style=discord.ButtonStyle.primary)
    async def view_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = get_player(self.owner_id)
        if not player:
            await interaction.response.send_message("Bạn chưa có nhân vật. Dùng `/start` trước.", ephemeral=True)
            return
        await interaction.response.send_message(embed=profile_embed(player), ephemeral=True)

    @discord.ui.button(label="Xóa nhân vật", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def delete_character(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DeleteCharacterModal(self.owner_id))


class AccountCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="account", description="Quản lý nhân vật RPG của bạn")
    async def account(self, interaction: discord.Interaction):
        player = get_player(interaction.user.id)

        if not player:
            embed = discord.Embed(
                title="👤 Account RPG",
                description="Bạn chưa có nhân vật. Dùng `/start` để tạo nhân vật mới.",
                color=discord.Color.orange(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="👤 Account RPG",
            description=(
                f"Nhân vật hiện tại: **{player.name}**\n"
                f"Level: **{player.level}**\n"
                f"Souls: **{player.souls}**\n"
                f"Gold: **{player.gold}**\n\n"
                "Bạn có thể xem profile hoặc xóa nhân vật hiện tại.\n"
                "⚠️ Xóa nhân vật là hành động không thể hoàn tác."
            ),
            color=discord.Color.dark_teal(),
        )
        await interaction.response.send_message(embed=embed, view=AccountView(interaction.user.id), ephemeral=True)

    @app_commands.command(name="deletecharacter", description="Xóa nhân vật hiện tại và bắt đầu lại")
    async def deletecharacter(self, interaction: discord.Interaction):
        player = get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message(
                "Bạn chưa có nhân vật để xóa. Dùng `/start` để tạo nhân vật.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(DeleteCharacterModal(interaction.user.id))


async def setup(bot: commands.Bot):
    await bot.add_cog(AccountCog(bot))
