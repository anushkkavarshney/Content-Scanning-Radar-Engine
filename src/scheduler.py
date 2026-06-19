from apscheduler.schedulers.background import BackgroundScheduler
import os
from .trend_engine import generate_trends
import logging

logger = logging.getLogger("trend_scheduler")

sched = None

def start_scheduler():
    global sched
    if sched:
        return
    sched = BackgroundScheduler()
    # default: run every hour
    interval_minutes = int(os.getenv('SCHEDULE_MINUTES', '60'))
    sched.add_job(generate_trends, 'interval', minutes=interval_minutes, id='generate_trends')
    sched.start()
    logger.info(f"Scheduler started: generate_trends every {interval_minutes} minutes")
