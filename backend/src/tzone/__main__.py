import asyncio
import logging

from dotenv import load_dotenv

from .bot import TzoneBot
from .config import Settings
from .d1 import D1Client


async def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    db = D1Client(
        settings.cloudflare_account_id,
        settings.d1_database_id,
        settings.cloudflare_api_token,
    )
    bot = TzoneBot(settings, db)
    try:
        await bot.start(settings.discord_bot_token)
    finally:
        await bot.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
