# Alpha Harness — Meta Model API

A lightweight FastAPI model gateway and benchmarking workspace for Meta Model API. The runtime is designed for the 120 MB Deplexo service; measure actual memory under workload rather than assuming the target is guaranteed.

## Architecture

- `main.py`: Meta-native `/v1/responses` gateway, model listing and health routes.
- `provider.py`: isolated Meta HTTP/SSE transport.
- `model_catalog.py`: supported model IDs, capability metadata, reasoning effort and published pricing.
- `model_settings.py`: one global model selection and optional global reasoning override.
- `ui_api.py`: only HTTP contract consumed by the frontend; all application UI routes live under `/ui`.
- `test_library.py`: 165 Meta-compatible benchmark scenarios.
- `test_engine.py`: one-at-a-time run lifecycle, cancellation, live events and model metadata.
- `evaluator.py`: deterministic assertions and a separate structured-output model judge.
- `playground.py`: Meta Responses tool loop with stateless encrypted reasoning replay.
- `tools.py`: bounded local tool registry and task-intent selection.
- `ui_store.py`: D1 persistence, bounded in-memory fallback, one-time workspace reset and encrypted-reasoning state.
- `store.py`: Cloudflare D1 adapter.

Each module has a narrow input/output boundary. The frontend calls only the routes in `ui_api.py`; it does not access Meta or D1 directly.

## Meta model catalogue

The UI exposes the following model IDs. USD prices are per million tokens; cached-input prices are separately identified.

| Model | Input | Cached input | Output |
|---|---:|---:|---:|
| Muse Wonder 1.0 | $4.00 | $0.20 | $20.00 |
| Muse Spark 1.3 | $1.25 | $0.15 | $4.25 |
| Muse Spark 1.2 | $1.25 | $0.15 | $4.25 |
| Muse Spark 1.1 | $1.25 | $0.15 | $4.25 |
| Muse Spark 1.3 Contributor | $0.10 | $0.002 | $0.20 |
| Muse Spark 1.2 Contributor | $0.10 | $0.002 | $0.20 |
| Muse Ember 1.0 (up to 200K input) | $0.10 | $0.004 | $0.50 |
| Muse Ember 1.0 (over 200K input) | $0.30 | $0.012 | $1.50 |

The catalogue is a local display/validation allowlist, not a live pricing feed. Verify published rates before financial decisions. Contributor variants carry Meta's additional data-use terms; the UI requires explicit confirmation before selecting one.

Reasoning effort is model-aware: minimal, low, medium, high, xhigh, and max where supported. The default is to omit the reasoning override so Meta applies that model's default. Max is not available on every model. The UI explains that higher effort can increase reasoning tokens, latency and cost.

Responses API settings are validated against Meta's request rules:
- `max_output_tokens` (minimum 16).
- `reasoning.effort` with model-supported values.
- `temperature` or `top_p`, never both.
- Structured output through Responses `text.format`.
- Chat Completions-only options such as `max_tokens`, penalties, `stop`, `logit_bias`, `n` and `stream_options` are not accepted in internal test settings.

## Built-in benchmark library

The test library seeds 165 scenarios: 11 capability categories × 5 difficulty levels × 3 distinct scenarios per category and level.

Categories: reasoning, instruction following, JSON output, tool calling, multi-turn, streaming, planning, error handling, latency/tokens, context limits and custom prompts.

Difficulty labels:
- **Easy:** one objective and one primary constraint.
- **Mid:** linked requirements and an independent check.
- **Hard:** interacting constraints, edge cases and explicit validation.
- **Expert:** auditable synthesis, assumptions, alternatives and verification.
- **Adversarial:** expert-level work with misleading or embedded instructions treated as untrusted task data.

The streaming category measures actual text-delta events. JSON cases use Meta Responses structured-output schemas. Local tool tests use the Meta Responses function-tool shape.

## Agent and evaluation behavior

- Free chat selects relevant ordinary tools from task intent.
- Test-backed runs use the tool set assigned to the scenario.
- The tested agent receives only the developer/user input, model settings and selected local tool definitions.
- Expected outputs, deterministic assertions, private judge rubric, scores and evaluator instructions are not included in the tested agent's input.
- The model judge uses the globally selected Meta model and a separate request. Its output is structured JSON and is reported independently from deterministic checks.
- Tool results are paired with Meta `function_call` items using `function_call_output` and the exact `call_id`.
- App-managed conversations use stateless reasoning replay: `store:false` and `include:["reasoning.encrypted_content"]`. Returned reasoning output items are replayed in the next request. Conversation state is stored in D1, bounded to 4 MB per session and associated with its originating model. Switching models starts a fresh reasoning context for that conversation.
- Local tools are bounded and have no real-world side effects: calculator, UTC clock, JSON validator, session memory and unit conversion.

## Workspace data reset

The Meta migration performs one one-time reset of legacy workspace data after D1 schemas are available. It clears old custom tests, built-in/custom run history, run events, conversations, messages, tool traces, metrics, encrypted-reasoning state and old model settings. A migration marker then prevents subsequent backend restarts from clearing new Meta-era data.

Tables and schema are retained. The 165 built-in tests are generated by the backend and are not stored as custom-test rows.

## HTTP API

Native Meta API proxy:
- `GET /v1/models`
- `POST /v1/responses`
- `POST /v1/responses/input_tokens`
- `GET /health`

The public model API uses Meta Responses request and response formats. Streaming is passed through as Meta SSE when `stream:true`; non-streaming JSON responses are also supported.

UI routes (all prefixed with `/ui`):

| Group | Routes |
|---|---|
| Dashboard/system | `GET /dashboard`, `GET /system` |
| Model catalogue | `GET /models`, `GET /model/status`, `GET /model/config` |
| Test library | `GET /tests/categories`, `GET /tests`, `GET /tests/{id}` |
| Custom tests | `POST /tests`, `PUT /tests/{id}`, `DELETE /tests/{id}` |
| Global model settings | `GET /settings`, `PUT /settings` |
| Test runs | `POST /runs`, `GET /runs`, `GET /runs/{id}` |
| Run lifecycle | `GET /runs/{id}/stream`, `POST /runs/{id}/cancel`, `POST /runs/compare` |
| Harness playground | `GET /agent`, `POST /agent/chat` |
| Conversations/tools | `GET /conversations`, `GET /conversations/{id}`, `GET /tools` |
| Observability | `GET /metrics`, `GET /traces`, `GET /traces/{id}`, `GET /logs` |

Chat and run streams use Server-Sent Events. Run events include activity, token deltas, tool calls/results, evaluation stages, errors and final results.

## Deplexo Docker service

Configure the service:
- **Repository:** `alphaspex/Tzone`
- **Branch:** `main`
- **Build context / root directory:** `backend`
- **Dockerfile path:** `Dockerfile`
- **Container port:** `8000` (or platform-injected `PORT`)

Required environment variables:
- `MODEL_API_KEY` — Meta Model API key; configure privately in Deplexo.
- `CLOUDFLARE_ACCOUNT_ID` — existing Cloudflare account ID.
- `CLOUDFLARE_API_TOKEN` — token with D1 read/write permissions.
- `D1_DATABASE_ID=520245ce-7de8-4462-afe6-3de6f0f9e985`.

Optional:
- `META_API_BASE_URL=https://api.meta.ai/v1`
- `MODEL_NAME=muse-spark-1.3` (initial fallback until the global model is selected in Settings).
- `REQUEST_TIMEOUT_SECONDS=90` (per individual upstream request).
- `MAX_REQUEST_BYTES=16777216`.

Do not configure or retain `ZAI_API_KEY` / `ZAI_BASE_URL`; the application no longer uses Z.ai. The old secret can be removed from Deplexo after the Meta key has been set.

D1 tables are created automatically on startup. When D1 is not configured, the UI services use bounded in-process memory; those records are not durable across restarts.

## Runtime and security

One Uvicorn worker, concurrency cap 2, one active test run, bounded HTTP pools, bounded session state, 90-second default per-provider-request timeout, no overall test-run timeout, unlimited agent steps, short keep-alive and no heavyweight database SDK. Actual RAM use must be measured under load.

No backend authentication is enabled, as previously configured. Reachable callers can consume Meta API quota. Restrict ingress at the platform or place the service behind access control before exposing the URL. CORS is currently permissive.

## Local validation

From the `backend` directory:

    pip install -r requirements.txt
    python -m compileall -q app tests
    python -m unittest discover -s tests -v
