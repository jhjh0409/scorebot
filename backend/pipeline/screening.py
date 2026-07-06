"""
Preset-driven resume screening.

This is the service layer the web API (Phase 2) will call. It reuses the
upstream pipeline pieces (PDF extraction, GitHub enrichment, provider layer)
but replaces the hardcoded evaluation rubric with one rendered from a Preset:
the LLM scores each rubric dimension 0-10 with evidence, and the weighted
0-100 overall score is computed here in code, never by the LLM.
"""

import json
import logging
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from .github import fetch_and_display_github_info
from .llm_utils import extract_json_from_response, initialize_llm_provider
from .models import JSONResume
from .pdf import PDFHandler
from .presets import Preset
from .prompt import DEFAULT_MODEL, MODEL_PARAMETERS
from .prompts.template_manager import TemplateManager
from .transform import convert_github_data_to_text, convert_json_resume_to_text

logger = logging.getLogger(__name__)

MAX_DIMENSION_SCORE = 10


class DimensionScore(BaseModel):
    """Raw per-dimension output from the LLM."""

    score: int = Field(ge=0, le=MAX_DIMENSION_SCORE)
    evidence: str = Field(min_length=1)


class RubricEvaluation(BaseModel):
    """The exact JSON shape the evaluation prompt asks the LLM for."""

    dimension_scores: Dict[str, DimensionScore]
    key_strengths: List[str] = Field(min_length=1, max_length=5)
    concerns: List[str] = Field(default_factory=list, max_length=3)
    verdict: str = Field(min_length=1)


class ScoredDimension(BaseModel):
    """One dimension of the final result, weight-resolved and evidence-backed."""

    key: str
    name: str
    weight: float  # normalized fraction of the overall score (sums to 1.0)
    score: int  # 0-10
    evidence: str


class ScreeningResult(BaseModel):
    """
    A complete screening: what the API returns and (later) what persists.
    Snapshots the rubric so the result stays interpretable after preset edits.
    """

    candidate_name: Optional[str] = None
    preset_id: str
    preset_name: str
    rubric_snapshot: Preset
    overall_score: float  # 0-100
    dimensions: List[ScoredDimension]
    key_strengths: List[str]
    concerns: List[str]
    verdict: str


def compute_overall_score(preset: Preset, evaluation: RubricEvaluation) -> float:
    """Weighted sum of dimension scores, normalized to 0-100."""
    weights = preset.normalized_weights()
    overall = sum(
        weights[key] * evaluation.dimension_scores[key].score
        for key in weights
    ) * (100 / MAX_DIMENSION_SCORE)
    return round(overall, 1)


def build_result(
    preset: Preset,
    evaluation: RubricEvaluation,
    candidate_name: Optional[str] = None,
) -> ScreeningResult:
    """Assemble the final result from a validated LLM evaluation."""
    weights = preset.normalized_weights()
    dimensions = [
        ScoredDimension(
            key=d.key,
            name=d.name,
            weight=round(weights[d.key], 4),
            score=evaluation.dimension_scores[d.key].score,
            evidence=evaluation.dimension_scores[d.key].evidence,
        )
        for d in preset.dimensions
    ]
    return ScreeningResult(
        candidate_name=candidate_name,
        preset_id=preset.id,
        preset_name=preset.name,
        # deep copy: the snapshot must not change when the preset is edited later
        rubric_snapshot=preset.model_copy(deep=True),
        overall_score=compute_overall_score(preset, evaluation),
        dimensions=dimensions,
        key_strengths=evaluation.key_strengths,
        concerns=evaluation.concerns,
        verdict=evaluation.verdict,
    )


class PresetEvaluator:
    """Scores resume text against a preset's rubric via one LLM call."""

    def __init__(self, model_name: str = DEFAULT_MODEL, model_params: dict = None):
        if not model_name:
            raise ValueError("Model name cannot be empty")
        self.model_name = model_name
        self.model_params = model_params or MODEL_PARAMETERS.get(
            model_name, {"temperature": 0.1, "top_p": 0.9}
        )
        self.template_manager = TemplateManager()
        self.provider = initialize_llm_provider(model_name)

    def render_prompt(self, preset: Preset, resume_text: str) -> str:
        prompt = self.template_manager.render_template(
            "preset_evaluation_criteria",
            preset_name=preset.name,
            role_description=preset.role_description,
            dimensions=preset.dimensions,
            text_content=resume_text,
        )
        if prompt is None:
            raise ValueError("Failed to render preset evaluation criteria template")
        return prompt

    def evaluate(
        self, preset: Preset, resume_text: str, max_attempts: int = 2
    ) -> RubricEvaluation:
        system_message = self.template_manager.render_template(
            "preset_evaluation_system_message"
        )
        if system_message is None:
            raise ValueError("Failed to render preset evaluation system message")
        prompt = self.render_prompt(preset, resume_text)

        chat_params = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "stream": False,
                "temperature": self.model_params.get("temperature", 0.1),
                "top_p": self.model_params.get("top_p", 0.9),
            },
        }
        kwargs = {"format": RubricEvaluation.model_json_schema()}

        last_error: Exception = None
        for attempt in range(1, max_attempts + 1):
            response = self.provider.chat(**chat_params, **kwargs)
            response_text = extract_json_from_response(
                response["message"]["content"]
            )
            try:
                evaluation = RubricEvaluation(**json.loads(response_text))
                validate_evaluation_against_preset(preset, evaluation)
                return evaluation
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning(
                    f"Evaluation attempt {attempt}/{max_attempts} returned "
                    f"invalid output: {exc}"
                )
        raise ValueError(
            f"LLM evaluation failed validation after {max_attempts} attempts"
        ) from last_error


def validate_evaluation_against_preset(
    preset: Preset, evaluation: RubricEvaluation
) -> None:
    """Every rubric dimension must be scored; unknown keys are rejected."""
    expected = {d.key for d in preset.dimensions}
    got = set(evaluation.dimension_scores)
    missing = expected - got
    extra = got - expected
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing dimensions: {sorted(missing)}")
        if extra:
            parts.append(f"unexpected dimensions: {sorted(extra)}")
        raise ValueError("; ".join(parts))


def parse_resume(pdf_path: str) -> Optional[JSONResume]:
    """Extract a structured resume from a PDF (six section-wise LLM calls)."""
    return PDFHandler().extract_json_from_pdf(pdf_path)


def enrich(resume: JSONResume, preset: Preset) -> dict:
    """Run the enrichment steps the preset asks for. Returns extra text data."""
    if not preset.enrichments.github:
        return {}
    profiles = []
    if resume and resume.basics:
        profiles = resume.basics.profiles or []
    github_profile = next(
        (p for p in profiles if p.network and p.network.lower() == "github"), None
    )
    if not github_profile:
        return {}
    return fetch_and_display_github_info(github_profile.url) or {}


def build_resume_text(resume: JSONResume, github_data: dict) -> str:
    resume_text = convert_json_resume_to_text(resume)
    if github_data:
        resume_text += convert_github_data_to_text(github_data)
    return resume_text


def screen(
    pdf_path: str,
    preset: Preset,
    model_name: str = DEFAULT_MODEL,
) -> Optional[ScreeningResult]:
    """Full pipeline: parse -> enrich (per preset) -> evaluate -> result."""
    resume = parse_resume(pdf_path)
    if resume is None:
        return None
    github_data = enrich(resume, preset)
    return screen_parsed(resume, preset, github_data, model_name=model_name)


def screen_parsed(
    resume: JSONResume,
    preset: Preset,
    github_data: dict = None,
    model_name: str = DEFAULT_MODEL,
) -> ScreeningResult:
    """Screen an already-parsed resume (lets callers cache the parse step)."""
    github_data = github_data or {}
    resume_text = build_resume_text(resume, github_data)
    evaluator = PresetEvaluator(model_name=model_name)
    evaluation = evaluator.evaluate(preset, resume_text)
    candidate_name = resume.basics.name if resume.basics else None
    return build_result(preset, evaluation, candidate_name=candidate_name)
