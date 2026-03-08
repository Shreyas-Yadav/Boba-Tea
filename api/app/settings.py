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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        gemini_api_key=_clean_env("GEMINI_API_KEY") or _clean_env("GOOGLE_API_KEY"),
        analysis_model=_clean_env("ANALYSIS_MODEL") or "gemini-3-flash-preview",
        search_model=_clean_env("SEARCH_MODEL") or "gemini-3-flash-preview",
        image_model=_clean_env("IMAGE_MODEL") or "gemini-2.5-flash-image",
        mock_fallback_enabled=os.getenv("MOCK_FALLBACK_ENABLED", "true").lower() == "true",
    )
