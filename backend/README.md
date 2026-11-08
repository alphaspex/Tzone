# Tzone Backend

Cloudflare Worker API + D1 database for the Tzone Discord timezone bot.

## Components

- `src/index.js`: Worker API, Discord interaction endpoint, timezone command.
- `migrations/0001_initial.sql`: D1 schema for per-server user timezones and message history.
- Cloudflare D1 database: `tzone-db`.

## Routes

- `GET /health`: health check.
- `POST /discord/interactions`: Discord HTTP interactions endpoint. Configure this as the Discord application's Interactions Endpoint URL. Set `DISCORD_PUBLIC_KEY` as a Worker secret.
- `GET /api/messages?guild_id=...`: read recent messages; requires `Authorization: Bearer <API_TOKEN>`.
- `POST /api/messages`: ingest a message; requires the same bearer token.

## Required Worker configuration

Bind the D1 database as `DB` and set these secrets:

- `DISCORD_PUBLIC_KEY`: Discord application's public key.
- `API_TOKEN`: long random token shared only with the trusted message-ingestion service and dashboard server-side integration.

Never commit Discord bot tokens or API tokens.

## Discord command

Register a slash command named `set_timezone` with one required STRING option named `timezone`. Use IANA identifiers such as `Europe/Paris`, `Africa/Algiers`, or `America/New_York`.

## Message ingestion architecture

Cloudflare Workers handle HTTP requests and Discord interactions, but do not run a permanent Discord Gateway client. To capture server messages, run a separate Discord Gateway listener (for example, a Node.js service) that forwards permitted message events to `POST /api/messages`.

Enable Discord's Message Content privileged intent only if the bot genuinely needs message text. Obtain server-admin consent, disclose what is stored, and provide retention/deletion controls before collecting message content.

## Database

The initial schema is in `migrations/0001_initial.sql`. It has been applied to the `tzone-db` database in the connected Cloudflare account.
