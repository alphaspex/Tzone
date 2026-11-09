# Tzone Bot

Single Python Discord bot container with Cloudflare D1 as its external database.

## Runtime

- Python 3.12
- discord.py for the Discord Gateway and native slash-command UI
- httpx for direct Cloudflare D1 REST API access
- zoneinfo / tzdata for IANA timezone conversion
- One Docker container; no separate application Worker is required

## Build

    cp .env.example .env
    docker build -t tzone-bot .
    docker run --env-file .env --restart unless-stopped tzone-bot

Required environment variables are listed in .env.example. Keep .env private.

## Database

The existing D1 database already contains the initial timezone/message schema.
Apply migrations in order:

1. migrations/0001_initial.sql (already applied)
2. migrations/0002_availability_and_nicknames.sql

The bot uses the Cloudflare D1 REST query endpoint directly. The API token needs permission to edit/query the target D1 database.

## Current implementation boundaries

- tzone/d1.py: SQL + parameters in; rows out.
- tzone/schedules.py: schedule persistence.
- tzone/nickname_queue.py: durable nickname queue and per-member attempt tracking.
- tzone/config.py: environment configuration.
- tzone/__main__.py: process startup and Discord Gateway connection.

Nickname updates are paced at a configurable target (default 40/sec), while discord.py's route/global rate-limit handling remains authoritative. The database stores attempts and terminal failures. The queue allows at most four total attempts per member per hourly cycle.

## Not yet wired

The native slash-command flows, multi-step schedule editor, weekly views, and hourly scheduler are the next implementation layer. The exact nickname display format also needs to be decided before the queue is connected to live member edits.
