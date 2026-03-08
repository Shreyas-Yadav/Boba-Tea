# ReCraft Demo Workspace

This workspace contains a web-first ReCraft demo:

- `web/`: React + Vite + TypeScript frontend
- `api/`: FastAPI backend with Gemini 3 analysis, grounded tutorial links, and image visualization
- `Makefile`: common local commands

## Gemini API key

Place the Gemini key in the backend only.

1. Copy [api/.env.example](/Users/manmohan/Documents/FinalSemester/dons_hack/api/.env.example) to `api/.env`
2. Set:

```bash
GEMINI_API_KEY=your_real_key_here
```

Do not put the Gemini key in `web/.env`, because anything in the frontend can be exposed to the browser.

Optional backend settings:

```bash
ANALYSIS_MODEL=gemini-3-flash-preview
SEARCH_MODEL=gemini-3-flash-preview
IMAGE_MODEL=gemini-2.5-flash-image
MOCK_FALLBACK_ENABLED=true
```

## Run locally

### 1. Start the API

```bash
cd /Users/manmohan/Documents/FinalSemester/dons_hack/api
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Start the web app

```bash
cd /Users/manmohan/Documents/FinalSemester/dons_hack/web
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Or from the project root:

```bash
cd /Users/manmohan/Documents/FinalSemester/dons_hack
make install
make api
make web
```

### 3. Open the app

- Desktop: `http://localhost:5173`
- Mobile browser on the same Wi-Fi: `http://<your-mac-ip>:5173`

The dev server proxies `/api` to the local backend, so mobile devices hitting the Vite server can use the same app without changing the frontend API URL.

For direct camera stream APIs, mobile browsers generally prefer HTTPS. The current implementation uses a camera-capable file input, which is the most reliable local demo path on mobile browsers.

## API endpoints

- `GET /health`
- `POST /scan`
- `POST /visualize`

`POST /scan` accepts a single multipart field named `image`.

`POST /visualize` accepts:

- `image`
- `idea_id`
- `detected_label`
- `idea_title`
- `idea_description`
- `visualization_prompt`

## What works now

- mobile-friendly web UI
- photo capture or gallery upload
- FastAPI backend
- Gemini 3 based object analysis and idea generation
- grounded tutorial links per idea
- image concept preview generation for the featured idea
- deterministic mock fallback if Gemini is unavailable and fallback stays enabled
- recent local scan history in the browser
- local git repo and root `.gitignore`

## What is still pending

- more reliable object detection tuning for difficult images
- deployed hosting instead of local-only development
- user accounts and synced history
- Capacitor packaging for Android and iOS
- automated tests beyond manual smoke checks
