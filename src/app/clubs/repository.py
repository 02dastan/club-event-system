"""SQLite storage for club profiles and memberships."""
import sqlite3
from dataclasses import dataclass
from typing import Optional

CLUBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS club_profiles (
    club_id INTEGER PRIMARY KEY REFERENCES clubs (id) ON DELETE CASCADE,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS club_memberships (
    club_id INTEGER NOT NULL REFERENCES clubs (id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    PRIMARY KEY (club_id, student_id)
);

CREATE INDEX IF NOT EXISTS club_memberships_student_idx
    ON club_memberships (student_id, club_id);
"""

SELECT_CLUB = (
    "SELECT clubs.id, clubs.name, COALESCE(club_profiles.description, '') AS description,"
    " clubs.organizer_id FROM clubs LEFT JOIN club_profiles ON club_profiles.club_id = clubs.id"
)


@dataclass(frozen=True)
class Club:
    id: int
    name: str
    description: str
    organizer_id: int


class SqliteClubRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list_all(self) -> list[Club]:
        rows = self._conn.execute(SELECT_CLUB + " ORDER BY clubs.name COLLATE NOCASE, clubs.id")
        return [Club(**dict(row)) for row in rows]

    def get(self, club_id: int) -> Optional[Club]:
        row = self._conn.execute(SELECT_CLUB + " WHERE clubs.id = ?", (club_id,)).fetchone()
        return Club(**dict(row)) if row else None

    def add(self, name: str, description: str, organizer_id: int) -> Club:
        cursor = self._conn.execute(
            "INSERT INTO clubs (name, organizer_id) VALUES (?, ?)", (name, organizer_id),
        )
        self._save_profile(cursor.lastrowid, description)
        return self.get(cursor.lastrowid)

    def update(self, club_id: int, name: str, description: str, organizer_id: int) -> Club:
        self._conn.execute(
            "UPDATE clubs SET name = ?, organizer_id = ? WHERE id = ?", (name, organizer_id, club_id),
        )
        self._save_profile(club_id, description)
        return self.get(club_id)

    def _save_profile(self, club_id: int, description: str) -> None:
        self._conn.execute(
            "INSERT INTO club_profiles (club_id, description) VALUES (?, ?)"
            " ON CONFLICT (club_id) DO UPDATE SET description = excluded.description",
            (club_id, description),
        )

    def member_ids(self, club_id: int) -> list[int]:
        rows = self._conn.execute(
            "SELECT student_id FROM club_memberships WHERE club_id = ? ORDER BY student_id",
            (club_id,),
        )
        return [row["student_id"] for row in rows]

    def memberships_for(self, student_id: int) -> list[int]:
        rows = self._conn.execute(
            "SELECT club_id FROM club_memberships WHERE student_id = ? ORDER BY club_id",
            (student_id,),
        )
        return [row["club_id"] for row in rows]

    def add_member(self, club_id: int, student_id: int) -> None:
        self._conn.execute(
            "INSERT INTO club_memberships (club_id, student_id) VALUES (?, ?)"
            " ON CONFLICT (club_id, student_id) DO NOTHING",
            (club_id, student_id),
        )

    def remove_member(self, club_id: int, student_id: int) -> None:
        self._conn.execute(
            "DELETE FROM club_memberships WHERE club_id = ? AND student_id = ?",
            (club_id, student_id),
        )
