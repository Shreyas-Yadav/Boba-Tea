# ReCraft Next Session Guide

This file is the quickest way to resume work on the ReCraft demo without re-discovering the codebase.

## Project goal

ReCraft is a web-first mobile-friendly demo that lets a user:

1. Upload or capture a photo of a waste object.
2. Analyze the object with Gemini.
3. Show reuse ideas, materials, steps, and related tutorial links.
4. Generate a concept image showing how the reused object could look.

The project is intentionally built as a web app first so it can later become:

- a PWA
- a Capacitor-wrapped iOS app
- a Capacitor-wrapped Android app

## Stack

- Frontend: React + Vite + TypeScript
- Backend: FastAPI
- AI: Gemini API
- Local package tools:
  - `uv` for Python
  - `npm` for frontend

## Folder map

- `web/`
  - frontend app
  - main UI lives in `web/src/App.tsx`
  - styling lives in `web/src/App.css`
  - frontend API client lives in `web/src/api.ts`
- `api/`
  - backend app
  - API entrypoint lives in `api/app/main.py`
  - scan and visualization orchestration lives in `api/app/services.py`
  - Gemini integration lives in `api/app/gemini.py`
  - settings/env loading lives in `api/app/settings.py`
  - response schemas live in `api/app/schemas.py`
- `Makefile`
  - local helper commands
- `README.md`
  - basic setup and run instructions

## How the app flows

### Frontend flow

1. User selects a photo from camera or gallery.
2. Frontend sends the image to `POST /scan`.
3. Backend returns:
   - detected object
   - confidence
   - reuse ideas
   - steps
   - tutorial links
   - provider state
4. Frontend auto-selects the top idea.
5. If the scan came from real Gemini output, frontend triggers `POST /visualize`.
6. The generated image is shown beside the original image.

### Backend flow

1. `POST /scan`
   - validates image
   - calls Gemini analysis
   - tries grounded link generation
   - if Gemini fails and fallback is enabled, returns local mock ideas
2. `POST /visualize`
   - validates image
   - sends the uploaded image plus selected idea context to Gemini image generation
   - returns base64 image data for the frontend

## Local run order

From the project root:

```bash
cd /Users/manmohan/Documents/FinalSemester/dons_hack
make install
make api
```

Open a second terminal:

```bash
cd /Users/manmohan/Documents/FinalSemester/dons_hack
make web
```

Useful URLs:

- frontend: `http://localhost:5173`
- backend health: `http://localhost:8000/health`

## Environment file

The Gemini key must be placed only here:

- `api/.env`

Expected format:

```bash
GEMINI_API_KEY=your_real_google_ai_studio_key
ANALYSIS_MODEL=gemini-3-flash-preview
SEARCH_MODEL=gemini-3-flash-preview
IMAGE_MODEL=gemini-2.5-flash-image
MOCK_FALLBACK_ENABLED=true
```

Important:

- do not put the key in `web/.env`
- do not leave the placeholder value in place
- restart the API after changing `api/.env`

## Current status

What is already implemented:

- mobile-first browser UI
- camera/gallery file input flow
- `/health`, `/scan`, `/visualize`
- Gemini analysis path
- Gemini image generation path
- idea-specific tutorial links
- local browser history
- on-screen debug panel
- backend request logging
- mock fallback when Gemini is unavailable

## Current blocker

As of the latest session, the main blocker is not layout or frontend state. The actual blocker is the Gemini credential.

Observed behavior:

- `GET /health` may show that a Gemini key is present
- but Google still rejects the loaded key with `API_KEY_INVALID`
- when that happens:
  - `/scan` falls back to mock mode
  - `/visualize` fails to generate the image

This is why the app can appear partly functional while still not generating concept images.

## How to verify whether Gemini is really working

1. Start backend and frontend.
2. Open the app.
3. Upload a photo.
4. Open the `Debug flow` panel at the bottom.
5. Check for:

- `Scan request succeeded`
- `provider=ok`
- `Auto visualization triggered`
- `Visualization request succeeded`

If you instead see:

- `provider=fallback_invalid_key`

then the key in `api/.env` is still wrong or not accepted by Google.

## Debugging places

### Frontend

- `web/src/App.tsx`
  - main UI and flow state
  - debug events
  - scan request
  - visualization request
- browser console
  - logs are prefixed with `ReCraft`

### Backend

- `api/app/main.py`
  - request lifecycle logs
- `api/app/services.py`
  - fallback logic
  - provider state handling
- terminal running the API server
  - easiest place to see Gemini errors

## How to navigate the UI

Top section:

- hero area
- API and Gemini status pills
- `Take a photo`
- `Upload from gallery`
- `Generate reuse plan`

Middle section:

- uploaded object preview
- featured reuse idea
- before / reimagined comparison
- materials
- difficulty
- step-by-step instructions
- related tutorials

Lower section:

- alternative ideas
- local history
- debug panel

## Most important files for the next session

- `/Users/manmohan/Documents/FinalSemester/dons_hack/web/src/App.tsx`
- `/Users/manmohan/Documents/FinalSemester/dons_hack/web/src/App.css`
- `/Users/manmohan/Documents/FinalSemester/dons_hack/web/src/api.ts`
- `/Users/manmohan/Documents/FinalSemester/dons_hack/api/app/main.py`
- `/Users/manmohan/Documents/FinalSemester/dons_hack/api/app/services.py`
- `/Users/manmohan/Documents/FinalSemester/dons_hack/api/app/gemini.py`
- `/Users/manmohan/Documents/FinalSemester/dons_hack/api/app/settings.py`
- `/Users/manmohan/Documents/FinalSemester/dons_hack/api/app/schemas.py`

## Recommended next steps

1. Fix the Gemini key in `api/.env`.
2. Re-test one full upload and image generation flow.
3. Once real Gemini generation works, improve:
   - quality of visualization prompts
   - tutorial link grounding quality
   - empty and error states
4. After stable local behavior, add:
   - hosted deployment
   - PWA install support
   - Capacitor packaging

## Quick restart prompt for the next session

If a future session needs context fast, use a prompt like:

```text
Read NEXT_SESSION_GUIDE.md first, then inspect the current Gemini key issue and continue the ReCraft web demo from there.
```
