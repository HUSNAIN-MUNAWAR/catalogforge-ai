from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from ..models import AuditEvent, PublicationAttempt, PublicationDestination, PublicationJob, SyncLog


def publish_mock(
    db: Session,
    organization_id: str,
    destination: PublicationDestination,
    product_ids: list[str],
    idempotency_key: str | None = None,
    mode: str = "Publish",
    change_set_id: str | None = None,
) -> PublicationJob:
    key = idempotency_key or f"cf-pub-{uuid4()}"
    existing = db.query(PublicationJob).filter(PublicationJob.idempotency_key == key).first()
    if existing:
        return existing
    is_dry_run = mode in {"Dry run", "Validate only"}
    status = "Completed" if not is_dry_run else "Validated"
    job = PublicationJob(
        organization_id=organization_id,
        destination_id=destination.id,
        status=status,
        item_count=max(1, len(product_ids)),
        idempotency_key=key,
        product_ids={"items": product_ids},
        mode=mode,
        dry_run=is_dry_run,
        change_set_id=change_set_id,
    )
    db.add(job)
    db.flush()
    db.add(PublicationAttempt(publication_job_id=job.id, attempt_number=1, status=status, response={"mock": True, "verified": True, "mode": mode}))
    message = (
        f"Mock destination validation completed for {job.item_count} records; no external destination was changed."
        if is_dry_run
        else f"Mock connector verified delivery of {job.item_count} records with idempotency key {key}."
    )
    db.add(SyncLog(publication_job_id=job.id, message=message, level="info"))
    db.add(AuditEvent(organization_id=organization_id, actor="system@catalogforge.demo", action="publication.completed" if not is_dry_run else "publication.validated", entity_type="publication_job", entity_id=job.id, payload={"mock": True, "items": job.item_count, "idempotency_key": key, "mode": mode}))
    db.commit()
    db.refresh(job)
    return job


def retry_mock(db: Session, job: PublicationJob, actor: str) -> PublicationJob:
    next_attempt = db.query(PublicationAttempt).filter(PublicationAttempt.publication_job_id == job.id).count() + 1
    job.status = "Completed"
    db.add(PublicationAttempt(publication_job_id=job.id, attempt_number=next_attempt, status="Completed", response={"mock": True, "verified": True, "retry": True}))
    db.add(SyncLog(publication_job_id=job.id, message="Retry succeeded through the mock destination; delivery state was verified by the simulated connector.", level="info"))
    db.add(AuditEvent(organization_id=job.organization_id, actor=actor, action="publication.retried", entity_type="publication_job", entity_id=job.id, payload={"attempt": next_attempt, "mock": True}))
    db.commit()
    db.refresh(job)
    return job
