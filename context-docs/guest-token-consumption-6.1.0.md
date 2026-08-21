# Guest token consumption and BigQuery impersonation

Apache Superset **6.1.0** (`c83fb2bb1d`). Portal mints its own guest JWTs with the shared signing key; it does not call Superset’s issuance endpoint. This document is consume-side only.

**Pick: option 1** — email claim in the guest JWT + domain-wide delegation in `DB_CONNECTION_MUTATOR`. No Google credential in the browser. SIP-85 (option 2) does not work for embedded guests or for BigQuery in this release.

---

## A. Guest token claims (consumption)

### Decoded payload is a permissive dict

`GuestToken` / `GuestTokenUser` in `superset/security/guest_token.py` are **typing-only** `TypedDict`s. They are not a runtime schema. Decode does not run marshmallow.

`parse_jwt_guest_token` returns `dict[str, Any]`. The docstring says the token is “tested but unchanged”:

```python
# superset/security/manager.py:3072
def parse_jwt_guest_token(self, raw_token: str) -> dict[str, Any]:
    """
    Parses a guest token. Raises an error if the jwt fails standard claims checks.
    :return: the same token that was passed in, tested but unchanged
    """
    secret = get_conf()["GUEST_TOKEN_JWT_SECRET"]
    algo = get_conf()["GUEST_TOKEN_JWT_ALGO"]
    audience = self._get_guest_token_jwt_audience()
    return self.pyjwt_for_guest_token.decode(
        raw_token, secret, algorithms=[algo], audience=audience
    )
```

Runtime checks in `get_guest_user_from_request` (then `cast(GuestToken, token)`, not validation):

- `user` must be present
- `resources` must be present
- `rls_rules` must be present
- `type` must equal `"guest"`

Missing any of those → log warning, return `None` (login manager sends 401). Unknown claims are **kept**.

The TypedDict does not even list `aud` or `type`, which the real JWT has — further proof it is documentation, not enforcement.

**Issuance is stricter, consume is not.** `POST /api/v1/security/guest_token/` uses `GuestTokenCreateSchema` with `unknown = EXCLUDE` (`superset/security/api.py`). Extra user fields are dropped **only** if minted through that API. Portal-minted tokens bypass this.

### Fields that land on `GuestUser`

```python
# superset/security/guest_token.py:82
def __init__(self, token: GuestToken, roles: list[Role]):
    user = token["user"]
    self.guest_token = token          # entire decoded JWT
    self.username = user.get("username", "guest_user")
    self.first_name = user.get("first_name", "Guest")
    self.last_name = user.get("last_name", "User")
    self.roles = roles
    self.groups: list[Group] = []
    self.resources = token["resources"]
    self.rls = token.get("rls_rules", [])
```

`get_guest_user_from_token` only wraps that with `GUEST_ROLE_NAME` (default `"Public"`).

| Attribute | Source | Default |
|---|---|---|
| `guest_token` | entire decoded JWT dict | — |
| `username` | `token["user"].username` | `guest_user` |
| `first_name` | `token["user"].first_name` | `Guest` |
| `last_name` | `token["user"].last_name` | `User` |
| `resources` | `token["resources"]` | required |
| `rls` | `token["rls_rules"]` | `[]` |
| `roles` | `find_role(GUEST_ROLE_NAME)` | `Public` |
| `groups` | hardcoded | `[]` |
| `email` | **not set** | missing |
| `id` | **not set** | missing |

Custom claims (e.g. `user_email` at top level, or extra keys under `user`) survive on `g.user.guest_token`. They are **not** copied to `g.user.email`.

`get_user_email()` reads `g.user.email` and swallows `AttributeError` → `None`. Jinja `current_user_email()` therefore returns `None` for guests unless `GuestUser` is patched.

### Minimal change to carry `user_email` to query time

**Zero core patch** if you only need credential resolution:

1. Portal puts `user_email` (top-level or under `user`) in the JWT.
2. `DB_CONNECTION_MUTATOR` reads it:

```python
def DB_CONNECTION_MUTATOR(uri, params, username, security_manager, source):
    guest = security_manager.get_current_guest_user_if_guest()
    email = None
    if guest is not None:
        token = guest.guest_token or {}
        user = token.get("user") or {}
        email = token.get("user_email") or user.get("email") or user.get("user_email")
    email = email or username
    # apply with_subject(email) — see section C
    return uri, params
```

**One-line `GuestUser` patch** only if you also need `g.user.email` / Jinja:

```python
self.email = user.get("email") or user.get("user_email") or token.get("user_email")
```

Putting the email in `user.username` also works for `get_username()` / `effective_username` with no patch, but then Admin-issued tokens can assert an arbitrary identity via `username`.

### JWT signing — actual defaults (`superset/config.py`)

```python
GUEST_ROLE_NAME = "Public"
GUEST_TOKEN_JWT_SECRET = "test-guest-secret-change-me"
GUEST_TOKEN_JWT_ALGO = "HS256"
GUEST_TOKEN_HEADER_NAME = "X-GuestToken"
GUEST_TOKEN_JWT_EXP_SECONDS = 300  # 5 minutes
GUEST_TOKEN_JWT_AUDIENCE: Callable[[], str] | str | None = None
```

| Key | Default | Used at |
|---|---|---|
| `GUEST_TOKEN_JWT_SECRET` | `"test-guest-secret-change-me"` | encode **and** decode |
| `GUEST_TOKEN_JWT_ALGO` | `HS256` | encode **and** decode |
| `GUEST_TOKEN_JWT_EXP_SECONDS` | **300** | issuance only (`create_guest_access_token`) |
| `GUEST_TOKEN_JWT_AUDIENCE` | `None` → `WEBDRIVER_BASEURL` (`http://0.0.0.0:8080/`) | `aud` on encode and decode |
| `GUEST_TOKEN_HEADER_NAME` | `X-GuestToken` | `request_loader` (also form field `guest_token`) |

Expiry on consume is whatever `exp` is in the token; PyJWT verifies it. Portal chooses TTL. The 300s figure is only what Superset’s own issuer writes.

`aud` resolution (`manager.py:_get_guest_token_jwt_audience`):

```python
audience = get_conf()["GUEST_TOKEN_JWT_AUDIENCE"] or get_url_host()
```

`get_url_host()` returns `WEBDRIVER_BASEURL`. Portal must set `aud` to that same value (or set `GUEST_TOKEN_JWT_AUDIENCE` explicitly and match it).

There is no separate verify key. Encode and decode share `GUEST_TOKEN_JWT_SECRET`.

### Critical plumbing: does `g.user` reach credential resolution?

**Yes**, on every embedded path that hits `Database._get_sqla_engine`.

`create_login_manager` registers `request_loader`. If `EMBEDDED_SUPERSET` is on, it calls `get_guest_user_from_request`. Flask-Login only uses the request loader when there is no session, so a logged-in cookie wins over a guest token.

During an embedded request, `g.user` **is** a `GuestUser` instance (`is_guest_user = True`).

`Database._get_sqla_engine` (`superset/models/core.py`):

1. `effective_username = get_username()` → `g.user.username` (try/except → `None`).
2. Optional `IMPERSONATE_WITH_EMAIL_PREFIX`: `find_user(username=...)` then email prefix. Guests are not in `ab_user` — this does nothing.
3. SIP-85 token lookup only if `oauth2_config` and `hasattr(g.user, "id")`. `GuestUser` has no `id` → skipped.
4. If `database.impersonate_user`: `db_engine_spec.impersonate_user(...)`. **BigQuery does not override this.** Base implementation rewrites the URL username, which is useless for `bigquery://{project_id}`.
5. If configured: `DB_CONNECTION_MUTATOR(url, engine_kwargs, effective_username, security_manager, source)`.

The mutator is **not** passed `g.user`, but it runs in the same Flask context. `security_manager.get_current_guest_user_if_guest()` reads `g.user`. Engines are created with `NullPool` by default (`nullpool=True`), so credentials are not reused across users via a pool.

`with_subject()` does **not** exist in `BigQueryEngineSpec`. It has to be applied in `DB_CONNECTION_MUTATOR` (or a forked engine spec).

---

## Query paths (`get_sqla_engine` / `g.user`)

All of these go through `Database.get_sqla_engine` → `_get_sqla_engine` → `DB_CONNECTION_MUTATOR`.

| Path | `g.user` restored? | Mutator runs? |
|---|---|---|
| Sync chart data, native filters, samples, expression validation | Yes — `request_loader` | Yes |
| `GLOBAL_ASYNC_QUERIES` (chart + explore) | Yes — full `guest_token` dict (extra claims included) stuffed into Celery `job_metadata`, rebuilt with `get_guest_user_from_token`, `override_user` | Yes |
| Dashboard screenshot / thumbnail | Yes — `dashboards/api.py` passes `g.user.guest_token` into Celery; task rebuilds `GuestUser` | Yes, when that session queries |
| SQL Lab | Not a guest path (`GUEST_ROLE_NAME` is `Public`) | N/A for embed |
| Alerts / reports | Executor user (`THUMBNAIL_EXECUTORS` / report executor), not guest | N/A for embed |
| Jinja `current_user_email()` | `g.user` exists but has no `.email` | Returns `None` unless `GuestUser` is patched |

Async reconstruction (`superset/async_events/async_query_manager.py`, `superset/tasks/async_queries.py`) copies `guest_user.guest_token` — the whole dict, not a subset — so a custom `user_email` survives the worker.

### Cache (must not skip this)

`CACHE_IMPERSONATION` and `CACHE_QUERY_BY_USER` default **False**. `get_impersonation_key` uses `user.username`, not email.

If every guest shares username `guest_user`, chart cache is shared across identities even when BigQuery ACLs differ. Enable `CACHE_QUERY_BY_USER` (or `CACHE_IMPERSONATION` plus `impersonate_user`) and put a **unique** username or include email in the impersonation key.

---

## A2. Shared-secret trust boundary

### Issuance endpoint

`POST /api/v1/security/guest_token/` — `SecurityRestApi.guest_token` in `superset/security/api.py`.

- `@protect()` — must be authenticated
- `@permission_name("grant_guest_token")` → permission `can_grant_guest_token`
- That permission is in `ADMIN_ONLY_PERMISSIONS` (`superset/security/manager.py`)
- Tests: unauthenticated → 401, Gamma → 403, Admin → 200

Body is validated by `GuestTokenCreateSchema` (`user.username/first_name/last_name`, `resources`, `rls`). Extra fields **excluded**. Then `validate_guest_token_resources` (dashboard / embedded UUID must exist), then optional `GUEST_TOKEN_VALIDATOR_HOOK`, then `create_guest_access_token`.

Issuance **does not** check `EMBEDDED_SUPERSET`.

### Can it be disabled by config, no patch?

**No dedicated flag.**

| Lever | Effect |
|---|---|
| `EMBEDDED_SUPERSET = False` | Stops `request_loader` (consume). Issuance API still works. |
| `GUEST_TOKEN_VALIDATOR_HOOK = lambda body: False` | Issuance API always 400. Route still exists. Admin still has the permission. |
| Removing the permission from Admin | Not possible by config. Seeded via `ADMIN_ONLY_PERMISSIONS`. Needs a custom security manager or a patch. |

### Issuer distinction — what the code actually supports

| Mechanism | Supported? |
|---|---|
| `aud` | Yes. Validated on decode. Shared if portal copies the same audience. Does not distinguish issuers. |
| `iss` | **Not set, not checked.** |
| Separate consume vs issue keys | **No.** One `GUEST_TOKEN_JWT_SECRET` for encode and decode. |
| Asymmetric (RS256 portal-private / Superset-public) | Not first-class. `ALGO` is a string you can set to `RS256`, but both encode and decode use the same `SECRET`. Putting a public key in `SECRET` would let consume work and would **break** Superset’s own encoder if anyone hit the API. |
| `kid` / key ring | **No.** |

### Who can mint a token asserting an arbitrary identity (default deploy)

1. **Portal** (holder of `GUEST_TOKEN_JWT_SECRET`) — any claim, including `user_email`. Intended path.
2. **Anyone else with the secret** — config, env, image, or the default `"test-guest-secret-change-me"`. Symmetric key = equivalent issuer.
3. **Any Admin** via `POST /api/v1/security/guest_token/` — arbitrary `username` / `first_name` / `last_name`. Cannot add `user_email` through the API (`EXCLUDE`). Can still impersonate if you key off `username`.
4. **Gamma / Public / anonymous** — no (401/403).

---

## C. Mechanism ranking

### 1. Email claim + domain-wide delegation — **pick this**

Portal puts the end-user email in the JWT. Superset never sees a Google token.

`with_subject()` is applied only in `DB_CONNECTION_MUTATOR`:

```python
from google.oauth2 import service_account

creds = service_account.Credentials.from_service_account_info(sa_info)
creds = creds.with_subject(email).with_scopes([
    "https://www.googleapis.com/auth/bigquery",
])
params.setdefault("connect_args", {})["credentials"] = creds
```

This survives every embed query path in the table above because they all rebuild `GuestUser` from the same token dict and then call `get_sqla_engine`.

Companion settings:

- Unique `username` (or email-as-username) per guest
- `CACHE_QUERY_BY_USER = True` (or `CACHE_IMPERSONATION` + `impersonate_user`)
- Rotate `GUEST_TOKEN_JWT_SECRET` off the default
- Optionally `GUEST_TOKEN_VALIDATOR_HOOK` that rejects API issuance so only the portal mints

### 2. OAuth2 token passthrough (SIP-85) — **do not use**

SIP-85 as implemented (`superset/utils/oauth2.py`, `DatabaseUserOAuth2Tokens`):

- Personal OAuth tokens stored in `database_user_oauth2_tokens`, keyed by `ab_user.id`
- Looked up only when `hasattr(g.user, "id")`
- `supports_oauth2` is **False** on `BigQueryEngineSpec` (only **gsheets** and **trino** set it)

Embedded guests fail both requirements: no `id`, engine spec does not support OAuth2.

Stuffing a BigQuery-scoped Google access token into the guest JWT is **not** SIP-85. It is a bearer credential in a browser-visible token (`X-GuestToken` header / embed SDK, sent on every chart request). XSS, an extension, or a copied JWT yields live BQ access for that token’s TTL — often longer than the 300s guest default if you embed Google’s own expiry. Treat that as credential theft, not impersonation.

---

## Source map (6.1.0)

| Topic | File |
|---|---|
| TypedDict + `GuestUser` | `superset/security/guest_token.py` |
| Parse / create / request loader | `superset/security/manager.py` (~477, ~2984–3101, `ADMIN_ONLY_PERMISSIONS`) |
| Issuance API + marshmallow | `superset/security/api.py` |
| JWT / mutator / feature-flag defaults | `superset/config.py` |
| Engine + mutator + OAuth2 lookup | `superset/models/core.py` (`_get_sqla_engine`) |
| `get_username` / `get_user_email` / `override_user` | `superset/utils/core.py` |
| BigQuery engine spec (no `impersonate_user`, no OAuth2) | `superset/db_engine_specs/bigquery.py` |
| Base `impersonate_user` / `supports_oauth2 = False` | `superset/db_engine_specs/base.py` |
| SIP-85 token store | `superset/utils/oauth2.py`, `DatabaseUserOAuth2Tokens` |
| Async guest reconstruction | `superset/async_events/async_query_manager.py`, `superset/tasks/async_queries.py` |
| Screenshot guest reconstruction | `superset/dashboards/api.py`, `superset/tasks/thumbnails.py` |
| Chart cache impersonation key | `superset/common/query_object.py` |
| Audience fallback | `superset/utils/urls.py` (`WEBDRIVER_BASEURL`) |
