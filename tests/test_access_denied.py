from app.users.denials import AccessDenied
from conftest import STUDENT_ONE, STUDENT_TWO, event_body


def test_denied_action_publishes_event_and_counts_attempt(client):
    published = []
    client.app.state.denial_bus.subscribe(published.append)

    response = client.post("/api/events", json=event_body(), headers=STUDENT_ONE)

    assert response.status_code == 403
    db = client.app.state.db
    assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    audit = db.execute("SELECT * FROM audit_log").fetchone()
    event, = published
    assert isinstance(event, AccessDenied)
    assert event.event_id == audit["id"]
    assert event.user_id == audit["user_id"] == 2
    assert event.occurred_at.isoformat() == audit["created_at"]
    assert db.execute("SELECT attempts FROM denied_attempt_counts WHERE user_id = 2").fetchone()[0] == 1


def test_duplicate_access_denied_counts_only_once_per_event(client):
    published = []
    bus = client.app.state.denial_bus
    bus.subscribe(published.append)

    for student in (STUDENT_ONE, STUDENT_ONE, STUDENT_TWO):
        assert client.post("/api/events", json=event_body(), headers=student).status_code == 403

    # The first denial was already published by AccessPolicy. Deliver it again.
    bus.publish(published[0])
    counts = client.app.state.db.execute("SELECT user_id, attempts FROM denied_attempt_counts")
    assert dict(counts) == {2: 2, 3: 1}
