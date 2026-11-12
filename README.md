# Model Lab

A lightweight model-testing workspace for GLM-4.7-Flash.

## Repository layout

- **backend/** — FastAPI gateway, isolated UI endpoint contract, test engine, evaluator, tools, and Cloudflare D1 adapter. See backend/README.md.
- **frontend/** — static workspace UI. It communicates only with the backend's /ui/* endpoints.

## Connection

Deploy the backend using backend/ as the Docker build context. Host the contents of frontend/ as a static site or Hugging Face Static Space. Open Settings in the UI and enter the deployed Deplexo service base URL.

The browser saves that URL locally. No API key is stored in the frontend.

## Important

The backend currently has no application authentication, by design. Restrict public access to the Deplexo service before sharing it. The tested model does not receive private evaluator rules or scores.
