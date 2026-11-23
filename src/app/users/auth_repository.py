"""SQLite persistence for accounts, sessions, and organizer applications."""
from dataclasses import dataclass

AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_credentials (
    user_id       INTEGER PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    password_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS users_email_nocase ON users (email COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS user_sessions (
    token_digest TEXT PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expires_at   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS user_session_expiration ON user_sessions (expires_at);

CREATE TABLE IF NOT EXISTS organizer_requests (
    user_id INTEGER PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    status  TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected'))
);

CREATE TABLE IF NOT EXISTS platform_settings (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    signup_enabled INTEGER NOT NULL CHECK (signup_enabled IN (0, 1))
);

INSERT OR IGNORE INTO platform_settings (id, signup_enabled) VALUES (1, 1);
"""


@dataclass(frozen=True)
class Profile:
    id: int
    name: str
    email: str
    role: str
    organizer_request: str | None


_PROFILE_QUERY = """
    SELECT u.id, u.name, u.email, u.role, r.status AS organizer_request
    FROM users AS u
    LEFT JOIN organizer_requests AS r ON r.user_id = u.id
"""


class AuthRepository:
    def __init__(self, db):
        self._db = db

    def profile(self, user_id: int) -> Profile | None:
        row = self._db.execute(_PROFILE_QUERY + " WHERE u.id = ?", (user_id,)).fetchone()
        return Profile(**dict(row)) if row else None

    def list_profiles(self) -> list[Profile]:
        rows = self._db.execute(_PROFILE_QUERY + " ORDER BY u.name, u.id").fetchall()
        return [Profile(**dict(row)) for row in rows]

    def email_in_use(self, email: str) -> bool:
        return self._db.execute(
            "SELECT 1 FROM users WHERE email = ? COLLATE NOCASE", (email,),
        ).fetchone() is not None

    def credentials(self, email: str) -> tuple[int, str] | None:
        row = self._db.execute(
            "SELECT c.user_id, c.password_hash FROM user_credentials AS c "
            "JOIN users AS u ON u.id = c.user_id WHERE u.email = ? COLLATE NOCASE",
            (email,),
        ).fetchone()
        return (row["user_id"], row["password_hash"]) if row else None

    def has_admin(self) -> bool:
        return self._db.execute(
            "SELECT 1 FROM users AS u JOIN user_credentials AS c ON c.user_id = u.id "
            "WHERE u.role = 'admin' LIMIT 1"
        ).fetchone() is not None

    def has_real_accounts(self) -> bool:
        return self._db.execute("SELECT 1 FROM user_credentials LIMIT 1").fetchone() is not None

    def create_account(self, name: str, email: str, role: str, password_hash: str) -> int:
        user_id = self._db.execute(
            "INSERT INTO users (name, email, role) VALUES (?, ?, ?)", (name, email, role),
        ).lastrowid
        self._db.execute(
            "INSERT INTO user_credentials (user_id, password_hash) VALUES (?, ?)",
            (user_id, password_hash),
        )
        return user_id

    def demo_account_exists(self, user_id: int, email: str) -> bool:
        return self._db.execute(
            "SELECT 1 FROM users AS u LEFT JOIN user_credentials AS c ON c.user_id = u.id "
            "WHERE u.id = ? AND u.email = ? AND c.user_id IS NULL",
            (user_id, email),
        ).fetchone() is not None

    def issue_session(self, token_digest: str, user_id: int, expires_at: int, now: int) -> None:
        self._db.execute("DELETE FROM user_sessions WHERE expires_at <= ?", (now,))
        self._db.execute(
            "INSERT INTO user_sessions (token_digest, user_id, expires_at) VALUES (?, ?, ?)",
            (token_digest, user_id, expires_at),
        )

    def session_user(self, token_digest: str, now: int) -> int | None:
        row = self._db.execute(
            "SELECT user_id FROM user_sessions WHERE token_digest = ? AND expires_at > ?",
            (token_digest, now),
        ).fetchone()
        return row["user_id"] if row else None

    def revoke_session(self, token_digest: str) -> None:
        self._db.execute("DELETE FROM user_sessions WHERE token_digest = ?", (token_digest,))

    def signup_enabled(self) -> bool:
        row = self._db.execute("SELECT signup_enabled FROM platform_settings WHERE id = 1").fetchone()
        return bool(row["signup_enabled"])

    def set_signup_enabled(self, enabled: bool) -> None:
        self._db.execute(
            "UPDATE platform_settings SET signup_enabled = ? WHERE id = 1", (enabled,),
        )

    def set_role(self, user_id: int, role: str) -> None:
        self._db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))

    def set_organizer_request(self, user_id: int, status: str) -> None:
        self._db.execute(
            "INSERT INTO organizer_requests (user_id, status) VALUES (?, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET status = excluded.status",
            (user_id, status),
        )
