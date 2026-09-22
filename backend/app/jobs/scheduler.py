"""In-process scheduler for the deadline-reminder job.

APScheduler in the API process, not Celery: the only job is a periodic scan
that writes notifications, and a broker would be infrastructure (and cost)
for no benefit. It is off unless `ENABLE_SCHEDULER=true`, so tests and CLI
runs never start a background thread, and with several web workers only the
process(es) with it enabled will run it -- the job is idempotent either way.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session, sessionmaker

from app.jobs.reminders import send_deadline_reminders

logger = logging.getLogger(__name__)


def run_reminders(session_factory: Callable[[], Session]) -> None:
    """One reminder pass, with its own session and its own failure domain."""
    session = session_factory()
    try:
        sent = send_deadline_reminders(session)
        if sent:
            logger.info("deadline reminders sent: %d", sent)
    except Exception:  # noqa: BLE001 - a scheduled job must not kill the thread
        session.rollback()
        logger.exception("deadline reminder job failed")
    finally:
        session.close()


def start_scheduler(
    session_factory: sessionmaker[Session], *, interval_minutes: int
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_reminders,
        trigger="interval",
        minutes=interval_minutes,
        args=[session_factory],
        id="deadline-reminders",
        # A missed run is harmless: the next one covers the same window.
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    scheduler.start()
    logger.info("deadline reminder scheduler started (every %d min)", interval_minutes)
    return scheduler
