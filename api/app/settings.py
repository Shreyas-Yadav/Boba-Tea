from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _clean_env(name: str) -> str | None:
    raw_value = os.getenv(name)
    if raw_value is None:
        return None

    cleaned = raw_value.strip().strip('"').strip("'")
    return cleaned or None


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    analysis_model: str
    search_model: str
    image_model: str
    mock_fallback_enabled: bool
    aws_region: str
    visualization_jobs_enabled: bool
    visualization_jobs_bucket: str | None
    visualization_jobs_queue_url: str | None
    visualization_jobs_prefix: str
    visualization_job_poll_ms: int
    visualization_worker_concurrency: int
    visualization_worker_wait_seconds: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        gemini_api_key=_clean_env("GEMINI_API_KEY") or _clean_env("GOOGLE_API_KEY"),
        analysis_model=_clean_env("ANALYSIS_MODEL") or "gemini-3-flash-preview",
        search_model=_clean_env("SEARCH_MODEL") or "gemini-3-flash-preview",
        image_model=_clean_env("IMAGE_MODEL") or "gemini-2.5-flash-image",
        mock_fallback_enabled=os.getenv("MOCK_FALLBACK_ENABLED", "true").lower() == "true",
        aws_region=_clean_env("AWS_REGION") or _clean_env("AWS_DEFAULT_REGION") or "us-west-2",
        visualization_jobs_enabled=os.getenv("VISUALIZATION_JOBS_ENABLED", "false").lower() == "true",
        visualization_jobs_bucket=_clean_env("VISUALIZATION_JOBS_BUCKET"),
        visualization_jobs_queue_url=_clean_env("VISUALIZATION_JOBS_QUEUE_URL"),
        visualization_jobs_prefix=_clean_env("VISUALIZATION_JOBS_PREFIX") or "visualization-jobs",
        visualization_job_poll_ms=max(500, int(os.getenv("VISUALIZATION_JOB_POLL_MS", "1500"))),
        visualization_worker_concurrency=max(1, int(os.getenv("VISUALIZATION_WORKER_CONCURRENCY", "2"))),
        visualization_worker_wait_seconds=max(1, min(20, int(os.getenv("VISUALIZATION_WORKER_WAIT_SECONDS", "20")))),
    )
