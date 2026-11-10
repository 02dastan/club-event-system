"""Tests for the outbox, the dispatcher and the adapters. No real Telegram or SMTP is used."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.notifications.sender import DeliveryError, SmtpAdapter, TelegramAdapter
from conftest import STUDENT_ONE, STUDENT_TWO, FakeNotificationSender, event_body, ORGANIZER


def outbox_statuses(client):
    return [(m["recipient_id"], m["status"], m["attempts"]) for m in client.get("/api/notifications").json()]


# --- ADR-001 check: channel outage does not affect registration ---

def test_registration_succeeds_while_notification_channels_are_down():
    down = {"telegram": FakeNotificationSender(fail=True), "email": FakeNotificationSender(fail=True)}
    client = TestClient(create_app(":memory:", senders=down))
    event_id = client.post("/api/events", json=event_body(), headers=ORGANIZER).json()["id"]

    response = client.post(f"/api/events/{event_id}/registrations", headers=STUDENT_ONE)
    client.post("/api/notifications/dispatch")

    assert response.status_code == 201
    assert outbox_statuses(client) == [(2, "PENDING", 1)]  # kept for a retry


def test_dispatcher_sends_through_the_users_channel_and_marks_sent(client, senders, create_event):
    event_id = create_event()
    client.post(f"/api/events/{event_id}/registrations", headers=STUDENT_ONE)  # Telegram linked
    client.post(f"/api/events/{event_id}/registrations", headers=STUDENT_TWO)  # e-mail only

    result = client.post("/api/notifications/dispatch").json()

    assert result == {"sent": 2, "failed_attempts": 0}
    assert [a for a, _ in senders["telegram"].sent] == ["100200300"]
    assert [a for a, _ in senders["email"].sent] == ["student2@example.com"]
    assert {s for _, s, _ in outbox_statuses(client)} == {"SENT"}


def test_message_is_marked_failed_after_five_attempts(senders, create_event, client):
    senders["telegram"].fail = True
    event_id = create_event()
    client.post(f"/api/events/{event_id}/registrations", headers=STUDENT_ONE)

    for _ in range(6):
        client.post("/api/notifications/dispatch")

    assert outbox_statuses(client) == [(2, "FAILED", 5)]


# --- Adapter translation (fake external clients, no network) ---

class FakeTelegramApi:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def send_message(self, chat_id, text):
        self.calls.append((chat_id, text))
        return self.response


def test_telegram_adapter_translates_call_and_error_format():
    ok_api = FakeTelegramApi({"ok": True})
    TelegramAdapter(ok_api).send("100200300", "Hello")
    assert ok_api.calls == [(100200300, "Hello")]  # string address -> integer chat_id

    blocked_api = FakeTelegramApi({"ok": False, "description": "bot was blocked by the user"})
    with pytest.raises(DeliveryError, match="blocked"):
        TelegramAdapter(blocked_api).send("100200300", "Hello")


class FakeSmtp:
    def __init__(self, fail=False):
        self.fail = fail
        self.messages = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send_message(self, msg):
        if self.fail:
            raise OSError("connection refused")
        self.messages.append(msg)


def test_smtp_adapter_builds_email_and_wraps_errors():
    smtp = FakeSmtp()
    SmtpAdapter(lambda: smtp, "events@sdu.edu.kz").send("student2@example.com", "Hello")
    msg = smtp.messages[0]
    assert (msg["To"], msg["From"], msg.get_content().strip()) == \
        ("student2@example.com", "events@sdu.edu.kz", "Hello")

    with pytest.raises(DeliveryError, match="SMTP"):
        SmtpAdapter(lambda: FakeSmtp(fail=True), "events@sdu.edu.kz").send("x@example.com", "Hi")
