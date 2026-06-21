"""
Background scheduler for proactive outbound campaigns.
Uses APScheduler — install: pip install apscheduler

Run standalone: python -m backend.agents.scheduler
Or import and start in FastAPI lifespan.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging

log = logging.getLogger(__name__)


def start_scheduler():
    from backend.agents.outbound import (
        run_delay_notification_campaign,
        run_ticket_followup_campaign,
    )

    scheduler = BackgroundScheduler()

    # Check for delayed shipments every 4 hours
    scheduler.add_job(
        run_delay_notification_campaign,
        trigger=IntervalTrigger(hours=1),
        id="delay_notifications",
        name="Delay Notification Campaign",
        replace_existing=True,
    )

    # Follow up on stale tickets every 6 hours
    scheduler.add_job(
        run_ticket_followup_campaign,
        trigger=IntervalTrigger(hours=1),
        id="ticket_followups",
        name="Ticket Followup Campaign",
        replace_existing=True,
    )

    scheduler.start()
    log.info("Background scheduler started.")
    return scheduler


if __name__ == "__main__":
    import time
    logging.basicConfig(level=logging.INFO)
    scheduler = start_scheduler()
    print("Scheduler running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("Scheduler stopped.")
