# scorebot

Resume screening for busy founders: drop a candidate's PDF resume in, pick a role
preset, and get a 0–100 score with per-dimension evidence, strengths, and concerns —
a **first-pass triage aid**, not an auto-rejector. A human still reads every resume.

Built on top of [HackerRank's open-source hiring-agent](https://github.com/hackerrank/hiring-agent)
(MIT) — its PDF→JSON-Resume extraction pipeline, GitHub enrichment, and
LLM evaluation loop form the core of `backend/pipeline/`. See [LICENSE](LICENSE).

## Status

Phase 2 — the API is live: async screening jobs plus Postgres-backed, editable presets.

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Repo bootstrap, package layout, CLI parity | ✅ |
| 1 | Preset-driven rubrics (weighted dimensions, normalized to 100) + tests | ✅ |
| 2 | FastAPI + async screening jobs + Postgres-backed presets | ✅ |
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
.venv/bin/python -m backend.cli path/to/resume.pdf --preset software-engineer
.venv/bin/python -m backend.cli path/to/resume.pdf --preset bd-intern --json
```

Presets (`backend/pipeline/presets.py`): `software-engineer` (GitHub enrichment on),
`bd-intern`, `marketing-intern`. Each preset is a set of weighted rubric dimensions;
the LLM scores each dimension 0–10 with evidence, and the weighted overall score
(0–100) is computed in code. Results include strengths, concerns, a one-line
verdict, and a snapshot of the rubric used.

With `DEVELOPMENT_MODE = True` (see `backend/pipeline/config.py`), the parse and
GitHub steps are cached in `cache/`, so re-scoring with a different preset only
spends one LLM call.

Tests: `.venv/bin/python -m pytest backend/tests`

## API

```bash
docker compose up -d postgres          # presets DB on localhost:5434
.venv/bin/uvicorn backend.api.main:app --reload
```

- `POST /api/screenings` (multipart `file` PDF + `preset_id` form field) → `202` with a job id
- `GET /api/screenings/{id}` — poll status: `queued → parsing → enriching → scoring → done|failed`, result included when done
- `GET /api/screenings` — all jobs, newest first
- `GET|POST /api/presets`, `GET|PUT|DELETE /api/presets/{id}` — preset CRUD (delete is a soft delete)
- `GET /api/health`

Postgres stores **presets only**. Screening jobs, results, and uploaded PDFs are
never persisted: PDFs exist on disk only during parsing, and results live in
process memory until restart (stateless v1 — auth and result persistence arrive
together in a later phase).

## Attribution

The extraction/evaluation pipeline originates from
[hackerrank/hiring-agent](https://github.com/hackerrank/hiring-agent),
Copyright (c) 2025 HackerRank, MIT License. This project restructures it into a
package and builds a web application around it.
