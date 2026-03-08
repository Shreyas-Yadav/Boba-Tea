from __future__ import annotations

import json
import logging
import mimetypes
from datetime import UTC, datetime
from functools import lru_cache
from time import perf_counter
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel

from .schemas import VisualizationJobResponse
from .services import build_visualization_response
from .settings import Settings

logger = logging.getLogger(__name__)


class VisualizationJobMessage(BaseModel):
    job_id: str
    idea_id: str
    detected_label: str
    idea_title: str
    idea_description: str
    visualization_prompt: str
    image_asset_key: str
    mime_type: str


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))


def _extension_for_mime(mime_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/heic": ".heic",
    }.get(mime_type, mimetypes.guess_extension(mime_type) or ".bin")


def visualization_jobs_configured(settings: Settings) -> bool:
    return bool(settings.visualization_jobs_bucket and settings.visualization_jobs_queue_url)


def visualization_jobs_ready(settings: Settings) -> bool:
    return settings.visualization_jobs_enabled and visualization_jobs_configured(settings)


def visualization_mode(settings: Settings) -> str:
    return "async" if visualization_jobs_ready(settings) else "inline"


@lru_cache(maxsize=4)
def _s3_client(region_name: str):
    return boto3.client("s3", region_name=region_name)


@lru_cache(maxsize=4)
def _sqs_client(region_name: str):
    return boto3.client("sqs", region_name=region_name)


def _input_key(identifier: str, mime_type: str, settings: Settings) -> str:
    return f"{settings.visualization_jobs_prefix}/inputs/{identifier}{_extension_for_mime(mime_type)}"


def _state_key(job_id: str, settings: Settings) -> str:
    return f"{settings.visualization_jobs_prefix}/states/{job_id}.json"


def _put_json(bucket: str, key: str, payload: dict, settings: Settings) -> None:
    _s3_client(settings.aws_region).put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload).encode("utf-8"),
        ContentType="application/json",
    )


def _write_job_state(job: VisualizationJobResponse, settings: Settings) -> None:
    if not settings.visualization_jobs_bucket:
        raise ValueError("VISUALIZATION_JOBS_BUCKET is not configured.")
    _put_json(
        settings.visualization_jobs_bucket,
        _state_key(job.job_id, settings),
        job.model_dump(mode="json"),
        settings,
    )


def _load_job_state(job_id: str, settings: Settings) -> VisualizationJobResponse:
    if not settings.visualization_jobs_bucket:
        raise FileNotFoundError("Visualization job storage is not configured.")

    try:
        response = _s3_client(settings.aws_region).get_object(
            Bucket=settings.visualization_jobs_bucket,
            Key=_state_key(job_id, settings),
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
            raise FileNotFoundError(f"Visualization job {job_id} was not found.") from exc
        raise

    return VisualizationJobResponse.model_validate_json(response["Body"].read().decode("utf-8"))


def store_scan_asset(
    *,
    image_bytes: bytes,
    mime_type: str,
    scan_id: str,
    settings: Settings,
) -> str | None:
    if not visualization_jobs_ready(settings) or not settings.visualization_jobs_bucket:
        return None

    key = _input_key(scan_id, mime_type, settings)
    _s3_client(settings.aws_region).put_object(
        Bucket=settings.visualization_jobs_bucket,
        Key=key,
        Body=image_bytes,
        ContentType=mime_type,
    )
    return key


def create_visualization_job_response(
    *,
    image_bytes: bytes | None,
    image_asset_key: str | None,
    mime_type: str | None,
    detected_label: str,
    idea_id: str,
    idea_title: str,
    idea_description: str,
    visualization_prompt: str,
    settings: Settings,
) -> VisualizationJobResponse:
    started_at = perf_counter()

    if visualization_jobs_ready(settings):
        if not image_asset_key:
            if image_bytes is None or mime_type is None:
                raise ValueError("Either an image file or a stored scan asset is required.")
            image_asset_key = store_scan_asset(
                image_bytes=image_bytes,
                mime_type=mime_type,
                scan_id=f"{idea_id}-{uuid4().hex[:8]}",
                settings=settings,
            )

        if not image_asset_key:
            raise ValueError("Image asset storage failed for the visualization job.")

        message_mime_type = mime_type or mimetypes.guess_type(image_asset_key)[0] or "application/octet-stream"
        now = datetime.now(UTC)
        job = VisualizationJobResponse(
            job_id=f"vizjob_{uuid4().hex[:12]}",
            idea_id=idea_id,
            status="queued",
            source_mode="async",
            created_at=now,
            updated_at=now,
            timings_ms={"enqueue": _elapsed_ms(started_at)},
            poll_after_ms=settings.visualization_job_poll_ms,
        )
        _write_job_state(job, settings)
        try:
            message = VisualizationJobMessage(
                job_id=job.job_id,
                idea_id=idea_id,
                detected_label=detected_label,
                idea_title=idea_title,
                idea_description=idea_description,
                visualization_prompt=visualization_prompt,
                image_asset_key=image_asset_key,
                mime_type=message_mime_type,
            )
            _sqs_client(settings.aws_region).send_message(
                QueueUrl=settings.visualization_jobs_queue_url,
                MessageBody=message.model_dump_json(),
            )
        except Exception as exc:
            job.status = "failed"
            job.updated_at = datetime.now(UTC)
            job.error = str(exc)
            job.poll_after_ms = None
            job.timings_ms["total"] = _elapsed_ms(started_at)
            _write_job_state(job, settings)
            raise
        job.timings_ms["total"] = _elapsed_ms(started_at)
        _write_job_state(job, settings)
        return job

    if image_bytes is None or mime_type is None:
        raise ValueError("Image upload is required when async visualization jobs are disabled.")

    result = build_visualization_response(
        image_bytes=image_bytes,
        mime_type=mime_type,
        detected_label=detected_label,
        idea_id=idea_id,
        idea_title=idea_title,
        idea_description=idea_description,
        visualization_prompt=visualization_prompt,
        settings=settings,
    )
    now = datetime.now(UTC)
    return VisualizationJobResponse(
        job_id=f"inline_{uuid4().hex[:12]}",
        idea_id=idea_id,
        status="completed",
        source_mode="inline",
        created_at=now,
        updated_at=now,
        result=result,
        timings_ms={"total": _elapsed_ms(started_at)},
    )


def get_visualization_job_response(job_id: str, settings: Settings) -> VisualizationJobResponse:
    if not visualization_jobs_ready(settings):
        raise FileNotFoundError("Visualization jobs are not enabled on this deployment.")

    return _load_job_state(job_id, settings)


def process_visualization_job(message_body: str, settings: Settings) -> VisualizationJobResponse:
    if not visualization_jobs_ready(settings) or not settings.visualization_jobs_bucket:
        raise RuntimeError("Visualization worker is enabled without queue storage configuration.")

    message = VisualizationJobMessage.model_validate_json(message_body)
    state = _load_job_state(message.job_id, settings)
    started_at = perf_counter()
    now = datetime.now(UTC)
    queue_wait_ms = max(0, round((now - state.created_at).total_seconds() * 1000))
    state.status = "processing"
    state.updated_at = now
    state.error = None
    state.poll_after_ms = settings.visualization_job_poll_ms
    state.timings_ms["queue_wait"] = queue_wait_ms
    _write_job_state(state, settings)

    try:
        image_object = _s3_client(settings.aws_region).get_object(
            Bucket=settings.visualization_jobs_bucket,
            Key=message.image_asset_key,
        )
        image_bytes = image_object["Body"].read()
        mime_type = image_object.get("ContentType") or message.mime_type
        result = build_visualization_response(
            image_bytes=image_bytes,
            mime_type=mime_type,
            detected_label=message.detected_label,
            idea_id=message.idea_id,
            idea_title=message.idea_title,
            idea_description=message.idea_description,
            visualization_prompt=message.visualization_prompt,
            settings=settings,
        )
        state.status = "completed"
        state.updated_at = datetime.now(UTC)
        state.result = result
        state.error = None
        state.poll_after_ms = None
        state.timings_ms["processing"] = _elapsed_ms(started_at)
        state.timings_ms["total"] = max(0, round((state.updated_at - state.created_at).total_seconds() * 1000))
    except Exception as exc:
        logger.exception("visualization job failed: job_id=%s", message.job_id)
        state.status = "failed"
        state.updated_at = datetime.now(UTC)
        state.result = None
        state.error = str(exc)
        state.poll_after_ms = None
        state.timings_ms["processing"] = _elapsed_ms(started_at)
        state.timings_ms["total"] = max(0, round((state.updated_at - state.created_at).total_seconds() * 1000))

    _write_job_state(state, settings)
    return state
