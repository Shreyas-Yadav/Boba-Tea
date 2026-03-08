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

## AWS deployment

This repo now supports a single-container AWS deployment on EC2:

- one Docker image builds the Vite frontend and serves it from the FastAPI app
- backend secrets and model config are loaded from AWS SSM Parameter Store
- one public EC2 instance serves both the web app and the API
- an Elastic IP keeps the demo URL stable across redeploys

Expected AWS defaults:

- region: `us-west-2`
- account: `883107058766`
- ECR repo: `recraft-web-demo`
- EC2 instance: `recraft-web-demo`
- EC2 instance role: `RecraftEc2InstanceRole`
- EC2 instance profile: `RecraftEc2InstanceProfile`
- SSM prefix: `/recraft/prod`

SSM parameters:

- `/recraft/prod/GEMINI_API_KEY` (`SecureString`)
- `/recraft/prod/ANALYSIS_MODEL`
- `/recraft/prod/SEARCH_MODEL`
- `/recraft/prod/IMAGE_MODEL`
- `/recraft/prod/MOCK_FALLBACK_ENABLED`

Bootstrap AWS resources and parameters:

```bash
cd /Users/manmohan/Documents/Karathpy/Boba-Tea
chmod +x scripts/aws/bootstrap.sh scripts/aws/deploy.sh
export GEMINI_API_KEY=your_real_key
scripts/aws/bootstrap.sh
```

Deploy the current branch to EC2:

```bash
cd /Users/manmohan/Documents/Karathpy/Boba-Tea
scripts/aws/deploy.sh
```

GitHub Actions deployment is configured in [deploy-aws.yml](/Users/manmohan/Documents/Karathpy/Boba-Tea/.github/workflows/deploy-aws.yml) using AWS OIDC. The workflow assumes the role `arn:aws:iam::883107058766:role/GitHubActionsRecraftDeployRole`.
