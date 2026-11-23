"""Compose the FastAPI app and start the notification dispatcher."""
import asyncio
import logging
import os
import smtplib
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .clubs.repository import CLUBS_SCHEMA, SqliteClubRepository
from .clubs.router import make_router as clubs_router
from .clubs.service import ClubService
from .database import Database
from .events.repository import EVENTS_SCHEMA, SqliteEventRepository
from .events.router import make_router as events_router
from .events.service import EventService
from .notifications.dispatcher import NotificationDispatcher
from .notifications.outbox import NOTIFICATION_SCHEMA, SqliteOutbox
from .notifications.reminders import ReminderJob
from .notifications.router import make_router as notifications_router
from .notifications.sender import (ConsoleSmtp, ConsoleTelegramBotApi, HttpTelegramBotApi,
                                   NotificationSender, SmtpAdapter, TelegramAdapter)
from .notifications.telegram import SqliteTelegramLinks, TelegramLinkPoller, TelegramLinkService
from .registrations.repository import SqliteRegistrationRepository
from .registrations.router import make_router as registrations_router
from .registrations.service import RegistrationService
from .users.access import AccessPolicy
from .users.auth import AUTH_SCHEMA, AuthService
from .users.contacts import UserDirectory
from .users.router import make_auth_router, make_current_user

STATIC = Path(__file__).parent / "static"
logger = logging.getLogger(__name__)


def default_senders(*, demo_mode: bool = False) -> dict[str, NotificationSender]:
    from_address = os.getenv("SMTP_FROM", "events@sdu.edu.kz")
    if demo_mode:
        return {
            "telegram": TelegramAdapter(ConsoleTelegramBotApi()),
            "email": SmtpAdapter(ConsoleSmtp, from_address),
        }

    result = {}
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        result["telegram"] = TelegramAdapter(HttpTelegramBotApi(token))

    smtp_host = os.getenv("SMTP_HOST")
    if smtp_host:
        port = int(os.getenv("SMTP_PORT", "25"))

        def smtp_factory():
            return smtplib.SMTP(smtp_host, port, timeout=5)

        result["email"] = SmtpAdapter(smtp_factory, from_address)
    return result


async def run_notification_jobs(stop: asyncio.Event, interval: float, jobs) -> None:
    while not stop.is_set():
        for name, job in jobs:
            if stop.is_set():
                return
            try:
                await asyncio.to_thread(job)
            except Exception:
                logger.error("Notification job failed (%s)", name)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


def create_app(db_path: str | None = None,
               senders: dict[str, NotificationSender] | None = None,
               clock: Callable[[], datetime] = datetime.now,
               *, demo_mode: bool | None = None, scheduler_interval: float = 60) -> FastAPI:
    if demo_mode is None:
        demo_mode = os.getenv("CLUB_EVENTS_DEMO") == "1"
    if db_path is None:
        default_path = "club_events_demo.db" if demo_mode else "club_events.db"
        db_path = os.getenv("CLUB_EVENTS_DB", default_path)

    db = Database(db_path, demo_mode=demo_mode,
                  extra_schema=(AUTH_SCHEMA, CLUBS_SCHEMA, EVENTS_SCHEMA, NOTIFICATION_SCHEMA))
    auth = AuthService(db, transaction=db.transaction)
    if demo_mode and auth.has_real_accounts():
        db.close()
        raise ValueError("Use a separate database for demo mode")
    if not demo_mode:
        admin_email = os.getenv("CLUB_EVENTS_ADMIN_EMAIL")
        admin_password = os.getenv("CLUB_EVENTS_ADMIN_PASSWORD")
        if admin_email or admin_password:
            try:
                if not admin_email or not admin_password:
                    raise ValueError("Set both CLUB_EVENTS_ADMIN_EMAIL and CLUB_EVENTS_ADMIN_PASSWORD")
                auth.bootstrap_admin(admin_email, admin_password)
            except BaseException:
                db.close()
                raise

    current_user = make_current_user(auth, demo_mode)
    access = AccessPolicy(db)
    contacts = UserDirectory(db)
    outbox = SqliteOutbox(db)

    clubs = ClubService(SqliteClubRepository(db), access, transaction=db.transaction)
    events = EventService(
        SqliteEventRepository(db), access, clock,
        transaction=db.transaction, member_ids=clubs.member_ids,
        participant_ids=lambda event_id: registrations.participant_ids(event_id),
        enqueue=outbox.enqueue,
    )
    registrations = RegistrationService(
        SqliteRegistrationRepository(db), events, access, outbox,
        transaction=db.transaction, clock=clock,
    )
    enabled_senders = senders if senders is not None else default_senders(demo_mode=demo_mode)
    dispatcher = NotificationDispatcher(outbox, contacts, enabled_senders)
    reminders = ReminderJob(outbox, events.upcoming_published, registrations.participant_ids,
                            db.transaction, clock=clock)
    jobs = [("reminders", reminders.enqueue_due)]
    if enabled_senders:
        jobs.append(("dispatcher", dispatcher.dispatch_pending))

    telegram_links = None
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_username = os.getenv("TELEGRAM_BOT_USERNAME")
    if not demo_mode and telegram_token and telegram_username:
        telegram_links = TelegramLinkService(
            SqliteTelegramLinks(db), contacts, db.transaction, telegram_username,
        )
        poller = TelegramLinkPoller(HttpTelegramBotApi(telegram_token), telegram_links)
        jobs.insert(0, ("Telegram linking", poller.poll))

    @asynccontextmanager
    async def lifespan(_app):
        stop = asyncio.Event()
        worker = None
        if not demo_mode and scheduler_interval > 0:
            worker = asyncio.create_task(run_notification_jobs(stop, scheduler_interval, jobs))
        try:
            yield
        finally:
            stop.set()
            if worker is not None:
                await worker
            db.close()

    app = FastAPI(title="Student-Club Event Management System", lifespan=lifespan)
    app.state.db = db
    app.state.dispatcher = dispatcher
    app.include_router(make_auth_router(auth, current_user, demo_mode))
    app.include_router(clubs_router(clubs, current_user))
    app.include_router(events_router(events, current_user))
    app.include_router(registrations_router(registrations, current_user))
    app.include_router(notifications_router(
        outbox, dispatcher, current_user_id=current_user,
        demo_mode=demo_mode, telegram_links=telegram_links, contacts=contacts,
    ))
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/api/config", tags=["configuration"])
    def config():
        return {"demo_mode": demo_mode, "signup_enabled": not demo_mode and auth.signup_enabled()}

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    return app
