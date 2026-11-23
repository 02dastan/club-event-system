"""Account sign-in, session validation, and administrator workflows."""
import hashlib
import hmac
import re
import secrets
import time

from .auth_repository import AUTH_SCHEMA as AUTH_SCHEMA
from .auth_repository import AuthRepository, Profile

SESSION_LIFETIME = 7 * 24 * 60 * 60
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
_PASSWORD_ROUNDS = 600_000
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_DEMO_EMAILS = {
    "1": "organizer@example.com",
    "2": "student1@example.com",
    "3": "student2@example.com",
    "4": "admin@example.com",
}


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _password_key(password: str, salt: bytes, rounds: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _password_key(password, salt, _PASSWORD_ROUNDS)
    return f"{_PASSWORD_ROUNDS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    rounds, salt, expected = stored.split("$")
    digest = _password_key(password, bytes.fromhex(salt), int(rounds))
    return hmac.compare_digest(digest, bytes.fromhex(expected))


def _session_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, db, transaction=None):
        self._repo = AuthRepository(db)
        self._transaction = transaction or (lambda: db)
        self._dummy_password_hash = _hash_password(secrets.token_urlsafe(32))

    def profile(self, user_id: int) -> Profile:
        profile = self._repo.profile(user_id)
        if profile is None:
            raise AuthError(404, "User not found.")
        return profile

    def signup_enabled(self) -> bool:
        return self._repo.signup_enabled()

    def has_real_accounts(self) -> bool:
        return self._repo.has_real_accounts()

    def signup(self, name: str, email: str, password: str) -> tuple[Profile, str]:
        if not self.signup_enabled():
            raise AuthError(403, "Sign-up is currently disabled.")
        name, email = name.strip(), self._validate_new_account(email, password)
        if not name:
            raise AuthError(400, "Enter your name.")
        password_hash = _hash_password(password)
        with self._transaction():
            if not self.signup_enabled():
                raise AuthError(403, "Sign-up is currently disabled.")
            if self._repo.email_in_use(email):
                raise AuthError(409, "An account already uses this email.")
            user_id = self._repo.create_account(name, email, "student", password_hash)
            return self.profile(user_id), self._issue_session(user_id)

    def login(self, email: str, password: str) -> tuple[Profile, str]:
        if not password or len(password) > PASSWORD_MAX_LENGTH:
            raise AuthError(401, "Invalid email or password.")
        credentials = self._repo.credentials(email.strip().casefold())
        stored_hash = credentials[1] if credentials else self._dummy_password_hash
        verified = _verify_password(password, stored_hash)
        if credentials is None or not verified:
            raise AuthError(401, "Invalid email or password.")
        user_id = credentials[0]
        with self._transaction():
            return self.profile(user_id), self._issue_session(user_id)

    def _issue_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        self._repo.issue_session(_session_digest(token), user_id, now + SESSION_LIFETIME, now)
        return token

    def session_user(self, token: str | None) -> int:
        if token and len(token) <= 128:
            user_id = self._repo.session_user(_session_digest(token), int(time.time()))
            if user_id is not None:
                return user_id
        raise AuthError(401, "Sign in first.")

    def demo_user(self, selected_id: str) -> int:
        email = _DEMO_EMAILS.get(selected_id)
        if email and self._repo.demo_account_exists(int(selected_id), email):
            return int(selected_id)
        raise AuthError(401, "Choose an available demo user.")

    def logout(self, token: str | None) -> None:
        if token and len(token) <= 128:
            with self._transaction():
                self._repo.revoke_session(_session_digest(token))

    def bootstrap_admin(self, email: str, password: str) -> None:
        if self._repo.has_admin():
            return
        email = self._validate_new_account(email, password)
        password_hash = _hash_password(password)
        with self._transaction():
            if self._repo.has_admin():
                return
            if self._repo.email_in_use(email):
                raise ValueError("The initial admin email is already in use. Choose another email.")
            self._repo.create_account("Platform Administrator", email, "admin", password_hash)

    def list_users(self, admin_id: int) -> list[Profile]:
        self._require_admin(admin_id)
        return self._repo.list_profiles()

    def admin_settings(self, admin_id: int) -> bool:
        self._require_admin(admin_id)
        return self.signup_enabled()

    def update_settings(self, admin_id: int, enabled: bool) -> bool:
        with self._transaction():
            self._require_admin(admin_id)
            self._repo.set_signup_enabled(enabled)
            return self.signup_enabled()

    def update_role(self, admin_id: int, user_id: int, role: str) -> Profile:
        with self._transaction():
            self._require_admin(admin_id)
            profile = self.profile(user_id)
            if user_id == admin_id and role != profile.role:
                raise AuthError(400, "You cannot change your own administrator role.")
            self._repo.set_role(user_id, role)
            if profile.organizer_request == "pending" and role != "student":
                status = "approved" if role == "organizer" else "rejected"
                self._repo.set_organizer_request(user_id, status)
            if profile.organizer_request == "approved" and role != "organizer":
                self._repo.set_organizer_request(user_id, "rejected")
            return self.profile(user_id)

    def request_organizer(self, user_id: int) -> Profile:
        with self._transaction():
            profile = self.profile(user_id)
            if profile.role != "student":
                raise AuthError(400, "Only students can request organizer access.")
            self._repo.set_organizer_request(user_id, "pending")
            return self.profile(user_id)

    def review_organizer(self, admin_id: int, user_id: int, approved: bool) -> Profile:
        with self._transaction():
            self._require_admin(admin_id)
            profile = self.profile(user_id)
            if profile.role != "student" or profile.organizer_request != "pending":
                raise AuthError(409, "This user has no pending organizer request.")
            self._repo.set_organizer_request(user_id, "approved" if approved else "rejected")
            if approved:
                self._repo.set_role(user_id, "organizer")
            return self.profile(user_id)

    def _require_admin(self, user_id: int) -> None:
        if self.profile(user_id).role != "admin":
            raise AuthError(403, "Administrator access is required.")

    @staticmethod
    def _validate_new_account(email: str, password: str) -> str:
        email = email.strip().casefold()
        if len(email) > 254 or not _EMAIL.fullmatch(email):
            raise AuthError(400, "Enter a valid email address.")
        if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
            raise AuthError(400, f"Use a password of {PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters.")
        return email
