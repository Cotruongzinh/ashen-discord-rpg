import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")

if not TOKEN:
    raise RuntimeError("Thiếu DISCORD_TOKEN trong file .env")

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
)

# Load order matters: content_pack updates game.data before gameplay cogs use it.
ESSENTIAL_EXTENSIONS = [
    "cogs.content_pack",
    "cogs.rpg",
]

OPTIONAL_EXTENSIONS = [
    "cogs.story",
    "cogs.delve",
    "cogs.menu",
    "cogs.qol",
    "cogs.account",
    "cogs.ai",
    "cogs.ai_world",
    "cogs.ai_review",
]


@bot.event
async def on_ready():
    print(f"Bot đã đăng nhập: {bot.user}")

    # Avoid syncing repeatedly if Discord reconnects.
    if getattr(bot, "_ashen_synced", False):
        return

    try:
        if TEST_GUILD_ID:
            guild = discord.Object(id=int(TEST_GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"Đã sync {len(synced)} slash command trong test guild.")
        else:
            synced = await bot.tree.sync()
            print(f"Đã sync {len(synced)} slash command global.")
        bot._ashen_synced = True
    except Exception as e:
        print("Lỗi sync command:", e)


async def load_all_extensions():
    for extension in ESSENTIAL_EXTENSIONS:
        await bot.load_extension(extension)
        print(f"Loaded extension: {extension}")

    for extension in OPTIONAL_EXTENSIONS:
        try:
            await bot.load_extension(extension)
            print(f"Loaded extension: {extension}")
        except commands.ExtensionNotFound:
            print(f"Skipped missing optional extension: {extension}")
        except commands.NoEntryPointError:
            print(f"Skipped optional extension without setup(): {extension}")
        except Exception as e:
            print(f"Failed to load optional extension {extension}: {e}")
            raise


async def main():
    async with bot:
        await load_all_extensions()
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
