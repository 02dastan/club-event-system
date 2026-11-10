"""Composition root: the only place that chooses concrete classes and wires modules together.

Run:  uvicorn app.main:create_app --factory --reload --app-dir src

Notification channels:
  TELEGRAM_BOT_TOKEN set -> real Telegram Bot API, otherwise messages are printed to the console.
  SMTP_HOST set          -> real SMTP server (SMTP_PORT, SMTP_FROM), otherwise printed to the console.
"""
import logging
import os
import smtplib
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .database import connect
from .events.repository import SqliteEventRepository
from .events.router import make_router as events_router
from .events.service import EventService
from .notifications.dispatcher import NotificationDispatcher
from .notifications.outbox import SqliteOutbox
from .notifications.router import make_router as notifications_router
from .notifications.sender import (ConsoleSmtp, ConsoleTelegramBotApi, HttpTelegramBotApi,
                                   NotificationSender, SmtpAdapter, TelegramAdapter)
from .registrations.repository import SqliteRegistrationRepository
from .registrations.router import make_router as registrations_router
from .registrations.service import RegistrationService
from .users.access import AccessPolicy
from .users.contacts import UserDirectory

STATIC = Path(__file__).parent / "static"
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def default_senders() -> dict[str, NotificationSender]:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_api = HttpTelegramBotApi(token) if token else ConsoleTelegramBotApi()

    smtp_host = os.getenv("SMTP_HOST")
    if smtp_host:
        port = int(os.getenv("SMTP_PORT", "25"))
        smtp_factory = lambda: smtplib.SMTP(smtp_host, port, timeout=5)  # noqa: E731
    else:
        smtp_factory = ConsoleSmtp
    return {
        "telegram": TelegramAdapter(telegram_api),
        "email": SmtpAdapter(smtp_factory, os.getenv("SMTP_FROM", "events@sdu.edu.kz")),
    }


def create_app(db_path: str = "club_events.db",
               senders: Optional[dict[str, NotificationSender]] = None,
               clock: Callable[[], datetime] = datetime.now) -> FastAPI:
    conn = connect(db_path)

    access = AccessPolicy(conn)
    contacts = UserDirectory(conn)
    outbox = SqliteOutbox(conn)

    event_service = EventService(SqliteEventRepository(conn), access, clock)
    registration_service = RegistrationService(
        SqliteRegistrationRepository(conn), event_service, access, outbox,
        transaction=lambda: conn, clock=clock)
    dispatcher = NotificationDispatcher(outbox, contacts, senders or default_senders())

    app = FastAPI(title="Student-Club Event Management System")
    app.state.db = conn
    app.state.dispatcher = dispatcher
    app.include_router(events_router(event_service))
    app.include_router(registrations_router(registration_service))
    app.include_router(notifications_router(outbox, dispatcher))

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    return app
