"""Focused API regression tests for the local learning experience."""
import os
import io
import tempfile
import unittest

_TEST_HOME = tempfile.TemporaryDirectory(prefix="japanese-practice-tests-")
os.environ["JAPANESE_PRACTICE_DB"] = os.path.join(_TEST_HOME.name, "test.sqlite3")

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import mobile_server as server
import learning_store as store


class LearningApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store.initialize()

    def setUp(self):
        self.original_tutor_configured = server.tutor_configured
        server.ACCESS_CODE = "24681357"
        server._LOGIN_FAILURES.clear()
        self.client = server.app.test_client()
        self.client.get("/login")
        with self.client.session_transaction() as session:
            token = session["login_csrf"]
        self.client.post("/login", data={"code": "24681357", "csrf_token": token})

    def tearDown(self):
        server.tutor_configured = self.original_tutor_configured

    def test_access_code_login_requires_csrf_and_creates_session(self):
        page = self.client.get("/login")
        self.assertEqual(page.status_code, 200)
        with self.client.session_transaction() as session:
            token = session["login_csrf"]
        bad = self.client.post("/login", data={"code": "24681357", "csrf_token": "wrong"})
        self.assertEqual(bad.status_code, 400)
        good = self.client.post("/login", data={"code": "24681357", "csrf_token": token})
        self.assertEqual(good.status_code, 302)
        self.assertEqual(self.client.get("/api/v1/profile").status_code, 200)

    def test_guided_mode_is_respected_and_explains_limits(self):
        server.tutor_configured = lambda: True
        scenario_id = server.SCENARIOS[0]["id"]
        response = self.client.post("/api/v1/conversations", json={"scenario_id": scenario_id, "mode": "guided"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["mode"], "guided")
        self.assertIn("No live AI", response.json["notice"])

    def test_review_and_lesson_progress_persist(self):
        card = store.vocabulary("N5")[0]
        review = self.client.post(f"/api/v1/reviews/{card['id']}", json={"rating": "good"})
        self.assertEqual(review.status_code, 200)
        self.assertEqual(review.json["repetitions"], 1)

        lesson_id = server.LESSONS[0]["id"]
        attempt = self.client.post(f"/api/v1/lessons/{lesson_id}/complete", json={"answers": {"answer": "incorrect"}})
        self.assertEqual(attempt.status_code, 200)
        self.assertEqual(attempt.json["attempts"], 1)

    def test_lesson_and_scenario_inputs_are_validated(self):
        missing = self.client.get("/api/v1/lessons/not-a-lesson")
        self.assertEqual(missing.status_code, 404)
        bad = self.client.post("/api/v1/conversations", json={"scenario_id": "not-a-scenario"})
        self.assertEqual(bad.status_code, 400)

    def test_unauthorized_api_and_invalid_upload_are_handled(self):
        anonymous = server.app.test_client()
        server.ACCESS_CODE = "24681357"
        self.assertEqual(anonymous.get("/api/v1/profile").status_code, 401)
        response = self.client.post("/api/recognize", data={"image": (io.BytesIO(b"not an image"), "bad.png")})
        self.assertEqual(response.status_code, 400)

    def test_translation_endpoint_validates_and_returns_result(self):
        original = server.translate_japanese
        server.translate_japanese = lambda text: "Hello."
        try:
            empty = self.client.post("/api/translate", json={"text": "   "})
            self.assertEqual(empty.status_code, 400)
            response = self.client.post("/api/translate", json={"text": "こんにちは"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["translation"], "Hello.")
        finally:
            server.translate_japanese = original


if __name__ == "__main__":
    unittest.main()
