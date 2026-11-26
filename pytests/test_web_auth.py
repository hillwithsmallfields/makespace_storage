"""Tests of the web server's login handling (no Keycloak or API needed).

Run from the top of the repository with:  python3 -m pytest pytests
"""

import base64
import json
import os
import sys
import time
from urllib.parse import parse_qs, urlsplit

import pytest

WEB = "http://storage.test"
KEYCLOAK = "https://id.example.org"

os.environ.update({"KEYCLOAK_URL": KEYCLOAK,
                   "KEYCLOAK_INTERNAL_URL": "http://keycloak:8080",
                   "STORAGE_WEB_CLIENT_SECRET": "web-secret",
                   "FLASK_SECRET_KEY": "test-secret",
                   "STORAGE_WEB_URL": WEB})
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "webpages"))

import web_auth   # noqa: E402
import webpages   # noqa: E402


def fake_token(roles=("user",), membership="1234", username="alice"):
    """An unsigned JWT-shaped token: the web server doesn't check signatures."""
    def part(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    return ".".join([part({"alg": "RS256"}),
                     part({"preferred_username": username, "name": username.title(),
                           "membership_number": membership,
                           "resource_access": {"storage-api": {"roles": list(roles)}}}),
                     "sig"])


@pytest.fixture
def client():
    webpages.app.config["TESTING"] = True
    return webpages.app.test_client()


def log_in(client, expires_in=300, **kwargs):
    with client.session_transaction() as session:
        session["access_token"] = fake_token(**kwargs)
        session["refresh_token"] = "refresh-1"
        session["expires_at"] = time.time() + expires_in
        session["refresh_expires_at"] = time.time() + 1800
        session["user"] = web_auth._summarise(session["access_token"])


def test_anonymous_post_goes_to_login(client):
    response = client.post("/move", data={"current_item": "a", "destination": "b"},
                           headers={"Referer": f"{WEB}/item/Kettle"})
    assert response.status_code == 303
    assert response.headers["Location"] == "/login?next=%2Fitem%2FKettle"


def test_anonymous_post_from_elsewhere_goes_home_after_login(client):
    response = client.post("/move", headers={"Referer": "https://evil.example/x"})
    assert response.headers["Location"] == "/login?next=%2F"


def test_logged_in_post_passes_gate_and_forwards_token(client, monkeypatch):
    sent = {}

    def fake_post(url, data=None, headers=None, **kwargs):
        sent.update(url=url, headers=headers)
        raise RuntimeError("stop here")         # we only care what was sent
    monkeypatch.setattr(webpages.requests, "post", fake_post)
    log_in(client)
    with pytest.raises(RuntimeError):
        client.post("/move", data={"current_item": "a", "destination": "b"},
                    headers={"Origin": WEB})
    assert sent["url"].endswith("/move")
    assert sent["headers"]["Authorization"].startswith("Bearer ")


def test_cross_site_post_refused(client):
    log_in(client)
    response = client.post("/move", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_account_without_storage_role_cannot_post(client):
    log_in(client, roles=[])
    assert client.post("/move", headers={"Origin": WEB}).status_code == 403


def test_login_redirects_to_keycloak_with_pkce(client):
    response = client.get("/login?next=/item/Kettle")
    location = urlsplit(response.headers["Location"])
    assert f"{location.scheme}://{location.netloc}" == KEYCLOAK
    assert location.path == "/realms/makespace/protocol/openid-connect/auth"
    query = parse_qs(location.query)
    assert query["client_id"] == ["storage-web"]
    assert query["redirect_uri"] == [f"{WEB}/auth/callback"]
    assert query["code_challenge_method"] == ["S256"]
    with client.session_transaction() as session:
        assert session["after_login"] == "/item/Kettle"


def test_cancelled_login_goes_back_quietly(client):
    with client.session_transaction() as session:
        session["after_login"] = "/item/Kettle"
    response = client.get("/auth/callback?error=access_denied&state=whatever")
    assert response.status_code == 302
    assert response.headers["Location"] == "/item/Kettle"


def test_expired_access_token_is_refreshed(client, monkeypatch):
    calls = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"access_token": fake_token(username="alice2"), "expires_in": 300,
                    "refresh_token": "refresh-2", "refresh_expires_in": 1800}

    def fake_post(url, data=None, **kwargs):
        calls.append((url, data))
        return Response()
    monkeypatch.setattr(web_auth.requests, "post", fake_post)
    log_in(client, expires_in=-10)
    with webpages.app.test_request_context():
        from flask import session
        with client.session_transaction() as stored:
            session.update(stored)
        headers = web_auth.api_headers()
        assert headers["Authorization"] == f"Bearer {session['access_token']}"
        assert session["user"]["username"] == "alice2"
    url, data = calls[0]
    assert url == "http://keycloak:8080/realms/makespace/protocol/openid-connect/token"
    assert data["grant_type"] == "refresh_token" and data["refresh_token"] == "refresh-1"


def test_failed_refresh_logs_out(monkeypatch):
    class Response:
        status_code = 400
    monkeypatch.setattr(web_auth.requests, "post", lambda *a, **k: Response())
    with webpages.app.test_request_context():
        from flask import session
        session.update({"access_token": fake_token(), "refresh_token": "r",
                        "expires_at": 0, "refresh_expires_at": time.time() + 100})
        assert web_auth.current_user() is None
        assert "access_token" not in session


@pytest.mark.parametrize("target,expected", [
    ("/item/Kettle", "/item/Kettle"),
    ("/search?item=a%20b", "/search?item=a%20b"),
    (f"{WEB}/item/Kettle", "/item/Kettle"),
    ("https://evil.example/", "/"),
    ("//evil.example/", "/"),
    ("javascript:alert(1)", "/"),
    (None, "/"),
])
def test_safe_next(target, expected):
    assert web_auth._safe_next(target) == expected
