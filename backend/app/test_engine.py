"""Individual test-run lifecycle. Inputs: saved test ID and cancellation. Outputs: run state and live UI events."""
import asyncio
import time
import uuid
import traceback
from collections import deque
from datetime import datetime, timezone
from . import evaluator, playground, test_library, ui_store, model_settings, model_catalog

_LIVE = {}
_TASKS = {}
_MAX_LIVE_EVENTS = 1200
_MAX_LIVE_CACHE = 10
_MAX_CONCURRENT_RUNS = 1

def _now():
    return datetime.now(timezone.utc).isoformat()

async def _publish(run_id, event):
    state = _LIVE.get(run_id)
    if not state:
        return
    item = {"run_id":run_id,"timestamp":_now(),**event,"_seq":state["next_seq"]}
    state["next_seq"] += 1
    state["events"].append(item)
    if item.get("type") != "token":
        await ui_store.save_run_event(run_id,item)
    condition = state["condition"]
    async with condition:
        condition.notify_all()

async def start_run(test_id, reasoning_effort=None):
    case = test_library.get_case(test_id)
    if case is None:
        case = await ui_store.get_custom_test(test_id)
    if not case:
        raise KeyError("Test not found")
    active = [task for task in _TASKS.values() if not task.done()]
    if len(active) >= _MAX_CONCURRENT_RUNS:
        raise RuntimeError("A test run is already active. This service runs one test at a time.")
    while len(_TASKS) >= _MAX_LIVE_CACHE:
        oldest_id = next(iter(_TASKS))
        oldest_task = _TASKS[oldest_id]
        if not oldest_task.done():
            break
        _TASKS.pop(oldest_id, None)
        _LIVE.pop(oldest_id, None)
    model_id, global_effort, model = await model_settings.resolve()
    stored_effort = (case.get("parameters") or {}).get("reasoning_effort")
    requested_effort = reasoning_effort if reasoning_effort not in (None, "", "auto") else stored_effort
    selected_effort = model_settings.model_catalog.validate_reasoning_effort(
        model_id, requested_effort if requested_effort not in (None, "", "auto") else global_effort)
    if selected_effort:
        case["_reasoning_effort"] = selected_effort
    run_id = "run_" + uuid.uuid4().hex[:16]
    created_at = _now()
    run = {
        "id":run_id,"session_id":run_id,"test_id":test_id,
        "test_name":case.get("name","Unnamed test"),"category":case.get("category"),
        "difficulty":case.get("difficulty"),"difficulty_label":case.get("difficulty_label"),
        "model":model_id,"reasoning_effort":selected_effort or model["default_reasoning_effort"],
        "status":"queued","passed":None,
        "created_at":created_at,"started_at":None,"completed_at":None,
        "result":None,"error":None,
    }
    condition = asyncio.Condition()
    _LIVE[run_id] = {"events":deque(maxlen=_MAX_LIVE_EVENTS),"condition":condition,"done":False,"next_seq":0}
    await ui_store.create_run(run)
    _TASKS[run_id] = asyncio.create_task(_execute(run_id,case))
    return run

async def _execute_inner(run_id, case):
    run_record = await ui_store.get_run(run_id) or {}
    started = time.monotonic()
    await ui_store.update_run(run_id,{"status":"running","started_at":_now()})
    await _publish(run_id,{"type":"status","status":"running","message":"Starting test"})
    tool_events, responses, usage = [], [], {}
    stream_event_count = 0
    final_latency = 0.0
    error = None
    error_trace = None
    try:
        messages = case.get("messages") or [{"role":"user","content":case.get("user_prompt","")}]
        for index, message in enumerate(messages):
            if message.get("role") != "user":
                continue
            await _publish(run_id,{"type":"activity","stage":"turn","turn":index+1,"message":"Processing conversation turn"})
            turn_parameters = dict(case.get("parameters") or {})
            if case.get("_reasoning_effort"):
                turn_parameters["reasoning_effort"] = case["_reasoning_effort"]
            async for event in playground.stream_turn(
                session_id=run_id,
                user_text=message.get("content",""),
                tool_names=case.get("tool_names",[]),
                parameters=turn_parameters,
                system_prompt=case.get("system_prompt",""),
            ):
                if event.get("type") == "done":
                    responses.append(event.get("content",""))
                    tool_events.extend(event.get("tool_events",[]))
                    for key, value in (event.get("usage") or {}).items():
                        if isinstance(value, (int, float)):
                            usage[key] = usage.get(key, 0) + value
                    final_latency += float(event.get("latency_ms",0))
                    await _publish(run_id,{"type":"turn_complete","turn":index+1,
                                           "content":event.get("content",""),
                                           "usage":event.get("usage") or {},
                                           "latency_ms":event.get("latency_ms",0)})
                elif event.get("type") == "error":
                    error = event.get("message","Model error")
                    error_trace = event.get("traceback","")
                    await _publish(run_id,{"type":"error","message":error,"traceback":error_trace})
                else:
                    if event.get("type") == "token":
                        stream_event_count += 1
                    await _publish(run_id,event)
            if error:
                break
        final_response = responses[-1] if responses else ""
        deterministic = evaluator.run_assertions(final_response,case.get("assertions",[]),tool_events,stream_event_count)
        await _publish(run_id,{"type":"evaluation","stage":"assertions","passed":deterministic["passed"],
                               "score":deterministic["score"]})
        judge = await evaluator.run_judge(final_response,case.get("judge_rubric",""))
        judge_usage = judge.get("usage") or {}
        for key,value in judge_usage.items():
            if isinstance(value,(int,float)):
                await ui_store.save_metric(run_id,"judge_"+key,value)
        await _publish(run_id,{"type":"evaluation","stage":"model_judge","available":judge.get("available"),
                               "score":judge.get("score"),"passed":judge.get("passed")})
        passed = bool(deterministic["passed"] and (judge.get("passed") if judge.get("available") else True))
        total_latency = (time.monotonic()-started)*1000
        model_id = run_record.get("model")
        agent_cost = model_catalog.estimate_price(
            model_id, usage.get("input_tokens", 0), usage.get("output_tokens", 0),
            usage.get("cached_input_tokens", 0))
        judge_cost = model_catalog.estimate_price(
            model_id, judge_usage.get("input_tokens", 0), judge_usage.get("output_tokens", 0),
            (judge_usage.get("input_tokens_details") or {}).get("cached_tokens", 0))
        estimated_cost = round((agent_cost or 0) + (judge_cost or 0), 8)
        result = {
            "full_prompt":case.get("messages") or [{"role":"user","content":case.get("user_prompt","")}],
            "system_prompt":case.get("system_prompt",""),
            "full_response":final_response,"turn_responses":responses,
            "expected_output":case.get("expected_output"),
            "assertion_results":deterministic,"model_evaluation":judge,
            "tool_events":tool_events,"errors":[{"message":error,"stack_trace":error_trace}] if error else [],
            "usage":usage,"judge_usage":judge_usage,"model":run_record.get("model"),
            "reasoning_effort":run_record.get("reasoning_effort"),
            "stream_text_events":stream_event_count,"estimated_cost_usd":estimated_cost,"latency_ms":round(total_latency,2),
            "model_latency_ms":round(final_latency,2),
        }
        final_status = "failed" if error else "completed"
        run = await ui_store.update_run(run_id,{
            "status":final_status,"passed":passed,"completed_at":_now(),
            "result":result,"error":error,"latency_ms":round(total_latency,2),
            "estimated_cost_usd":estimated_cost,
        })
        await ui_store.save_metric(run_id,"estimated_cost_usd",estimated_cost)
        await _publish(run_id,{"type":"done","status":final_status,"passed":passed,
                               "result":result,"latency_ms":round(total_latency,2)})
    except Exception as exc:
        error = str(exc)[:1200]
        error_trace = traceback.format_exc()[-6000:]
        await ui_store.update_run(run_id,{"status":"failed","completed_at":_now(),"error":error})
        await _publish(run_id,{"type":"error","status":"failed","message":error,"traceback":error_trace})
        await _publish(run_id,{"type":"done","status":"failed","passed":False,"error":error})


async def _execute(run_id, case):
    """Run until completion, error, or explicit cancellation."""
    state = _LIVE.get(run_id)
    try:
        await _execute_inner(run_id, case)
    except asyncio.CancelledError:
        message = "Cancelled by user"
        run = await ui_store.get_run(run_id)
        if run and run.get("status") in ("queued","running"):
            await ui_store.update_run(run_id,{"status":"cancelled",
                "completed_at":_now(),"error":message})
            await _publish(run_id,{"type":"cancelled","status":"cancelled","message":message})
        raise
    finally:
        if state:
            state["done"] = True
            async with state["condition"]:
                state["condition"].notify_all()

async def cancel_run(run_id):
    task = _TASKS.get(run_id)
    run = await ui_store.get_run(run_id)
    if not run:
        return None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    run = await ui_store.get_run(run_id)
    # A task cancelled before its coroutine first runs cannot execute its own cleanup.
    if run and run.get("status") in ("queued","running"):
        await ui_store.update_run(run_id,{"status":"cancelled","completed_at":_now(),"error":"Cancelled by user"})
        await _publish(run_id,{"type":"cancelled","status":"cancelled","message":"Cancelled by user"})
        state = _LIVE.get(run_id)
        if state:
            state["done"] = True
            async with state["condition"]:
                state["condition"].notify_all()
    return await ui_store.get_run(run_id)

async def stream_events(run_id):
    """Replay buffered activity and wait safely for new events until the run completes."""
    state = _LIVE.get(run_id)
    if state is None:
        for event in await ui_store.list_run_events(run_id):
            yield event
        return
    cursor = 0
    condition = state["condition"]
    while True:
        async with condition:
            await condition.wait_for(
                lambda: state["done"] or any(item["_seq"] >= cursor for item in state["events"])
            )
            batch = list(state["events"])
            finished = state["done"]
        for item in batch:
            if item["_seq"] >= cursor:
                cursor = item["_seq"] + 1
                yield {key:value for key,value in item.items() if key != "_seq"}
        if finished and not any(item["_seq"] >= cursor for item in state["events"]):
            break
