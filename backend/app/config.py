"""Environment configuration. Input: process environment. Output: immutable settings."""
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    zai_api_key: str = os.getenv("ZAI_API_KEY", "")
    zai_base_url: str = os.getenv("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4")
    model: str = os.getenv("MODEL_NAME", "glm-4.7-flash")
    cf_account_id: str = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    cf_api_token: str = os.getenv("CLOUDFLARE_API_TOKEN", "")
    d1_database_id: str = os.getenv("D1_DATABASE_ID", "520245ce-7de8-4462-afe6-3de6f0f9e985")
    max_agent_steps: int = int(os.getenv("MAX_AGENT_STEPS", "0"))
    request_timeout: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "90"))

settings = Settings()
