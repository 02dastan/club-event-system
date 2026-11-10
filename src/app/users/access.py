"""Users module: role and club-ownership checks, audit log of denied actions.

Supports the Security quality scenario: 100% of unauthorized edits are rejected
and every denied attempt is recorded.
"""
import sqlite3
from datetime import datetime


class PermissionDenied(Exception):
    """The current user is not allowed to perform the action."""


class AccessPolicy:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def role_of(self, user_id: int):
        row = self._conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["role"] if row else None

    def is_student(self, user_id: int) -> bool:
        return self.role_of(user_id) == "student"

    def is_club_organizer(self, user_id: int, club_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM clubs WHERE id = ? AND organizer_id = ?", (club_id, user_id)
        ).fetchone()
        return row is not None

    def deny(self, user_id: int, action: str, target: str) -> PermissionDenied:
        """Record the denied attempt and return the error for the caller to raise."""
        with self._conn:
            self._conn.execute(
                "INSERT INTO audit_log (user_id, action, target, created_at) VALUES (?, ?, ?, ?)",
                (user_id, action, target, datetime.now().isoformat(timespec="seconds")),
            )
        return PermissionDenied(f"User {user_id} is not allowed to {action} {target}")
