"""Khởi tạo bộ lập lịch chạy nền (APScheduler)."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings

scheduler = AsyncIOScheduler(timezone="UTC")


def start_scheduler() -> None:
    from app.jobs.session_jobs import run_session_jobs

    scheduler.add_job(
        run_session_jobs,
        "interval",
        seconds=get_settings().scheduler_interval_seconds,
        id="session_jobs",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.start()


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
