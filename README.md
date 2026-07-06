# scorebot

Resume screening for busy founders: drop a candidate's PDF resume in, pick a role
preset, and get a 0–100 score with per-dimension evidence, strengths, and concerns —
a **first-pass triage aid**, not an auto-rejector. A human still reads every resume.

Built on top of [HackerRank's open-source hiring-agent](https://github.com/hackerrank/hiring-agent)
(MIT) — its PDF→JSON-Resume extraction pipeline, GitHub enrichment, and
LLM evaluation loop form the core of `backend/pipeline/`. See [LICENSE](LICENSE).

## Status

Phase 0 — the upstream pipeline restructured into an app layout, CLI-parity preserved.

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Repo bootstrap, package layout, CLI parity | ✅ |
| 1 | Preset-driven rubrics (weighted dimensions, normalized to 100) + tests | — |
| 2 | FastAPI + async screening jobs + Postgres-backed presets | — |
| 3 | React SPA (multi-file drop, live results table, preset editor) | — |
| 4 | Railway deploy | — |

Design decisions (locked): stateless v1 (no auth, no PDF retention, no stored
results), Postgres holds presets/config only, provider-agnostic LLM seam
(Gemini day one), global non-configurable fairness constraints, per-preset
enrichment toggles.

## Layout

```
backend/
  cli.py         # python -m backend.cli <resume.pdf> — upstream score.py behavior
  pipeline/      # PDF extraction, GitHub enrichment, evaluation (from hiring-agent)
    prompts/     # Jinja prompt templates
  api/           # FastAPI app (Phase 2)
  tests/
frontend/        # React SPA (Phase 3)
```

## Setup

Requires Python 3.11 (see `.python-version`). With [uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.11 .venv
uv pip install -p .venv -r requirements.txt
cp .env.example .env   # set LLM_PROVIDER / DEFAULT_MODEL / GEMINI_API_KEY
```

For Gemini (hosted, recommended):

```
LLM_PROVIDER=gemini
DEFAULT_MODEL=gemini-2.5-flash
GEMINI_API_KEY=...
```

Free-tier Gemini keys are rate-limited (~10 req/min); one resume costs ~8 LLM
calls, so expect roughly one resume per minute. Optionally set `GITHUB_TOKEN`
to raise GitHub API rate limits for enrichment.

## Usage

```bash
.venv/bin/python -m backend.cli path/to/resume.pdf
```

Prints per-category scores with evidence, strengths, and areas for improvement.
With `DEVELOPMENT_MODE = True` (see `backend/pipeline/config.py`), extraction and
GitHub results are cached in `cache/` and rows are appended to `resume_evaluations.csv`.

## Attribution

The extraction/evaluation pipeline originates from
[hackerrank/hiring-agent](https://github.com/hackerrank/hiring-agent),
Copyright (c) 2025 HackerRank, MIT License. This project restructures it into a
package and builds a web application around it.
