"""Acceso a datos de trabajos. Cada función abre y cierra su propia sesión (es seguro
llamarlas desde cualquier hilo)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, delete, select

from setid.community import Hint
from setid.db.tables import CommunityHint, Job, JobStatus, TrackEntry, utcnow
from setid.jobs.views import entry_from_row, hint_from_row, row_from_entry, row_from_hint
from setid.models import TracklistEntry


class JobRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def add(self, job: Job) -> Job:
        with Session(self.engine) as session:
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    def get(self, job_id: int) -> Job | None:
        with Session(self.engine) as session:
            return session.get(Job, job_id)

    def update(self, job_id: int, **fields: Any) -> Job | None:
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                return None
            for name, value in fields.items():
                setattr(job, name, value)
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    def list_recent(self, limit: int = 50) -> list[Job]:
        with Session(self.engine) as session:
            query = select(Job).order_by(col(Job.created_at).desc(), col(Job.id).desc())
            return list(session.exec(query.limit(limit)))

    def queued_ids(self) -> list[int]:
        with Session(self.engine) as session:
            query = select(Job.id).where(Job.status == JobStatus.QUEUED).order_by(col(Job.id))
            return [i for i in session.exec(query) if i is not None]

    def count_queued(self) -> int:
        return len(self.queued_ids())

    def mark_interrupted(self) -> int:
        """Al arrancar: los trabajos que estaban en marcha cuando se cerró la app fallan."""
        with Session(self.engine) as session:
            active = [s for s in JobStatus if s.is_active]
            jobs = list(session.exec(select(Job).where(col(Job.status).in_(active))))
            for job in jobs:
                job.status = JobStatus.FAILED
                job.error = "Interrumpido: la app se cerró mientras se procesaba."
                job.finished_at = utcnow()
                session.add(job)
            session.commit()
            return len(jobs)

    def find_cached(self, canonical_id: str, exclude_id: int) -> Job | None:
        """El último trabajo terminado con éxito para la misma fuente (que no sea a su vez
        una copia de caché, para no encadenar copias)."""
        with Session(self.engine) as session:
            query = (
                select(Job)
                .where(
                    Job.canonical_id == canonical_id,
                    Job.status == JobStatus.DONE,
                    Job.id != exclude_id,
                    col(Job.cached_from_id).is_(None),
                )
                .order_by(col(Job.finished_at).desc())
            )
            return session.exec(query).first()

    def entries(self, job_id: int) -> list[TracklistEntry]:
        with Session(self.engine) as session:
            query = (
                select(TrackEntry)
                .where(TrackEntry.job_id == job_id)
                .order_by(col(TrackEntry.position))
            )
            return [entry_from_row(r) for r in session.exec(query)]

    def replace_entries(self, job_id: int, entries: list[TracklistEntry]) -> None:
        with Session(self.engine) as session:
            session.exec(delete(TrackEntry).where(col(TrackEntry.job_id) == job_id))
            session.add_all(row_from_entry(job_id, e) for e in entries)
            session.commit()

    def delete(self, job_id: int) -> bool:
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                return False
            session.delete(job)
            session.commit()
            return True

    def hints(self, job_id: int) -> list[Hint]:
        with Session(self.engine) as session:
            query = (
                select(CommunityHint)
                .where(CommunityHint.job_id == job_id)
                .order_by(col(CommunityHint.id))
            )
            return [hint_from_row(r) for r in session.exec(query)]

    def replace_hints(self, job_id: int, hints: list[Hint]) -> None:
        with Session(self.engine) as session:
            session.exec(delete(CommunityHint).where(col(CommunityHint.job_id) == job_id))
            session.add_all(row_from_hint(job_id, h) for h in hints)
            session.commit()
