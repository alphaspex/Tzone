"""Global Meta model settings. Input: validated UI selections. Output: saved effective configuration."""
from . import model_catalog, ui_store
from .config import settings


async def get_settings():
    saved = await ui_store.get_harness_settings()
    model_id = saved.get("model") or settings.default_model
    if not model_catalog.get_model(model_id):
        model_id = "muse-spark-1.3"
    effort = saved.get("reasoning_effort")
    try:
        effort = model_catalog.validate_reasoning_effort(model_id, effort)
    except ValueError:
        effort = None
    model = model_catalog.get_model(model_id)
    return {
        "provider": "Meta Model API",
        "base_url": settings.meta_base_url,
        "model": model_id,
        "model_name": model["name"],
        "reasoning_effort": effort,
        "meta_default_reasoning_effort": model["default_reasoning_effort"],
        "reasoning_efforts": model_catalog.reasoning_efforts(model_id),
        "provider_configured": bool(settings.meta_api_key),
    }


async def update_settings(model_id, reasoning_effort=None):
    model = model_catalog.get_model(str(model_id or ""))
    if not model:
        raise ValueError("Select a model from the Meta model catalogue.")
    effort = model_catalog.validate_reasoning_effort(model["id"], reasoning_effort)
    updated = {"model": model["id"], "reasoning_effort": effort}
    await ui_store.save_harness_settings(updated)
    return await get_settings()


async def resolve(model_override=None, reasoning_override=None):
    configured = await get_settings()
    model_id = model_override or configured["model"]
    model = model_catalog.get_model(model_id)
    if not model:
        raise ValueError(f"Unsupported Meta model: {model_id}")
    effort = reasoning_override if reasoning_override not in (None, "", "auto") else configured["reasoning_effort"]
    effort = model_catalog.validate_reasoning_effort(model_id, effort)
    return model_id, effort, model
