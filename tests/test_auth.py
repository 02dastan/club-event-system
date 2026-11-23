from fastapi.testclient import TestClient
import pytest

from app.main import create_app

ADMIN = {"email": "admin@campus.example", "password": "long-admin-password"}
STUDENT = {"name": "Demo Student", "email": "student@campus.example", "password": "long-student-password"}


@pytest.fixture
def secure_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLUB_EVENTS_ADMIN_EMAIL", ADMIN["email"])
    monkeypatch.setenv("CLUB_EVENTS_ADMIN_PASSWORD", ADMIN["password"])
    app = create_app(str(tmp_path / "accounts.db"), demo_mode=False, scheduler_interval=0)
    with TestClient(app, base_url="https://testserver") as client:
        yield client


def test_secure_account_session_and_cross_origin_protection(secure_client):
    spoofed_identity = {"X-User-Id": "1"}
    assert secure_client.get("/api/auth/me", headers=spoofed_identity).status_code == 401

    signup = secure_client.post("/api/auth/signup", json=STUDENT)
    assert signup.status_code == 201
    student_id = signup.json()["id"]
    cookie = signup.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
    token = secure_client.cookies["club_events_session"]
    assert secure_client.get("/api/auth/me", headers=spoofed_identity).json()["id"] == student_id
    assert secure_client.get("/api/admin/users", headers=spoofed_identity).status_code == 403

    blocked = secure_client.post("/api/auth/organizer-request", headers={"Origin": "https://external.example"})
    assert blocked.status_code == 403
    assert secure_client.get("/api/auth/me").json()["organizer_request"] is None

    assert secure_client.post("/api/auth/logout").status_code == 204
    revoked_cookie = {"Cookie": f"club_events_session={token}"}
    assert secure_client.get("/api/auth/me", headers=revoked_cookie).status_code == 401

    login = secure_client.post("/api/auth/login", json={
        "email": STUDENT["email"].upper(), "password": STUDENT["password"],
    })
    assert login.status_code == 200
    assert login.json()["id"] == student_id


def test_admin_can_approve_organizer_and_disable_signups(secure_client):
    signup = secure_client.post("/api/auth/signup", json=STUDENT)
    assert signup.status_code == 201
    student_id = signup.json()["id"]

    requested = secure_client.post("/api/auth/organizer-request")
    assert requested.json()["organizer_request"] == "pending"
    decision = f"/api/admin/organizer-requests/{student_id}"
    assert secure_client.patch(decision, json={"approved": True}).status_code == 403
    assert secure_client.post("/api/auth/logout").status_code == 204

    assert secure_client.post("/api/auth/login", json=ADMIN).status_code == 200
    approved = secure_client.patch(decision, json={"approved": True})
    assert approved.status_code == 200
    assert approved.json()["role"] == "organizer"
    assert approved.json()["organizer_request"] == "approved"
    assert secure_client.patch(decision, json={"approved": False}).status_code == 409

    settings = secure_client.patch("/api/admin/settings", json={"signup_enabled": False})
    assert settings.status_code == 200
    assert secure_client.get("/api/config").json()["signup_enabled"] is False
    assert secure_client.post("/api/auth/signup", json={**STUDENT, "email": "new@campus.example"}).status_code == 403


def test_demo_identity_remains_available_without_real_accounts(client):
    me = client.get("/api/auth/me", headers={"X-User-Id": "2"})
    assert me.status_code == 200
    assert me.json()["name"] == "Student One"
    assert client.post("/api/auth/signup", json=STUDENT).status_code == 404
    assert client.post("/api/auth/login", json=ADMIN).status_code == 404
