"""SQLite connection and schema.

Each module owns its own tables (see docs/architecture/selected-architecture.md):
Users -> users, audit_log; Clubs -> clubs; Events -> events;
Registrations -> registrations; Notifications -> notification_outbox.
"""
import sqlite3

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


def connect(path: str = "club_events.db") -> sqlite3.Connection:
    """Open the database, create tables and add demo data on first start.

    Use path=":memory:" in tests so no file is written.
    The connection is used as a context manager for transactions:
    `with conn:` commits on success and rolls back on an exception.
    """
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.executescript(SEED)
        conn.commit()
    return conn
