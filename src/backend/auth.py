"""Keycloak authentication and authorisation for the API server.

Policy
------

* Read requests (GET, HEAD, OPTIONS) can be made anonymously.
* Every other request (POST, PUT, PATCH, DELETE) must carry a valid
  Keycloak access token in an ``Authorization: Bearer ...`` header, and
  the token must give the caller at least the standard user role.
* A request that carries a token which is invalid or expired is
  rejected with 401 whatever its method, so that callers find out
  about bad tokens rather than silently being treated as anonymous.

The policy is applied to every route by `enforce_write_policy`, which
`storage_manager.py` installs as an application-wide dependency, so a
new write endpoint is protected even if its author forgets about
authentication.

Using the caller's identity in an API function
-----------------------------------------------

Declare a parameter with one of these annotated types, and FastAPI
fills it in (the token is verified once per request however many
times it is asked for)::

    @storage_manager.get("/something")
    def something(user: auth.CurrentUser):      # User, or None if anonymous
        ...

    @storage_manager.post("/something")
    def change_something(user: auth.LoggedInUser):   # always a User with a level
        print(user.username, user.level, user.membership_number)

    @storage_manager.post("/dangerous")
    def dangerous(user: auth.AdminUser):         # 403 unless an admin
        ...

Functions that are not endpoints, but are called from one, can use
``auth.current_user(request)`` given the Starlette request.

Configuration (environment variables)
-------------------------------------

KEYCLOAK_URL
    Base URL of Keycloak *as browsers see it*, e.g.
    ``https://id.makespace.org``.  The ``iss`` claim of every token
    must be ``{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}``.
KEYCLOAK_INTERNAL_URL
    Base URL this server uses to fetch Keycloak's signing keys, if
    different (e.g. ``http://keycloak:8080`` inside docker compose).
KEYCLOAK_REALM
    Realm name; default ``makespace``.
KEYCLOAK_API_CLIENT
    Client ID representing this API in Keycloak; default
    ``storage-api``.  Tokens must name it in their ``aud`` claim, and
    the storage roles are client roles of it.
STORAGE_USER_ROLE, STORAGE_ADMIN_ROLE
    Names of those client roles; defaults ``user`` and ``admin``.

If KEYCLOAK_URL is not set, anonymous reads still work but every
write is refused with 503, so the server fails closed.
"""

import dataclasses
import enum
import functools
import logging
import os
from typing import Annotated, Any, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Keycloak signs with RS256 by default; allow the other asymmetric
# algorithms it can be configured to use, but never "none" or HMAC.
ALLOWED_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512",
                      "ES256", "ES384", "ES512"]

# Tolerance for clock differences between this server and Keycloak.
CLOCK_SKEW_SECONDS = 30


class UserLevel(str, enum.Enum):
    """The levels of user that the storage system knows about."""
    USER = "user"
    ADMIN = "admin"


@dataclasses.dataclass(frozen=True)
class User:
    """The authenticated caller of an API request.

    ``level`` is None for someone who has logged in but has no storage
    role (only possible if the realm's default roles are changed);
    such a caller may read but not write.

    ``membership_number`` is None for service accounts and for people
    whose Keycloak account has no membership number recorded.
    """
    subject: str                        # Keycloak's stable user ID
    username: str
    level: Optional[UserLevel]
    membership_number: Optional[str]
    name: Optional[str] = None
    email: Optional[str] = None
    client_id: Optional[str] = None     # which Keycloak client got the token
    roles: frozenset = frozenset()      # all storage-api client roles
    is_service_account: bool = False

    @property
    def is_admin(self) -> bool:
        return self.level == UserLevel.ADMIN

    @property
    def is_user(self) -> bool:
        """True for standard users and admins."""
        return self.level is not None

    def as_dict(self) -> dict[str, Any]:
        """A JSON-friendly summary, as returned by /whoami."""
        return {'authenticated': True,
                'username': self.username,
                'level': self.level.value if self.level else None,
                'membership_number': self.membership_number,
                'name': self.name,
                'email': self.email,
                'client_id': self.client_id,
                'is_service_account': self.is_service_account,
                'roles': sorted(self.roles)}


@dataclasses.dataclass(frozen=True)
class Settings:
    issuer: Optional[str]
    jwks_url: Optional[str]
    api_client: str
    user_role: str
    admin_role: str

    @classmethod
    def from_environment(cls) -> "Settings":
        public = os.environ.get("KEYCLOAK_URL", "").rstrip("/")
        internal = os.environ.get("KEYCLOAK_INTERNAL_URL", "").rstrip("/") or public
        realm = os.environ.get("KEYCLOAK_REALM", "makespace")
        return cls(
            issuer=f"{public}/realms/{realm}" if public else None,
            jwks_url=(f"{internal}/realms/{realm}/protocol/openid-connect/certs"
                      if internal else None),
            api_client=os.environ.get("KEYCLOAK_API_CLIENT", "storage-api"),
            user_role=os.environ.get("STORAGE_USER_ROLE", "user"),
            admin_role=os.environ.get("STORAGE_ADMIN_ROLE", "admin"))


def user_from_claims(claims: dict[str, Any], settings: Settings) -> User:
    """Build a `User` from the claims of a verified access token."""
    roles = frozenset(claims.get("resource_access", {})
                      .get(settings.api_client, {})
                      .get("roles", []))
    level = (UserLevel.ADMIN if settings.admin_role in roles
             else UserLevel.USER if settings.user_role in roles
             else None)
    username = claims.get("preferred_username") or claims["sub"]
    membership = claims.get("membership_number")
    return User(subject=claims["sub"],
                username=username,
                level=level,
                membership_number=str(membership) if membership not in (None, "") else None,
                name=claims.get("name"),
                email=claims.get("email"),
                client_id=claims.get("azp"),
                roles=roles,
                is_service_account=username.startswith("service-account-"))


class TokenVerifier:
    """Checks Keycloak access tokens against the realm's published keys."""

    def __init__(self, settings: Settings):
        self.settings = settings
        # PyJWKClient caches the keys, and fetches them again when it
        # meets a key ID it doesn't know (i.e. after key rotation).
        self._jwks = jwt.PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=3600)

    def signing_key(self, token: str):
        return self._jwks.get_signing_key_from_jwt(token).key

    def verify(self, token: str) -> dict[str, Any]:
        """Return the token's claims, or raise a jwt.PyJWTError."""
        claims = jwt.decode(token,
                            key=self.signing_key(token),
                            algorithms=ALLOWED_ALGORITHMS,
                            audience=self.settings.api_client,
                            issuer=self.settings.issuer,
                            leeway=CLOCK_SKEW_SECONDS,
                            options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        # Keycloak marks access tokens with typ "Bearer"; refuse ID
        # and refresh tokens even if they somehow had the right audience.
        if claims.get("typ", "Bearer") != "Bearer":
            raise jwt.InvalidTokenError("not an access token")
        return claims


@functools.cache
def get_settings() -> Settings:
    return Settings.from_environment()


@functools.cache
def get_verifier() -> Optional[TokenVerifier]:
    settings = get_settings()
    if not (settings.issuer and settings.jwks_url):
        logger.warning("KEYCLOAK_URL is not set: all write requests will be refused")
        return None
    return TokenVerifier(settings)


# auto_error=False because anonymous requests are allowed; declaring
# the scheme also gives the /docs page an "Authorize" button.
_bearer = HTTPBearer(auto_error=False,
                     description="A Keycloak access token for the storage-api audience")


def _unauthorised(detail: str, error: Optional[str] = None) -> HTTPException:
    challenge = "Bearer" + (f' error="{error}"' if error else "")
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                         detail=detail,
                         headers={"WWW-Authenticate": challenge})


def optional_user(request: Request,
                  credentials: Annotated[Optional[HTTPAuthorizationCredentials],
                                         Depends(_bearer)]) -> Optional[User]:
    """Dependency: the caller as a `User`, or None if no token was sent."""
    user = None
    if credentials is not None:
        verifier = get_verifier()
        if verifier is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="Authentication is not configured on this server")
        try:
            claims = verifier.verify(credentials.credentials)
        except jwt.PyJWKClientConnectionError as err:
            logger.error("Could not get Keycloak signing keys: %s", err)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="Cannot check tokens at the moment") from err
        except jwt.PyJWKClientError as err:
            # e.g. signed with a key our Keycloak doesn't have
            raise _unauthorised(f"Invalid access token: {err}", "invalid_token") from err
        except jwt.ExpiredSignatureError as err:
            raise _unauthorised("Access token has expired", "invalid_token") from err
        except jwt.PyJWTError as err:
            raise _unauthorised(f"Invalid access token: {err}", "invalid_token") from err
        user = user_from_claims(claims, get_settings())
    request.state.user = user
    return user


def require_user(user: Annotated[Optional[User], Depends(optional_user)]) -> User:
    """Dependency: the caller, who must be at least a standard user."""
    if user is None:
        if get_verifier() is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="Authentication is not configured on this server")
        raise _unauthorised("You must log in to do this")
    if not user.is_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"{user.username} is not a storage system user")
    return user


def require_admin(user: Annotated[User, Depends(require_user)]) -> User:
    """Dependency: the caller, who must be a storage admin."""
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only storage admins can do this")
    return user


def enforce_write_policy(request: Request,
                         user: Annotated[Optional[User], Depends(optional_user)]) -> None:
    """Application-wide dependency: anyone may read, only users may write."""
    if request.method not in SAFE_METHODS:
        require_user(user)


def current_user(request: Request) -> Optional[User]:
    """The caller of the request being handled, or None if anonymous.

    For use in helper functions that are given the request; endpoint
    functions should declare a `CurrentUser` parameter instead."""
    return getattr(request.state, "user", None)


def user_level(request: Request) -> Optional[UserLevel]:
    """The level of the caller of this request, or None if anonymous."""
    user = current_user(request)
    return user.level if user else None


CurrentUser = Annotated[Optional[User], Depends(optional_user)]
LoggedInUser = Annotated[User, Depends(require_user)]
AdminUser = Annotated[User, Depends(require_admin)]
