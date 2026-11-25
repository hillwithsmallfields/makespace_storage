"""Keycloak login for the web front-end.

People log in with the OpenID Connect authorisation code flow (with
PKCE).  The resulting access and refresh tokens are kept in the Flask
session cookie, and the access token is forwarded to the API server on
every call, so the API server sees, and checks, the real person.

Policy, matching the API server's:

* GET/HEAD/OPTIONS pages can be viewed without logging in.
* Any other request needs a logged-in storage user; anonymous visitors
  are sent to the login page, then back to the page they were on.

Configuration (environment variables)
-------------------------------------

KEYCLOAK_URL              Keycloak's base URL as browsers see it.
KEYCLOAK_INTERNAL_URL     Base URL this server uses to talk to Keycloak
                          directly, if different (e.g. http://keycloak:8080).
KEYCLOAK_REALM            Default ``makespace``.
STORAGE_WEB_CLIENT_ID     Default ``storage-web``.
STORAGE_WEB_CLIENT_SECRET That client's secret, from Keycloak.
FLASK_SECRET_KEY          Long random string used to sign session cookies.
STORAGE_WEB_URL           This server's address as browsers see it.
KEYCLOAK_API_CLIENT, STORAGE_USER_ROLE, STORAGE_ADMIN_ROLE
                          As for the API server; used only for display.
"""

import base64
import json
import logging
import os
import secrets
import time
from typing import Any, Optional
from urllib.parse import urlsplit

import requests
from authlib.integrations.base_client import OAuthError
from authlib.integrations.flask_client import OAuth
from flask import Flask, abort, redirect, request, session

logger = logging.getLogger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Refresh the access token when it has less than this long to run.
REFRESH_MARGIN_SECONDS = 30

PUBLIC_URL = os.environ.get("KEYCLOAK_URL", "").rstrip("/")
INTERNAL_URL = os.environ.get("KEYCLOAK_INTERNAL_URL", "").rstrip("/") or PUBLIC_URL
REALM = os.environ.get("KEYCLOAK_REALM", "makespace")
CLIENT_ID = os.environ.get("STORAGE_WEB_CLIENT_ID", "storage-web")
CLIENT_SECRET = os.environ.get("STORAGE_WEB_CLIENT_SECRET", "")
API_CLIENT = os.environ.get("KEYCLOAK_API_CLIENT", "storage-api")
USER_ROLE = os.environ.get("STORAGE_USER_ROLE", "user")
ADMIN_ROLE = os.environ.get("STORAGE_ADMIN_ROLE", "admin")


def _oidc(base: str, endpoint: str) -> str:
    return f"{base}/realms/{REALM}/protocol/openid-connect/{endpoint}"


TOKEN_URL = _oidc(INTERNAL_URL, "token")
LOGOUT_URL = _oidc(INTERNAL_URL, "logout")

oauth = OAuth()


def enabled() -> bool:
    return bool(PUBLIC_URL and CLIENT_SECRET)


def _claims_of(token: str) -> dict[str, Any]:
    """Read the claims of an access token without checking its signature.

    This is safe only because the tokens come straight from Keycloak's
    token endpoint; we use the claims only to label the page, and the
    API server checks the signature of every token it is given."""
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def _summarise(access_token: str) -> dict[str, Any]:
    claims = _claims_of(access_token)
    roles = claims.get("resource_access", {}).get(API_CLIENT, {}).get("roles", [])
    return {'username': claims.get("preferred_username"),
            'name': claims.get("name"),
            'membership_number': claims.get("membership_number"),
            'level': ("admin" if ADMIN_ROLE in roles
                      else "user" if USER_ROLE in roles
                      else None)}


def _store_tokens(token: dict[str, Any]) -> None:
    """Keep what we need of a token response in the session.

    The ID token is deliberately not kept, to keep the cookie small."""
    now = time.time()
    session['access_token'] = token['access_token']
    session['refresh_token'] = token.get('refresh_token')
    session['expires_at'] = now + int(token.get('expires_in', 60))
    session['refresh_expires_at'] = now + int(token.get('refresh_expires_in') or 0)
    session['user'] = _summarise(token['access_token'])


def _forget_tokens() -> None:
    for key in ('access_token', 'refresh_token', 'expires_at', 'refresh_expires_at', 'user'):
        session.pop(key, None)


def _refresh() -> bool:
    """Swap the refresh token for new tokens.  Returns whether it worked."""
    refresh_token = session.get('refresh_token')
    if not refresh_token or session.get('refresh_expires_at', 0) < time.time():
        return False
    try:
        response = requests.post(TOKEN_URL, timeout=10, data={
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET})
    except requests.RequestException as err:
        logger.warning("Could not reach Keycloak to refresh a token: %s", err)
        return False
    if response.status_code != 200:
        # Typically the Keycloak session has ended (logged out
        # elsewhere, or timed out); the person must log in again.
        return False
    _store_tokens(response.json())
    return True


def access_token() -> Optional[str]:
    """The current person's access token, refreshed if need be, or None."""
    if 'access_token' not in session:
        return None
    if session.get('expires_at', 0) - REFRESH_MARGIN_SECONDS > time.time():
        return session['access_token']
    if _refresh():
        return session['access_token']
    _forget_tokens()
    return None


def current_user() -> Optional[dict[str, Any]]:
    """A summary of the logged-in person (username, name, level,
    membership_number), or None if nobody is logged in."""
    return session.get('user') if access_token() else None


def api_headers() -> dict[str, str]:
    """Headers to send with a request to the API server."""
    token = access_token()
    return {'Authorization': f"Bearer {token}"} if token else {}


def _safe_next(target: Optional[str]) -> str:
    """Only allow redirects back into this site, to avoid open redirects."""
    if not target:
        return "/"
    parts = urlsplit(target)
    web = urlsplit(os.environ.get("STORAGE_WEB_URL", ""))
    if parts.netloc and parts.netloc != web.netloc:
        return "/"
    path = parts.path or "/"
    if not path.startswith("/") or path.startswith("//"):
        return "/"
    return path + (f"?{parts.query}" if parts.query else "")


def _same_origin(url: str) -> bool:
    web = urlsplit(os.environ.get("STORAGE_WEB_URL", ""))
    there = urlsplit(url)
    return (there.scheme, there.netloc) == (web.scheme, web.netloc)


def init_app(app: Flask, web_url: str) -> None:
    """Set up sessions, the login routes, and the write gate."""
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
    if not os.environ.get("FLASK_SECRET_KEY"):
        logger.warning("FLASK_SECRET_KEY not set: sessions will not survive a restart "
                       "or be shared between worker processes")
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        # Lax stops other sites' forms POSTing with our session cookie.
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=web_url.startswith("https:"),
        SESSION_COOKIE_NAME="storage_session")

    if enabled():
        oauth.init_app(app)
        oauth.register(
            "keycloak",
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            # The browser is sent to the public address; this server
            # talks to Keycloak directly at the internal one.
            authorize_url=_oidc(PUBLIC_URL, "auth"),
            access_token_url=TOKEN_URL,
            jwks_uri=_oidc(INTERNAL_URL, "certs"),
            issuer=f"{PUBLIC_URL}/realms/{REALM}",
            client_kwargs={'scope': "openid profile email",
                           'code_challenge_method': "S256"})
    else:
        logger.warning("Keycloak is not configured: nobody can log in, so the site is read-only")

    @app.route("/login")
    def login():
        if not enabled():
            abort(503, "Logging in is not configured on this server")
        session['after_login'] = _safe_next(request.args.get('next') or request.referrer)
        return oauth.keycloak.authorize_redirect(f"{web_url}/auth/callback")

    @app.route("/auth/callback")
    def auth_callback():
        if not enabled():
            abort(503)
        try:
            token = oauth.keycloak.authorize_access_token()
        except OAuthError as err:
            # e.g. they pressed "back" or cancelled on the login page,
            # or the login took so long that its state expired.
            logger.info("Login did not complete: %s", err)
            return redirect(session.pop('after_login', "/"))
        _store_tokens(token)
        return redirect(session.pop('after_login', "/"))

    @app.route("/logout")
    def logout():
        refresh_token = session.get('refresh_token')
        if enabled() and refresh_token:
            # End the Keycloak session too, from the back channel, so
            # the next visitor to this browser isn't silently logged in.
            try:
                requests.post(LOGOUT_URL, timeout=10, data={
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'refresh_token': refresh_token})
            except requests.RequestException as err:
                logger.warning("Could not tell Keycloak about logout: %s", err)
        session.clear()
        return redirect("/")

    @app.before_request
    def write_gate():
        if request.method in SAFE_METHODS:
            return None
        # Defence in depth against cross-site form posts.
        origin = request.headers.get("Origin")
        if origin and origin != "null" and not _same_origin(origin):
            abort(403, "Cross-site request refused")
        user = current_user()
        if user is None:
            if not enabled():
                abort(503, "This site is read-only: logging in is not configured")
            # Any form data is lost; take them back to the page the
            # form was on once they have logged in.
            back = _safe_next(request.referrer) if request.referrer and _same_origin(request.referrer) else "/"
            return redirect(f"/login?next={requests.utils.quote(back, safe='')}", code=303)
        if not user.get('level'):
            abort(403, "Your account does not have access to change the storage database")
        return None
