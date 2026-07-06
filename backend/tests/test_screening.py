import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.pipeline.presets import Preset, RubricDimension
from backend.pipeline.prompts.template_manager import TemplateManager
from backend.pipeline.screening import (
    DimensionScore,
    PresetEvaluator,
    RubricEvaluation,
    build_result,
    compute_overall_score,
    validate_evaluation_against_preset,
)


@pytest.fixture
def preset() -> Preset:
    return Preset(
        id="test-role",
        name="Test Role",
        role_description="A role used in tests.",
        dimensions=[
            RubricDimension(
                key="skill", name="Skill", weight=60, guidance="Skill evidence."
            ),
            RubricDimension(
                key="drive", name="Drive", weight=40, guidance="Drive evidence."
            ),
        ],
    )


def make_evaluation(skill=8, drive=5, **overrides) -> RubricEvaluation:
    base = dict(
        dimension_scores={
            "skill": DimensionScore(score=skill, evidence="built things"),
            "drive": DimensionScore(score=drive, evidence="started things"),
        },
        key_strengths=["ships fast"],
        concerns=["no production experience"],
        verdict="Worth an interview.",
    )
    base.update(overrides)
    return RubricEvaluation(**base)


class TestScoreNormalization:
    def test_weighted_overall_score(self, preset):
        # 0.6 * 8 + 0.4 * 5 = 6.8 -> 68.0
        assert compute_overall_score(preset, make_evaluation()) == 68.0

    def test_all_max_scores_give_100(self, preset):
        assert compute_overall_score(preset, make_evaluation(10, 10)) == 100.0

    def test_all_zero_scores_give_0(self, preset):
        assert compute_overall_score(preset, make_evaluation(0, 0)) == 0.0

    def test_score_independent_of_weight_scale(self, preset):
        doubled = preset.model_copy(deep=True)
        for d in doubled.dimensions:
            d.weight *= 7
        evaluation = make_evaluation()
        assert compute_overall_score(doubled, evaluation) == compute_overall_score(
            preset, evaluation
        )


class TestRubricEvaluationSchema:
    def test_score_above_10_rejected(self):
        with pytest.raises(ValidationError):
            DimensionScore(score=11, evidence="x")

    def test_negative_score_rejected(self):
        with pytest.raises(ValidationError):
            DimensionScore(score=-1, evidence="x")

    def test_empty_evidence_rejected(self):
        with pytest.raises(ValidationError):
            DimensionScore(score=5, evidence="")

    def test_missing_dimension_detected(self, preset):
        evaluation = make_evaluation()
        del evaluation.dimension_scores["drive"]
        with pytest.raises(ValueError, match="missing dimensions.*drive"):
            validate_evaluation_against_preset(preset, evaluation)

    def test_unexpected_dimension_detected(self, preset):
        evaluation = make_evaluation()
        evaluation.dimension_scores["invented"] = DimensionScore(
            score=1, evidence="x"
        )
        with pytest.raises(ValueError, match="unexpected dimensions.*invented"):
            validate_evaluation_against_preset(preset, evaluation)


class TestBuildResult:
    def test_result_snapshots_rubric(self, preset):
        result = build_result(preset, make_evaluation(), candidate_name="Ada")
        assert result.rubric_snapshot == preset
        assert result.candidate_name == "Ada"
        assert result.overall_score == 68.0
        assert [d.key for d in result.dimensions] == ["skill", "drive"]
        assert result.dimensions[0].weight == pytest.approx(0.6)
        assert result.dimensions[0].evidence == "built things"

    def test_snapshot_unaffected_by_later_preset_edits(self, preset):
        result = build_result(preset, make_evaluation())
        preset.dimensions[0].weight = 999
        preset.dimensions[0].guidance = "changed"
        assert result.rubric_snapshot.dimensions[0].weight == 60
        assert result.rubric_snapshot.dimensions[0].guidance == "Skill evidence."
        assert result.overall_score == 68.0


class TestPromptRendering:
    def test_criteria_prompt_contains_rubric_and_resume(self, preset):
        rendered = TemplateManager().render_template(
            "preset_evaluation_criteria",
            preset_name=preset.name,
            role_description=preset.role_description,
            dimensions=preset.dimensions,
            text_content="RESUME BODY HERE",
        )
        assert "Test Role" in rendered
        assert "A role used in tests." in rendered
        assert "Skill evidence." in rendered
        assert "Drive evidence." in rendered
        assert '"skill": {"score": 0, "evidence": "string"}' in rendered
        assert '"drive": {"score": 0, "evidence": "string"}' in rendered
        assert "RESUME BODY HERE" in rendered

    def test_system_message_keeps_global_fairness_rules(self):
        rendered = TemplateManager().render_template(
            "preset_evaluation_system_message"
        )
        for banned in ("name, gender", "GPA", "institution name"):
            assert banned in rendered


class FakeProvider:
    """Provider double returning queued responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        return {"message": {"content": self.responses.pop(0)}}


def valid_llm_json() -> str:
    return json.dumps(
        {
            "dimension_scores": {
                "skill": {"score": 7, "evidence": "shipped an app"},
                "drive": {"score": 6, "evidence": "founded a club"},
            },
            "key_strengths": ["builder"],
            "concerns": [],
            "verdict": "Solid candidate.",
        }
    )


class TestPresetEvaluator:
    @patch("backend.pipeline.screening.initialize_llm_provider")
    def test_valid_response_parsed(self, init_provider, preset):
        init_provider.return_value = FakeProvider([valid_llm_json()])
        evaluation = PresetEvaluator(model_name="test-model").evaluate(
            preset, "resume text"
        )
        assert evaluation.dimension_scores["skill"].score == 7
        assert evaluation.verdict == "Solid candidate."

    @patch("backend.pipeline.screening.initialize_llm_provider")
    def test_retries_once_on_invalid_then_succeeds(self, init_provider, preset):
        provider = FakeProvider(["{not json", valid_llm_json()])
        init_provider.return_value = provider
        evaluation = PresetEvaluator(model_name="test-model").evaluate(
            preset, "resume text"
        )
        assert provider.calls == 2
        assert evaluation.dimension_scores["drive"].score == 6

    @patch("backend.pipeline.screening.initialize_llm_provider")
    def test_fails_after_max_attempts(self, init_provider, preset):
        missing_dim = json.dumps(
            {
                "dimension_scores": {
                    "skill": {"score": 7, "evidence": "shipped an app"}
                },
                "key_strengths": ["builder"],
                "concerns": [],
                "verdict": "Incomplete.",
            }
        )
        init_provider.return_value = FakeProvider([missing_dim, missing_dim])
        with pytest.raises(ValueError, match="failed validation after 2 attempts"):
            PresetEvaluator(model_name="test-model").evaluate(preset, "resume text")

    @patch("backend.pipeline.screening.initialize_llm_provider")
    def test_markdown_fenced_json_accepted(self, init_provider, preset):
        init_provider.return_value = FakeProvider(
            [f"```json\n{valid_llm_json()}\n```"]
        )
        evaluation = PresetEvaluator(model_name="test-model").evaluate(
            preset, "resume text"
        )
        assert evaluation.dimension_scores["skill"].score == 7
