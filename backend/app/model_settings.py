"""Static model selection. Input: environment settings. Output: validated Meta model configuration."""
from . import model_catalog
from .config import settings


def get_settings():
    model = model_catalog.get_model(settings.default_model)
    if model is None:
        model = model_catalog.get_model("muse-spark-1.3")
    return model
