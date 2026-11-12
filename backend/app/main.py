"""HTTP entry point. Existing OpenAI-compatible routes and UI-only routes remain separate."""
import json
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from . import agent, provider, store, ui_api, ui_store
from .config import settings

@asynccontextmanager
async def lifespan(app):
    await provider.start_provider()
    await store.start_store()
    await ui_store.start_ui_store()
    yield
    await store.close_store()
    await provider.close_provider()

app = FastAPI(title="GLM Model Test Harness", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET","POST","PUT","DELETE","OPTIONS"], allow_headers=["*"])
app.include_router(ui_api.router)

@app.get("/")
async def root():
    return {"name":"GLM Model Test Harness","status":"ok","model":settings.model,"streaming":True,"ui_api":"/ui"}

@app.get("/health")
async def health():
    return {"status":"ok","provider_configured":bool(settings.zai_api_key),"d1_configured":store.configured(),"model":settings.model}

@app.get("/v1/models")
async def models():
    return {"object":"list","data":[{"id":settings.model,"object":"model","created":0,"owned_by":"z.ai"}]}

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    raw = await request.body()
    if len(raw) > 1_000_000:
        return JSONResponse({"error":{"message":"Request body exceeds 1 MB limit","type":"invalid_request_error"}}, status_code=413)
    try:
        body = json.loads(raw)
    except Exception:
        return JSONResponse({"error":{"message":"Request body must be valid JSON","type":"invalid_request_error"}}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error":{"message":"Request body must be a JSON object","type":"invalid_request_error"}}, status_code=400)
    if body.get("stream") is False:
        return JSONResponse({"error":{"message":"This service supports streaming only. Set stream=true.","type":"invalid_request_error"}}, status_code=400)
    metadata = body.get("metadata") or {}
    session_id = str(metadata.get("session_id") or body.get("user") or uuid.uuid4())
    headers = {"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-ID":session_id}
    return StreamingResponse(agent.stream_response(body, session_id), media_type="text/event-stream", headers=headers)
