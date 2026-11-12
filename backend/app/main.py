"""Meta Responses API gateway. Input: native Meta request JSON. Output: native Meta response or SSE."""
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from . import model_catalog, provider, store
from .config import settings


def selected_model():
    model_id = settings.default_model
    return model_catalog.get_model(model_id) or model_catalog.get_model("muse-spark-1.3")


@asynccontextmanager
async def lifespan(app):
    await provider.start_provider()
    await store.start_store()
    yield
    await store.close_store()
    await provider.close_provider()


app = FastAPI(title="Meta Responses API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def api_error(message, status=400, error_type="invalid_request_error"):
    return JSONResponse({"error": {"message": str(message), "type": error_type}}, status_code=status)


async def proxy(request: Request, path: str):
    raw = await request.body()
    if len(raw) > settings.max_request_bytes:
        return api_error("Request body exceeds configured size limit.", 413)
    try:
        body = json.loads(raw)
    except Exception:
        return api_error("Request body must be valid JSON.")
    if not isinstance(body, dict):
        return api_error("Request body must be a JSON object.")

    model = selected_model()
    model_id = model["id"]
    requested_model = body.get("model")
    if requested_model not in (None, model_id):
        return api_error("Configured model is " + model_id + ".", 400)
    body["model"] = model_id

    reasoning = body.get("reasoning")
    if reasoning is not None:
        if not isinstance(reasoning, dict):
            return api_error("reasoning must be an object.")
        try:
            model_catalog.validate_reasoning_effort(model_id, reasoning.get("effort"))
        except ValueError as exc:
            return api_error(str(exc))
    if body.get("temperature") is not None and body.get("top_p") is not None:
        return api_error("Meta accepts temperature or top_p, not both.")

    try:
        upstream = await provider.open_response(body, path=path)
    except RuntimeError as exc:
        return api_error(str(exc), 503, "server_error")
    except Exception as exc:
        return api_error(str(exc), 502, "server_error")

    if upstream.status_code >= 400:
        detail = (await upstream.aread()).decode("utf-8", "replace")
        status = upstream.status_code
        media_type = upstream.headers.get("content-type", "application/json")
        await upstream.aclose()
        try:
            return JSONResponse(json.loads(detail), status_code=status, headers={"Cache-Control": "no-store"})
        except Exception:
            return Response(detail, status_code=status, media_type=media_type, headers={"Cache-Control": "no-store"})

    headers = {
        "Cache-Control": "no-cache" if body.get("stream") else "no-store",
        "X-Accel-Buffering": "no",
    }
    media_type = upstream.headers.get("content-type", "text/event-stream" if body.get("stream") else "application/json")
    if body.get("stream"):
        return StreamingResponse(
            upstream.aiter_bytes(),
            status_code=upstream.status_code,
            media_type=media_type,
            headers=headers,
            background=BackgroundTask(upstream.aclose),
        )
    payload = await upstream.aread()
    await upstream.aclose()
    return Response(payload, status_code=upstream.status_code, media_type=media_type, headers=headers)


@app.get("/")
async def root():
    return {"name": "Meta Responses API", "status": "ok", "api": "/v1/responses", "model": selected_model()["id"]}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "provider": "Meta",
        "provider_configured": bool(settings.meta_api_key),
        "d1_configured": store.configured(),
        "d1_connected": await store.check_connection(),
        "model": selected_model()["id"],
    }


@app.get("/v1/models")
async def models():
    model = selected_model()
    return {"object": "list", "data": [{"id": model["id"], "object": "model", "created": 0, "owned_by": "meta"}]}


@app.post("/v1/responses")
async def responses(request: Request):
    return await proxy(request, "responses")


@app.post("/v1/responses/input_tokens")
async def response_input_tokens(request: Request):
    return await proxy(request, "responses/input_tokens")
