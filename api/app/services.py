from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from time import perf_counter
from urllib.parse import quote_plus

from .catalog import CATALOG
from .gemini import generate_grounded_links, generate_scan_payload, generate_visualization
from .schemas import Idea, ScanResponse, TutorialLink, TutorialLinksResponse, VisualizationResponse
from .settings import Settings

logger = logging.getLogger(__name__)


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))


def _is_invalid_key_error(message: str) -> bool:
    normalized = message.lower()
    return "api_key_invalid" in normalized or "api key not valid" in normalized


def _is_quota_error(message: str) -> bool:
    normalized = message.lower()
    return "resource_exhausted" in normalized or "quota exceeded" in normalized


def _fallback_links(search_query: str, idea_title: str) -> list[TutorialLink]:
    return [
        TutorialLink(
            id="link_1",
            source="youtube",
            title=f"{idea_title} tutorial",
            url=f"https://www.youtube.com/results?search_query={quote_plus(search_query)}",
            reason="Searches YouTube for tutorials matching this exact reuse idea.",
        ),
        TutorialLink(
            id="link_2",
            source="web",
            title=f"{idea_title} how-to search",
            url=f"https://www.google.com/search?q={quote_plus(search_query + ' tutorial')}",
            reason="Searches the web for step-by-step instructions for this exact idea.",
        ),
    ]


def build_mock_scan_response(
    image_bytes: bytes,
    filename: str | None,
    *,
    provider_state: str = "not_configured",
    provider_notice: str | None = None,
    timings_ms: dict[str, int] | None = None,
) -> ScanResponse:
    started_at = perf_counter()
    payload = image_bytes or (filename or "fallback").encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    object_index = digest[0] % len(CATALOG)
    selected = CATALOG[object_index]
    confidence = round(0.74 + (digest[1] / 255) * 0.22, 2)
    scan_id = f"scan_{digest.hex()[:10]}"

    ideas = [
        Idea(
            id=f"idea_{index + 1}",
            title=idea.title,
            description=idea.description,
            difficulty=idea.difficulty,
            why_this_works=f"This reuse idea fits a {selected.label} because it uses the original shape with minimal extra work.",
            materials=["Scissors", "Marker", "Cleaning cloth"],
            steps=[
                "Clean and dry the object thoroughly.",
                "Mark the cut or fold lines for the DIY shape.",
                "Assemble the final item and test that it is stable and safe to use.",
            ],
            search_query=idea.source_query,
            visualization_prompt=(
                f"Transform the uploaded {selected.label} into a realistic finished {idea.title.lower()} "
                "while preserving the original material and proportions."
            ),
            tutorial_links=_fallback_links(idea.source_query, idea.title),
        )
        for index, idea in enumerate(selected.ideas)
    ]

    response = ScanResponse(
        scan_id=scan_id,
        detected_label=selected.label,
        confidence=confidence,
        summary=f"The image most closely resembles a {selected.label}.",
        safety_note="Clean the item well and check for sharp edges before starting any DIY project.",
        source_mode="mock",
        provider_state=provider_state,
        provider_notice=provider_notice,
        created_at=datetime.now(UTC),
        ideas=ideas,
        timings_ms={
            **(timings_ms or {}),
            "fallback_build": _elapsed_ms(started_at),
            "total": (timings_ms or {}).get("total", _elapsed_ms(started_at)),
        },
    )
    logger.info("mock scan response built: scan_id=%s object=%s", response.scan_id, response.detected_label)
    return response


def _generate_tutorial_links(
    *,
    detected_label: str,
    idea_title: str,
    idea_description: str,
    search_query: str,
    settings: Settings,
) -> tuple[list[TutorialLink], str, int]:
    started_at = perf_counter()

    if not settings.gemini_api_key:
        return _fallback_links(search_query, idea_title), "fallback", _elapsed_ms(started_at)

    try:
        grounded = generate_grounded_links(
            detected_label=detected_label,
            idea_title=idea_title,
            idea_description=idea_description,
            search_query=search_query,
            settings=settings,
        )
        tutorial_links = [
            TutorialLink(
                id=f"link_{link_index + 1}",
                source=link.source,
                title=link.title,
                url=link.url,
                reason=link.reason,
            )
            for link_index, link in enumerate(grounded.links[:3])
        ]
        link_mode = "grounded"
    except Exception as exc:
        logger.warning("Grounded link generation failed for '%s': %s", idea_title, exc)
        tutorial_links = _fallback_links(search_query, idea_title)
        link_mode = "fallback"

    return tutorial_links, link_mode, _elapsed_ms(started_at)


def build_scan_response(
    *,
    image_bytes: bytes,
    filename: str | None,
    mime_type: str,
    settings: Settings,
) -> ScanResponse:
    total_started_at = perf_counter()

    if not settings.gemini_api_key:
        return build_mock_scan_response(
            image_bytes=image_bytes,
            filename=filename,
            provider_state="not_configured",
            provider_notice="Gemini is not configured, so this scan is using local mock ideas.",
            timings_ms={"total": _elapsed_ms(total_started_at)},
        )

    analysis_started_at = perf_counter()
    try:
        payload = generate_scan_payload(
            image_bytes=image_bytes,
            mime_type=mime_type,
            settings=settings,
        )
        analysis_ms = _elapsed_ms(analysis_started_at)
        logger.info(
            "gemini scan payload generated: object=%s confidence=%.2f ideas=%s analysis_ms=%s",
            payload.detected_label,
            payload.confidence,
            len(payload.ideas),
            analysis_ms,
        )
    except Exception as exc:
        analysis_ms = _elapsed_ms(analysis_started_at)
        logger.warning("Gemini scan generation failed, falling back to mock mode: %s", exc)
        if settings.mock_fallback_enabled:
            provider_notice = (
                "Gemini rejected the API key, so this scan is using local mock ideas."
                if _is_invalid_key_error(str(exc))
                else "Gemini analysis failed, so this scan is using local mock ideas."
            )
            provider_state = "fallback_invalid_key" if _is_invalid_key_error(str(exc)) else "fallback_error"
            return build_mock_scan_response(
                image_bytes=image_bytes,
                filename=filename,
                provider_state=provider_state,
                provider_notice=provider_notice,
                timings_ms={
                    "analysis": analysis_ms,
                    "total": _elapsed_ms(total_started_at),
                },
            )
        raise

    scan_id_seed = hashlib.sha256(image_bytes).hexdigest()[:10]
    ideas: list[Idea] = []

    for index, idea in enumerate(payload.ideas):
        ideas.append(
            Idea(
                id=f"idea_{index + 1}",
                title=idea.title,
                description=idea.description,
                difficulty=idea.difficulty,
                why_this_works=idea.why_this_works,
                materials=idea.materials,
                steps=idea.steps,
                search_query=idea.search_query,
                visualization_prompt=idea.visualization_prompt,
                tutorial_links=_fallback_links(idea.search_query, idea.title),
            )
        )

    response = ScanResponse(
        scan_id=f"scan_{scan_id_seed}",
        detected_label=payload.detected_label.strip().lower(),
        confidence=payload.confidence,
        summary=payload.summary.strip(),
        safety_note=payload.safety_note.strip(),
        source_mode="gemini",
        provider_state="ok",
        provider_notice=None,
        created_at=datetime.now(UTC),
        ideas=ideas,
        timings_ms={
            "analysis": analysis_ms,
            "total": _elapsed_ms(total_started_at),
        },
    )
    logger.info(
        "gemini scan response built: scan_id=%s object=%s total_ms=%s ideas=%s",
        response.scan_id,
        response.detected_label,
        response.timings_ms["total"],
        len(response.ideas),
    )
    return response


def build_tutorial_links_response(
    *,
    detected_label: str,
    idea_id: str,
    idea_title: str,
    idea_description: str,
    search_query: str,
    settings: Settings,
) -> TutorialLinksResponse:
    tutorial_links, link_mode, elapsed_ms = _generate_tutorial_links(
        detected_label=detected_label,
        idea_title=idea_title,
        idea_description=idea_description,
        search_query=search_query,
        settings=settings,
    )
    logger.info(
        "tutorial links generated: idea_id=%s mode=%s elapsed_ms=%s",
        idea_id,
        link_mode,
        elapsed_ms,
    )
    return TutorialLinksResponse(
        idea_id=idea_id,
        tutorial_links=tutorial_links,
        links_mode=link_mode,
        timings_ms={"total": elapsed_ms},
    )


def build_visualization_response(
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
    started_at = perf_counter()
    if not settings.gemini_api_key:
        raise ValueError("Gemini API key is missing. Add a valid key to generate concept images.")

    try:
        response = generate_visualization(
            image_bytes=image_bytes,
            mime_type=mime_type,
            detected_label=detected_label,
            idea_id=idea_id,
            idea_title=idea_title,
            idea_description=idea_description,
            visualization_prompt=visualization_prompt,
            settings=settings,
        )
        response.timings_ms["total"] = _elapsed_ms(started_at)
        logger.info(
            "visualization generated: idea_id=%s model=%s total_ms=%s",
            response.idea_id,
            response.model,
            response.timings_ms["total"],
        )
        return response
    except Exception as exc:
        message = str(exc)
        if _is_invalid_key_error(message):
            raise ValueError(
                "Gemini API key is invalid. Replace GEMINI_API_KEY in api/.env with a valid Google AI Studio key.",
            ) from exc
        if _is_quota_error(message):
            raise ValueError(
                f"Gemini image generation quota is exhausted for {settings.image_model}. "
                "Retry later or enable a paid tier for image generation.",
            ) from exc
        raise ValueError("Gemini image generation failed. Check the configured model and API key.") from exc
