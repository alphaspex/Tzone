from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    discord_application_id: int | None
    discord_guild_id: int | None
    cloudflare_account_id: str
    d1_database_id: str
    cloudflare_api_token: str
    nickname_updates_per_second: float = 40.0
    nickname_window_minutes: int = 10
    nickname_max_attempts: int = 4

    @classmethod
    def from_env(cls) -> "Settings":
        def optional_int(name: str) -> int | None:
            value = os.getenv(name, "").strip()
            return int(value) if value else None

        token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
        database_id = os.getenv("CLOUDFLARE_D1_DATABASE_ID", "").strip()
        api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
        missing = [
            name for name, value in (
                ("DISCORD_BOT_TOKEN", token),
                ("CLOUDFLARE_ACCOUNT_ID", account_id),
                ("CLOUDFLARE_D1_DATABASE_ID", database_id),
                ("CLOUDFLARE_API_TOKEN", api_token),
            ) if not value
        ]
        if missing:
            raise ValueError("Missing required environment variables: " + ", ".join(missing))

        return cls(
            discord_bot_token=token,
            discord_application_id=optional_int("DISCORD_APPLICATION_ID"),
            discord_guild_id=optional_int("DISCORD_GUILD_ID"),
            cloudflare_account_id=account_id,
            d1_database_id=database_id,
            cloudflare_api_token=api_token,
            nickname_updates_per_second=max(
                1.0, min(40.0, float(os.getenv("NICKNAME_UPDATES_PER_SECOND", "40")))
            ),
            nickname_window_minutes=max(
                1, min(10, int(os.getenv("NICKNAME_WINDOW_MINUTES", "10")))
            ),
            nickname_max_attempts=4,
        )
