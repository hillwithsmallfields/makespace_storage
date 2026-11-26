"""Tests of the API server's Keycloak authentication (no Keycloak needed).

Run from the top of the repository with:  python3 -m pytest pytests
"""

import time

import jwt
import mongomock
import pymongo
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ISSUER_BASE = "https://id.example.org"
ISSUER = f"{ISSUER_BASE}/realms/makespace"

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_token(roles=("user",), membership="1234", key=KEY, alg="RS256", **overrides):
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": ["storage-api", "account"], "sub": "abc-123",
              "typ": "Bearer", "azp": "storage-web", "iat": now, "exp": now + 300,
              "preferred_username": "alice", "name": "Alice Test", "email": "alice@example.org",
              "resource_access": {"storage-api": {"roles": list(roles)}}}
    if membership is not None:
        claims["membership_number"] = membership
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm=alg)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_URL", ISSUER_BASE)
    monkeypatch.setattr(pymongo, "MongoClient", mongomock.MongoClient)
    from src.backend import auth, storage_manager as sm
    auth.get_settings.cache_clear()
    auth.get_verifier.cache_clear()
    # Use our test key instead of fetching Keycloak's.
    monkeypatch.setattr(auth.TokenVerifier, "signing_key",
                        lambda self, token: KEY.public_key())
    sm._database_client = None
    sm._types = sm._stock_types = sm._inventory = sm._stock = None
    yield TestClient(sm.storage_manager)
    auth.get_settings.cache_clear()
    auth.get_verifier.cache_clear()


def write_routes():
    from src.backend import storage_manager as sm
    return [(method, route.path)
            for route in sm.storage_manager.routes
            if isinstance(route, APIRoute)
            for method in route.methods
            if method not in ("GET", "HEAD", "OPTIONS")]


def test_there_are_write_routes():
    assert ("POST", "/move") in write_routes()


@pytest.mark.parametrize("method,path", write_routes())
def test_every_write_route_needs_login(api, method, path):
    url = path.replace("{item}", "x")
    response = api.request(method, url)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer")


def test_reads_need_no_login(api):
    assert api.get("/").status_code == 200
    assert api.get("/sites").json() == {"sites": []}
    assert api.get("/whoami").json() == {"authenticated": False, "level": None}


def test_standard_user(api):
    me = api.get("/whoami", headers=bearer(make_token())).json()
    assert me["authenticated"] and me["username"] == "alice"
    assert me["level"] == "user"
    assert me["membership_number"] == "1234"
    response = api.post("/update_inventory_item", headers=bearer(make_token()),
                        json={"item_name": "Kettle", "colour": "red"})
    assert response.status_code == 200


def test_admin(api):
    me = api.get("/whoami", headers=bearer(make_token(roles=["admin", "user"], membership="42"))).json()
    assert me["level"] == "admin"
    assert me["membership_number"] == "42"


def test_service_account_has_no_membership_number(api):
    token = make_token(membership=None, preferred_username="service-account-storage-service")
    me = api.get("/whoami", headers=bearer(token)).json()
    assert me["membership_number"] is None
    assert me["is_service_account"]


def test_admin_only_routes(api):
    csv = "name,parent,preposition\nroom,,in\n"
    assert api.post("/load-types", content=csv, headers=bearer(make_token())).status_code == 403
    assert api.post("/load-types", content=csv,
                    headers=bearer(make_token(roles=["admin"]))).status_code == 200


def test_logged_in_without_storage_role_cannot_write(api):
    token = make_token(roles=[])
    assert api.get("/whoami", headers=bearer(token)).json()["level"] is None
    response = api.post("/update_inventory_item", headers=bearer(token), json={"item_name": "x"})
    assert response.status_code == 403


@pytest.mark.parametrize("token", [
    make_token(exp=int(time.time()) - 120),             # expired
    make_token(aud="some-other-api"),                   # wrong audience
    make_token(iss="https://evil.example/realms/makespace"),  # wrong issuer
    make_token(typ="ID"),                               # an ID token
    make_token(key=OTHER_KEY),                          # wrong signature
    "not.a.token",
], ids=["expired", "audience", "issuer", "id-token", "signature", "garbage"])
def test_bad_tokens_rejected_even_for_reads(api, token):
    assert api.get("/whoami", headers=bearer(token)).status_code == 401
    assert api.post("/update_inventory_item", headers=bearer(token),
                    json={"item_name": "x"}).status_code == 401


def test_token_from_unknown_key_is_401_not_503(api, monkeypatch):
    from src.backend import auth

    def unknown_kid(self, token):
        raise jwt.PyJWKClientError("Unable to find a signing key that matches: 'xyz'")
    monkeypatch.setattr(auth.TokenVerifier, "signing_key", unknown_kid)
    assert api.get("/whoami", headers=bearer(make_token())).status_code == 401


def test_keycloak_unreachable_is_503(api, monkeypatch):
    from src.backend import auth

    def unreachable(self, token):
        raise jwt.PyJWKClientConnectionError("Fail to fetch data from the url")
    monkeypatch.setattr(auth.TokenVerifier, "signing_key", unreachable)
    assert api.get("/whoami", headers=bearer(make_token())).status_code == 503


def test_unsigned_token_rejected(api):
    claims = jwt.decode(make_token(), options={"verify_signature": False})
    unsigned = jwt.encode(claims, None, algorithm="none")
    assert api.get("/whoami", headers=bearer(unsigned)).status_code == 401


def test_fails_closed_without_keycloak(api, monkeypatch):
    from src.backend import auth
    monkeypatch.delenv("KEYCLOAK_URL")
    auth.get_settings.cache_clear()
    auth.get_verifier.cache_clear()
    assert api.get("/sites").status_code == 200
    assert api.post("/update_inventory_item", json={"item_name": "x"}).status_code == 503
    assert api.get("/whoami", headers=bearer(make_token())).status_code == 503
