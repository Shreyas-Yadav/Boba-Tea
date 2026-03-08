from __future__ import annotations

import base64
from urllib.parse import urlparse

from google import genai
from google.genai import types

from .schemas import GroundedTutorialPayload, GeminiScanPayload, VisualizationResponse
from .settings import Settings

SCAN_PROMPT = """
You are generating structured output for ReCraft, a reuse-ideas demo app.

Analyze the uploaded image and identify the main household object most likely intended for reuse.
Return only JSON matching the provided schema.

Rules:
- Choose a broad, practical object label such as plastic bottle, cardboard box, tin can, glass jar, old t-shirt, paper bag, egg carton, food container, or shoe box.
- If the image is ambiguous, pick the most likely household discardable object and lower the confidence.
- Produce 3 or 4 DIY reuse ideas ordered from strongest to weakest fit for the image.
- Prefer safe, low-cost, beginner-friendly ideas.
- Avoid dangerous advice for chemicals, broken glass, sharp metal, or electrical parts.
- The steps must be concise and practical.
- The visualization_prompt should transform the uploaded object into the finished DIY result while preserving original material and shape cues.
""".strip()

SEARCH_PROMPT_TEMPLATE = """
Find 2 or 3 highly relevant tutorial links for this exact DIY reuse idea.

Detected object: {detected_label}
Idea title: {idea_title}
Idea description: {idea_description}
Suggested search query: {search_query}

Rules:
- Prefer direct tutorial pages or YouTube videos.
- Avoid broad recycling explainers, shopping pages, or generic unrelated pages.
- The links must be closely related to the exact transformation above.
- Return only JSON matching the provided schema.
""".strip()

VISUALIZATION_PROMPT_TEMPLATE = """
Use the uploaded image as the "before" object.

Create a photorealistic "after" visualization showing the same object transformed into this finished DIY reuse outcome:

Object: {detected_label}
Idea: {idea_title}
Description: {idea_description}
Visualization direction: {visualization_prompt}

Requirements:
- Preserve key visual cues from the original object so the transformation feels believable.
- Show the finished object in a clean, realistic setting.
- Make it look achievable by a real person, not fantasy or concept art.
- No text overlay, no split-screen, no collage.
- Focus on one polished hero image of the final reused item.
""".strip()


def _build_client(settings: Settings) -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


def _response_parts(response: object) -> list[object]:
    direct_parts = getattr(response, "parts", None)
    if direct_parts:
        return list(direct_parts)

    candidates = getattr(response, "candidates", None) or []
    parts: list[object] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        candidate_parts = getattr(content, "parts", None) or []
        parts.extend(candidate_parts)
    return parts


def generate_scan_payload(*, image_bytes: bytes, mime_type: str, settings: Settings) -> GeminiScanPayload:
    client = _build_client(settings)
    response = client.models.generate_content(
        model=settings.analysis_model,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            SCAN_PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeminiScanPayload,
            temperature=0.2,
        ),
    )

    if not response.text:
        raise ValueError("Gemini returned an empty scan response.")

    return GeminiScanPayload.model_validate_json(response.text)


def generate_grounded_links(
    *,
    detected_label: str,
    idea_title: str,
    idea_description: str,
    search_query: str,
    settings: Settings,
) -> GroundedTutorialPayload:
    client = _build_client(settings)
    response = client.models.generate_content(
        model=settings.search_model,
        contents=SEARCH_PROMPT_TEMPLATE.format(
            detected_label=detected_label,
            idea_title=idea_title,
            idea_description=idea_description,
            search_query=search_query,
        ),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            response_mime_type="application/json",
            response_schema=GroundedTutorialPayload,
            temperature=0.1,
        ),
    )

    if not response.text:
        raise ValueError("Gemini returned an empty grounding response.")

    payload = GroundedTutorialPayload.model_validate_json(response.text)
    filtered_links = [
        link
        for link in payload.links
        if urlparse(link.url).scheme in {"http", "https"} and urlparse(link.url).netloc
    ]
    if len(filtered_links) < 2:
        raise ValueError("Grounded response did not contain enough valid URLs.")

    return GroundedTutorialPayload(links=filtered_links[:3])


def generate_visualization(
    *,
    image_bytes: bytes,
    mime_type: str,
    detected_label: str,
    idea_id: str,
    idea_title: str,
    idea_description: str,
    visualization_prompt: str,
    settings: Settings,
) -> VisualizationResponse:
    client = _build_client(settings)
    response = client.models.generate_content(
        model=settings.image_model,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            VISUALIZATION_PROMPT_TEMPLATE.format(
                detected_label=detected_label,
                idea_title=idea_title,
                idea_description=idea_description,
                visualization_prompt=visualization_prompt,
            ),
        ],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            temperature=0.6,
        ),
    )

    for part in _response_parts(response):
        inline_data = getattr(part, "inline_data", None)
        if not inline_data or not getattr(inline_data, "data", None):
            continue

        image_bytes = inline_data.data
        if isinstance(image_bytes, str):
            image_bytes = image_bytes.encode("utf-8")

        return VisualizationResponse(
            idea_id=idea_id,
            model=settings.image_model,
            mime_type=inline_data.mime_type or "image/png",
            image_base64=base64.b64encode(image_bytes).decode("utf-8"),
            caption=f"Concept preview for {idea_title}",
        )

    raise ValueError("Gemini image generation did not return an image.")
