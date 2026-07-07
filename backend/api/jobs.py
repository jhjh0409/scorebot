"""
Screening jobs: in-memory by design (stateless-v1 decision — no candidate
data at rest). Results live until process restart; the UI says so.

ScreeningStore is the persistence seam: when result persistence lands
(together with auth), a DB-backed store replaces InMemoryScreeningStore
behind the same interface.
"""

import logging
import os
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel

from ..pipeline import screening
from ..pipeline.llm_utils import _is_rate_limit_error
from ..pipeline.presets import Preset

logger = logging.getLogger(__name__)


def classify_error(exc: Exception) -> str:
    """Turn a pipeline exception into a message a non-engineer can act on.
    The raw error is logged; it never reaches the UI."""
    if _is_rate_limit_error(exc):
        return (
            "The AI provider's rate limit was hit — the free-tier quota may be "
            "exhausted for now. Wait a bit (limits reset over time, daily quota "
            "resets at midnight Pacific) and try again."
        )
    text = f"{type(exc).__name__} {exc}".lower()
    if "failed validation" in text or "json" in text:
        return (
            "The AI returned an unusable response even after a retry. "
            "Re-submitting the resume usually fixes this."
        )
    if any(m in text for m in ("timeout", "timed out", "connection", "unreachable", "getaddrinfo")):
        return (
            "A network problem interrupted the screening. "
            "Check connectivity and re-submit the resume."
        )
    if "api key" in text or "unauthorized" in text or "401" in text:
        return "The AI provider rejected the server's API key — check the deployment's credentials."
    return "The screening failed unexpectedly. It was logged; re-submitting the resume may work."

SCREENING_WORKERS = int(os.getenv("SCREENING_WORKERS", "2"))
MAX_JOBS_KEPT = int(os.getenv("MAX_JOBS_KEPT", "200"))


class JobStatus(str, Enum):
    QUEUED = "queued"
    PARSING = "parsing"
    ENRICHING = "enriching"
    SCORING = "scoring"
    DONE = "done"
    FAILED = "failed"


class ScreeningJob(BaseModel):
    id: str
    filename: str
    preset_id: str
    status: JobStatus = JobStatus.QUEUED
    result: Optional[screening.ScreeningResult] = None
    error: Optional[str] = None
    created_at: datetime


class InMemoryScreeningStore:
    """Thread-safe job store; prunes the oldest finished jobs past the cap."""

    def __init__(self, max_jobs: int = MAX_JOBS_KEPT):
        self._jobs: Dict[str, ScreeningJob] = {}
        self._lock = threading.Lock()
        self._max_jobs = max_jobs

    def add(self, job: ScreeningJob) -> None:
        with self._lock:
            self._jobs[job.id] = job
            self._prune_locked()

    def get(self, job_id: str) -> Optional[ScreeningJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> List[ScreeningJob]:
        with self._lock:
            return sorted(
                self._jobs.values(), key=lambda j: j.created_at, reverse=True
            )

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            self._jobs[job_id] = job.model_copy(update=fields)

    def _prune_locked(self) -> None:
        finished = [
            j
            for j in sorted(self._jobs.values(), key=lambda j: j.created_at)
            if j.status in (JobStatus.DONE, JobStatus.FAILED)
        ]
        while len(self._jobs) > self._max_jobs and finished:
            del self._jobs[finished.pop(0).id]


class ScreeningRunner:
    """Runs screening jobs on a small thread pool with stage updates."""

    def __init__(self, store: InMemoryScreeningStore, workers: int = SCREENING_WORKERS):
        self.store = store
        self._executor = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="screening"
        )

    def submit(self, filename: str, pdf_bytes: bytes, preset: Preset) -> ScreeningJob:
        job = ScreeningJob(
            id=uuid.uuid4().hex,
            filename=filename,
            preset_id=preset.id,
            created_at=datetime.now(timezone.utc),
        )
        self.store.add(job)
        self._executor.submit(self._run, job.id, pdf_bytes, preset)
        return job

    def _run(self, job_id: str, pdf_bytes: bytes, preset: Preset) -> None:
        # The PDF exists on disk only for the duration of the parse step —
        # no retention by design.
        try:
            self.store.update(job_id, status=JobStatus.PARSING)
            with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                tmp.write(pdf_bytes)
                tmp.flush()
                resume = screening.parse_resume(tmp.name)
            if resume is None:
                self.store.update(
                    job_id,
                    status=JobStatus.FAILED,
                    error="Could not extract resume data from the PDF.",
                )
                return

            github_data = {}
            if preset.enrichments.github:
                self.store.update(job_id, status=JobStatus.ENRICHING)
                try:
                    github_data = screening.enrich(resume, preset)
                except Exception:
                    # Enrichment is a bonus signal — degrade to scoring the
                    # resume alone rather than failing the whole screening.
                    logger.exception(f"Enrichment failed for job {job_id}; scoring without it")
                    github_data = {}

            self.store.update(job_id, status=JobStatus.SCORING)
            result = screening.screen_parsed(resume, preset, github_data)
            self.store.update(job_id, status=JobStatus.DONE, result=result)
        except Exception as exc:
            logger.exception(f"Screening job {job_id} failed")
            self.store.update(job_id, status=JobStatus.FAILED, error=classify_error(exc))

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
