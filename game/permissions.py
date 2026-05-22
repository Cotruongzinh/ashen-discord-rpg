import os
import discord


def _parse_id_set(raw: str | None) -> set[int]:
    ids: set[int] = set()

    if not raw:
        return ids

    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))

    return ids


def ai_admin_ids() -> set[int]:
    """
    Danh sách Discord User ID được quyền tạo/duyệt/reject AI content.

    .env local / Railway Variables:
    AI_ADMIN_IDS=123456789012345678,987654321098765432

    Optional fallback:
    BOT_OWNER_ID=123456789012345678
    """

    ids = _parse_id_set(os.getenv("AI_ADMIN_IDS"))
    ids |= _parse_id_set(os.getenv("BOT_OWNER_ID"))
    return ids


def is_ai_admin(user_id: int) -> bool:
    ids = ai_admin_ids()
    return int(user_id) in ids


async def require_ai_admin(interaction: discord.Interaction) -> bool:
    """
    Guard cho các lệnh AI nguy hiểm.
    Chỉ user nằm trong AI_ADMIN_IDS mới dùng được.
    """

    if is_ai_admin(interaction.user.id):
        return True

    message = (
        "🔒 Bạn không có quyền dùng chức năng AI này.\n"
        "Chỉ AI owner trong `AI_ADMIN_IDS` mới được tạo, duyệt hoặc reject nội dung AI."
    )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception:
        pass

    return False