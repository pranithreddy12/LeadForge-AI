from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery = Celery(
    "leadforge",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.discovery",
        "app.workers.signals",
        "app.workers.scoring",
        "app.workers.validation",
        "app.workers.outreach",
        "app.workers.workflows",
        "app.workers.embeddings",
        "app.workers.enrichment",
        "app.workers.research",
        "app.workers.inbox",
        "app.workers.reclassify",
    ],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=200,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_default_queue="default",
    task_routes={
        "app.workers.discovery.*": {"queue": "discovery"},
        "app.workers.scoring.*": {"queue": "scoring"},
        "app.workers.outreach.*": {"queue": "outreach"},
        "app.workers.embeddings.*": {"queue": "embeddings"},
        "app.workers.enrichment.*": {"queue": "discovery"},
        "app.workers.research.*": {"queue": "discovery"},
    },
)

# ---- Beat schedule ----
celery.conf.beat_schedule = {
    "run-due-workflows-every-5m": {
        "task": "app.workers.workflows.run_due_workflows",
        "schedule": crontab(minute="*/5"),
    },
    "refresh-signals-hourly": {
        "task": "app.workers.signals.refresh_active_companies",
        "schedule": crontab(minute="7"),
    },
    "embed-new-rows-every-10m": {
        "task": "app.workers.embeddings.embed_pending_rows",
        "schedule": crontab(minute="*/10"),
    },
    "enrich-pending-every-15m": {
        "task": "app.workers.enrichment.enrich_pending",
        "schedule": crontab(minute="*/15"),
    },
    "poll-email-replies-every-5m": {
        "task": "app.workers.inbox.poll_replies",
        "schedule": crontab(minute="*/5"),
    },
    "send-scheduled-emails-hourly": {
        "task": "app.workers.outreach.send_scheduled_emails",
        "schedule": crontab(minute="23"),
    },
    "draft-followups-daily": {
        "task": "app.workers.outreach.draft_followups",
        "schedule": crontab(hour="8", minute="30"),
    },
    "retry-held-unknowns-hourly": {
        "task": "app.workers.reclassify.retry_held_unknowns",
        "schedule": crontab(minute="17"),
    },
    # Fresh-signal re-scan of uncontacted local leads (rating drift, booking widget
    # appearing, hours changes). Weekly - each scan refetches Place Details per lead,
    # so keep it infrequent. Sends nothing.
    "rescan-local-signals-weekly": {
        "task": "app.workers.signals.rescan_local_signals",
        "schedule": crontab(day_of_week="mon", hour="6", minute="41"),
    },
}
