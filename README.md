# GLM Model Test Harness

Small FastAPI streaming gateway for Z.ai GLM-4.7-Flash. Designed for a 120 MB service: one Uvicorn worker, bounded HTTP connection pools, no background worker or heavyweight database client.

## Deplexo environment variables

Required:
- `ZAI_API_KEY` — your Z.ai API key
- `CLOUDFLARE_ACCOUNT_ID` — existing Cloudflare account ID
- `CLOUDFLARE_API_TOKEN` — token with D1 read/write permissions

Already known:
- `D1_DATABASE_ID=520245ce-7de8-4462-afe6-3de6f0f9e985`

Optional:
- `ZAI_BASE_URL=https://api.z.ai/api/paas/v4`
- `MODEL_NAME=glm-4.7-flash`
- `MAX_AGENT_STEPS=4`
- `REQUEST_TIMEOUT_SECONDS=90`

No backend API key is enabled, as requested. Do not expose this service publicly without adding authentication or restricting ingress.

## Run

- Install: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`
- Health: `GET /health`
- Models: `GET /v1/models`
- Chat: `POST /v1/chat/completions` with `"stream": true`

The API is streaming-only. Send `metadata.session_id` or `user` to keep requests in the same session.

## Tool behavior

Calculator, clock, JSON validation, and temporary session memory run locally. Unknown/client-provided tools are returned as OpenAI tool-call events and are not executed by this service. The client must execute them with approval and submit the resulting `tool` messages on the next request.

## Persistence

D1 tables are created automatically on startup: sessions, messages, tool_events, test_runs, and metrics. If D1 credentials are absent, the API still starts but persistence is disabled.

## Resource profile

One worker is intentional. Avoid multiple workers and large concurrency on the 120 MB plan. This service keeps a small HTTP connection pool and uses D1's REST API rather than a database SDK.
