# scorebot — frontend design brief

## What it is

scorebot is an internal resume-screening tool for a small startup. A team member
drops one or more candidate resume PDFs in, picks a role preset (e.g. "Software Engineer"), and the app scores each resume 0–100 against that role's
weighted rubric — with cited evidence per dimension, key strengths, concerns, and
a one-line verdict. It is a **first-pass triage aid**: it orders the pile and
surfaces talking points; a human still reads every resume. It must never feel
like an auto-rejection machine.

## Who uses it

1–3 engineers today, the whole (small) team soon. Technical and non-technical
users. Desktop browser is the primary context (someone at their laptop working
through applications); responsive down to tablet is nice, mobile is not a priority.

## Feel

Clean, fast, scannable internal tool — closer to Linear/Vercel dashboard than to
a consumer app. The name "scorebot" can carry a light, friendly robot/scoring
motif (e.g. in the logo, empty states, loading moments) but the results
themselves are serious content about real people — keep the playfulness out of
the candidate data. Light mode required; dark mode welcome if cheap.

## Technical frame (fixed, don't fight it)

- React + Vite SPA served by the backend — client-side routing, two main views.
- Talks to a REST API (shapes below). Screening is **asynchronous**: submit
  returns a job id; the client polls ~every 2s. A job takes **1–3 minutes**
  (free-tier LLM rate limits), passing through stages:
  `queued → parsing → enriching (engineering preset only) → scoring → done | failed`.
- **No auth. No history.** Results live in server memory and are lost on
  restart/redeploy. The UI must communicate this honestly (e.g. a quiet
  persistent note: "Results last until the server restarts — copy what you need")
  without being alarmist.
- Uploaded PDFs are never stored; there is no "view original resume" feature.

## View 1: Screen (default view)

The core workflow: **drop a pile → watch it sort itself → read the details**.

- **Preset picker**: choose the role before/while dropping files. Show each
  preset's name; a compact peek at its dimensions+weights is a plus.
- **Drop zone**: drag-and-drop multiple PDFs (also click-to-browse). PDF-only,
  max 10MB each — reject others inline with a clear reason.
- **Results table** (the heart of the app): one row per screening in this
  session. Columns roughly: candidate name (falls back to filename until parsed),
  preset, status/stage, **overall score**, one-line verdict. Rows appear
  immediately on drop and update live as stages progress; when a job completes,
  the row gets its score and the table can **sort by score** so the pile orders
  itself. In-progress rows need a clear stage indicator ("parsing…",
  "scoring…"); failures show inline with the error and don't block other rows.
  Mixed-preset sessions are allowed — make it visible which preset scored which
  row (scores across different presets aren't comparable; a subtle cue matters).
- **Detail view** (click a row; drawer or panel — designer's call):
  - Overall score, prominent, with the verdict sentence.
  - Per-dimension breakdown: name, score 0–10, weight (%), and the cited
    evidence text. Evidence is the product's credibility — give it room; it's
    1–3 sentences per dimension quoting the resume.
  - Key strengths (1–5 bullets) and concerns (0–3 bullets).
  - A small note of which rubric version scored this (the result carries a full
    rubric snapshot, so the data is present).
- **Empty state**: first-run moment; sell the workflow in one line ("Drop
  resumes, pick a role, get a ranked pile").

## View 2: Presets

Where the team tunes scoring criteria — the "easily configurable" promise.

- **Preset list**: name, role, dimension count, enrichment badge (e.g. "GitHub
  analysis on"), edit/delete. Three presets ship by default: Founding Software
  Engineer, Business Development Intern, Marketing Intern.
- **Preset editor** (create + edit):
  - Name, role description (2–4 sentence textarea — this text is read by the AI).
  - **Dimensions list** (1–8 typical): each has a display name, a weight, and a
    "guidance" textarea describing what good evidence looks like (also read by
    the AI — expect a paragraph). Add/remove/reorder dimensions.
  - **Weights**: any positive numbers, normalized server-side — but the UI
    should show live "% of overall score" per dimension so people understand
    what they're doing. A sums-to-100 helper is nice, not required.
  - Enrichment toggle(s): currently one — "GitHub analysis" (fetches and
    classifies the candidate's repos; only meaningful for engineering roles).
    Designed as a list that will grow.
  - Deleting asks for confirmation; editing warns lightly that past scores used
    the old rubric (results snapshot their rubric, so nothing breaks).
- Validation errors come from the API (duplicate ids, empty guidance, zero
  weights) — design inline error presentation.

## API shapes (abbreviated, real)

`POST /api/screenings` (multipart: `file`, `preset_id`) → `202 {"id": "...", "status": "queued", ...}`

`GET /api/screenings/{id}` →
```json
{
  "id": "ae4149c9...", "filename": "JaneDoe.pdf", "preset_id": "bd-intern",
  "status": "done", "error": null,
  "result": {
    "candidate_name": "Jane Doe",
    "preset_name": "Business Development Intern",
    "overall_score": 36.0,
    "verdict": "Strong initiative, but no direct sales or communication evidence.",
    "dimensions": [
      {"key": "communication", "name": "Communication & Persuasion",
       "weight": 0.3, "score": 2,
       "evidence": "The resume mentions 'maintaining a client-facing CRM' but no direct communication or persuasion work."}
    ],
    "key_strengths": ["Strong technical initiative..."],
    "concerns": ["No customer-facing experience..."],
    "rubric_snapshot": { "...full preset as scored..." : "" }
  }
}
```

`GET /api/presets` → array of:
```json
{
  "id": "bd-intern", "name": "Business Development Intern",
  "role_description": "An intern who will do outbound outreach...",
  "enrichments": {"github": false},
  "dimensions": [
    {"key": "communication", "name": "Communication & Persuasion",
     "weight": 30, "guidance": "Evidence of communicating and persuading: pitch competitions, ..."}
  ]
}
```

## Moments that need design attention

- A 1–3 minute wait per resume with visible stages — make waiting feel alive,
  not broken (per-row stage progress; the pile keeps sorting as results land).
- A failed job among successful ones (bad PDF, rate-limit exhaustion).
- Score presentation that invites reading the evidence rather than worshipping
  the number (this is a triage aid; 62 vs 58 is not a meaningful difference).
- The ephemerality notice (results don't survive restarts) — honest but calm.
- Fairness footnote worth surfacing somewhere unobtrusive: scoring ignores
  name, gender, school, GPA, and location by design.

## Out of scope (don't design for it yet)

Login/accounts, screening history across sessions, side-by-side candidate
comparison view, PDF preview, DOCX uploads, multi-tenant/public use, mobile-first
layouts.
