import asyncio
import logging

import discord
from dotenv import load_dotenv

from .config import Settings
from .d1 import D1Client


async def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    logging.basicConfig(level=logging.INFO)

    intents = discord.Intents.default()
    intents.members = True
    client = discord.Client(intents=intents)
    db = D1Client(
        settings.cloudflare_account_id,
        settings.d1_database_id,
        settings.cloudflare_api_token,
    )

    @client.event
    async def on_ready() -> None:
        logging.info("Tzone connected as %s", client.user)

    try:
        await client.start(settings.discord_bot_token)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
