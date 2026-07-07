# scorebot

Resume screening for busy founders: drop a candidate's PDF resume in, pick a role
preset, and get a 0–100 score with per-dimension evidence, strengths, and concerns —
a **first-pass triage aid**, not an auto-rejector. A human still reads every resume.

Built on top of [HackerRank's open-source hiring-agent](https://github.com/hackerrank/hiring-agent)
(MIT) — its PDF→JSON-Resume extraction pipeline, GitHub enrichment, and
LLM evaluation loop form the core of `backend/pipeline/`. See [LICENSE](LICENSE).

## Status

Phase 5 — hardened: friendly failure messages everywhere, and rate limits guard the LLM quota.

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Repo bootstrap, package layout, CLI parity | ✅ |
| 1 | Preset-driven rubrics (weighted dimensions, normalized to 100) + tests | ✅ |
| 2 | FastAPI + async screening jobs + Postgres-backed presets | ✅ |
| 3 | React SPA (multi-file drop, live results table, preset editor) | ✅ |
| 4 | Dockerfile + Railway deploy | ✅ |
| 5 | Hardening: graceful error handling + API rate limiting | ✅ |

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

### Choosing the LLM

Switching models/providers is a pure env change — set `DEFAULT_MODEL` and the
provider is inferred from the name:

| `DEFAULT_MODEL` | Provider | Key needed |
|---|---|---|
| `gemini-2.5-flash-lite` (default) | Google Gemini | `GEMINI_API_KEY` |
| `claude-sonnet-5` | Anthropic | `ANTHROPIC_API_KEY` |
| `gpt-5.1-mini` | OpenAI | `OPENAI_API_KEY` |
| `gemma3:4b` etc. | local Ollama | — |

`LLM_PROVIDER` (`ollama`/`gemini`/`anthropic`/`openai`) is only consulted for
model ids the prefix rules don't recognize (fine-tunes, gateways). A missing
API key fails loudly at startup of a screening, not silently mid-pipeline.

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

## Web app

```bash
docker compose up -d postgres          # presets DB on localhost:5434
cd frontend && pnpm install && pnpm build && cd ..   # build the SPA once
.venv/bin/uvicorn backend.api.main:app --reload      # serves app + API on :8000
```

Open http://localhost:8000 — drop resume PDFs, pick a role preset, and the
results table fills in live (parsing → GitHub analysis → scoring). Click a row
for the full breakdown: score ring, per-dimension evidence, strengths, and
concerns. The Presets tab edits rubrics (dimensions, weights, guidance,
enrichment toggles) with live weight normalization.

For frontend development: `cd frontend && pnpm dev` (vite on :5173, proxying
/api to :8000). The design source lives in `docs/design/scorebot-A.dc.html`.

## API

- `POST /api/screenings` (multipart `file` PDF + `preset_id` form field) → `202` with a job id
- `GET /api/screenings/{id}` — poll status: `queued → parsing → enriching → scoring → done|failed`, result included when done
- `GET /api/screenings` — all jobs, newest first
- `GET|POST /api/presets`, `GET|PUT|DELETE /api/presets/{id}` — preset CRUD (delete is a soft delete)
- `GET /api/health`

Postgres stores **presets only**. Screening jobs, results, and uploaded PDFs are
never persisted: PDFs exist on disk only during parsing, and results live in
process memory until restart (stateless v1 — auth and result persistence arrive
together in a later phase).

### Rate limits & errors

There is no auth yet, so in-process rate limits are what stop a leaked URL or a
runaway script from burning the LLM quota (env-tunable):

| Variable | Default | Guards |
|----------|---------|--------|
| `API_RATE_LIMIT_PER_MINUTE` | 120 | all `/api/*` requests, per IP |
| `SCREENINGS_PER_HOUR_PER_IP` | 20 | resume submissions, per IP |
| `SCREENINGS_PER_HOUR_GLOBAL` | 60 | resume submissions, whole deployment |

Limited requests get `429` + `Retry-After`, which the UI shows as a friendly
banner. Failed screenings carry a classified, human-readable message (provider
quota exhausted / unusable AI response / network problem / bad credentials) —
raw provider errors are logged server-side, never shown. GitHub enrichment
failures degrade to scoring the resume alone instead of failing the screening,
and if the server restarts mid-screening the UI says so instead of spinning.

## Deploy (Railway)

The [Dockerfile](Dockerfile) builds the SPA and serves everything from one
uvicorn process, honoring Railway's `PORT`.

1. Railway → New Project → **Deploy from GitHub repo** → pick `scorebot`
   (it auto-detects the Dockerfile).
2. Give it a Postgres. On Railway's free plan, use **[Neon](https://neon.tech)'s
   free tier** instead of a Railway database: create a Neon project, copy its
   connection string, and set it as `DATABASE_URL` on the app service.
   Neon's `postgresql://…?sslmode=require` URLs work as-is (the dialect is
   normalized automatically; presets seed on first boot). If your plan does
   include Railway Postgres, a `DATABASE_URL` variable reference works the same.
3. Set the remaining variables on the app service:
   `DEFAULT_MODEL=gemini-2.5-flash-lite` and `GEMINI_API_KEY=…` (or a
   `claude-*`/`gpt-*` model with its key — see "Choosing the LLM"), and
   optionally `GITHUB_TOKEN` (raises GitHub rate limits for enrichment) and
   `LLM_MAX_CONCURRENCY` (default 2).
4. Settings → Networking → **Generate Domain**. Done — `/api/health` should
   return `{"status":"ok"}`.

Local sanity check of the exact image Railway builds:

```bash
docker build -t scorebot .
docker run -p 8000:8000 --env-file .env \
  -e DATABASE_URL=postgres://scorebot:scorebot@host.docker.internal:5434/scorebot scorebot
```

Notes: screening results are in process memory by design, so each deploy/restart
clears them (the UI says so). Keep the service at **1 replica** — jobs and
results live in that process. No auth yet: treat the generated domain as a
private URL and prefer keeping it unshared outside the team until phase 5+.

## Attribution

The extraction/evaluation pipeline originates from
[hackerrank/hiring-agent](https://github.com/hackerrank/hiring-agent),
Copyright (c) 2025 HackerRank, MIT License. This project restructures it into a
package and builds a web application around it.
