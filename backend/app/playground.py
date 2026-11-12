"""Meta agent turn runner. Inputs: session text, tools and Meta request settings. Outputs: live activity events."""
import json
import time
import traceback
import uuid

from . import provider, tools, ui_store, model_settings


_PARAMETER_KEYS = {"max_output_tokens", "reasoning_effort", "temperature", "top_p", "text"}


def normalize_parameters(parameters, model_id):
    """Validate only request options supported by Meta Responses for the selected model."""
    source = parameters if isinstance(parameters, dict) else {}
    unknown = set(source) - _PARAMETER_KEYS
    if unknown:
        raise ValueError("Unsupported Meta Responses parameter(s): " + ", ".join(sorted(unknown)))
    result = {}
    if "max_output_tokens" in source and source["max_output_tokens"] is not None:
        result["max_output_tokens"] = max(16, min(65536, int(source["max_output_tokens"])))
    if "temperature" in source and source["temperature"] not in (None, ""):
        result["temperature"] = max(0.0, min(2.0, float(source["temperature"])))
    if "top_p" in source and source["top_p"] not in (None, ""):
        result["top_p"] = max(0.0, min(1.0, float(source["top_p"])))
    if "temperature" in result and "top_p" in result:
        raise ValueError("Meta Model API accepts temperature or top_p; choose one, not both.")
    if source.get("reasoning_effort") not in (None, "", "auto"):
        result["reasoning_effort"] = model_settings.model_catalog.validate_reasoning_effort(
            model_id, source["reasoning_effort"])
    if "text" in source:
        if not isinstance(source["text"], dict):
            raise ValueError("text must be a Meta Responses text configuration object.")
        result["text"] = source["text"]
    result.setdefault("max_output_tokens", 2048)
    return result


def _add_usage(total, incoming):
    if not isinstance(incoming, dict):
        return
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        if isinstance(incoming.get(key), (int, float)):
            total[key] = total.get(key, 0) + int(incoming[key])
    input_details = incoming.get("input_tokens_details") or {}
    output_details = incoming.get("output_tokens_details") or {}
    cached = input_details.get("cached_tokens")
    reasoning = output_details.get("reasoning_tokens")
    if isinstance(cached, (int, float)):
        total["cached_input_tokens"] = total.get("cached_input_tokens", 0) + int(cached)
    if isinstance(reasoning, (int, float)):
        total["reasoning_tokens"] = total.get("reasoning_tokens", 0) + int(reasoning)


def _response_text(response):
    parts = []
    for item in (response or {}).get("output") or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
    return "".join(parts)


async def stream_turn(session_id, user_text, tool_names=None, parameters=None, system_prompt=""):
    """Run a Meta Responses tool loop while preserving encrypted reasoning across stateless turns."""
    started = time.monotonic()
    source = parameters if isinstance(parameters, dict) else {}
    try:
        model_id, global_effort, model = await model_settings.resolve(
            reasoning_override=source.get("reasoning_effort"))
        model_params = normalize_parameters(source, model_id)
        effort = model_params.pop("reasoning_effort", global_effort)
        selected_names = list(tool_names) if tool_names is not None else tools.select_for_task(user_text)
        selected_names = [name for name in selected_names if name in tools.available_names()]
        tool_defs = tools.responses_definitions(selected_names)
        input_items = await ui_store.get_agent_state(session_id, model_id)
        if not input_items and system_prompt:
            input_items.append({
                "role": "developer",
                "content": [{"type": "input_text", "text": str(system_prompt)[:8000]}],
            })
        user_item = {
            "role": "user",
            "content": [{"type": "input_text", "text": str(user_text)[:30000]}],
        }
        input_items.append(user_item)
        await ui_store.save_chat_message(session_id, "user", str(user_text)[:30000])
        yield {"type": "activity", "status": "thinking", "message": "Preparing Meta Responses request"}
        if tool_defs:
            yield {"type": "activity", "status": "ready", "message": f"{len(tool_defs)} local tool(s) available"}

        usage, call_events = {}, []
        response_parts = []
        step = 0
        while True:
            step += 1
            payload = {
                "model": model_id,
                "input": input_items,
                "stream": True,
                "store": False,
                "include": ["reasoning.encrypted_content"],
                "max_output_tokens": model_params["max_output_tokens"],
            }
            if effort:
                payload["reasoning"] = {"effort": effort}
            if "temperature" in model_params:
                payload["temperature"] = model_params["temperature"]
            if "top_p" in model_params:
                payload["top_p"] = model_params["top_p"]
            if "text" in model_params:
                payload["text"] = model_params["text"]
            if tool_defs:
                payload["tools"] = tool_defs
                payload["tool_choice"] = "auto"
                payload["parallel_tool_calls"] = True

            yield {
                "type": "activity", "status": "model",
                "step": step, "message": f"{model['name']} is responding",
                "model": model_id, "reasoning_effort": effort or model["default_reasoning_effort"],
            }
            final_response = None
            async for event in provider.stream_events(payload):
                event_type = event.get("type")
                if event_type == "response.output_text.delta":
                    piece = event.get("delta") or ""
                    if piece:
                        response_parts.append(piece)
                        yield {"type": "token", "text": piece, "step": step}
                elif event_type == "response.reasoning_summary_text.delta":
                    # Meta summaries are optional and not treated as visible model answers.
                    yield {"type": "activity", "status": "reasoning_summary", "message": event.get("delta", "")}
                elif event_type in ("response.completed", "response.failed", "response.incomplete"):
                    final_response = event.get("response") or {}
                    if event_type != "response.completed" or final_response.get("status") != "completed":
                        detail = final_response.get("error") or final_response.get("incomplete_details") or {}
                        raise RuntimeError(
                            f"Meta response ended with {final_response.get('status', event_type)}: "
                            + json.dumps(detail, ensure_ascii=False)[:1200]
                        )
                    _add_usage(usage, final_response.get("usage") or {})
                    yield {"type": "metrics", "usage": dict(usage)}
            if final_response is None:
                raise RuntimeError("Meta Responses stream ended without a terminal response event.")

            output_items = final_response.get("output") or []
            # Preserve all returned messages, function calls and encrypted reasoning exactly.
            input_items.extend(output_items)
            function_calls = [item for item in output_items if item.get("type") == "function_call"]
            if not function_calls:
                break

            for call in function_calls:
                args = {}
                name = str(call.get("name") or "")
                call_id = str(call.get("call_id") or "")
                raw_args = call.get("arguments") or "{}"
                try:
                    if not call_id or len(call_id) > 64:
                        raise ValueError("Meta returned an invalid function call id.")
                    args = json.loads(raw_args)
                    if not isinstance(args, dict):
                        raise ValueError("Function arguments must be a JSON object.")
                    if name not in selected_names:
                        raise PermissionError("This tool is not enabled for the current conversation.")
                    yield {
                        "type": "tool_call", "tool_call_id": call_id,
                        "tool_name": name, "arguments": args, "step": step,
                    }
                    output = tools.run(name, args, session_id)
                    status = "ok"
                except Exception as exc:
                    output = {"error": str(exc)[:500]}
                    status = "error"
                    yield {
                        "type": "tool_call", "tool_call_id": call_id or "invalid",
                        "tool_name": name or "unknown", "arguments": args, "step": step,
                    }
                record = {
                    "tool_call_id": call_id, "tool_name": name,
                    "input": args, "output": output, "status": status, "step": step,
                }
                call_events.append({
                    "tool_name": name, "status": status, "input": args, "output": output,
                })
                await ui_store.save_tool_event(session_id, name, args, output, status)
                yield {"type": "tool_result", **record}
                # The call_id exactly pairs this result with the function_call item above.
                input_items.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(output, ensure_ascii=False),
                })
            await ui_store.save_agent_state(session_id, input_items, model_id)

        final_text = "".join(response_parts) or _response_text(final_response)
        final_text = final_text[:100000]
        await ui_store.save_agent_state(session_id, input_items)
        await ui_store.save_chat_message(session_id, "assistant", final_text)
        latency_ms = (time.monotonic() - started) * 1000
        await ui_store.save_metric(session_id, "latency_ms", latency_ms)
        for key, value in usage.items():
            await ui_store.save_metric(session_id, key, value)
        yield {
            "type": "done", "content": final_text, "tool_events": call_events,
            "usage": usage, "latency_ms": round(latency_ms, 2),
            "tool_names": selected_names, "model": model_id,
            "reasoning_effort": effort or model["default_reasoning_effort"],
        }
    except Exception as exc:
        yield {
            "type": "error", "message": str(exc)[:1200],
            "traceback": traceback.format_exc()[-6000:],
            "tool_events": call_events if "call_events" in locals() else [],
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
        }
