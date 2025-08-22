import os
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_scheduler():
    """Set up the scheduler for digest and notification tasks"""
    scheduler = BlockingScheduler()
    
    # Import here to avoid circular imports
    from services.digest_service import send_daily_digests, send_weekly_digests
    from services.categorization_service import sync_articles
    
    # Schedule daily digest sending (9 AM every day)
    scheduler.add_job(
        func=send_daily_digests,
        trigger=CronTrigger(hour=9, minute=0),
        id='daily_digests',
        name='Send daily digests',
        replace_existing=True
    )
    
    # Schedule weekly digest sending (Monday 9 AM)
    scheduler.add_job(
        func=send_weekly_digests,
        trigger=CronTrigger(day_of_week='mon', hour=9, minute=0),
        id='weekly_digests',
        name='Send weekly digests',
        replace_existing=True
    )
    
    # Schedule article synchronization (every 2 hours)
    scheduler.add_job(
        func=sync_articles,
        trigger=CronTrigger(minute=0, second=0),  # Every hour at the top of the hour
        id='sync_articles',
        name='Sync articles from files',
        replace_existing=True
    )
    
    # Log scheduled jobs
    logger.info("Scheduled jobs:")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name} (ID: {job.id}) - Next run: {job.next_run_time}")
    
    return scheduler

def run_scheduler():
    """Run the scheduler"""
    logger.info("Starting digest scheduler...")
    
    # Initialize database first
    from database import init_database
    init_database()
    
    scheduler = setup_scheduler()
    
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
        scheduler.shutdown()
    except Exception as e:
        logger.error(f"Scheduler error: {e}")
        scheduler.shutdown()

if __name__ == "__main__":
    run_scheduler()