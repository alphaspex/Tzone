"""HTTP boundary. Input: OpenAI chat-completion requests. Output: streaming SSE."""
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from . import agent, provider, store
from .config import settings

@asynccontextmanager
async def lifespan(app):
    await provider.start_provider()
    await store.start_store()
    yield
    await store.close_store()
    await provider.close_provider()

app = FastAPI(title="GLM Model Test Harness", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET","POST","OPTIONS"], allow_headers=["*"])

@app.get("/")
async def root():
    return {"name":"GLM Model Test Harness","status":"ok","model":settings.model,"streaming":True}

@app.get("/health")
async def health():
    return {"status":"ok","provider_configured":bool(settings.zai_api_key),"d1_configured":store.configured(),"model":settings.model}

@app.get("/v1/models")
async def models():
    return {"object":"list","data":[{"id":settings.model,"object":"model","created":0,"owned_by":"z.ai"}]}

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error":{"message":"Request body must be valid JSON","type":"invalid_request_error"}}, status_code=400)
    if body.get("stream") is False:
        return JSONResponse({"error":{"message":"This service supports streaming only. Set stream=true.","type":"invalid_request_error"}}, status_code=400)
    metadata = body.get("metadata") or {}
    session_id = str(metadata.get("session_id") or body.get("user") or uuid.uuid4())
    headers = {"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-ID":session_id}
    return StreamingResponse(agent.stream_response(body, session_id), media_type="text/event-stream", headers=headers)
