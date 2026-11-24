"""Record completed registrations in the Users module's audit log."""
import sqlite3

from ..registrations.domain_events import StudentRegistered


class RegistrationAuditConsumer:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def handle(self, event: StudentRegistered) -> None:
        with self._conn:
            receipt = self._conn.execute(
                "INSERT INTO processed_events (consumer, event_id) VALUES (?, ?)"
                " ON CONFLICT (consumer, event_id) DO NOTHING",
                ("registration_audit", event.event_id),
            )
            if receipt.rowcount:
                self._conn.execute(
                    "INSERT INTO audit_log (user_id, action, target, created_at) VALUES (?, ?, ?, ?)",
                    (event.student_id, "STUDENT_REGISTERED", str(event.registration_id),
                     event.occurred_at.isoformat()),
                )
