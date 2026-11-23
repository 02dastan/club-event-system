"""Browser sessions and protected account administration endpoints."""
from threading import Lock
from time import monotonic
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr

from .auth import AuthError, AuthService, SESSION_LIFETIME

_SESSION_COOKIE = "club_events_session"


class SignUpIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: SecretStr


class RoleIn(BaseModel):
    role: Literal["student", "organizer", "admin"]


class SettingsIn(BaseModel):
    signup_enabled: bool


class ReviewIn(BaseModel):
    approved: bool


class LoginLimit:
    def __init__(self):
        self._lock = Lock()
        self._minute = 0
        self._counts = {}

    def check(self, request: Request) -> None:
        host = request.client.host if request.client else "unknown"
        with self._lock:
            minute = int(monotonic() // 60)
            if minute != self._minute:
                self._minute = minute
                self._counts.clear()
            attempts = self._counts.get(host, 0)
            if attempts >= 30:
                raise HTTPException(429, "Too many attempts. Try again in a minute.",
                                    headers={"Retry-After": "60"})
            self._counts[host] = attempts + 1


def _auth_call(method, *args):
    try:
        return method(*args)
    except AuthError as error:
        raise HTTPException(error.status, str(error)) from error


def _check_origin(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("origin")
    expected = f"{request.url.scheme}://{request.url.netloc}"
    if (origin is not None and origin != expected
            or request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}):
        raise HTTPException(403, "This request must come from the same site.")


def _private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _set_session(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        _SESSION_COOKIE, token, max_age=SESSION_LIFETIME,
        httponly=True, secure=request.url.scheme == "https", samesite="strict",
    )


def make_current_user(auth: AuthService, demo_mode: bool):
    def current_user(request: Request) -> int:
        _check_origin(request)
        demo_id = request.headers.get("X-User-Id")
        if demo_mode and demo_id is not None:
            return _auth_call(auth.demo_user, demo_id)
        return _auth_call(auth.session_user, request.cookies.get(_SESSION_COOKIE))

    return current_user


def make_auth_router(auth: AuthService, current_user, demo_mode: bool):
    router = APIRouter(dependencies=[Depends(_private_response)])
    limiter = LoginLimit()

    @router.post("/api/auth/signup", status_code=201)
    def signup(body: SignUpIn, request: Request, response: Response):
        if demo_mode:
            raise HTTPException(404, "Choose a demo user to sign in.")
        _check_origin(request)
        limiter.check(request)
        profile, token = _auth_call(auth.signup, body.name, body.email, body.password.get_secret_value())
        _set_session(request, response, token)
        return profile

    @router.post("/api/auth/login")
    def login(body: LoginIn, request: Request, response: Response):
        if demo_mode:
            raise HTTPException(404, "Choose a demo user to sign in.")
        _check_origin(request)
        limiter.check(request)
        profile, token = _auth_call(auth.login, body.email, body.password.get_secret_value())
        _set_session(request, response, token)
        return profile

    @router.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response):
        _check_origin(request)
        auth.logout(request.cookies.get(_SESSION_COOKIE))
        response.delete_cookie(
            _SESSION_COOKIE, httponly=True, secure=request.url.scheme == "https", samesite="strict",
        )

    @router.get("/api/auth/me")
    def me(user_id: int = Depends(current_user)):
        return _auth_call(auth.profile, user_id)

    @router.post("/api/auth/organizer-request")
    def request_organizer(user_id: int = Depends(current_user)):
        return _auth_call(auth.request_organizer, user_id)

    @router.get("/api/admin/users")
    def users(user_id: int = Depends(current_user)):
        return _auth_call(auth.list_users, user_id)

    @router.patch("/api/admin/users/{target_id}")
    def update_role(target_id: int, body: RoleIn, user_id: int = Depends(current_user)):
        return _auth_call(auth.update_role, user_id, target_id, body.role)

    @router.get("/api/admin/settings")
    def settings(user_id: int = Depends(current_user)):
        return {"signup_enabled": _auth_call(auth.admin_settings, user_id)}

    @router.patch("/api/admin/settings")
    def update_settings(body: SettingsIn, user_id: int = Depends(current_user)):
        return {"signup_enabled": _auth_call(auth.update_settings, user_id, body.signup_enabled)}

    @router.patch("/api/admin/organizer-requests/{target_id}")
    def review_organizer(target_id: int, body: ReviewIn, user_id: int = Depends(current_user)):
        return _auth_call(auth.review_organizer, user_id, target_id, body.approved)

    return router
