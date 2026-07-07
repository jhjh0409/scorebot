import io
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api.db import _normalize_url
from backend.api.main import create_app
from backend.pipeline.models import Basics, JSONResume
from backend.pipeline.presets import Preset, RubricDimension
from backend.pipeline.screening import (
    DimensionScore,
    RubricEvaluation,
    build_result,
)

FAKE_PDF = b"%PDF-1.4 fake resume bytes"


@pytest.fixture
def client():
    app = create_app(database_url="sqlite://")
    with TestClient(app) as client:
        yield client


def fake_resume() -> JSONResume:
    return JSONResume(basics=Basics(name="Ada Lovelace"))


def fake_result(preset: Preset):
    evaluation = RubricEvaluation(
        dimension_scores={
            d.key: DimensionScore(score=7, evidence="evidence")
            for d in preset.dimensions
        },
        key_strengths=["builder"],
        concerns=[],
        verdict="Solid.",
    )
    return build_result(preset, evaluation, candidate_name="Ada Lovelace")


def wait_for_done(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/screenings/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish in time")


class TestHealth:
    def test_health(self, client):
        assert client.get("/api/health").json() == {"status": "ok"}


class TestDatabaseUrlNormalization:
    def test_managed_host_urls_get_psycopg_dialect(self):
        assert _normalize_url("postgres://u:p@host:5432/db") == (
            "postgresql+psycopg://u:p@host:5432/db"
        )
        assert _normalize_url("postgresql://u:p@host/db") == (
            "postgresql+psycopg://u:p@host/db"
        )

    def test_explicit_and_sqlite_urls_untouched(self):
        assert _normalize_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"
        assert _normalize_url("sqlite://") == "sqlite://"


class TestPresetCrud:
    def test_seeded_with_all_starter_presets(self, client):
        presets = client.get("/api/presets").json()
        assert sorted(p["id"] for p in presets) == [
            "bd-intern",
            "data-analyst",
            "marketing-intern",
            "product-designer",
            "software-engineer",
        ]

    def test_seeding_adds_missing_without_touching_edits_or_deletes(self):
        # simulate a pre-existing DB: seed, edit one preset, soft-delete
        # another, drop a third entirely — re-seeding must restore only the
        # dropped one and leave the edit and the delete alone
        from backend.api.db import (
            Base,
            PresetRow,
            make_engine,
            make_session_factory,
            seed_missing_presets,
        )

        engine = make_engine("sqlite://")
        Base.metadata.create_all(engine)
        session_factory = make_session_factory(engine)

        with session_factory() as s:
            assert seed_missing_presets(s) == 5

            s.get(PresetRow, "bd-intern").name = "Team-Renamed Role"
            s.get(PresetRow, "marketing-intern").active = False  # deliberate delete
            s.delete(s.get(PresetRow, "data-analyst"))  # missing entirely
            s.commit()

        with session_factory() as s:
            assert seed_missing_presets(s) == 1  # only data-analyst comes back
            assert s.get(PresetRow, "bd-intern").name == "Team-Renamed Role"
            assert s.get(PresetRow, "marketing-intern").active is False
            assert s.get(PresetRow, "data-analyst") is not None

    def test_get_single_preset(self, client):
        preset = client.get("/api/presets/software-engineer").json()
        assert preset["name"] == "Software Engineer"
        assert preset["enrichments"]["github"] is True

    def test_get_unknown_preset_404(self, client):
        assert client.get("/api/presets/nope").status_code == 404

    def test_create_update_delete_roundtrip(self, client):
        new_preset = {
            "id": "designer",
            "name": "Product Designer",
            "role_description": "Designs the product.",
            "dimensions": [
                {
                    "key": "portfolio",
                    "name": "Portfolio",
                    "weight": 100,
                    "guidance": "Linked, real work.",
                }
            ],
        }
        assert client.post("/api/presets", json=new_preset).status_code == 201
        assert client.post("/api/presets", json=new_preset).status_code == 409

        new_preset["name"] = "Senior Product Designer"
        updated = client.put("/api/presets/designer", json=new_preset)
        assert updated.status_code == 200
        assert client.get("/api/presets/designer").json()["name"] == (
            "Senior Product Designer"
        )

        assert client.delete("/api/presets/designer").status_code == 204
        assert client.get("/api/presets/designer").status_code == 404
        ids = [p["id"] for p in client.get("/api/presets").json()]
        assert "designer" not in ids

    def test_deleted_id_can_be_recreated(self, client):
        preset = {
            "id": "temp",
            "name": "Temp",
            "role_description": "x",
            "dimensions": [
                {"key": "a", "name": "A", "weight": 1, "guidance": "g"}
            ],
        }
        client.post("/api/presets", json=preset)
        client.delete("/api/presets/temp")
        assert client.post("/api/presets", json=preset).status_code == 201

    def test_invalid_preset_rejected(self, client):
        bad = {
            "id": "bad",
            "name": "Bad",
            "role_description": "x",
            "dimensions": [
                {"key": "a", "name": "A", "weight": 0, "guidance": "g"}
            ],
        }
        assert client.post("/api/presets", json=bad).status_code == 422

    def test_update_id_mismatch_rejected(self, client):
        preset = client.get("/api/presets/bd-intern").json()
        assert client.put("/api/presets/software-engineer", json=preset).status_code == 422


class TestScreenings:
    def _post_screening(self, client, preset_id="bd-intern", filename="cv.pdf"):
        return client.post(
            "/api/screenings",
            files={"file": (filename, io.BytesIO(FAKE_PDF), "application/pdf")},
            data={"preset_id": preset_id},
        )

    @patch("backend.api.jobs.screening.screen_parsed")
    @patch("backend.api.jobs.screening.parse_resume")
    def test_screening_happy_path(self, parse, screen_parsed, client):
        parse.return_value = fake_resume()
        screen_parsed.side_effect = lambda resume, preset, github_data=None, **kw: (
            fake_result(preset)
        )

        created = self._post_screening(client)
        assert created.status_code == 202
        job = wait_for_done(client, created.json()["id"])

        assert job["status"] == "done"
        assert job["result"]["candidate_name"] == "Ada Lovelace"
        assert job["result"]["overall_score"] == 70.0
        assert job["result"]["preset_id"] == "bd-intern"
        # rubric snapshot rides along with the result
        assert job["result"]["rubric_snapshot"]["id"] == "bd-intern"

    @patch("backend.api.jobs.screening.screen_parsed")
    @patch("backend.api.jobs.screening.enrich")
    @patch("backend.api.jobs.screening.parse_resume")
    def test_enrichment_only_runs_when_preset_asks(
        self, parse, enrich, screen_parsed, client
    ):
        parse.return_value = fake_resume()
        enrich.return_value = {}
        screen_parsed.side_effect = lambda resume, preset, github_data=None, **kw: (
            fake_result(preset)
        )

        job = wait_for_done(
            client, self._post_screening(client, "bd-intern").json()["id"]
        )
        assert job["status"] == "done"
        enrich.assert_not_called()

        job = wait_for_done(
            client, self._post_screening(client, "software-engineer").json()["id"]
        )
        assert job["status"] == "done"
        enrich.assert_called_once()

    @patch("backend.api.jobs.screening.parse_resume")
    def test_unparseable_pdf_fails_job(self, parse, client):
        parse.return_value = None
        job = wait_for_done(client, self._post_screening(client).json()["id"])
        assert job["status"] == "failed"
        assert "extract" in job["error"]

    @patch("backend.api.jobs.screening.parse_resume")
    def test_pipeline_exception_fails_job(self, parse, client):
        parse.side_effect = RuntimeError("boom")
        job = wait_for_done(client, self._post_screening(client).json()["id"])
        assert job["status"] == "failed"
        # raw exception text is classified into a friendly message, not leaked
        assert "boom" not in job["error"]
        assert "failed" in job["error"].lower()

    def test_unknown_preset_404(self, client):
        assert self._post_screening(client, "nope").status_code == 404

    def test_non_pdf_rejected(self, client):
        resp = client.post(
            "/api/screenings",
            files={"file": ("cv.docx", io.BytesIO(b"PK"), "application/msword")},
            data={"preset_id": "bd-intern"},
        )
        assert resp.status_code == 400

    def test_wrong_magic_bytes_rejected(self, client):
        resp = client.post(
            "/api/screenings",
            files={"file": ("cv.pdf", io.BytesIO(b"not a pdf"), "application/pdf")},
            data={"preset_id": "bd-intern"},
        )
        assert resp.status_code == 400

    @patch("backend.api.jobs.screening.screen_parsed")
    @patch("backend.api.jobs.screening.parse_resume")
    def test_list_screenings_newest_first(self, parse, screen_parsed, client):
        parse.return_value = fake_resume()
        screen_parsed.side_effect = lambda resume, preset, github_data=None, **kw: (
            fake_result(preset)
        )
        first = self._post_screening(client, filename="a.pdf").json()["id"]
        second = self._post_screening(client, filename="b.pdf").json()["id"]
        wait_for_done(client, first)
        wait_for_done(client, second)

        listed = client.get("/api/screenings").json()
        assert [j["filename"] for j in listed][:2] == ["b.pdf", "a.pdf"]

    def test_unknown_job_404(self, client):
        assert client.get("/api/screenings/deadbeef").status_code == 404
