from __future__ import annotations

import base64
import importlib
import os
import unittest

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

        from app.settings import get_settings

        get_settings.cache_clear()

        import app.main as main_module

        cls.main_module = importlib.reload(main_module)
        cls.client = TestClient(cls.main_module.app)

    def test_health(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["gemini_configured"], "no")
        self.assertEqual(payload["mock_fallback_enabled"], "yes")
        self.assertEqual(payload["max_upload_megabytes"], 10)

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


if __name__ == "__main__":
    unittest.main()
