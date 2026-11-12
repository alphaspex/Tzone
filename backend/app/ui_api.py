"""UI-only HTTP boundary. Inputs: UI JSON requests. Outputs: stable UI JSON responses and named SSE events."""
import json
import os
import resource
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, Response, PlainTextResponse
from . import playground, test_engine, test_library, tools, ui_store, store, model_catalog, model_settings
from .config import settings

router = APIRouter(prefix="/ui", tags=["ui"])

def _sse(event):
    event_type = str(event.get("type","message"))
    return "event: " + event_type + "\ndata: " + json.dumps(event,ensure_ascii=False) + "\n\n"

def _run_summary(run):
    result = run.get("result") or {}
    assertion = result.get("assertion_results") or {}
    usage = result.get("usage") or {}
    return {key:run.get(key) for key in
            ("id","test_id","test_name","category","difficulty","difficulty_label","model","reasoning_effort","status","passed",
             "created_at","started_at","completed_at","latency_ms","error")} | {
            "assertion_score":assertion.get("score"),
            "assertions_passed":assertion.get("passed_count"),
            "assertions_total":assertion.get("total"),
            "judge_score":(result.get("model_evaluation") or {}).get("score"),
            "total_tokens":usage.get("total_tokens"),
        }

def _current_memory_mb():
    try:
        with open("/proc/self/status","r",encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1])/1024,2)
    except Exception:
        pass
    try:
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2)
    except Exception:
        return None

async def _validate_custom_test(body, existing=None):
    data = dict(existing or {})
    data.update(body or {})
    name = str(data.get("name","")).strip()
    prompt = str(data.get("user_prompt","")).strip()
    if not name or len(name) > 120:
        raise HTTPException(422,"name is required and must be at most 120 characters")
    if not prompt or len(prompt) > 30000:
        raise HTTPException(422,"user_prompt is required and must be at most 30000 characters")
    category = str(data.get("category","custom_prompts"))
    if category not in test_library.CATEGORIES:
        raise HTTPException(422,"unsupported test category")
    assertions = data.get("assertions") or []
    if not isinstance(assertions,list) or len(assertions) > 25:
        raise HTTPException(422,"assertions must be a list of at most 25 rules")
    configured = await model_settings.get_settings()
    parameters = playground.normalize_parameters(data.get("parameters") or {}, configured["model"])
    parameters.setdefault("max_output_tokens", 1024)
    return {
        "id":data.get("id") or "custom_" + uuid.uuid4().hex[:16],
        "name":name,"category":category,
        "difficulty":str(data.get("difficulty","mid")),
        "difficulty_label":test_library.LEVEL_METADATA.get(str(data.get("difficulty","mid")), {}).get("label", "Custom"),
        "description":str(data.get("description",""))[:1000],
        "system_prompt":str(data.get("system_prompt",""))[:8000],
        "user_prompt":prompt,
        "messages":[{"role":"user","content":prompt}],
        "expected_output":str(data.get("expected_output",""))[:8000],
        "assertions":assertions,
        "judge_rubric":str(data.get("judge_rubric",""))[:3000],
        "tool_names":[n for n in data.get("tool_names",[]) if n in tools.available_names()] if data.get("tool_names") else tools.select_for_task(prompt),
        "parameters":parameters,
        "tags":[str(x)[:40] for x in data.get("tags",[])[:20]],
        "is_builtin":False,
    }

@router.get("/dashboard")
async def dashboard():
    runs = await ui_store.list_runs(20)
    completed = [r for r in runs if r.get("status") in ("completed","failed")]
    passed = [r for r in completed if r.get("passed") is True]
    active = [r for r in runs if r.get("status") in ("queued","running")]
    return {
        "model":(await model_settings.get_settings())["model"],"provider_configured":bool(settings.meta_api_key),
        "d1_configured":store.configured(),"system_memory_mb":_current_memory_mb(),
        "runs_total":len(runs),"runs_completed":len(completed),
        "runs_passed":len(passed),"pass_rate":round(len(passed)/len(completed),4) if completed else None,
        "active_runs":[_run_summary(r) for r in active],
        "recent_runs":[_run_summary(r) for r in runs[:10]],
        "built_in_tests":test_library.count(),
    }

@router.get("/system")
async def system_status():
    try:
        load = list(os.getloadavg())
    except (AttributeError,OSError):
        load = None
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "status":"ok","memory_rss_mb":_current_memory_mb(),
        "memory_peak_mb":round(usage.ru_maxrss/1024,2),
        "cpu_count":os.cpu_count(),"load_average":load,
        "process_cpu_seconds":round(usage.ru_utime+usage.ru_stime,3),
        "provider_configured":bool(settings.meta_api_key),
        "d1_configured":store.configured(),
        "model":(await model_settings.get_settings())["model"],"timestamp":datetime.now(timezone.utc).isoformat(),
    }

@router.get("/model/status")
async def model_status():
    configured = await model_settings.get_settings()
    return {
        "model": configured["model"], "model_name": configured["model_name"],
        "provider": "Meta Model API", "base_url": settings.meta_base_url,
        "configured": bool(settings.meta_api_key), "streaming": True,
        "reasoning_effort": configured["reasoning_effort"],
        "default_reasoning_effort": configured["meta_default_reasoning_effort"],
    }


@router.get("/models")
async def list_models():
    return {"provider": "Meta Model API", "models": model_catalog.public_models()}


@router.get("/model/config")
async def model_config():
    configured = await model_settings.get_settings()
    return {
        "provider": "Meta Model API", "model": configured["model"],
        "reasoning_efforts": configured["reasoning_efforts"],
        "supported_parameters": {
            "max_output_tokens": {"type": "integer", "min": 16, "max": 65536},
            "reasoning.effort": {"enum": configured["reasoning_efforts"]},
            "temperature": {"type": "number", "min": 0, "max": 2, "mutually_exclusive_with": "top_p"},
            "top_p": {"type": "number", "min": 0, "max": 1, "mutually_exclusive_with": "temperature"},
            "text.format": {"type": "object", "description": "Responses API output formatting and JSON Schema."},
        },
        "defaults": {"max_output_tokens": 2048, "reasoning_effort": "Meta model default"},
        "unsupported": ["max_tokens", "presence_penalty", "frequency_penalty", "stop", "logit_bias", "logprobs", "n", "stream_options"],
    }

@router.get("/tests/categories")
async def test_categories():
    return {"categories":test_library.category_summary(),
            "levels":test_library.LEVELS,
            "level_details":test_library.LEVEL_METADATA,
            "built_in_count":test_library.count()}

@router.get("/tests")
async def list_tests(category: str | None = None, difficulty: str | None = None):
    if category and category not in test_library.CATEGORIES:
        raise HTTPException(422,"unknown category")
    if difficulty and difficulty not in test_library.LEVELS:
        raise HTTPException(422,"unknown difficulty")
    builtins = test_library.list_cases(category,difficulty)
    custom = await ui_store.list_custom_tests()
    custom = [test_library.public_case(case) for case in custom
              if (not category or case.get("category") == category)
              and (not difficulty or case.get("difficulty") == difficulty)]
    return {"tests":builtins+custom,"built_in_count":len(builtins),"custom_count":len(custom)}

@router.get("/tests/{test_id}")
async def get_test(test_id: str):
    case = test_library.get_case(test_id)
    if case is None:
        case = await ui_store.get_custom_test(test_id)
    if not case:
        raise HTTPException(404,"test not found")
    # Full evaluation setup is returned only to the trusted UI, never to playground.stream_turn.
    return case

@router.post("/tests")
async def create_test(body: dict):
    case = await _validate_custom_test(body)
    await ui_store.save_custom_test(case)
    return {"test":case,"saved":True}

@router.put("/tests/{test_id}")
async def update_test(test_id: str, body: dict):
    if test_library.get_case(test_id):
        raise HTTPException(403,"built-in tests are read-only")
    existing = await ui_store.get_custom_test(test_id)
    if not existing:
        raise HTTPException(404,"custom test not found")
    case = await _validate_custom_test(body,existing)
    case["id"] = test_id
    await ui_store.save_custom_test(case)
    return {"test":case,"saved":True}

@router.delete("/tests/{test_id}")
async def delete_test(test_id: str):
    if test_library.get_case(test_id):
        raise HTTPException(403,"built-in tests cannot be deleted")
    deleted = await ui_store.delete_custom_test(test_id)
    if not deleted:
        raise HTTPException(404,"custom test not found")
    return {"deleted":True,"test_id":test_id}

@router.post("/runs")
async def start_test_run(body: dict):
    test_id = str(body.get("test_id","")).strip()
    if not test_id:
        raise HTTPException(422,"test_id is required")
    try:
        run = await test_engine.start_run(test_id, body.get("reasoning_effort"))
    except KeyError as exc:
        raise HTTPException(404,str(exc))
    except RuntimeError as exc:
        raise HTTPException(409,str(exc))
    return {"run":_run_summary(run),"stream_url":f"/ui/runs/{run['id']}/stream"}

@router.get("/runs")
async def list_test_runs(limit: int = 100, status: str | None = None,
                         category: str | None = None, test_id: str | None = None,
                         passed: bool | None = None):
    runs = await ui_store.list_runs(limit)
    if status:
        runs = [r for r in runs if r.get("status") == status]
    if category:
        runs = [r for r in runs if r.get("category") == category]
    if test_id:
        runs = [r for r in runs if r.get("test_id") == test_id]
    if passed is not None:
        runs = [r for r in runs if r.get("passed") is passed]
    return {"runs":[_run_summary(run) for run in runs]}

@router.post("/runs/compare")
async def compare_test_runs(body: dict):
    ids = body.get("run_ids") or []
    if not isinstance(ids,list) or not 2 <= len(ids) <= 10:
        raise HTTPException(422,"run_ids must contain between 2 and 10 IDs")
    runs = []
    for run_id in ids:
        run = await ui_store.get_run(str(run_id))
        if not run:
            raise HTTPException(404,f"run not found: {run_id}")
        runs.append(run)
    return {"runs":[_run_summary(run) for run in runs],
            "comparison":[{"run_id":r.get("id"),"passed":r.get("passed"),
                           "latency_ms":r.get("latency_ms"),
                           "usage":(r.get("result") or {}).get("usage"),
                           "assertion_score":((r.get("result") or {}).get("assertion_results") or {}).get("score"),
                           "judge_score":((r.get("result") or {}).get("model_evaluation") or {}).get("score")}
                          for r in runs]}

@router.get("/runs/{run_id}")
async def get_test_run(run_id: str):
    run = await ui_store.get_run(run_id)
    if not run:
        raise HTTPException(404,"run not found")
    return {"run":run}

@router.get("/runs/{run_id}/export")
async def export_test_run(run_id: str, format: str = "json"):
    run = await ui_store.get_run(run_id)
    if not run:
        raise HTTPException(404,"run not found")
    export_format = format.lower()
    if export_format == "json":
        payload = json.dumps(run,ensure_ascii=False,indent=2)
        return Response(payload,media_type="application/json",
                        headers={"Content-Disposition":f'attachment; filename="{run_id}.json"'})
    if export_format == "markdown":
        result = run.get("result") or {}
        assertion = result.get("assertion_results") or {}
        fence = chr(96) * 3
        lines = [
            f"# {run.get('test_name','Test run')}",
            "",
            f"- Run: {run_id}",
            f"- Status: {run.get('status')}",
            f"- Passed: {run.get('passed')}",
            f"- Latency: {run.get('latency_ms')} ms",
            "",
            "## Prompt",
            fence + "text",
            json.dumps(result.get("full_prompt",[]),ensure_ascii=False,indent=2),
            fence,
            "",
            "## Response",
            fence + "text",
            result.get("full_response",""),
            fence,
            "",
            "## Assertions",
        ]
        for item in assertion.get("assertions",[]):
            lines.append(f"- [{'x' if item.get('passed') else ' '}] {item.get('type')}: {item.get('detail')}")
        lines.extend(["","## Usage",json.dumps({"agent":result.get("usage"),"judge":result.get("judge_usage"),"latency_ms":result.get("latency_ms")},ensure_ascii=False,indent=2),
                      "","## Model evaluation",json.dumps(result.get("model_evaluation"),ensure_ascii=False,indent=2),
                      "","## Tool events",json.dumps(result.get("tool_events",[]),ensure_ascii=False,indent=2),
                      "","## Errors",json.dumps(result.get("errors",[]),ensure_ascii=False,indent=2)])
        return PlainTextResponse("\n".join(lines),media_type="text/markdown",
                                 headers={"Content-Disposition":f'attachment; filename="{run_id}.md"'})
    raise HTTPException(422,"format must be json or markdown")

@router.post("/runs/{run_id}/cancel")
async def cancel_test_run(run_id: str):
    run = await test_engine.cancel_run(run_id)
    if not run:
        raise HTTPException(404,"run not found")
    return {"run":_run_summary(run)}

@router.get("/runs/{run_id}/events")
async def get_run_events(run_id: str):
    run = await ui_store.get_run(run_id)
    if not run:
        raise HTTPException(404,"run not found")
    return {"events":await ui_store.list_run_events(run_id)}

@router.get("/runs/{run_id}/stream")
async def stream_test_run(run_id: str):
    run = await ui_store.get_run(run_id)
    if not run:
        raise HTTPException(404,"run not found")
    async def generate():
        async for event in test_engine.stream_events(run_id):
            yield _sse(event)
        yield "event: end\ndata: [DONE]\n\n"
    return StreamingResponse(generate(),media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@router.get("/agent")
async def agent_info():
    configured = await model_settings.get_settings()
    return {"model":configured["model"],"mode":"direct-playground",
            "free_chat":True,"test_backed_chat":True,
            "tool_selection":"automatic by task intent or selected test scenario",
            "evaluation_visible_to_agent":False}

@router.post("/agent/chat")
async def agent_chat(request: Request):
    raw = await request.body()
    if len(raw) > 100000:
        raise HTTPException(413,"request body exceeds 100 KB")
    try:
        body = json.loads(raw)
    except Exception:
        raise HTTPException(400,"request body must be valid JSON")
    if not isinstance(body,dict):
        raise HTTPException(400,"request body must be a JSON object")
    test_id = body.get("test_id")
    case = None
    if test_id:
        case = test_library.get_case(str(test_id)) or await ui_store.get_custom_test(str(test_id))
        if not case:
            raise HTTPException(404,"test not found")
    user_text = str(body.get("message") or (case or {}).get("user_prompt") or "").strip()
    if not user_text:
        raise HTTPException(422,"message is required for free chat")
    session_id = str(body.get("conversation_id") or "chat_" + uuid.uuid4().hex[:16])
    selected_tools = case.get("tool_names",[]) if case else None
    system_prompt = (case or {}).get("system_prompt","")
    parameters = body.get("parameters") or ((case or {}).get("parameters") or {})
    if body.get("reasoning_effort") not in (None, "", "auto"):
        parameters = dict(parameters)
        parameters["reasoning_effort"] = body["reasoning_effort"]
    async def generate():
        async for event in playground.stream_turn(session_id,user_text,
                    tool_names=selected_tools,parameters=parameters,system_prompt=system_prompt):
            yield _sse({"conversation_id":session_id,**event})
        yield "event: end\ndata: [DONE]\n\n"
    return StreamingResponse(generate(),media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Conversation-ID":session_id})

@router.get("/conversations")
async def conversations(limit: int = 100):
    return {"conversations":await ui_store.list_conversations(limit)}

@router.get("/conversations/{conversation_id}")
async def conversation_detail(conversation_id: str):
    messages = await ui_store.get_messages(conversation_id,200)
    if not messages:
        raise HTTPException(404,"conversation not found")
    return {"id":conversation_id,"messages":messages}

@router.get("/tools")
async def list_tools():
    return {"tools":[item["function"] for item in tools.definitions()],
            "selection":"Tools are selected automatically for free chat and from each test scenario for test-backed runs."}

@router.get("/metrics")
async def metrics(session_id: str | None = None, limit: int = 500):
    values = await ui_store.list_metrics(session_id,limit)
    latency = [float(x.get("value",0)) for x in values if x.get("metric") == "latency_ms"]
    return {"metrics":values,"summary":{
        "samples":len(values),"latency_samples":len(latency),
        "average_latency_ms":round(sum(latency)/len(latency),2) if latency else None,
        "max_latency_ms":max(latency) if latency else None,
    }}

@router.get("/traces")
async def traces(limit: int = 50):
    events = await ui_store.list_tool_events(limit=limit)
    runs = await ui_store.list_runs(min(limit,100))
    return {"tool_events":events,"runs":[_run_summary(run) for run in runs]}

@router.get("/traces/{trace_id}")
async def trace_detail(trace_id: str):
    run = await ui_store.get_run(trace_id)
    if run:
        return {"run":run,"events":await ui_store.list_run_events(trace_id)}
    events = await ui_store.list_tool_events(session_id=trace_id,limit=500)
    if not events:
        raise HTTPException(404,"trace not found")
    return {"session_id":trace_id,"tool_events":events}

@router.get("/logs")
async def logs(limit: int = 100):
    runs = await ui_store.list_runs(limit)
    errors = [{"run_id":r.get("id"),"status":r.get("status"),"error":r.get("error"),
               "created_at":r.get("created_at")} for r in runs if r.get("error")]
    failed_tools = [e for e in await ui_store.list_tool_events(limit=limit) if e.get("status") != "ok"]
    return {"errors":errors,"tool_errors":failed_tools}

@router.get("/settings")
async def ui_settings():
    configured = await model_settings.get_settings()
    return {
        **configured,
        "models": model_catalog.public_models(),
        "base_url": settings.meta_base_url,
        "max_agent_steps": settings.max_agent_steps,
        "request_timeout_seconds": settings.request_timeout,
        "d1_configured": store.configured(),
        "authentication_enabled": False,
        "warning": "No backend authentication is configured. Restrict service ingress before public exposure.",
    }


@router.put("/settings")
async def update_ui_settings(body: dict):
    contributor = str(body.get("model", "")).endswith("-contributor")
    if contributor and body.get("confirm_contributor") is not True:
        raise HTTPException(428, "Contributor model selection requires explicit data-use confirmation.")
    try:
        updated = await model_settings.update_settings(
            body.get("model"), body.get("reasoning_effort"))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {
        **updated,
        "models": model_catalog.public_models(),
        "d1_configured": store.configured(),
        "request_timeout_seconds": settings.request_timeout,
    }
