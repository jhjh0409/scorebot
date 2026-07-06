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
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from ..pipeline.presets import Preset
from .db import Base, PresetRow, make_engine, make_session_factory, seed_presets_if_empty
from .jobs import InMemoryScreeningStore, JobStatus, ScreeningJob, ScreeningRunner

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


def create_app(database_url: str = None) -> FastAPI:
    engine = make_engine(database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        with session_factory() as session:
            inserted = seed_presets_if_empty(session)
            if inserted:
                logger.info(f"Seeded {inserted} starter presets")
        yield
        app.state.runner.shutdown()

    app = FastAPI(title="scorebot", lifespan=lifespan)
    app.state.store = InMemoryScreeningStore()
    app.state.runner = ScreeningRunner(app.state.store)

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
        file: UploadFile = File(...),
        preset_id: str = Form(...),
        db: Session = Depends(get_db),
    ):
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(400, "Only PDF resumes are supported")
        pdf_bytes = await file.read()
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

    return app


app = create_app()
