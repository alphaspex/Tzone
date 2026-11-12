# Meta Responses API

Minimal Meta Responses API gateway with Cloudflare D1 connectivity monitoring.

- `backend/`: FastAPI gateway, Meta transport, model catalogue/configuration, and D1 connection check.
- `frontend/`: intentionally empty placeholder.

The backend uses the existing Deplexo environment variables. D1 remains connected for health checks, but all application tables and persistence logic have been removed.
