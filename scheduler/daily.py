"""
R&V IPC — Scheduler.

Configura las corridas automáticas:
- Diarias: 6am, 12pm, 8pm (collectors de alta frecuencia)
- Semanales: lunes 7am (cálculo de índice semanal)
- Mensuales: día 1 a las 8am (cálculo de índice mensual + comparación INDEC)
"""
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date
import structlog

from engine.pipeline import run_pipeline, run_weekly_pipeline, run_monthly_pipeline

log = structlog.get_logger()


def job_daily_collection():
    """Daily price collection."""
    log.info("scheduler.daily_run")
    result = run_pipeline(fecha=date.today(), periodo_tipo="diario")
    log.info("scheduler.daily_done", nivel_general=result.get("nivel_general"))


def job_weekly_index():
    """Weekly index calculation."""
    log.info("scheduler.weekly_run")
    result = run_weekly_pipeline(fecha=date.today())
    log.info("scheduler.weekly_done", nivel_general=result.get("nivel_general"))


def job_monthly_index():
    """Monthly index + INDEC comparison."""
    log.info("scheduler.monthly_run")
    result = run_monthly_pipeline(fecha=date.today())
    log.info("scheduler.monthly_done", nivel_general=result.get("nivel_general"))


def start_scheduler():
    """Start the APScheduler with all configured jobs."""
    scheduler = BlockingScheduler()

    # Daily collection — 3 times per day
    scheduler.add_job(
        job_daily_collection,
        CronTrigger(hour="6,12,20", minute=0),
        id="daily_collection",
        name="Recolección diaria de precios",
    )

    # Weekly index — every Monday at 7am
    scheduler.add_job(
        job_weekly_index,
        CronTrigger(day_of_week="mon", hour=7, minute=0),
        id="weekly_index",
        name="Cálculo de índice semanal R&V",
    )

    # Monthly index — 1st of each month at 8am
    scheduler.add_job(
        job_monthly_index,
        CronTrigger(day=1, hour=8, minute=0),
        id="monthly_index",
        name="Cálculo de índice mensual R&V",
    )

    log.info("scheduler.started", jobs=len(scheduler.get_jobs()))
    scheduler.start()


if __name__ == "__main__":
    start_scheduler()
