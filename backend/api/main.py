"""
scorebot API.

Run locally:
    docker compose up -d postgres
    .venv/bin/uvicorn backend.api.main:app --reload

Postgres stores presets only; screening jobs and results are in-memory and
vanish on restart (stateless v1). In Phase 3 this app also serves the built
React SPA.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from ..pipeline.presets import Preset
from .db import Base, PresetRow, make_engine, make_session_factory, seed_missing_presets
from .jobs import InMemoryScreeningStore, JobStatus, ScreeningJob, ScreeningRunner
from .ratelimit import RateLimits, SlidingWindowLimiter, client_ip

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 10 * 1024 * 1024


class ScreeningJobOut(BaseModel):
    """What the UI polls: job status plus the result once done."""

    id: str
    filename: str
    preset_id: str
    status: JobStatus
    error: Optional[str] = None
    result: Optional[dict] = None

    @classmethod
    def from_job(cls, job: ScreeningJob) -> "ScreeningJobOut":
        return cls(
            id=job.id,
            filename=job.filename,
            preset_id=job.preset_id,
            status=job.status,
            error=job.error,
            result=job.result.model_dump() if job.result else None,
        )


def _rate_limited(retry_after: int, what: str) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(retry_after)},
        content={"detail": f"{what} Try again in about {retry_after}s."},
    )


def create_app(database_url: str = None, rate_limits: RateLimits = None) -> FastAPI:
    engine = make_engine(database_url)
    session_factory = make_session_factory(engine)
    limits = rate_limits or RateLimits()
    api_limiter = SlidingWindowLimiter(limits.api_per_minute, 60)
    screening_ip_limiter = SlidingWindowLimiter(limits.screenings_per_hour_per_ip, 3600)
    screening_global_limiter = SlidingWindowLimiter(limits.screenings_per_hour_global, 3600)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        with session_factory() as session:
            inserted = seed_missing_presets(session)
            if inserted:
                logger.info(f"Seeded {inserted} starter presets")
        yield
        app.state.runner.shutdown()

    app = FastAPI(title="scorebot", lifespan=lifespan)
    app.state.store = InMemoryScreeningStore()
    app.state.runner = ScreeningRunner(app.state.store)

    @app.middleware("http")
    async def api_rate_limit(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            allowed, retry_after = api_limiter.allow(client_ip(request))
            if not allowed:
                return _rate_limited(retry_after, "Too many requests.")
        return await call_next(request)

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        # Log the traceback, hand the client something calm and non-leaky.
        logger.exception(f"Unhandled error on {request.method} {request.url.path}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong on the server. It was logged — try again."},
        )

    def get_db():
        with session_factory() as session:
            yield session

    def load_preset_row(preset_id: str, db: Session) -> PresetRow:
        row = db.get(PresetRow, preset_id)
        if row is None or not row.active:
            raise HTTPException(404, f"Preset '{preset_id}' not found")
        return row

    # ---- health ----

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    # ---- presets ----

    @app.get("/api/presets", response_model=List[Preset])
    def list_presets(db: Session = Depends(get_db)):
        rows = (
            db.query(PresetRow)
            .filter(PresetRow.active)
            .order_by(PresetRow.created_at)
            .all()
        )
        return [Preset(**row.data) for row in rows]

    @app.get("/api/presets/{preset_id}", response_model=Preset)
    def get_preset(preset_id: str, db: Session = Depends(get_db)):
        return Preset(**load_preset_row(preset_id, db).data)

    @app.post("/api/presets", response_model=Preset, status_code=201)
    def create_preset(preset: Preset, db: Session = Depends(get_db)):
        existing = db.get(PresetRow, preset.id)
        if existing is not None and existing.active:
            raise HTTPException(409, f"Preset '{preset.id}' already exists")
        if existing is not None:  # revive a soft-deleted id
            existing.name = preset.name
            existing.data = preset.model_dump()
            existing.active = True
        else:
            db.add(
                PresetRow(id=preset.id, name=preset.name, data=preset.model_dump())
            )
        db.commit()
        return preset

    @app.put("/api/presets/{preset_id}", response_model=Preset)
    def update_preset(preset_id: str, preset: Preset, db: Session = Depends(get_db)):
        if preset.id != preset_id:
            raise HTTPException(422, "Preset id in body must match the URL")
        row = load_preset_row(preset_id, db)
        row.name = preset.name
        row.data = preset.model_dump()
        db.commit()
        return preset

    @app.delete("/api/presets/{preset_id}", status_code=204)
    def delete_preset(preset_id: str, db: Session = Depends(get_db)):
        row = load_preset_row(preset_id, db)
        row.active = False  # soft delete: old results may reference the id
        db.commit()

    # ---- screenings ----

    @app.post("/api/screenings", response_model=ScreeningJobOut, status_code=202)
    async def create_screening(
        request: Request,
        file: UploadFile = File(...),
        preset_id: str = Form(...),
        db: Session = Depends(get_db),
    ):
        # Screenings spend LLM quota — they get their own, tighter budgets.
        allowed, retry_after = screening_ip_limiter.allow(client_ip(request))
        if not allowed:
            return _rate_limited(retry_after, "You've submitted a lot of resumes this hour.")
        allowed, retry_after = screening_global_limiter.allow("global")
        if not allowed:
            return _rate_limited(
                retry_after, "The team's hourly screening budget is used up."
            )

        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(400, "Only PDF resumes are supported")
        # read one byte past the cap instead of the whole upload, so an
        # oversized file is rejected without buffering it all in memory
        pdf_bytes = await file.read(MAX_PDF_BYTES + 1)
        if len(pdf_bytes) > MAX_PDF_BYTES:
            raise HTTPException(413, "PDF larger than 10MB")
        if not pdf_bytes.startswith(b"%PDF"):
            raise HTTPException(400, "File does not look like a PDF")

        try:
            preset = Preset(**load_preset_row(preset_id, db).data)
        except ValidationError:
            raise HTTPException(500, f"Stored preset '{preset_id}' is invalid")

        job = app.state.runner.submit(file.filename, pdf_bytes, preset)
        return ScreeningJobOut.from_job(job)

    @app.get("/api/screenings", response_model=List[ScreeningJobOut])
    def list_screenings():
        return [ScreeningJobOut.from_job(j) for j in app.state.store.list()]

    @app.get("/api/screenings/{job_id}", response_model=ScreeningJobOut)
    def get_screening(job_id: str):
        job = app.state.store.get(job_id)
        if job is None:
            raise HTTPException(404, "Screening not found (results are in-memory and cleared on restart)")
        return ScreeningJobOut.from_job(job)

    # ---- SPA (built by `pnpm build` in frontend/; absent in dev, where vite serves it) ----

    spa_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if spa_dist.is_dir():
        app.mount("/", StaticFiles(directory=spa_dist, html=True), name="spa")

    return app


app = create_app()
