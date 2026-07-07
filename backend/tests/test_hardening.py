import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api.jobs import classify_error
from backend.api.main import create_app
from backend.api.ratelimit import RateLimits, SlidingWindowLimiter
from backend.tests.test_api import FAKE_PDF, fake_resume, fake_result, wait_for_done


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class TestSlidingWindowLimiter:
    def test_allows_up_to_limit_then_blocks(self):
        clock = FakeClock()
        limiter = SlidingWindowLimiter(limit=3, window_seconds=60, clock=clock)
        assert all(limiter.allow("ip1")[0] for _ in range(3))
        allowed, retry_after = limiter.allow("ip1")
        assert not allowed
        assert 0 < retry_after <= 61

    def test_window_slides(self):
        clock = FakeClock()
        limiter = SlidingWindowLimiter(limit=2, window_seconds=60, clock=clock)
        limiter.allow("ip1")
        limiter.allow("ip1")
        assert limiter.allow("ip1")[0] is False
        clock.advance(61)
        assert limiter.allow("ip1")[0] is True

    def test_keys_are_independent(self):
        limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=FakeClock())
        assert limiter.allow("ip1")[0] is True
        assert limiter.allow("ip2")[0] is True
        assert limiter.allow("ip1")[0] is False


class TestClientIp:
    def test_last_forwarded_hop_wins(self):
        from backend.api.ratelimit import client_ip

        class Req:
            headers = {"x-forwarded-for": "6.6.6.6, 203.0.113.7"}
            client = None

        # 6.6.6.6 is client-forgeable; 203.0.113.7 is what the proxy appended
        assert client_ip(Req()) == "203.0.113.7"


class TestUploadSizeCap:
    def test_oversized_pdf_rejected_413(self, strict_client):
        big = b"%PDF-1.4 " + b"x" * (10 * 1024 * 1024)
        resp = strict_client.post(
            "/api/screenings",
            files={"file": ("big.pdf", io.BytesIO(big), "application/pdf")},
            data={"preset_id": "bd-intern"},
        )
        assert resp.status_code == 413


class TestClassifyError:
    def test_rate_limit_errors_mention_quota(self):
        msg = classify_error(Exception("429 You exceeded your current quota"))
        assert "rate limit" in msg.lower() or "quota" in msg.lower()
        assert "429" not in msg  # raw provider text stays out of the UI

    def test_validation_errors_suggest_retry(self):
        msg = classify_error(ValueError("LLM evaluation failed validation after 2 attempts"))
        assert "re-submit" in msg.lower()

    def test_network_errors_named(self):
        assert "network" in classify_error(Exception("Connection timed out")).lower()

    def test_fallback_is_calm_and_generic(self):
        msg = classify_error(RuntimeError("KeyError: 'message'"))
        assert "unexpected" in msg.lower()
        assert "KeyError" not in msg


@pytest.fixture
def strict_client():
    limits = RateLimits(
        api_per_minute=1000,
        screenings_per_hour_per_ip=2,
        screenings_per_hour_global=3,
    )
    app = create_app(database_url="sqlite://", rate_limits=limits)
    with TestClient(app) as client:
        yield client


def post_screening(client, filename="cv.pdf"):
    return client.post(
        "/api/screenings",
        files={"file": (filename, io.BytesIO(FAKE_PDF), "application/pdf")},
        data={"preset_id": "bd-intern"},
    )


class TestScreeningRateLimits:
    @patch("backend.api.jobs.screening.screen_parsed")
    @patch("backend.api.jobs.screening.parse_resume")
    def test_per_ip_limit_gives_429_with_retry_after(self, parse, screen_parsed, strict_client):
        parse.return_value = fake_resume()
        screen_parsed.side_effect = lambda resume, preset, github_data=None, **kw: (
            fake_result(preset)
        )
        assert post_screening(strict_client).status_code == 202
        assert post_screening(strict_client).status_code == 202
        resp = post_screening(strict_client)
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert "this hour" in resp.json()["detail"]

    def test_global_limit_message_differs(self):
        limits = RateLimits(
            api_per_minute=1000,
            screenings_per_hour_per_ip=100,
            screenings_per_hour_global=1,
        )
        app = create_app(database_url="sqlite://", rate_limits=limits)
        with TestClient(app) as client, patch(
            "backend.api.jobs.screening.parse_resume", return_value=None
        ):
            assert post_screening(client).status_code == 202
            resp = post_screening(client)
            assert resp.status_code == 429
            assert "budget" in resp.json()["detail"]


class TestApiWideRateLimit:
    def test_general_api_limit(self):
        limits = RateLimits(
            api_per_minute=3, screenings_per_hour_per_ip=100, screenings_per_hour_global=100
        )
        app = create_app(database_url="sqlite://", rate_limits=limits)
        with TestClient(app) as client:
            for _ in range(3):
                assert client.get("/api/health").status_code == 200
            resp = client.get("/api/health")
            assert resp.status_code == 429
            assert "Retry-After" in resp.headers


class TestGracefulDegradation:
    @patch("backend.api.jobs.screening.screen_parsed")
    @patch("backend.api.jobs.screening.enrich")
    @patch("backend.api.jobs.screening.parse_resume")
    def test_enrichment_failure_does_not_fail_screening(
        self, parse, enrich, screen_parsed, strict_client
    ):
        parse.return_value = fake_resume()
        enrich.side_effect = RuntimeError("GitHub API exploded")
        captured = {}

        def capture(resume, preset, github_data=None, **kw):
            captured["github_data"] = github_data
            return fake_result(preset)

        screen_parsed.side_effect = capture
        resp = strict_client.post(
            "/api/screenings",
            files={"file": ("cv.pdf", io.BytesIO(FAKE_PDF), "application/pdf")},
            data={"preset_id": "software-engineer"},  # github enrichment on
        )
        job = wait_for_done(strict_client, resp.json()["id"])
        assert job["status"] == "done"
        assert captured["github_data"] == {}

    @patch("backend.api.jobs.screening.parse_resume")
    def test_job_error_is_classified_not_raw(self, parse, strict_client):
        parse.side_effect = Exception("429 RESOURCE_EXHAUSTED: quota exceeded")
        job = wait_for_done(strict_client, post_screening(strict_client).json()["id"])
        assert job["status"] == "failed"
        assert "quota" in job["error"].lower() or "rate limit" in job["error"].lower()
        assert "RESOURCE_EXHAUSTED" not in job["error"]


class TestUnhandledErrorHandler:
    def test_500s_are_calm_and_non_leaky(self):
        from fastapi.routing import APIRoute

        app = create_app(database_url="sqlite://")

        def boom():
            raise RuntimeError("secret internals: /etc/passwd")

        # insert ahead of the SPA catch-all mount so the route is reachable
        app.router.routes.insert(0, APIRoute("/api/boom", boom, methods=["GET"]))

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/boom")
            assert resp.status_code == 500
            assert "secret" not in resp.text
            assert "logged" in resp.json()["detail"]
