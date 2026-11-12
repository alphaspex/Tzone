"""Tested-agent execution. Inputs: conversation messages and selected tool names. Outputs: streamed activity events and a final assistant response."""
import json
import time
import uuid
from . import provider, tools, ui_store
from .config import settings

_PARAMETER_KEYS = {
    "temperature", "top_p", "max_tokens", "presence_penalty",
    "frequency_penalty", "stop", "response_format", "seed",
    "logit_bias", "n", "user",
}

def normalize_parameters(parameters):
    result = {}
    for key, value in (parameters or {}).items():
        if key in _PARAMETER_KEYS and value is not None:
            result[key] = value
    return result

async def stream_turn(session_id, user_text, tool_names=None, parameters=None, system_prompt="", history=None):
    """Yield {type, ...} events. Hidden expected outputs and evaluator rules are never accepted here."""
    started = time.monotonic()
    selected_names = list(tool_names) if tool_names is not None else tools.select_for_task(user_text)
    selected_names = [name for name in selected_names if name in tools.available_names()]
    tool_defs = tools.definitions(selected_names)
    messages = []
    if history is None:
        previous = await ui_store.get_messages(session_id, 80)
        messages.extend([{"role":item["role"],"content":item["content"]} for item in previous
                         if item.get("role") in ("user","assistant","system")])
    else:
        messages.extend(history)
    if system_prompt and not any(item.get("role") == "system" for item in messages):
        messages.insert(0, {"role":"system","content":str(system_prompt)[:8000]})
    messages.append({"role":"user","content":str(user_text)[:30000]})
    await ui_store.save_chat_message(session_id, "user", str(user_text)[:30000])
    yield {"type":"activity","status":"thinking","message":"Preparing response"}
    if tool_defs:
        yield {"type":"activity","status":"ready","message":f"{len(tool_defs)} available tool(s)"}
    model_params = normalize_parameters(parameters)
    model_params.setdefault("max_tokens", 1024)
    model_params.setdefault("temperature", 0.4)
    max_steps = max(1, min(int(settings.max_agent_steps), 8))
    call_events, response_parts, usage = [], [], {}
    try:
        for step in range(max_steps):
            payload = {"model":settings.model,"messages":messages,"stream":True,
                       "stream_options":{"include_usage":True}, **model_params}
            if tool_defs:
                payload["tools"] = tool_defs
                payload["tool_choice"] = "auto"
            tool_calls, step_parts = {}, []
            yield {"type":"activity","status":"model","step":step+1,"message":"Model is responding"}
            async for event in provider.stream_chat(payload):
                if event.get("usage"):
                    usage.update(event["usage"])
                for choice in event.get("choices", []):
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        piece = str(delta["content"])
                        step_parts.append(piece)
                        response_parts.append(piece)
                        yield {"type":"token","text":piece,"step":step+1}
                    for call in delta.get("tool_calls", []):
                        index = int(call.get("index",0))
                        target = tool_calls.setdefault(index, {"id":"","type":"function","function":{"name":"","arguments":""}})
                        if call.get("id"):
                            target["id"] += call["id"]
                        function = call.get("function") or {}
                        target["function"]["name"] += function.get("name") or ""
                        target["function"]["arguments"] += function.get("arguments") or ""
            if not tool_calls:
                break
            ordered = [tool_calls[index] for index in sorted(tool_calls)]
            messages.append({"role":"assistant","content":"".join(step_parts) or None,"tool_calls":ordered})
            for call in ordered:
                name = call["function"]["name"]
                raw_args = call["function"]["arguments"] or "{}"
                call_id = call.get("id") or "call_" + uuid.uuid4().hex[:10]
                try:
                    args = json.loads(raw_args)
                    if not isinstance(args, dict):
                        raise ValueError("Tool arguments must be a JSON object")
                    if name not in selected_names:
                        raise PermissionError("This tool is not available in the current conversation")
                    yield {"type":"tool_call","tool_call_id":call_id,"tool_name":name,"arguments":args,"step":step+1}
                    output = tools.run(name,args,session_id)
                    status = "ok"
                except Exception as exc:
                    args = {}
                    output = {"error":str(exc)[:500]}
                    status = "error"
                    yield {"type":"tool_call","tool_call_id":call_id,"tool_name":name,"arguments":args,"step":step+1}
                record = {"tool_call_id":call_id,"tool_name":name,"input":args,"output":output,"status":status,"step":step+1}
                call_events.append({"tool_name":name,"status":status,"input":args,"output":output})
                await ui_store.save_tool_event(session_id,name,args,output,status)
                yield {"type":"tool_result",**record}
                messages.append({"role":"tool","tool_call_id":call_id,"content":json.dumps(output,ensure_ascii=False)})
            if step == max_steps - 1:
                response_parts.append("\n[Execution step limit reached.]")
        final_text = "".join(response_parts)[:100000]
        await ui_store.save_chat_message(session_id,"assistant",final_text)
        latency_ms = (time.monotonic()-started)*1000
        await ui_store.save_metric(session_id,"latency_ms",latency_ms)
        for key,value in usage.items():
            if isinstance(value,(int,float)):
                await ui_store.save_metric(session_id,key,value)
        yield {"type":"done","content":final_text,"tool_events":call_events,
               "usage":usage,"latency_ms":round(latency_ms,2),
               "tool_names":selected_names,"model":settings.model}
    except Exception as exc:
        yield {"type":"error","message":str(exc)[:1200],"tool_events":call_events,
               "latency_ms":round((time.monotonic()-started)*1000,2)}
