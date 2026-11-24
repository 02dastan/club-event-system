from datetime import datetime

from app.database import connect
from app.events.domain_events import EventCreated
from app.messaging.event_bus import EventBus
from app.statistics.club_stats import ClubStatisticsConsumer
from conftest import ORGANIZER, event_body


def test_event_created_is_published_and_club_statistic_is_updated(client):
    published = []
    client.app.state.event_bus.subscribe(EventCreated, published.append)

    response = client.post("/api/events", json=event_body(), headers=ORGANIZER)

    assert response.status_code == 201                          
    assert len(published) == 1                                    
    assert published[0].club_event_id == response.json()["id"]
    assert client.app.state.club_stats.events_created(1) == 1    

def test_same_event_delivered_twice_is_counted_once():
    conn = connect(":memory:")
    bus = EventBus()
    consumer = ClubStatisticsConsumer(conn)
    bus.subscribe(EventCreated, consumer.handle)
    event = EventCreated(event_id="evt-1", club_event_id=10, club_id=1,
                         occurred_at=datetime(2026, 11, 24, 10, 0))

    bus.publish(event)
    bus.publish(event)

    assert consumer.events_created(1) == 1
    assert conn.execute("SELECT COUNT(*) FROM processed_events").fetchone()[0] == 1