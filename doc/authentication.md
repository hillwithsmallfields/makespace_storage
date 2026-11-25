# Logins and access control (Keycloak)

Anyone can look things up, but changing anything needs a login.  Logins
are handled by [Keycloak](https://www.keycloak.org/).  The same rule is
enforced in two places:

* **API server**: GET, HEAD and OPTIONS requests are open to all.  Any
  other method needs an `Authorization: Bearer <access token>` header
  carrying a valid Keycloak access token.  The rule is installed as an
  application-wide FastAPI dependency (`auth.enforce_write_policy` in
  `src/backend/auth.py`), so new endpoints are covered automatically.
  The API is the real gatekeeper, because other services may call it
  directly.
* **Web server**: pages can be viewed without logging in.  A form
  submission (any non-GET request) from someone not logged in sends
  them to the Keycloak login page, then back to the page they were on.
  Logged-in people's access tokens are forwarded to the API, so the
  API sees, and checks, who is making each change.  Editing forms are
  hidden from people who are not logged in.

## Levels of user, and membership numbers

| Level      | How they get it                                      | Can do |
|------------|------------------------------------------------------|--------|
| anonymous  | not logged in                                        | read   |
| `user`     | every account in the realm (it is a default role)    | read, and change the database |
| `admin`    | the `admin` role of the `storage-api` client         | everything, including `/load-*` and `/delete/*` |

The roles are *client roles* of the `storage-api` client in Keycloak,
so they don't clash with other applications that might share the
realm.  `admin` includes `user`.

Each person's membership number is a Keycloak user attribute,
`membership_number`.  People can see theirs on their Keycloak account
page but only Keycloak admins can set it.  It is put into access
tokens as the claim `membership_number`.  Service accounts don't have
one.

## Using the caller's identity in API functions

```python
from . import auth

@storage_manager.post("/borrow/{item}")
def borrow(item: str, user: auth.LoggedInUser):
    # user.username, user.level (auth.UserLevel.USER or .ADMIN),
    # user.is_admin, user.membership_number (str or None), user.name, user.email
    ...

@storage_manager.get("/my-things")
def my_things(user: auth.CurrentUser):      # None if anonymous
    ...

@storage_manager.post("/purge")
def purge(user: auth.AdminUser):             # 403 unless admin
    ...
```

In a helper function that is given the Starlette `Request`, use
`auth.current_user(request)` or `auth.user_level(request)`.  The token
is checked only once per request, however many times it is asked for.

`GET /whoami` returns the caller's details, which is handy for checking
a token or a client setup.

## Keycloak clients in the realm

`docker/keycloak/makespace-realm.json` is imported the first time
Keycloak starts with an empty database.  It defines:

| Client                | Kind                          | Used by |
|-----------------------|-------------------------------|---------|
| `storage-api`         | no login flows; holds the roles | the API server (it is the token *audience*) |
| `storage-web`         | confidential, auth code + PKCE | the web server |
| `storage-cli`         | public, device login          | people running scripts (`storage_client.py --login`) |
| `storage-service`     | service account, `user` level | other programs that use the API |
| `storage-maintenance` | service account, `admin` level | `dev-scripts/loader` and other bulk jobs |

Secrets for the confidential clients come from `.env` at import time.
After the first start, change the realm in the admin console
(`$KEYCLOAK_URL/admin/`), not the file.  To give another service its
own credentials, copy `storage-service` in the admin console and
assign the new client's service account the `storage-api` role it
needs (Clients > the client > Service account roles > Assign role >
Filter by clients).

The `storage-api audience` mapper on each client puts `storage-api`
into the tokens' `aud` claim.  The API refuses tokens without it, so
any new client that calls the API needs the same mapper (or a client
scope that has it).

## Setting up

1. Copy `.env.example` to `.env` and set the new Keycloak variables.
   Generate each secret with `openssl rand -hex 32`.  Set
   `KEYCLOAK_URL` to the address browsers will use to reach Keycloak,
   e.g. `http://storage-pi.local:8080`.  This exact string becomes the
   token issuer that the API checks.
2. `docker compose up -d --build`.  Keycloak takes a minute or two to
   start the first time.
3. Add people:

   ```sh
   scripts/add-storage-user jbloggs jo@example.org Jo Bloggs 1234          # standard user
   scripts/add-storage-user asmith al@example.org Al Smith 99 admin       # storage admin
   ```

   Or use the admin console: Users > Add user, then set the
   `Membership number` field, and for admins, Role mapping > Assign
   role > Filter by clients > `storage-api` `admin`.
4. `dev-scripts/loader` loads the sample data using the
   `storage-maintenance` service account.

Plain HTTP is accepted only from private network addresses (the realm
has `sslRequired: external`), which suits a Pi on the Makespace LAN.
To use it from outside, put Keycloak and the web server behind an
HTTPS reverse proxy, use `https://` addresses in `KEYCLOAK_URL` and
`STORAGE_WEB_URL`, and enable `KC_PROXY_HEADERS` in
`docker-compose.yaml`.  Do not use logins over plain HTTP across the
internet.

To use an existing Makespace Keycloak instead of the one in
docker-compose, point `KEYCLOAK_URL` (and `KEYCLOAK_INTERNAL_URL`, if
different) at it and create the clients, roles, user-profile attribute
and mappers described above in its realm (or partially import the
realm file from the admin console).

## Calling the API from Python

`src/client/storage_client.py` depends only on `requests`:

```python
from storage_client import StorageClient, ClientCredentials, DeviceLogin

# Anonymous: reading only
StorageClient("http://127.0.0.1:8000").where("Betsy")

# Another service
client = StorageClient("http://127.0.0.1:8000",
                       auth=ClientCredentials(KEYCLOAK_URL, "storage-service", SECRET))
client.move("Betsy", "Secure workshop")

# A person at a terminal: prints a URL to open in a browser
client = StorageClient("http://127.0.0.1:8000", auth=DeviceLogin(KEYCLOAK_URL))
client.whoami()   # {'username': 'jbloggs', 'level': 'user', 'membership_number': '1234', ...}
```

Tokens are fetched, cached and refreshed automatically.  It also works
from the command line, e.g. `storage_client.py --login whoami`, or
`TOKEN=$(storage_client.py token)` to use with curl.  See its
docstring for the environment variables it reads.

## Running without docker

Set the same environment variables for the scripts in `scripts/`:
`KEYCLOAK_URL` for the API server; `KEYCLOAK_URL`,
`STORAGE_WEB_CLIENT_SECRET`, `FLASK_SECRET_KEY` and `STORAGE_WEB_URL`
for the web server.  If `KEYCLOAK_URL` is not set, both servers still
serve reads but refuse all changes.

## Tests

`python3 -m pytest pytests` (after `pip install -r requirements-dev.txt`)
tests both servers' access rules with locally made tokens, so it needs
no Keycloak.
