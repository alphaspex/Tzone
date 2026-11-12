# GLM Model Test Harness

A lightweight FastAPI model gateway and testing workspace backend for Z.ai GLM-4.7-Flash. Designed for the 120 MB Deplexo runtime.

## Architecture

- `main.py`: startup, existing OpenAI-compatible API, router registration.
- `ui_api.py`: the only HTTP contract used by the frontend. All UI routes live under `/ui`.
- `test_library.py`: built-in capability-test catalog.
- `test_engine.py`: one-at-a-time test-run lifecycle and live events.
- `evaluator.py`: hidden deterministic assertions and a separate model-judge call.
- `playground.py`: the same tested GLM agent for free chat and test-backed chat.
- `tools.py`: bounded local tool registry and intent-based selection.
- `ui_store.py`: UI data persistence and bounded in-memory fallback.
- `provider.py`: Z.ai streaming adapter.
- `store.py`: Cloudflare D1 adapter.

Each module has a narrow input/output boundary. The frontend must call only the routes in `ui_api.py`; it does not access D1 or provider internals.

## Built-in test library

The backend seeds 165 built-in test scenarios: 11 categories, 5 difficulty levels, and 3 scenarios per category/level.

Categories:
- Reasoning
- Instruction following
- JSON output
- Tool calling
- Multi-turn
- Streaming
- Planning
- Error handling
- Latency and tokens
- Context limits
- Custom prompts

Difficulty levels: Foundation, Intermediate, Advanced, Expert, Adversarial.

Built-in tests are read-only. Create, edit, and delete your own tests through the UI endpoints.

## Agent isolation

The Harness Agent screen is a direct playground for the same configured GLM model.

- Free chat selects relevant ordinary tools from task intent.
- Test-backed chat uses the tool set assigned to the selected test scenario.
- The tested agent receives only its conversation, user task, configured system prompt, and selected tool definitions.
- Expected output, deterministic assertions, private judge rubric, scores, and evaluator instructions are not passed to the tested agent.
- Test results and traces are stored separately and remain visible to the UI user.
- The model judge is a separate evaluation call using the configured model. Deterministic assertions remain the pass/fail ground truth.

The toolset is local and bounded: calculator, UTC clock, JSON validator, session memory, and common unit conversion. No tools with real-world side effects are exposed.

## UI endpoint contract

All routes are prefixed with `/ui`.

| Group | Routes |
|---|---|
| Dashboard/system | `GET /dashboard`, `GET /system` |
| Model | `GET /model/status`, `GET /model/config` |
| Test library | `GET /tests/categories`, `GET /tests`, `GET /tests/{id}` |
| Custom tests | `POST /tests`, `PUT /tests/{id}`, `DELETE /tests/{id}` |
| Test runs | `POST /runs`, `GET /runs`, `GET /runs/{id}` |
| Run lifecycle | `GET /runs/{id}/stream`, `POST /runs/{id}/cancel`, `POST /runs/compare` |
| Harness playground | `GET /agent`, `POST /agent/chat` |
| Conversations/tools | `GET /conversations`, `GET /conversations/{id}`, `GET /tools` |
| Observability | `GET /metrics`, `GET /traces`, `GET /traces/{id}`, `GET /logs` |
| Settings | `GET /settings` |

Chat and run streams use Server-Sent Events. Run events include activity, token deltas, tool calls/results, evaluation stages, errors, and final results. Token deltas are streamed live; completed responses and important events are persisted.

## Existing OpenAI-compatible API

- `GET /`
- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions` — streaming only; send `"stream": true`.

The original `/v1` routes remain separate from the UI API.

## Deplexo Docker service

Configure the service with:
- **Repository:** `alphaspex/Tzone`
- **Branch:** `main`
- **Build context / root directory:** `backend`
- **Dockerfile path:** `Dockerfile`
- **Container port:** `8000` (or platform-injected `PORT`)

Required environment variables:
- `ZAI_API_KEY` — set privately in Deplexo
- `CLOUDFLARE_ACCOUNT_ID` — existing Cloudflare account ID
- `CLOUDFLARE_API_TOKEN` — token with D1 read/write permissions
- `D1_DATABASE_ID=520245ce-7de8-4462-afe6-3de6f0f9e985`

Optional:
- `ZAI_BASE_URL=https://api.z.ai/api/paas/v4`
- `MODEL_NAME=glm-4.7-flash`
- `MAX_AGENT_STEPS=4`
- `REQUEST_TIMEOUT_SECONDS=90`

D1 tables are created automatically on startup. UI persistence creates `custom_tests` and `run_events` in addition to the existing sessions, messages, tool events, test runs, and metrics tables. If D1 is not configured, the UI services use bounded in-process memory; those records are not durable across restarts.

## Runtime and security

One Uvicorn worker, concurrency cap 2, one active test run at a time, bounded HTTP pools, bounded session memory, short keep-alive, and no heavyweight database SDK. Monitor actual memory under load; the 120 MB target is not a measured guarantee.

No backend authentication is enabled, as previously requested. The UI routes can start model calls and consume API quota. Restrict ingress at the platform or place the service behind access control before making it public. CORS is currently permissive.

## Local validation

From the `backend` directory:

    pip install -r requirements.txt
    python -m compileall -q app tests
    python -m unittest discover -s tests -v
