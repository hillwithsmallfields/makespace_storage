#!/usr/bin/env python3

"""Python access to the Makespace storage API, with Keycloak authentication.

Reading needs no login; changing anything needs a Keycloak access
token, which this module gets and refreshes for you.  It needs only
the `requests` package, so it can be copied into other projects.

Three ways to authenticate
--------------------------

Anonymous (read only)::

    client = StorageClient("http://127.0.0.1:8000")
    print(client.where("soldering iron 3"))

As another service, using a Keycloak client with a service account
(the "client credentials" grant)::

    client = StorageClient(
        "http://127.0.0.1:8000",
        auth=ClientCredentials("https://id.makespace.org", "storage-service", secret))
    client.move("soldering iron 3", "Electronics shelf 2")

As a person running a script (the "device authorization" grant: it
prints a URL to open in a browser, then waits for you to log in)::

    client = StorageClient("http://127.0.0.1:8000",
                           auth=DeviceLogin("https://id.makespace.org"))
    print(client.whoami())   # {'username': ..., 'level': 'admin', 'membership_number': '42', ...}

Or let `StorageClient.from_environment()` choose, from the variables
STORAGE_API_URL, KEYCLOAK_URL, KEYCLOAK_REALM, STORAGE_CLIENT_ID and
STORAGE_CLIENT_SECRET (see its docstring).

Command line
------------

    storage_client.py whoami [--login]
    storage_client.py token                    # print an access token, for curl
    storage_client.py get /where/Fridge
    storage_client.py load types dev-data/initial-types.csv
    storage_client.py dump inventory > inventory.csv
"""

import argparse
import json
import os
import sys
import threading
import time
from typing import Any, Optional
from urllib.parse import quote

import requests

DEFAULT_REALM = "makespace"
DEFAULT_TIMEOUT = 30
# Get a new access token when the current one has less than this long left.
EXPIRY_MARGIN_SECONDS = 30


class StorageAPIError(Exception):
    """The API server refused a request or failed."""

    def __init__(self, status_code: int, detail: Any, response: requests.Response):
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail
        self.response = response


class AuthenticationError(Exception):
    """Could not get a token from Keycloak."""


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class KeycloakAuth(requests.auth.AuthBase):
    """Base class: adds a Keycloak bearer token to each request,
    getting or refreshing the token as needed.

    Subclasses implement `_fetch_new_token`."""

    def __init__(self, keycloak_url: str, client_id: str,
                 realm: str = DEFAULT_REALM, timeout: float = DEFAULT_TIMEOUT):
        base = keycloak_url.rstrip("/")
        self.client_id = client_id
        self.timeout = timeout
        self.token_url = f"{base}/realms/{realm}/protocol/openid-connect/token"
        self.device_url = f"{base}/realms/{realm}/protocol/openid-connect/auth/device"
        self._token: Optional[dict[str, Any]] = None
        self._lock = threading.Lock()

    # -- the token itself --

    def access_token(self, force_new: bool = False) -> str:
        """Return a currently valid access token."""
        with self._lock:
            if force_new or not self._still_valid():
                if not (self._token and self._try_refresh()):
                    self._token = self._stamp(self._fetch_new_token())
            return self._token["access_token"]

    def invalidate(self) -> None:
        """Forget the access token (but keep any refresh token)."""
        with self._lock:
            if self._token:
                self._token["expires_at"] = 0

    def _still_valid(self) -> bool:
        return bool(self._token
                    and self._token.get("expires_at", 0) - EXPIRY_MARGIN_SECONDS > time.time())

    @staticmethod
    def _stamp(token: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        token["expires_at"] = now + int(token.get("expires_in", 60))
        token["refresh_expires_at"] = now + int(token.get("refresh_expires_in") or 0)
        return token

    def _client_auth(self) -> dict[str, str]:
        """Form fields identifying this client to Keycloak."""
        return {"client_id": self.client_id}

    def _post_token(self, **fields) -> requests.Response:
        return requests.post(self.token_url, timeout=self.timeout,
                             data={**fields, **self._client_auth()})

    def _try_refresh(self) -> bool:
        refresh = self._token.get("refresh_token")
        if not refresh or self._token.get("refresh_expires_at", 0) < time.time():
            return False
        response = self._post_token(grant_type="refresh_token", refresh_token=refresh)
        if response.status_code != 200:
            return False
        self._token = self._stamp(response.json())
        return True

    def _fetch_new_token(self) -> dict[str, Any]:
        raise NotImplementedError

    # -- requests.auth.AuthBase --

    def __call__(self, request: requests.PreparedRequest) -> requests.PreparedRequest:
        request.headers["Authorization"] = f"Bearer {self.access_token()}"
        return request


class ClientCredentials(KeycloakAuth):
    """Authenticate as a service, with a confidential Keycloak client
    that has "Service accounts roles" enabled.  The level of access is
    set by the storage-api client roles given to its service account."""

    def __init__(self, keycloak_url: str, client_id: str, client_secret: str,
                 realm: str = DEFAULT_REALM, timeout: float = DEFAULT_TIMEOUT):
        super().__init__(keycloak_url, client_id, realm, timeout)
        self.client_secret = client_secret

    def _client_auth(self) -> dict[str, str]:
        return {"client_id": self.client_id, "client_secret": self.client_secret}

    def _try_refresh(self) -> bool:
        return False            # Keycloak gives no refresh token for this grant

    def _fetch_new_token(self) -> dict[str, Any]:
        response = self._post_token(grant_type="client_credentials")
        if response.status_code != 200:
            raise AuthenticationError(f"Keycloak refused client {self.client_id}: "
                                      f"{response.status_code} {response.text}")
        return response.json()


class DeviceLogin(KeycloakAuth):
    """Authenticate as a person, by logging in through a web browser
    (OAuth 2 device authorization grant).  Uses the public client
    "storage-cli" by default.

    `prompt` is called with the verification URL and user code; by
    default it prints them on stderr.  If `cache_file` is given, the
    refresh token is kept there (readable only by you) so that later
    runs don't need a new login until the Keycloak session ends."""

    def __init__(self, keycloak_url: str, client_id: str = "storage-cli",
                 realm: str = DEFAULT_REALM, timeout: float = DEFAULT_TIMEOUT,
                 prompt=None, cache_file: Optional[str] = None):
        super().__init__(keycloak_url, client_id, realm, timeout)
        self.prompt = prompt or self._print_prompt
        self.cache_file = cache_file
        if cache_file and os.path.exists(cache_file):
            try:
                with open(cache_file) as instream:
                    self._token = json.load(instream)
            except (OSError, ValueError):
                self._token = None

    @staticmethod
    def _print_prompt(url: str, user_code: str) -> None:
        print(f"To log in to the storage system, open {url}\n"
              f"(and check that it shows the code {user_code})", file=sys.stderr)

    def _save(self) -> None:
        if self.cache_file and self._token:
            os.makedirs(os.path.dirname(os.path.abspath(self.cache_file)), exist_ok=True)
            descriptor = os.open(self.cache_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w") as outstream:
                json.dump(self._token, outstream)

    def _try_refresh(self) -> bool:
        worked = super()._try_refresh()
        if worked:
            self._save()
        return worked

    def _fetch_new_token(self) -> dict[str, Any]:
        response = requests.post(self.device_url, timeout=self.timeout,
                                 data={**self._client_auth(), "scope": "openid"})
        if response.status_code != 200:
            raise AuthenticationError(f"Could not start device login: "
                                      f"{response.status_code} {response.text}")
        device = response.json()
        self.prompt(device.get("verification_uri_complete") or device["verification_uri"],
                    device["user_code"])
        interval = int(device.get("interval", 5))
        deadline = time.time() + int(device.get("expires_in", 600))
        while time.time() < deadline:
            time.sleep(interval)
            response = self._post_token(grant_type="urn:ietf:params:oauth:grant-type:device_code",
                                        device_code=device["device_code"])
            if response.status_code == 200:
                self._token = self._stamp(response.json())
                self._save()
                return self._token
            error = response.json().get("error")
            if error == "slow_down":
                interval += 5
            elif error != "authorization_pending":
                raise AuthenticationError(f"Login failed: {response.text}")
        raise AuthenticationError("Timed out waiting for login")


class StaticToken(requests.auth.AuthBase):
    """Use an access token that you got some other way."""

    def __init__(self, token: str):
        self.token = token

    def access_token(self, force_new: bool = False) -> str:
        return self.token

    def invalidate(self) -> None:
        pass

    def __call__(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        return request


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------

def _q(name: Any) -> str:
    """Quote an item name for use as a path segment."""
    return quote(str(name), safe="")


class StorageClient:
    """Wrapper for the storage API.  Methods return the decoded JSON
    (or text, for CSV dumps) and raise `StorageAPIError` on failure.

    With `auth=None` only reads work; writes raise StorageAPIError 401."""

    def __init__(self, api_url: str = "http://127.0.0.1:8000",
                 auth: Optional[requests.auth.AuthBase] = None,
                 timeout: float = DEFAULT_TIMEOUT):
        self.api_url = api_url.rstrip("/")
        self.auth = auth
        self.timeout = timeout
        self.session = requests.Session()

    @classmethod
    def from_environment(cls, interactive: bool = False) -> "StorageClient":
        """Make a client configured by environment variables:

        STORAGE_API_URL       default http://127.0.0.1:8000
        KEYCLOAK_URL          Keycloak's base URL; if unset, the client is anonymous
        KEYCLOAK_REALM        default "makespace"
        STORAGE_CLIENT_ID     Keycloak client ID
        STORAGE_CLIENT_SECRET if set, log in as that client's service account;
                              otherwise, if `interactive`, log in as a person
                              with the device flow (client default "storage-cli")
        """
        api = os.environ.get("STORAGE_API_URL", "http://127.0.0.1:8000")
        keycloak = os.environ.get("KEYCLOAK_URL")
        realm = os.environ.get("KEYCLOAK_REALM", DEFAULT_REALM)
        client_id = os.environ.get("STORAGE_CLIENT_ID")
        secret = os.environ.get("STORAGE_CLIENT_SECRET")
        auth = None
        if keycloak and secret:
            auth = ClientCredentials(keycloak, client_id or "storage-service", secret, realm)
        elif keycloak and interactive:
            cache = os.path.join(os.path.expanduser("~"), ".cache", "makespace-storage", "token.json")
            auth = DeviceLogin(keycloak, client_id or "storage-cli", realm, cache_file=cache)
        return cls(api, auth)

    # -- generic requests --

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Send a request, retrying once with a fresh token if the API
        says the token is no good (e.g. it expired in transit)."""
        kwargs.setdefault("timeout", self.timeout)
        url = f"{self.api_url}/{path.lstrip('/')}"
        response = self.session.request(method, url, auth=self.auth, **kwargs)
        if response.status_code == 401 and self.auth is not None:
            self.auth.invalidate()
            response = self.session.request(method, url, auth=self.auth, **kwargs)
        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise StorageAPIError(response.status_code, detail, response)
        return response

    def get(self, path: str, **params) -> Any:
        return self.request("GET", path, params=params).json()

    def post_json(self, path: str, payload: Optional[dict] = None) -> Any:
        return self.request("POST", path, json=payload or {}).json()

    def post_form(self, path: str, fields: Optional[dict] = None) -> Any:
        return self.request("POST", path, data=fields or {}).json()

    # -- reading (no login needed) --

    def whoami(self) -> dict:
        """Who the API thinks we are: username, level, membership_number..."""
        return self.get("/whoami")

    def sites(self) -> list[str]:
        return self.get("/sites")["sites"]

    def item(self, name_or_barcode) -> dict:
        return self.get(f"/item/{_q(name_or_barcode)}")

    def where(self, name_or_barcode) -> dict:
        return self.get(f"/where/{_q(name_or_barcode)}")

    def details(self, name_or_barcode) -> dict:
        return self.get(f"/details/{_q(name_or_barcode)}")

    def contents(self, location, recursive: bool = False) -> dict:
        return self.get(f"/contents/{_q(location)}", recursive=recursive)

    def search(self, pattern: str) -> dict:
        return self.get("/search", pattern=pattern)

    def attribute(self, item, attribute: str):
        return self.get(f"/attribute/{_q(item)}/{_q(attribute)}").get(attribute)

    def stock_levels(self, stock_type: str) -> dict:
        return self.get(f"/levels/{_q(stock_type)}")["levels"]

    def dump(self, kind: str) -> str:
        """CSV text of a whole collection: kind is one of
        'types', 'stock-types', 'inventory', 'stock'."""
        return self.request("GET", f"/dump-{kind}").text

    # -- writing (login needed) --

    def move(self, item, location, quantity: int = 1) -> dict:
        return self.post_form("/move", {"item": item, "location": location,
                                        "quantity": quantity})

    def update_inventory_item(self, item_name: str, **fields) -> dict:
        return self.post_json("/update_inventory_item", {"item_name": item_name, **fields})

    def update_stock(self, stock_item: str, location, action: str, delta: int = 1,
                     existing: int = 0) -> dict:
        """action is '+', '-' or '=' (set the level to `delta`)."""
        return self.post_form("/update_stock", {
            "stock_item": stock_item, "location": location, "action": action,
            "delta": delta, "existing": existing, "referring_page": ""})

    # -- admin only --

    def load(self, kind: str, csv_text: str) -> dict:
        """Load CSV rows into a collection (admin only).
        kind is one of 'types', 'stock-types', 'inventory', 'stock'."""
        return self.request("POST", f"/load-{kind}", data=csv_text.encode("utf-8"),
                            headers={"Content-Type": "text/csv"}).json()

    def delete(self, item) -> dict:
        """Delete an inventory item (admin only)."""
        return self.request("POST", f"/delete/{_q(item)}").json()


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--login", action="store_true",
                        help="log in as a person (device flow) if no client secret is set")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("whoami", help="show who the API thinks you are")
    sub.add_parser("token", help="print an access token")
    get = sub.add_parser("get", help="GET an API path and print the JSON")
    get.add_argument("path")
    load = sub.add_parser("load", help="load a CSV file into a collection (admin)")
    load.add_argument("kind", choices=["types", "stock-types", "inventory", "stock"])
    load.add_argument("file")
    dump = sub.add_parser("dump", help="print a collection as CSV")
    dump.add_argument("kind", choices=["types", "stock-types", "inventory", "stock"])
    args = parser.parse_args()

    client = StorageClient.from_environment(interactive=args.login)
    try:
        match args.command:
            case "whoami":
                print(json.dumps(client.whoami(), indent=2))
            case "token":
                if client.auth is None:
                    print("No credentials: set KEYCLOAK_URL and STORAGE_CLIENT_SECRET, or use --login",
                          file=sys.stderr)
                    return 1
                print(client.auth.access_token())
            case "get":
                print(json.dumps(client.get(args.path), indent=2))
            case "load":
                with open(args.file, encoding="utf-8") as instream:
                    print(json.dumps(client.load(args.kind, instream.read())))
            case "dump":
                sys.stdout.write(client.dump(args.kind))
    except (StorageAPIError, AuthenticationError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
