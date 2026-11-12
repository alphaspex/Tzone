# Meta Responses API

Minimal FastAPI gateway for Meta's native Responses API.

## Kept components

- `app/main.py`: `/v1/responses`, `/v1/responses/input_tokens`, `/v1/models`, `/health`.
- `app/provider.py`: isolated Meta HTTP and streaming transport.
- `app/model_catalog.py`: model IDs and reasoning capability validation.
- `app/config.py`: environment configuration.
- `app/store.py`: Cloudflare D1 connectivity check only. It does not create, read, or write application tables.

No frontend, harness agent, test runner, evaluator, tools, UI API, schema migrations, or application persistence remain.

## Environment variables

Existing names are preserved:

Required:
- `MODEL_API_KEY`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `D1_DATABASE_ID`

Optional:
- `META_API_BASE_URL` (default: `https://api.meta.ai/v1`)
- `MODEL_NAME` (default: `muse-spark-1.3`)
- `REQUEST_TIMEOUT_SECONDS` (default: `90`)
- `MAX_REQUEST_BYTES` (default: `16777216`)

No environment variable rename is required. D1 credentials and database ID remain configured and `/health` checks connectivity using `SELECT 1`; no application tables are needed.

## Deploy

- Repository: `alphaspex/Tzone`
- Branch: `main` after merging this cleanup
- Build context: `backend`
- Dockerfile: `Dockerfile`
- Port: `8000` or platform-provided `PORT`

## API

- `GET /`
- `GET /health`
- `GET /v1/models`
- `POST /v1/responses`
- `POST /v1/responses/input_tokens`

Requests and responses use Meta Responses API format. `stream: true` passes through Meta SSE.

## Security

The gateway has no application authentication and currently allows permissive CORS. Restrict ingress before exposing it publicly. Anyone who can reach it may consume the configured Meta API quota.
