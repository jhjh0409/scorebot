"""
scorebot CLI: score a resume PDF against a role preset.

Usage:
    python -m backend.cli <resume.pdf> [--preset software-engineer]

With DEVELOPMENT_MODE enabled (backend/pipeline/config.py), the parse and
GitHub-enrichment steps are cached under cache/ so rubric iterations don't
re-spend LLM calls.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .pipeline import screening
from .pipeline.config import DEVELOPMENT_MODE
from .pipeline.models import JSONResume
from .pipeline.presets import PRESETS_BY_ID, get_preset
from .pipeline.prompt import DEFAULT_MODEL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)5s - %(lineno)5d - %(funcName)33s - %(levelname)5s - %(message)s",
)
logger = logging.getLogger(__name__)


def print_result(result: screening.ScreeningResult) -> None:
    print("\n" + "=" * 80)
    print(f"📊 SCREENING RESULT: {result.candidate_name or 'Unknown candidate'}")
    print(f"🧾 Preset: {result.preset_name} ({result.preset_id})")
    print("=" * 80)
    print(f"\n🎯 OVERALL SCORE: {result.overall_score:.1f}/100")
    print(f"🗣️  Verdict: {result.verdict}")

    print("\n📈 DIMENSIONS:")
    print("-" * 60)
    for dim in result.dimensions:
        weight_pct = dim.weight * 100
        print(f"• {dim.name}  ({dim.score}/10, weight {weight_pct:.0f}%)")
        print(f"  Evidence: {dim.evidence}")
        print()

    if result.key_strengths:
        print("✅ KEY STRENGTHS:")
        for i, s in enumerate(result.key_strengths, 1):
            print(f"  {i}. {s}")

    if result.concerns:
        print("\n⚠️  CONCERNS:")
        for i, c in enumerate(result.concerns, 1):
            print(f"  {i}. {c}")

    print("\n" + "=" * 80)


def _cached_parse(pdf_path: str) -> JSONResume:
    """Parse the PDF, using the dev-mode cache exactly like upstream score.py."""
    cache_file = Path(
        f"cache/resumecache_{os.path.basename(pdf_path).replace('.pdf', '')}.json"
    )
    if DEVELOPMENT_MODE and cache_file.exists():
        print(f"Loading cached resume data from {cache_file}")
        return JSONResume(**json.loads(cache_file.read_text()))

    resume = screening.parse_resume(pdf_path)
    if resume is not None and DEVELOPMENT_MODE:
        cache_file.parent.mkdir(exist_ok=True)
        cache_file.write_text(
            json.dumps(resume.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return resume


def _cached_enrich(resume: JSONResume, preset, pdf_path: str) -> dict:
    """GitHub enrichment with the upstream dev-mode cache, gated by preset."""
    if not preset.enrichments.github:
        return {}
    cache_file = Path(
        f"cache/githubcache_{os.path.basename(pdf_path).replace('.pdf', '')}.json"
    )
    if DEVELOPMENT_MODE and cache_file.exists():
        print(f"Loading cached GitHub data from {cache_file}")
        return json.loads(cache_file.read_text())

    github_data = screening.enrich(resume, preset)
    if DEVELOPMENT_MODE:
        cache_file.parent.mkdir(exist_ok=True)
        cache_file.write_text(
            json.dumps(github_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return github_data


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.cli",
        description="Score a resume PDF against a role preset.",
    )
    parser.add_argument("pdf_path", help="Path to the resume PDF")
    parser.add_argument(
        "--preset",
        default="software-engineer",
        choices=sorted(PRESETS_BY_ID),
        help="Role preset to score against (default: software-engineer)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model to use (default from env: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full result as JSON instead of the readable report",
    )
    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"Error: File '{args.pdf_path}' does not exist.")
        return 1

    preset = get_preset(args.preset)

    resume = _cached_parse(args.pdf_path)
    if resume is None:
        print("Error: could not extract resume data from the PDF.")
        return 1

    github_data = _cached_enrich(resume, preset, args.pdf_path)
    result = screening.screen_parsed(
        resume, preset, github_data, model_name=args.model
    )

    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        print_result(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
