# Model Lab frontend

Static HTML, CSS, and JavaScript. No build step or frontend framework is required.

## Files

- index.html — page shell and sidebar navigation.
- styles.css — responsive dark workspace styling.
- app.js — UI behavior and API client.

## Connect to the backend

Host these files on a static host or in a Hugging Face Static Space. Open Settings, enter the deployed Deplexo service URL, and select Test connection.

The UI calls only the backend's /ui/* endpoints. It does not call /v1, Cloudflare D1, or Z.ai directly.

The API URL is saved in browser local storage. The Z.ai key remains on the backend and must never be added to frontend files.

The backend must allow browser CORS requests from the static site's origin. The current backend CORS configuration permits all origins; restrict this before public use.
