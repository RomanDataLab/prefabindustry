<!-- Copied and tailored for this repository. Keep concise: focus on what an AI coding agent needs to be productive. -->

# Copilot / AI Agent Instructions — Prefab Research

Quick summary
- This repo contains research scripts (JS + Python) and a small Next.js map app. The research code is stateful: it reads API keys from an external `config` folder, writes CSV/JSON to `research_output/`, and frequently saves progress so runs are resumable.

Key components
- `core/` — main research logic (mix of Python and Node helpers). Example runner: `node core/researchPrefabCompanies.js` (also invoked via `npm run research`). See [core/README.md](core/README.md).
- `configix/` — centralized config loader and AI-provider switching helpers:
  - `configix/apiManager.py` and `configix/apiManager.js` implement the same fallback logic for locating `config/` and expose: `get_current_ai()`, `switch_ai_provider('ai_gemini'|'ai_grok'|'ai_openai')`, and `get_mapbox_config()`.
- `maps/` — Next.js + Mapbox app. Dev: `cd maps && npm install && npm run dev`. See [maps/README.md](maps/README.md).
- `research_output/` — CSV/JSON outputs and progress backups; treat these as stateful artifacts that scripts rely on for resume behavior.

Configuration & secrets (very important)
- Config files are external to the repo. The loaders try these paths (in order):
  1. `./config` (repo-relative)
 2. `C:/12_CODINGHARD/config` (absolute Windows path used in this environment)
 3. alternative relative fallbacks used by the loader.
- Expected files (examples): `config_openai.json` (contains `openai_api_key`), `config_gemini.json`, `config_grok.json`, and `mapboxConfig.js` (contains `MAPBOX_ACCESS_TOKEN` and `MAPBOX_STYLE`).
- Mapbox parsing: the JS/Python loaders look for assignments like `MAPBOX_ACCESS_TOKEN = '...'` in `mapboxConfig.js` — keep that format.
- ORS key: optional `openrouteservice.env` in the config dir with a line `ORS_API_KEY=...`.

Running & developer workflows
- Node research (main entry): from repo root:
  - `npm install` (installs node deps used by JS research scripts)
  - `npm run research` (runs `core/researchPrefabCompanies.js`)
- Python scripts: use the Python environment and `requirements.txt`:
  - `pip install -r requirements.txt`
  - Run individual scripts under `core/` (many are standalone). Most Python scripts assume the same external `config` folder.
- Maps app: `cd maps && npm install && npm run dev` (serves at http://localhost:3000)
- Deployment: `maps/` is a Vercel project — `vercel` or connect via GitHub for automatic deploys.

Project-specific patterns and conventions
- Language & output: research uses local-language queries for discovery but writes English results. Expect column names in `research_output/` to match those listed in `core/README.md` (do not rename unless also updating consumers).
- Statefulness & resume behavior: scripts update `research_output/progress_backup.json` frequently (every ~5 companies). When writing fixes, preserve the resume semantics (skip already-processed entries).
- Rate limiting: the research code includes delays to avoid API rate limits. Avoid turning research into massively parallel requests without adjusting rate-limiting logic.
- AI provider switching: prefer using `configix/apiManager.*` for provider configuration rather than hardcoding keys. Example (Python):
  ```py
  from configix import apiManager
  apiManager.switch_ai_provider('ai_gemini')
  cfg = apiManager.get_current_ai()
  ```
  Example (Node):
  ```js
  const mgr = require('./configix/apiManager');
  mgr.switchAIProvider('ai_gemini');
  const cur = mgr.getCurrentAI();
  ```

Integration points & files to inspect when changing behavior
- `configix/apiManager.py` and `configix/apiManager.js` — config discovery and provider switching.
- `core/researchPrefabCompanies.js` and other `core/*.py` scripts — main logic, outputs, and progress handling.
- `maps/` — front-end Mapbox usage and API route that exposes Mapbox config to the client.
- `research_output/` — read these to understand the exact CSV/JSON schema used across scripts.

What NOT to change without caution
- Do not change the external config discovery heuristics lightly — tests and local setups rely on the three-path fallback behavior.
- Do not change output column names or progress file formats unless you update all consumers and the resume logic.

If you need to modify or extend
- Update `configix/apiManager.*` to add a new provider or config file; keep symmetric behavior between Python and JS loaders.
- When adding heavy parallelism, first locate where delays/rate-limiting are implemented and adapt them.

Examples to run quickly
- Run Node research: `npm run research`
- Run maps dev server: `cd maps && npm run dev`
- Switch AI provider in Python REPL:
  ```py
  from configix import apiManager
  apiManager.switch_ai_provider('ai_gemini')
  print(apiManager.get_current_ai())
  ```

Questions / missing info for maintainers
- The repo expects a local `config` directory (not in repo). If you need sample config files, ask and I can scaffold minimal example JSON files (without secrets) to make local dev easier.

---
Please review and tell me if you want more concrete examples (sample config snippets, a small test harness to run a single-country research job, or scaffolding for sample `config/*.json`).
