from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .schemas import (
    ScanResponse,
    TutorialLinksRequest,
    TutorialLinksResponse,
    VisualizationJobResponse,
    VisualizationResponse,
)
from .settings import get_settings
from .services import build_scan_response, build_tutorial_links_response, build_visualization_response
from .visualization_jobs import (
    create_visualization_job_response,
    get_visualization_job_response,
    store_scan_asset,
    visualization_jobs_configured,
    visualization_jobs_ready,
    visualization_mode,
)

app = FastAPI(title="ReCraft Demo API", version="0.1.0")
settings = get_settings()
logger = logging.getLogger("recraft.api")
logger.setLevel(logging.INFO)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_API_PATH_PREFIXES = {
    "health",
    "scan",
    "visualize",
    "links",
    "docs",
    "redoc",
    "openapi.json",
}


def _resolve_frontend_dist_dir() -> Path | None:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = (
        repo_root / "web_dist",
        repo_root / "web" / "dist",
    )

    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate

    return None


FRONTEND_DIST_DIR = _resolve_frontend_dist_dir()


@app.middleware("http")
async def log_request_timing(request: Request, call_next):
    request_id = request.headers.get("cf-ray") or uuid4().hex[:12]
    started_at = perf_counter()
    logger.info("request started: request_id=%s method=%s path=%s", request_id, request.method, request.url.path)

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request failed: request_id=%s method=%s path=%s elapsed_ms=%s",
            request_id,
            request.method,
            request.url.path,
            round((perf_counter() - started_at) * 1000),
        )
        raise

    elapsed_ms = round((perf_counter() - started_at) * 1000)
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
    logger.info(
        "request completed: request_id=%s method=%s path=%s status=%s elapsed_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.get("/health")
def health() -> dict[str, str | int]:
    return {
        "status": "ok",
        "gemini_configured": "yes" if settings.gemini_api_key else "no",
        "mock_fallback_enabled": "yes" if settings.mock_fallback_enabled else "no",
        "max_upload_megabytes": 10,
        "analysis_model": settings.analysis_model,
        "search_model": settings.search_model,
        "image_model": settings.image_model,
        "visualization_mode": visualization_mode(settings),
        "visualization_jobs_enabled": "yes" if settings.visualization_jobs_enabled else "no",
        "visualization_jobs_configured": "yes" if visualization_jobs_configured(settings) else "no",
    }


async def _read_uploaded_image(image: UploadFile) -> bytes:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file.")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Please upload an image smaller than 10 MB.")

    return image_bytes


@app.post("/scan", response_model=ScanResponse)
async def scan(image: UploadFile = File(...)):
    logger.info("scan request received: filename=%s content_type=%s", image.filename, image.content_type)
    image_bytes = await _read_uploaded_image(image)

    response = await asyncio.to_thread(
        build_scan_response,
        image_bytes=image_bytes,
        filename=image.filename,
        mime_type=image.content_type,
        settings=settings,
    )
    logger.info(
        "scan request completed: scan_id=%s object=%s source_mode=%s ideas=%s",
        response.scan_id,
        response.detected_label,
        response.source_mode,
        len(response.ideas),
    )

    if visualization_jobs_ready(settings):
        try:
            image_asset_key = await asyncio.to_thread(
                store_scan_asset,
                image_bytes=image_bytes,
                mime_type=image.content_type or "application/octet-stream",
                scan_id=response.scan_id,
                settings=settings,
            )
            response.image_asset_key = image_asset_key
            if image_asset_key:
                logger.info("scan asset stored: scan_id=%s key=%s", response.scan_id, image_asset_key)
        except Exception:
            logger.exception("scan asset storage failed: scan_id=%s", response.scan_id)

    return response


@app.post("/visualize", response_model=VisualizationResponse)
async def visualize(
    image: UploadFile = File(...),
    idea_id: str = Form(...),
    detected_label: str = Form(...),
    idea_title: str = Form(...),
    idea_description: str = Form(...),
    visualization_prompt: str = Form(...),
):
    logger.info(
        "visualize request received: idea_id=%s idea_title=%s content_type=%s",
        idea_id,
        idea_title,
        image.content_type,
    )

    image_bytes = await _read_uploaded_image(image)

    try:
        response = await asyncio.to_thread(
            build_visualization_response,
            image_bytes=image_bytes,
            mime_type=image.content_type,
            detected_label=detected_label,
            idea_id=idea_id,
            idea_title=idea_title,
            idea_description=idea_description,
            visualization_prompt=visualization_prompt,
            settings=settings,
        )
        logger.info(
            "visualize request completed: idea_id=%s model=%s mime_type=%s",
            response.idea_id,
            response.model,
            response.mime_type,
        )
        return response
    except ValueError as exc:
        logger.warning("visualize request failed with validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("visualize request failed")
        raise HTTPException(
            status_code=502,
            detail=f"Concept image generation failed: {exc}",
        ) from exc


@app.post("/visualize/jobs", response_model=VisualizationJobResponse)
async def create_visualization_job(
    image: UploadFile | None = File(None),
    image_asset_key: str | None = Form(None),
    idea_id: str = Form(...),
    detected_label: str = Form(...),
    idea_title: str = Form(...),
    idea_description: str = Form(...),
    visualization_prompt: str = Form(...),
):
    logger.info(
        "visualize job request received: idea_id=%s idea_title=%s has_asset=%s content_type=%s",
        idea_id,
        idea_title,
        "yes" if image_asset_key else "no",
        image.content_type if image else None,
    )

    image_bytes: bytes | None = None
    mime_type: str | None = None
    if image is not None:
        image_bytes = await _read_uploaded_image(image)
        mime_type = image.content_type

    if image_bytes is None and not image_asset_key:
        raise HTTPException(status_code=400, detail="Provide either an uploaded image or a stored scan asset.")

    try:
        response = await asyncio.to_thread(
            create_visualization_job_response,
            image_bytes=image_bytes,
            image_asset_key=image_asset_key,
            mime_type=mime_type,
            detected_label=detected_label,
            idea_id=idea_id,
            idea_title=idea_title,
            idea_description=idea_description,
            visualization_prompt=visualization_prompt,
            settings=settings,
        )
        logger.info(
            "visualize job request completed: job_id=%s idea_id=%s status=%s mode=%s",
            response.job_id,
            response.idea_id,
            response.status,
            response.source_mode,
        )
        return response
    except ValueError as exc:
        logger.warning("visualize job request failed with validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("visualize job request failed")
        raise HTTPException(status_code=502, detail=f"Visualization job creation failed: {exc}") from exc


@app.get("/visualize/jobs/{job_id}", response_model=VisualizationJobResponse)
async def get_visualization_job(job_id: str):
    try:
        response = await asyncio.to_thread(
            get_visualization_job_response,
            job_id,
            settings,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("visualize job lookup failed: job_id=%s", job_id)
        raise HTTPException(status_code=502, detail=f"Visualization job lookup failed: {exc}") from exc

    logger.info(
        "visualize job lookup completed: job_id=%s status=%s mode=%s",
        response.job_id,
        response.status,
        response.source_mode,
    )
    return response


@app.post("/links", response_model=TutorialLinksResponse)
async def tutorial_links(request: TutorialLinksRequest):
    logger.info(
        "links request received: idea_id=%s idea_title=%s object=%s",
        request.idea_id,
        request.idea_title,
        request.detected_label,
    )

    response = await asyncio.to_thread(
        build_tutorial_links_response,
        detected_label=request.detected_label,
        idea_id=request.idea_id,
        idea_title=request.idea_title,
        idea_description=request.idea_description,
        search_query=request.search_query,
        settings=settings,
    )
    logger.info(
        "links request completed: idea_id=%s mode=%s links=%s",
        response.idea_id,
        response.links_mode,
        len(response.tutorial_links),
    )
    return response


def _serve_frontend_path(path: str) -> FileResponse:
    if FRONTEND_DIST_DIR is None:
        raise HTTPException(status_code=404, detail="Frontend bundle is not available.")

    dist_root = FRONTEND_DIST_DIR.resolve()
    requested = (dist_root / path).resolve() if path else dist_root / "index.html"
    if requested.is_relative_to(dist_root) and requested.is_file():
        return FileResponse(requested)

    return FileResponse(dist_root / "index.html")


@app.get("/", include_in_schema=False)
async def frontend_root():
    return _serve_frontend_path("")


@app.get("/{full_path:path}", include_in_schema=False)
async def frontend_catch_all(full_path: str):
    if full_path.split("/", 1)[0] in _API_PATH_PREFIXES:
        raise HTTPException(status_code=404, detail="Not found.")

    return _serve_frontend_path(full_path)
