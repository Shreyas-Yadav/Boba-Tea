from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TutorialLink(BaseModel):
    id: str
    source: Literal["youtube", "article", "web"]
    title: str
    url: str
    reason: str


class Idea(BaseModel):
    id: str
    title: str
    description: str
    difficulty: Literal["easy", "medium", "hard"]
    why_this_works: str
    materials: list[str]
    steps: list[str]
    search_query: str
    visualization_prompt: str
    tutorial_links: list[TutorialLink]


class ScanResponse(BaseModel):
    scan_id: str
    detected_label: str
    confidence: float
    summary: str
    safety_note: str
    source_mode: Literal["gemini", "mock"]
    provider_state: Literal["ok", "not_configured", "fallback_invalid_key", "fallback_error"] = "ok"
    provider_notice: str | None = None
    created_at: datetime
    ideas: list[Idea]
    timings_ms: dict[str, int] = Field(default_factory=dict)


class TutorialLinksRequest(BaseModel):
    detected_label: str
    idea_id: str
    idea_title: str
    idea_description: str
    search_query: str


class TutorialLinksResponse(BaseModel):
    idea_id: str
    tutorial_links: list[TutorialLink]
    links_mode: Literal["grounded", "fallback"]
    timings_ms: dict[str, int] = Field(default_factory=dict)


class GeminiIdea(BaseModel):
    title: str = Field(description="Short DIY idea title for the detected object.")
    description: str = Field(description="One or two sentences describing the reuse idea.")
    difficulty: Literal["easy", "medium", "hard"] = Field(
        description="Practical difficulty for a beginner household user.",
    )
    why_this_works: str = Field(
        description="One sentence explaining why this reuse idea fits the detected object.",
    )
    materials: list[str] = Field(
        min_length=2,
        max_length=6,
        description="Simple materials needed for the DIY reuse idea.",
    )
    steps: list[str] = Field(
        min_length=3,
        max_length=6,
        description="Practical, concise steps for creating the DIY reuse idea.",
    )
    search_query: str = Field(
        description="Compact search query for finding closely related tutorials.",
    )
    visualization_prompt: str = Field(
        description=(
            "A detailed prompt for editing the uploaded image into a realistic after-state preview "
            "of the finished DIY outcome while preserving the original object cues."
        ),
    )


class GeminiScanPayload(BaseModel):
    detected_label: str = Field(
        description="Broad household object label, such as plastic bottle or glass jar.",
    )
    confidence: float = Field(
        ge=0,
        le=1,
        description="Confidence score from 0 to 1 for the detected object.",
    )
    summary: str = Field(description="One concise sentence describing what the object is.")
    safety_note: str = Field(
        description="Short DIY safety note tailored to the detected object and ideas.",
    )
    ideas: list[GeminiIdea] = Field(
        min_length=3,
        max_length=4,
        description="Three or four practical reuse ideas ordered from strongest to weakest fit.",
    )


class GroundedTutorialLink(BaseModel):
    source: Literal["youtube", "article", "web"] = Field(
        description="Link type based on the source domain and content style.",
    )
    title: str = Field(description="Short source title.")
    url: str = Field(description="Direct URL to the tutorial page or video.")
    reason: str = Field(description="One sentence explaining why the link is relevant.")


class GroundedTutorialPayload(BaseModel):
    links: list[GroundedTutorialLink] = Field(
        min_length=2,
        max_length=3,
        description="Two or three high-confidence tutorial links closely related to the DIY idea.",
    )


class VisualizationResponse(BaseModel):
    idea_id: str
    model: str
    mime_type: str
    image_base64: str
    caption: str
    timings_ms: dict[str, int] = Field(default_factory=dict)
