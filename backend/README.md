# GLM Model Test Harness Backend

Dockerized FastAPI streaming gateway for Z.ai GLM-4.7-Flash. Designed for a 120 MB runtime.

## Deplexo Docker service

Configure the service with:
- **Repository:** `alphaspex/Tzone`
- **Branch:** `main`
- **Build context / root directory:** `backend`
- **Dockerfile path:** `Dockerfile`
- **Container port:** `8000` (or let Deplexo inject `PORT`)

Required environment variables:
- `ZAI_API_KEY` — set privately in Deplexo when ready
- `CLOUDFLARE_ACCOUNT_ID` — existing Cloudflare account ID
- `CLOUDFLARE_API_TOKEN` — existing token with D1 read/write permissions
- `D1_DATABASE_ID=520245ce-7de8-4462-afe6-3de6f0f9e985`

Optional:
- `ZAI_BASE_URL=https://api.z.ai/api/paas/v4`
- `MODEL_NAME=glm-4.7-flash`
- `MAX_AGENT_STEPS=4`
- `REQUEST_TIMEOUT_SECONDS=90`

## API

- `GET /`
- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions` — streaming only; set `"stream": true`

Send `metadata.session_id` or `user` to reuse a session identifier.

## Runtime constraints

One Uvicorn worker, at most 8 concurrent connections, short keep-alive, bounded HTTP pools, no heavyweight database SDK. The image uses Python slim and installs only FastAPI, Uvicorn and HTTPX.

No backend API authentication is enabled, as requested. Restrict ingress before exposing the service publicly.
