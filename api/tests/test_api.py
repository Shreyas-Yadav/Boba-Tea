from __future__ import annotations

import base64
import importlib
import os
import unittest
from datetime import UTC, datetime
from unittest import mock

from fastapi.testclient import TestClient


TEST_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1EAAAAASUVORK5CYII="
)


class ApiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["GEMINI_API_KEY"] = ""
        os.environ["GOOGLE_API_KEY"] = ""
        os.environ["MOCK_FALLBACK_ENABLED"] = "true"
        os.environ["VISUALIZATION_JOBS_ENABLED"] = "false"
        os.environ["VISUALIZATION_JOBS_BUCKET"] = ""
        os.environ["VISUALIZATION_JOBS_QUEUE_URL"] = ""

        from app.settings import get_settings
        from app.schemas import VisualizationJobResponse, VisualizationResponse

        get_settings.cache_clear()

        import app.main as main_module

        cls.main_module = importlib.reload(main_module)
        cls.client = TestClient(cls.main_module.app)
        cls.VisualizationJobResponse = VisualizationJobResponse
        cls.VisualizationResponse = VisualizationResponse

    def test_health(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["gemini_configured"], "no")
        self.assertEqual(payload["mock_fallback_enabled"], "yes")
        self.assertEqual(payload["max_upload_megabytes"], 10)
        self.assertEqual(payload["visualization_mode"], "inline")

    def test_scan_falls_back_without_gemini(self) -> None:
        response = self.client.post(
            "/scan",
            files={"image": ("tiny.png", TEST_PNG, "image/png")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source_mode"], "mock")
        self.assertEqual(payload["provider_state"], "not_configured")
        self.assertGreaterEqual(len(payload["ideas"]), 1)
        self.assertIn("total", payload["timings_ms"])

    def test_links_fall_back_without_gemini(self) -> None:
        response = self.client.post(
            "/links",
            json={
                "detected_label": "plastic bottle",
                "idea_id": "idea_1",
                "idea_title": "Self-Watering Planter",
                "idea_description": "Turns a bottle into a planter with a water reservoir.",
                "search_query": "plastic bottle self watering planter",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["links_mode"], "fallback")
        self.assertGreaterEqual(len(payload["tutorial_links"]), 1)
        self.assertIn("total", payload["timings_ms"])

    def test_visualization_job_falls_back_to_inline_mode(self) -> None:
        fake_response = self.VisualizationJobResponse(
            job_id="inline_test",
            idea_id="idea_1",
            status="completed",
            source_mode="inline",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            result=self.VisualizationResponse(
                idea_id="idea_1",
                model="mock-model",
                mime_type="image/png",
                image_base64=base64.b64encode(TEST_PNG).decode("utf-8"),
                caption="Mock visualization",
                timings_ms={"total": 12},
            ),
            timings_ms={"total": 15},
        )

        with mock.patch.object(self.main_module, "create_visualization_job_response", return_value=fake_response):
            response = self.client.post(
                "/visualize/jobs",
                files={"image": ("tiny.png", TEST_PNG, "image/png")},
                data={
                    "idea_id": "idea_1",
                    "detected_label": "plastic bottle",
                    "idea_title": "Self-Watering Planter",
                    "idea_description": "Turns a bottle into a planter with a water reservoir.",
                    "visualization_prompt": "Create a realistic self-watering planter from the uploaded bottle.",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["source_mode"], "inline")
        self.assertEqual(payload["result"]["idea_id"], "idea_1")


if __name__ == "__main__":
    unittest.main()
