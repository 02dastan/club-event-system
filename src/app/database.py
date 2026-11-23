"""SQLite connection and schema.

Each module owns its own tables (see docs/architecture/selected-architecture.md):
Users -> users, audit_log; Clubs -> clubs; Events -> events;
Registrations -> registrations; Notifications -> notification_outbox.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock, local
from uuid import uuid4

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,
    email            TEXT NOT NULL,
    telegram_chat_id TEXT,
    role             TEXT NOT NULL CHECK (role IN ('student', 'organizer', 'admin'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    action     TEXT NOT NULL,
    target     TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clubs (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    organizer_id INTEGER NOT NULL REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    club_id     INTEGER NOT NULL REFERENCES clubs (id),
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    starts_at   TEXT NOT NULL,
    venue       TEXT NOT NULL,
    category    TEXT NOT NULL,
    capacity    INTEGER NOT NULL CHECK (capacity > 0),
    status      TEXT NOT NULL DEFAULT 'PUBLISHED'
);

CREATE TABLE IF NOT EXISTS registrations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   INTEGER NOT NULL REFERENCES events (id),
    student_id INTEGER NOT NULL REFERENCES users (id),
    created_at TEXT NOT NULL,
    UNIQUE (event_id, student_id)
);

CREATE TABLE IF NOT EXISTS notification_outbox (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_id INTEGER NOT NULL,
    text         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SENT', 'FAILED')),
    attempts     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    sent_at      TEXT
);
CREATE INDEX IF NOT EXISTS registrations_student_id ON registrations (student_id);
CREATE INDEX IF NOT EXISTS notification_outbox_status_id ON notification_outbox (status, id);
"""

# Demo data so the prototype can be shown without a sign-up screen.
SEED = """
INSERT INTO users (id, name, email, telegram_chat_id, role) VALUES
    (1, 'Club Organizer', 'organizer@example.com', NULL,        'organizer'),
    (2, 'Student One',    'student1@example.com',  '100200300', 'student'),
    (3, 'Student Two',    'student2@example.com',  NULL,        'student'),
    (4, 'Platform Admin', 'admin@example.com',     NULL,        'admin');
INSERT INTO clubs (id, name, organizer_id) VALUES
    (1, 'SDU Robotics Club', 1);
"""


def connect(path: str = "club_events.db", *, demo_mode: bool = True) -> sqlite3.Connection:
    """Initialize a standalone connection, including the sample users by default."""
    conn = _open(path)
    conn.executescript(SCHEMA)
    if demo_mode:
        _seed_demo(conn)
    return conn


def _open(path: str, *, uri: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(path, uri=uri, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _seed_demo(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.executescript(SEED)


class Database:
    """Provide a SQLite connection per worker thread and serialize write transactions."""

    def __init__(self, path: str, *, demo_mode: bool, extra_schema: tuple[str, ...] = ()):
        self._memory = str(path) == ":memory:"
        self._path = (
            f"file:club-events-{uuid4().hex}?mode=memory&cache=shared"
            if self._memory else str(Path(path))
        )
        self._local = local()
        self._connections = []
        self._connections_lock = Lock()
        self._write_lock = Lock()
        conn = self._connection()
        try:
            if not self._memory:
                conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript("\n".join((SCHEMA, *extra_schema)))
            if demo_mode:
                _seed_demo(conn)
        except BaseException:
            self.close()
            raise

    def _connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = _open(self._path, uri=self._memory)
            self._local.conn = conn
            self._local.contexts = []
            with self._connections_lock:
                self._connections.append(conn)
        return conn

    def execute(self, sql: str, parameters=()) -> sqlite3.Cursor:
        return self._connection().execute(sql, parameters)

    def create_function(self, name, argument_count, function, *, deterministic=False) -> None:
        self._connection().create_function(name, argument_count, function, deterministic=deterministic)

    @property
    def in_transaction(self) -> bool:
        return self._connection().in_transaction

    @contextmanager
    def transaction(self):
        conn = self._connection()
        if conn.in_transaction:
            yield conn
            return
        with self._write_lock, conn:
            conn.execute("BEGIN IMMEDIATE")
            yield conn

    def __enter__(self) -> sqlite3.Connection:
        context = self.transaction()
        conn = context.__enter__()
        self._local.contexts.append(context)
        return conn

    def __exit__(self, *exc):
        return self._local.contexts.pop().__exit__(*exc)

    def close(self) -> None:
        with self._connections_lock:
            for conn in self._connections:
                conn.close()
            self._connections.clear()
