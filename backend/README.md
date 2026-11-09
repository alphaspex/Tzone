# Tzone Bot

One Python Discord bot in one Docker container, using the existing Cloudflare D1 database directly. No application Worker or second container is required.

## Features

- /set_zone: native multi-step Discord modal for an IANA timezone and hourly Free/Chat-only intervals across all seven days.
- /delete_zone: delete your saved timezone and schedule.
- /whos_free and /whos_chat: private live availability lists, 10 members per page.
- /weekly_free and /weekly_chat: one weekday per page, hourly heatmap and best Free overlap.
- Nicknames preserve each member's server name and append their local hour, e.g. Alex | 2 PM.
- Each member is updated in their own local :50–:59 window. A :00–:04 recovery window catches missed updates after a restart.
- Nickname jobs and attempt counts are persisted in D1. Each member gets at most four total attempts per local hourly cycle.
- Nickname requests are paced at a maximum target of 40 per second. discord.py still enforces Discord's dynamic route and global rate limits.

## Schedule format

Enter whole-hour ranges in 24-hour format: 09-14, 18-21. The end hour is exclusive. Leave a field blank when unavailable. Overnight ranges such as 22-02 are split across midnight. Free and Chat-only ranges cannot overlap.

Nicknames use a 12-hour clock without minutes: Alex | 2 PM. The bot prepares the next local hour during the last ten minutes before the hour changes.

## Setup

1. Create a Discord application and bot.
2. Enable the Server Members Intent in the Discord Developer Portal.
3. Invite the bot with the bot and applications.commands scopes. Grant Manage Nicknames.
4. Put the bot's highest role above the members whose nicknames it must change.
5. Copy .env.example to .env and fill in the Discord bot token and Cloudflare API token. The account and D1 database IDs are already filled in.
6. The Cloudflare API token needs Account D1 Read and Account D1 Write permissions.
7. The connected tzone-db already contains the 0002 tables and indexes; I verified them in D1. For a fresh database, apply migrations/0001_initial.sql and then migrations/0002_availability_and_nicknames.sql.
8. Build and run from the backend directory:

    docker build -t tzone-bot .
    docker run -d --name tzone-bot --restart unless-stopped --env-file .env tzone-bot

Set DISCORD_GUILD_ID while developing to sync slash commands to one server immediately. Leave it empty for global command registration.

Run the standard-library unit tests from the backend directory:

    PYTHONPATH=src python -m unittest discover -s tests -v

## D1 API note

This project uses the D1 REST query API directly, as selected. Cloudflare documents that this API is primarily intended for administrative use and shares the account-wide Cloudflare API request limit. The bot batches queue-state writes to reduce API calls. If usage outgrows that allowance, the database transport can be replaced behind the D1Client boundary.

## Important behavior

- Discord's nickname route limits are dynamic. 40/s is a target ceiling, not a guaranteed endpoint allowance.
- The bot honors discord.py's rate-limit handling. Discord may slow the queue below 40/s.
- Four attempts means four total attempts, including the first. Failures are stored in D1 and retried; a terminal failure is retained until the next local hourly cycle.
- Nickname updates require Manage Nicknames and a role hierarchy that permits editing the target member.
- The bot needs Server Members Intent enabled both in code and in the Developer Portal.
- Do not commit .env or any Discord/Cloudflare tokens.

## File boundaries

- tzone/config.py: environment values in, validated settings out.
- tzone/d1.py: SQL and parameters in, rows or completed batch out.
- tzone/schedules.py: timezone/schedule persistence.
- tzone/availability.py: schedule input and timezone conversion.
- tzone/nickname_queue.py: due nickname jobs in, persisted attempt/success/failure state out.
- tzone/discord_commands.py: Discord interactions in, native Discord responses out.
- tzone/bot.py: connects commands and scheduled work.
- tzone/__main__.py: process startup and shutdown.
