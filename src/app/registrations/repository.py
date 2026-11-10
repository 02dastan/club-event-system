"""Data access for the Registrations module. Only this module reads the registrations table."""
import sqlite3
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Registration:
    id: int
    event_id: int
    student_id: int
    created_at: str


class DuplicateRegistration(Exception):
    """The student is already registered for this event."""


class RegistrationRepository(Protocol):
    def add(self, event_id: int, student_id: int, created_at: str) -> Registration: ...
    def exists(self, event_id: int, student_id: int) -> bool: ...
    def count_for_event(self, event_id: int) -> int: ...


class SqliteRegistrationRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add(self, event_id: int, student_id: int, created_at: str) -> Registration:
        # No commit here: RegistrationService owns the transaction.
        try:
            cursor = self._conn.execute(
                "INSERT INTO registrations (event_id, student_id, created_at) VALUES (?, ?, ?)",
                (event_id, student_id, created_at),
            )
        except sqlite3.IntegrityError as e:
            # UNIQUE (event_id, student_id) is the final guard against double registration (ADR-002).
            raise DuplicateRegistration("Student is already registered for this event") from e
        return Registration(cursor.lastrowid, event_id, student_id, created_at)

    def exists(self, event_id: int, student_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM registrations WHERE event_id = ? AND student_id = ?", (event_id, student_id)
        ).fetchone()
        return row is not None

    def count_for_event(self, event_id: int) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM registrations WHERE event_id = ?", (event_id,)
        ).fetchone()[0]
