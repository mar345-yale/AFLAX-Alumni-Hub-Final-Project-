"""Accounts, approvals, sessions, password reset, and rate limits."""

import email
import glob
from email import policy

from conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login, signup_form
from db import OUTBOX_DIR


def test_protected_routes_require_login(client):
    for path in ("/api/me", "/api/schedule", "/api/alumni", "/api/explore/afscs", "/api/chat/history"):
        assert client.get(path).status_code == 401


def test_signup_waits_for_board_approval(client, admin):
    form = signup_form()
    assert client.post("/api/auth/signup", data=form).status_code == 201
    r = client.post("/api/auth/login", json={"email": form["email"], "password": form["password"]})
    assert r.status_code == 403 and "approval" in r.json()["detail"]

    accounts = client.get("/api/admin/accounts", headers=admin).json()["accounts"]
    pending = next(a for a in accounts if a["email"] == form["email"])
    assert pending["approval"] == "pending"
    client.post(f"/api/admin/accounts/{pending['id']}/approve", headers=admin)
    login(client, form["email"], form["password"])


def test_signup_emails_the_board(client):
    before = set(glob.glob(str(OUTBOX_DIR / "*")))
    form = signup_form()
    client.post("/api/auth/signup", data=form)
    new = set(glob.glob(str(OUTBOX_DIR / "*"))) - before
    assert any("new-aflax-account-request" in p for p in new)


def test_signup_validation(client):
    r = client.post("/api/auth/signup", data=signup_form(confirm_email="other@example.com"))
    assert r.status_code == 422 and "match" in r.json()["detail"]
    r = client.post("/api/auth/signup", data=signup_form(status="Active Duty"))
    assert "rank" in r.json()["detail"] and "base" in r.json()["detail"]
    r = client.post("/api/auth/signup", data=signup_form(job="x" * 150))
    assert r.status_code == 422 and "100 characters" in r.json()["detail"]


def test_conditional_fields_are_dropped(client, admin):
    form = signup_form(status="Active Duty", rank="O-3", afsc="13S1", aircraft="F-35A",
                       base="Schriever SFB, CO", city="Should Be Dropped")
    assert client.post("/api/auth/signup", data=form).status_code == 201
    acct = next(a for a in client.get("/api/admin/accounts", headers=admin).json()["accounts"]
                if a["email"] == form["email"])
    assert acct["aircraft"] is None  # 13S1 is not an aircrew AFSC
    assert acct["city"] is None


def test_non_admin_cannot_use_board_endpoints(client, approved_member):
    headers, _, _ = approved_member
    assert client.get("/api/admin/accounts", headers=headers).status_code == 403
    assert client.get("/api/admin/usage", headers=headers).status_code == 403
    r = client.post("/api/tailgates", headers=headers, json={"game_id": 1, "title": "x", "location": "y"})
    assert r.status_code == 403


def test_logout_revokes_session(client, approved_member):
    headers, _, _ = approved_member
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/me", headers=headers).status_code == 401


def test_password_change_signs_out_other_devices(client, approved_member):
    laptop, mail, _ = approved_member
    phone = login(client, mail, "goFalcons1")
    r = client.post("/api/me/password", headers=laptop,
                    json={"current_password": "goFalcons1", "new_password": "newPassword9"})
    assert r.status_code == 200
    assert client.get("/api/me", headers=laptop).status_code == 200   # this device stays in
    assert client.get("/api/me", headers=phone).status_code == 401    # others are out


def test_revoking_an_account_takes_effect_immediately(client, admin, approved_member):
    headers, _, user_id = approved_member
    client.post(f"/api/admin/accounts/{user_id}/reject", headers=admin)
    assert client.get("/api/me", headers=headers).status_code == 401


def test_password_reset_flow(client, approved_member):
    headers, mail, _ = approved_member
    r = client.post("/api/auth/forgot", json={"email": mail})
    unknown = client.post("/api/auth/forgot", json={"email": "nobody@example.com"})
    assert r.json() == unknown.json()  # can't be used to discover accounts

    newest = sorted(glob.glob(str(OUTBOX_DIR / "*reset*")))[-1]
    msg = email.message_from_bytes(open(newest, "rb").read(), policy=policy.default)
    link = next(line for line in msg.get_body().get_content().splitlines() if "token=" in line)
    token = link.strip().split("token=")[1]

    assert client.post("/api/auth/reset", json={"token": token, "new_password": "brandNew99"}).status_code == 200
    assert client.post("/api/auth/reset", json={"token": token, "new_password": "again12345"}).status_code == 400
    assert client.get("/api/me", headers=headers).status_code == 401  # reset signs out everywhere
    login(client, mail, "brandNew99")


def test_login_lockout_after_repeated_failures(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 429


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
