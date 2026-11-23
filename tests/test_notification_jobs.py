from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from app.database import connect
from app.main import create_app
from app.notifications.dispatcher import NotificationDispatcher
from app.notifications.outbox import NOTIFICATION_SCHEMA, SqliteOutbox
from app.notifications.reminders import ReminderJob
from app.notifications.router import make_router
from app.notifications.telegram import SqliteTelegramLinks, TelegramLinkPoller, TelegramLinkService
from app.users.contacts import UserDirectory


@pytest.fixture
def db():
    connection = connect(":memory:")
    connection.executescript(NOTIFICATION_SCHEMA)
    yield connection
    connection.close()


def test_reminder_job_queues_each_participant_once_per_start(db):
    outbox = SqliteOutbox(db)
    clock = datetime(2026, 11, 25, 10)
    start = clock + timedelta(hours=2)
    event = SimpleNamespace(id=42, title="Arduino workshop", starts_at=start, venue="B112")

    def due_events(start, end):
        assert (start, end) == (clock, clock + timedelta(hours=24))
        return [event]

    job = ReminderJob(outbox, due_events, lambda event_id: [2, 3], lambda: db, clock=lambda: clock)
    assert job.enqueue_due() == 2
    assert job.enqueue_due() == 0
    assert {message.recipient_id for message in outbox.pending()} == {2, 3}
    assert all("Arduino workshop" in message.text for message in outbox.pending())

    event.starts_at += timedelta(hours=1)
    assert job.enqueue_due() == 2


def _code(link):
    return parse_qs(urlparse(link).query)["start"][0]


def test_telegram_codes_expire_rotate_and_cannot_be_reused(db):
    clock = [1000]
    contacts = UserDirectory(db)
    links = TelegramLinkService(SqliteTelegramLinks(db), contacts, lambda: db,
                                "SDUEventsBot", clock=lambda: clock[0])
    stale_code = _code(links.issue_link(3))
    new_code = _code(links.issue_link(3))
    assert not links.consume(stale_code, 12345)
    assert not links.consume(new_code, 100200300)  # seeded for another user
    assert links.consume(new_code, 12345)
    assert not links.consume(new_code, 67890)
    assert contacts.contact_for(3).address == "12345"

    expired_code = _code(links.issue_link(3))
    clock[0] += links.EXPIRES_IN
    assert not links.consume(expired_code, 12345)
    links.unlink(3)
    assert contacts.contact_for(3).channel == "email"


def test_telegram_polling_requires_a_private_start_and_acknowledges_updates(db):
    contacts = UserDirectory(db)
    links = TelegramLinkService(SqliteTelegramLinks(db), contacts, lambda: db, "SDUEventsBot")
    payload = f"/start {_code(links.issue_link(3))}"

    class Updates:
        def get_updates(self, offset=None):
            if offset is None:
                return [
                    {"update_id": 44, "message": {"chat": {"type": "group", "id": -999}, "text": payload}},
                    {"update_id": 45, "message": {"chat": {"type": "private", "id": 12345}, "text": payload}},
                ]
            assert offset == 46
            return []

    poller = TelegramLinkPoller(Updates(), links)
    assert poller.poll() == 1
    assert poller.poll() == 0
    assert contacts.contact_for(3).address == "12345"


def test_outbox_is_private_and_telegram_link_requires_current_user_in_real_mode(db):
    contacts = UserDirectory(db)
    links = TelegramLinkService(SqliteTelegramLinks(db), contacts, lambda: db, "SDUEventsBot")
    outbox = SqliteOutbox(db)
    app = FastAPI()

    def current_user_id(test_session: str = Header(default="")):
        if test_session != "student":
            raise HTTPException(401)
        return 3

    app.include_router(make_router(outbox, NotificationDispatcher(outbox, contacts, {}),
                                   current_user_id=current_user_id, demo_mode=False,
                                   telegram_links=links, contacts=contacts))
    client = TestClient(app)
    assert client.get("/api/notifications").status_code == 404
    assert client.post("/api/notifications/dispatch").status_code == 404
    assert client.post("/api/notifications/telegram/link").status_code == 401
    issued = client.post("/api/notifications/telegram/link", headers={"Test-Session": "student"})
    assert issued.status_code == 200
    assert issued.headers["Cache-Control"] == "no-store"
    assert links.consume(_code(issued.json()["url"]), 12345)


def test_app_scheduler_delivers_due_reminder_with_no_manual_call(tmp_path, monkeypatch):
    for name in ("TELEGRAM_BOT_TOKEN", "CLUB_EVENTS_ADMIN_EMAIL", "CLUB_EVENTS_ADMIN_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    clock = datetime(2026, 11, 25, 10)
    delivered = Event()

    class RecordingSender:
        def send(self, address, text):
            messages.append((address, text))
            delivered.set()

    messages = []
    app = create_app(str(tmp_path / "events.db"), senders={"email": RecordingSender()},
                     clock=lambda: clock, demo_mode=False, scheduler_interval=0.02)
    with TestClient(app):
        with app.state.db.transaction() as connection:
            connection.execute(
                "INSERT INTO users(id, name, email, role) VALUES"
                " (1, 'Organizer', 'organizer@example.test', 'organizer'),"
                " (2, 'Student', 'student@example.test', 'student')"
            )
            connection.execute("INSERT INTO clubs(id, name, organizer_id) VALUES (1, 'Robotics', 1)")
            connection.execute(
                "INSERT INTO events(id, club_id, title, starts_at, venue, category, capacity)"
                " VALUES (1, 1, 'Arduino workshop', ?, 'B112', 'Workshop', 5)",
                ((clock + timedelta(hours=2)).isoformat(),),
            )
            connection.execute(
                "INSERT INTO registrations(event_id, student_id, created_at) VALUES (1, 2, ?)",
                (clock.isoformat(),),
            )

        assert delivered.wait(timeout=3)
    assert messages == [("student@example.test", "Reminder: 'Arduino workshop' starts on 25.11.2026 12:00 at B112.")]
