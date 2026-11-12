"""Meta Model API gateway. Input: native Responses API requests. Output: native Meta responses."""
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.background import BackgroundTask
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from . import model_catalog, model_settings, provider, store, ui_api, ui_store
from .config import settings


@asynccontextmanager
async def lifespan(app):
    await provider.start_provider()
    await store.start_store()
    await ui_store.start_ui_store()
    yield
    await store.close_store()
    await provider.close_provider()


app = FastAPI(title="Meta Model Harness", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Conversation-ID", "X-Session-ID"],
)
app.include_router(ui_api.router)


def _api_error(message, error_type="invalid_request_error", status=400, code=None):
    error = {"message": str(message), "type": error_type}
    if code is not None:
        error["code"] = code
    return JSONResponse({"error": error}, status_code=status)


async def _meta_proxy(request: Request, path: str):
    raw = await request.body()
    if len(raw) > settings.max_request_bytes:
        return _api_error("Request body exceeds configured size limit.", status=413)
    try:
        body = json.loads(raw)
    except Exception:
        return _api_error("Request body must be valid JSON.")
    if not isinstance(body, dict):
        return _api_error("Request body must be a JSON object.")

    if path == "responses":
        configured = await model_settings.get_settings()
        body.setdefault("model", configured["model"])
        if not isinstance(body.get("model"), str) or not model_catalog.get_model(body["model"]):
            return _api_error("Unsupported Meta model. Retrieve available IDs from GET /v1/models.", status=400)
        if body.get("reasoning") is not None:
            reasoning = body["reasoning"]
            if not isinstance(reasoning, dict):
                return _api_error("reasoning must be an object.")
            try:
                model_catalog.validate_reasoning_effort(body["model"], reasoning.get("effort"))
            except ValueError as exc:
                return _api_error(str(exc))
        if body.get("temperature") is not None and body.get("top_p") is not None:
            return _api_error("Meta accepts temperature or top_p, not both.")
    try:
        upstream = await provider.open_response(body, path=path)
    except RuntimeError as exc:
        return _api_error(str(exc), error_type="server_error", status=503)
    except Exception as exc:
        return _api_error(str(exc), error_type="server_error", status=502)

    if upstream.status_code >= 400:
        detail = (await upstream.aread()).decode("utf-8", "replace")
        headers = {"Cache-Control": "no-store"}
        await upstream.aclose()
        try:
            payload = json.loads(detail)
            return JSONResponse(payload, status_code=upstream.status_code, headers=headers)
        except Exception:
            return Response(detail, status_code=upstream.status_code,
                            media_type=upstream.headers.get("content-type", "application/json"),
                            headers=headers)

    headers = {
        "Cache-Control": "no-cache" if body.get("stream") else "no-store",
        "X-Accel-Buffering": "no",
    }
    if body.get("stream"):
        return StreamingResponse(
            upstream.aiter_bytes(),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "text/event-stream"),
            headers=headers,
            background=BackgroundTask(upstream.aclose),
        )
    payload = await upstream.aread()
    media_type = upstream.headers.get("content-type", "application/json")
    await upstream.aclose()
    return Response(payload, status_code=upstream.status_code, media_type=media_type, headers=headers)


@app.get("/")
async def root():
    configured = await model_settings.get_settings()
    return {
        "name": "Meta Model Harness", "status": "ok",
        "provider": "Meta Model API", "model": configured["model"],
        "streaming": True, "api": "/v1/responses", "ui_api": "/ui",
    }


@app.get("/health")
async def health():
    configured = await model_settings.get_settings()
    return {
        "status": "ok", "provider": "Meta Model API",
        "provider_configured": bool(settings.meta_api_key),
        "d1_configured": store.configured(), "model": configured["model"],
    }


@app.get("/v1/models")
async def models():
    return {
        "object": "list",
        "data": [
            {"id": item["id"], "object": "model", "created": 0, "owned_by": "meta"}
            for item in model_catalog.list_models()
        ],
    }


@app.post("/v1/responses")
async def responses(request: Request):
    return await _meta_proxy(request, "responses")


@app.post("/v1/responses/input_tokens")
async def response_input_tokens(request: Request):
    return await _meta_proxy(request, "responses/input_tokens")
