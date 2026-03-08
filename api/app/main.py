from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .schemas import ScanResponse, VisualizationResponse
from .settings import get_settings
from .services import build_scan_response, build_visualization_response

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
    }


@app.post("/scan", response_model=ScanResponse)
async def scan(image: UploadFile = File(...)):
    logger.info("scan request received: filename=%s content_type=%s", image.filename, image.content_type)

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file.")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Please upload an image smaller than 10 MB.")

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

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file.")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Please upload an image smaller than 10 MB.")

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
