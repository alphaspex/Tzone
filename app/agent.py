"""Agent orchestration. Input: chat request + session ID. Output: OpenAI-compatible SSE frames."""
import json
import time
import uuid
from . import provider, store, tools
from .config import settings

def _frame(chunk_id, created, model, delta=None, finish_reason=None, usage=None):
    choice = {"index": 0, "delta": delta or {}, "finish_reason": finish_reason}
    item = {"id": chunk_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [choice]}
    if usage is not None:
        item["usage"] = usage
    return "data: " + json.dumps(item, ensure_ascii=False) + "\n\n"

async def stream_response(request, session_id):
    chunk_id, created = "chatcmpl-" + uuid.uuid4().hex[:20], int(time.time())
    model = request.get("model") or settings.model
    messages = list(request.get("messages") or [])
    if not messages:
        yield "data: " + json.dumps({"error":{"message":"messages is required","type":"invalid_request_error"}}) + "\n\n"
        yield "data: [DONE]\n\n"
        return
    await store.save_message(session_id, "user", messages[-1].get("content", ""))
    client_tools = request.get("tools") or []
    local_defs = tools.definitions()
    local_names = {item["function"]["name"] for item in local_defs}
    merged = {item.get("function", {}).get("name"): item for item in local_defs}
    for item in client_tools:
        name = item.get("function", {}).get("name")
        if name and name not in merged:
            merged[name] = item
    available_tools = list(merged.values())
    started = time.monotonic()
    final_text, total_usage = "", None
    try:
        for step in range(settings.max_agent_steps):
            payload = {"model": model, "messages": messages, "stream": True, "stream_options": {"include_usage": True}}
            if available_tools:
                payload["tools"] = available_tools
                payload["tool_choice"] = request.get("tool_choice", "auto")
            if request.get("temperature") is not None:
                payload["temperature"] = request["temperature"]
            if request.get("max_tokens") is not None:
                payload["max_tokens"] = request["max_tokens"]
            calls, content_parts, finish_reason = {}, [], "stop"
            async for event in provider.stream_chat(payload):
                if event.get("usage"):
                    total_usage = event["usage"]
                for choice in event.get("choices", []):
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        piece = delta["content"]
                        content_parts.append(piece)
                        yield _frame(chunk_id, created, model, {"content": piece})
                    for call in delta.get("tool_calls", []):
                        idx = call.get("index", 0)
                        target = calls.setdefault(idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        if call.get("id"): target["id"] += call["id"]
                        if call.get("function", {}).get("name"): target["function"]["name"] += call["function"]["name"]
                        if call.get("function", {}).get("arguments"): target["function"]["arguments"] += call["function"]["arguments"]
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]
            final_text += "".join(content_parts)
            if not calls:
                break
            ordered_calls = [calls[i] for i in sorted(calls)]
            messages.append({"role":"assistant","content":"".join(content_parts) or None,"tool_calls":ordered_calls})
            external = []
            for call in ordered_calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                if name in local_names:
                    try:
                        output = tools.run(name, args, session_id)
                        await store.save_tool_event(session_id, name, args, output)
                        messages.append({"role":"tool","tool_call_id":call["id"],"content":json.dumps(output, ensure_ascii=False)})
                    except Exception as exc:
                        output = {"error":str(exc)}
                        await store.save_tool_event(session_id, name, args, output, "error")
                        messages.append({"role":"tool","tool_call_id":call["id"],"content":json.dumps(output)})
                else:
                    external.append(call)
            if external:
                for i, call in enumerate(external):
                    yield _frame(chunk_id, created, model, {"tool_calls":[{"index":i,"id":call["id"],"type":"function","function":call["function"]}]})
                await store.save_message(session_id, "assistant", {"tool_calls":external})
                yield _frame(chunk_id, created, model, {}, "tool_calls")
                if total_usage:
                    await store.save_metric(session_id, "total_tokens", total_usage.get("total_tokens", 0))
                yield "data: [DONE]\n\n"
                return
            if step == settings.max_agent_steps - 1:
                yield _frame(chunk_id, created, model, {"content":"\n[Agent step limit reached.]"})
        await store.save_message(session_id, "assistant", final_text)
        await store.save_metric(session_id, "latency_ms", (time.monotonic()-started)*1000)
        if total_usage:
            for key, value in total_usage.items():
                if isinstance(value, (int, float)):
                    await store.save_metric(session_id, key, value)
        yield _frame(chunk_id, created, model, {}, "stop", total_usage)
    except Exception as exc:
        error = {"error":{"message":str(exc),"type":"server_error"}}
        yield "data: " + json.dumps(error, ensure_ascii=False) + "\n\n"
    yield "data: [DONE]\n\n"
