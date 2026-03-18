"""Scheduled tasks for automated backup and Google Sheets sync."""

import logging
import os
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

from app.config import get_settings
from app.database import SessionLocal
from app.models import User, UserSettings
from app.google_drive import upload_backup

logger = logging.getLogger("askesis.scheduler")

scheduler = BackgroundScheduler()


def run_scheduled_backup():
    """Run backup for all users with Google Drive configured."""
    logger.info("Starting scheduled backup...")

    settings = get_settings()
    db_url = settings.database_url

    # Only support SQLite backups
    if not db_url.startswith("sqlite"):
        logger.warning("Scheduled backup only supports SQLite databases")
        return

    db_path = db_url.replace("sqlite:///", "")

    if not os.path.exists(db_path):
        logger.error(f"Database file not found: {db_path}")
        return

    # Read database content once
    try:
        with open(db_path, "rb") as f:
            db_content = f.read()
    except Exception as e:
        logger.error(f"Failed to read database file: {e}")
        return

    # Get all users with refresh tokens
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.google_refresh_token.isnot(None)).all()

        if not users:
            logger.info("No users with Google Drive access configured")
            return

        success_count = 0
        for user in users:
            try:
                # Get user's parent folder setting
                user_settings = (
                    db.query(UserSettings)
                    .filter(UserSettings.user_id == user.id)
                    .first()
                )
                parent_folder_id = (
                    user_settings.drive_parent_folder_id if user_settings else None
                )

                # Upload backup for this user
                file_id = upload_backup(
                    refresh_token=user.google_refresh_token,
                    file_content=db_content,
                    filename="askesis_backup.db",
                    parent_folder_id=parent_folder_id,
                )
                logger.info(f"Backup successful for user {user.email}: {file_id}")
                success_count += 1

            except Exception as e:
                logger.error(f"Backup failed for user {user.email}: {e}")

        logger.info(f"Scheduled backup completed: {success_count}/{len(users)} users")

    finally:
        db.close()


def run_scheduled_gsheet_sync():
    """Run Google Sheets sync for users with auto-sync enabled."""
    from app.google_sheets import sync_to_sheet

    logger.info("Starting scheduled Google Sheets sync...")

    db = SessionLocal()
    try:
        # Find users with auto-sync enabled (have sheet_id and interval set)
        results = (
            db.query(User, UserSettings)
            .join(UserSettings, UserSettings.user_id == User.id)
            .filter(
                User.google_refresh_token.isnot(None),
                UserSettings.google_sheet_id.isnot(None),
                UserSettings.gsheet_sync_interval_hours.isnot(None),
            )
            .all()
        )

        if not results:
            logger.info("No users with Google Sheets auto-sync configured")
            return

        success_count = 0
        for user, user_settings in results:
            # Check if enough time has passed since last sync
            interval = timedelta(hours=user_settings.gsheet_sync_interval_hours)
            if user_settings.last_gsheet_sync:
                next_sync = user_settings.last_gsheet_sync + interval
                if datetime.utcnow() < next_sync:
                    logger.debug(
                        f"Skipping sync for {user.email}: next sync at {next_sync}"
                    )
                    continue

            try:
                result = sync_to_sheet(
                    sheet_id=user_settings.google_sheet_id,
                    user=user,
                    db=db,
                )
                # Update last sync timestamp
                user_settings.last_gsheet_sync = datetime.utcnow()
                db.commit()
                logger.info(f"Sheets sync successful for {user.email}: {result}")
                success_count += 1
            except Exception as e:
                logger.error(f"Sheets sync failed for {user.email}: {e}")

        logger.info(
            f"Scheduled Sheets sync completed: {success_count}/{len(results)} users"
        )

    finally:
        db.close()


def start_scheduler():
    """Start the background scheduler with daily backup and hourly Sheets sync check."""
    pst = pytz.timezone("America/Los_Angeles")

    # Schedule daily backup at 1am PST
    scheduler.add_job(
        run_scheduled_backup,
        CronTrigger(hour=1, minute=0, timezone=pst),
        id="daily_backup",
        name="Daily database backup to Google Drive",
        replace_existing=True,
    )

    # Check for Sheets syncs every hour (per-user intervals checked inside)
    scheduler.add_job(
        run_scheduled_gsheet_sync,
        IntervalTrigger(hours=1),
        id="gsheet_sync",
        name="Google Sheets auto-sync check",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started: daily backup at 1:00 AM PST, Sheets sync check hourly"
    )


def stop_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
