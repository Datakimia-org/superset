# Implementation plan: guest-token identity + BigQuery Workforce Identity Federation

Consume-side findings in `guest-token-consumption-6.1.0.md` remain valid and are
relied on throughout.

**Target:** Apache Superset **6.1.0**.

**Goal:** each embedded viewer queries BigQuery as themselves, so BigQuery IAM and
row-level access policies do the authorization. Portal obtains a short-lived federated
GCP token from the viewer's IdP token (STS). Superset attaches that credential to the
engine. No Google credential, IdP token, or refresh token ever reaches the browser.

**Non-goals:** SIP-85, Google/IdP tokens in the guest JWT, calling Superset's guest-token
issuance API, patching `BigQueryEngineSpec` unless the injection spike (3.0) forces it.

Claims below are marked **VERIFIED** (codebase or Google/IdP docs) or **ASSUMED**
(must be confirmed in our environments).

---

## Changelog

This revision: Section 9 enablement gate, Portal-vs-fork recommendation, 9.3 rewritten
around the delivery-loop constraint. Rows 12–14 are the reports/RS256 merge. Rows
8–11 are engine-lifetime. Rows 1–7 are the WIF rewrite.

The addendum numbered its changelog 8–10; those slots were already used. Reports/RS256
landed as **12–14**. This edit is **15**. The addendum named `SELECTED_USER`, which
does not exist at 6.1.0 — see 9.2.

| # | Leftover / defect | What was wrong | Fix |
|---|---|---|---|
| 1 | **STS from a subject string** (blocker) | DWD mental model: identifier → `with_subject(email)`. Draft 3.4 had a broker that accepted `user_subject` and "performed STS." Workforce STS has no such API. It requires the user's IdP subject token. | 3.4 rewritten as two variants that both start from a stored IdP token. Option "in-Superset STS" is marked unviable, not a fallback. |
| 2 | **Two different `aud` values conflated** | Guest JWT `aud` (Superset consume) vs OIDC ID-token `aud` (STS provider). A provider's default expected audience is its own URI unless `allowedAudiences` is set. | Named `guest_aud` and `oidc_aud`. Provider audience is a Section 1 config step and a Section 0 gate item. |
| 3 | **Dialect injection path** (the previously unstated leftover) | DWD plan wrote `connect_args["credentials"] = creds`. sqlalchemy-bigquery 1.15.0 (pinned on 6.1.0) does not take a live `Credentials` object that way. `credentials_info` / `credentials_path` / `credentials_base64` are **service-account JSON**. `BigQueryEngineSpec._get_client` also builds SA creds from `dialect.credentials_info`. | Spike 3.0 now targets the documented inject path: URL `user_supplied_client=True` plus `connect_args["client"]` = a `bigquery.Client`. Side paths that still use `_get_client` are called out. |
| 4 | Cache keyed by subject for ~1h | Would outlive guest JWT and delay revocation. | Credential handle is `jti`. Chart-cache identity remains stable `username` ≡ WIF subject. |
| 5 | `CACHE_QUERY_BY_USER` "confirm at pinned tag" | Already knowable. | **VERIFIED:** it is a `DEFAULT_FEATURE_FLAGS` entry in `superset/config.py` (~line 699). Overlay via `FEATURE_FLAGS`. |
| 6 | Filename / "everything else in the DWD plan survives" | False. Credential construction, injection, and the Section 0 gate do not survive. | This file is the WIF plan. |
| 7 | Instruction slip on Variant B | The prompt said Variant B has "no out-of-band refresh loop." That is wrong: the embed SDK guest-token refresh **is** that loop. It is an advantage (piggybacks on an existing path), not an absence of refresh. | Stated as such in 3.4. |
| 8 | **Engine lifetime / credential reuse** | Spike 3.0 asked whether a supplied `Client` works, not whether it leaks across users. Same class of defect as cache/identity divergence. | Investigated at 6.1.0: Engines are **not** reused (evidence in 3.0). Config-only estimate unchanged. Spike still must empirically confirm the dialect does not stash the Client on a class/module. E2e asserts on BigQuery job principal, not rendered rows. |
| 9 | `jti` marked ASSUMED unguessable | We mint it; guessable `jti` is a live GCP token under Variant B. | Required: ≥128-bit CSPRNG (UUIDv4 or equivalent), unique per JWT, never derived from user/session/subject/counter. VERIFIED-by-construction. |
| 10 | Redis key = bare `jti` | Fine for one-tenant-per-deployment until two envs share a Redis. | Namespaced `<env>:<tenant>:gcp:<jti>`. Instance-sharing rules in 3.5. |
| 11 | STS quota missing from the gate | Variant B volume scales with concurrent embed users, not with code. Workforce STS quota is **1,000 exchanges per organization per minute**. | Gate question + load-test comparison. Levers recorded, not recommended. |
| 12 | Binding did not bind identity | `jti` resolved to a credential without checking it belonged to the claimed subject. A holder of the guest signing secret could mint their own `jti` with a victim's `username` / `user_subject`; the query ran as the attacker but cached under the victim. | Binding stores WIF `subject` from the Portal session (not from the JWT). Mutator asserts `binding.subject == user_subject` after lookup. |
| 13 | Reports deferred with no model | Parked in Section 8. | Section 9: dedicated report GCP SA + `FixedExecutor` Superset user, SQL-level per-recipient filter from the RAP mapping table, fail-open vs embed stated. Stock `ALERT_REPORTS` is one payload for all recipients. Row 15 names where the loop lives. |
| 14 | Shared signing key deferred | Parked in Section 8 as needing a security-manager patch. | Section 10: RS256, Portal private key, public PEM in `GUEST_TOKEN_JWT_SECRET`. Likely config-only; spike defined. Residual after row 12 is Superset-side guest access, not BigQuery data. |
| 15 | Section 9 delivery loop | Addendum treated per-recipient SQL as report rules without naming where the loop lives. Stock `ALERT_REPORTS` is one payload. | Recommend **Portal-side** loop, not a Superset fork. Enablement gate before RAP reports. Mutator report-bot branch is the BQ identity half. |

---

## Why WIF, not DWD

Portal users are Workforce Identity Federation principals:

```
principal://iam.googleapis.com/locations/global/workforcePools/POOL_ID/subject/SUBJECT
```

`credentials.with_subject(email)` impersonates Google Workspace / Cloud Identity
accounts only. It cannot target a WIF principal.

| | Domain-wide delegation | Workforce Identity Federation |
|---|---|---|
| Credential at rest in Superset | SA key that can impersonate any domain user | Metadata SA only (non-guest paths) |
| Blast radius if the pod is compromised | Entire Workspace domain | One user, one GCP token lifetime, and only if a `jti` binding exists |
| Users must live in Google Workspace | Yes | No — external IdP |
| Revocation | Rotate key, redeploy | Disable in IdP; next mint/STS fails (latency depends on variant, 3.4) |
| Per-client isolation | One domain | Pool / provider per client or IdP |

BigQuery row access policies accept workforce principals. Google's docs: for users in
external identity providers, substitute WIF principal identifiers wherever you would
write `user:someone@example.com`. **VERIFIED** (IAM / BigQuery RAP docs).

What still holds from the DWD-era plan: guest-token consume behaviour, mutator as the
single engine injection point, fail-closed on every unresolved branch, `CACHE_QUERY_BY_USER`,
the validator hook, metadata-SA separation.

---

## Corrections carried forward

1. **Cache key and identity key must not disagree.** `CACHE_QUERY_BY_USER` hashes
   `g.user.username` (**VERIFIED**, `superset/common/query_object.py` +
   `BaseEngineSpec.get_impersonation_key`). Identity for chart cache is the stable WIF
   subject. If `username = X` and `user_subject = A`, A's rows cache under X. The mutator
   **rejects** any token where `user.username != user_subject`. `jti` is a *credential
   handle*, not the cache identity — putting `jti` in `username` would bust the chart
   cache on every guest-token refresh (~5 min).

2. **Credential handle caching.** Do not cache GCP tokens by subject for ~1h. Key them
   by `jti` with TTL at most the remaining guest-JWT lifetime (see 3.4).

3. **Tenant and IdP are different axes.** Client environments (`january`, `payfacto`,
   `meshads`, `clientx`) are one-tenant-per-deployment. One tenant can still have
   multiple IdPs (Google / Entra / Auth0), each a workforce *provider*. See 3.5.

4. **Supplied client must not outlive the identity.** Same weight as (1). At 6.1.0
   SQLAlchemy Engines are not memoized (3.0). The remaining leak class is a dialect or
   module stashing the `Client`, which the spike must rule out, plus `_get_client`
   ignoring the supplied client (already named).

---

## 0. Design gate (before any code)

The DWD gate was "users must be Workspace users." The WIF gate is:

> Portal must be able to obtain a fresh, valid OIDC ID token for the viewer, whose
> `oidc_aud` matches an allowed audience on the workforce pool provider, at any point
> during the embed session. If it cannot, this mechanism is dead.

Answer in writing:

| Question | Why it blocks |
|---|---|
| Can Portal obtain a fresh OIDC **ID token** (not just an access token) for the viewer for the whole embed session, including via refresh? | STS `subjectToken` must be that ID token (or a SAML assertion). No ID token, no federation. Kill switch: Section 0.5. |
| For each IdP used in each environment, what is the Portal OAuth client ID, and is it listed in the provider's `allowedAudiences`? | Default provider audience is the provider URI, not the Portal client. Mismatch → STS rejects. Record the `oidc_aud` map. Distinct from `guest_aud`. |
| Workforce pool + provider topology: one pool per client env? One provider per IdP? | Mutator/mint must pick the right provider; blast radius. |
| What is the stable `google.subject` per user, and does Portal know it at mint time? | Chart-cache identity. Must not change on profile edits. |
| Does BigQuery live in the same GCP org as the pools? | WIF principals cannot reach resources outside their org. |
| What happens to a user with no BigQuery IAM grant? | Must be an error, never a fallback to a shared identity. |
| Which environments use embedding? | Rollout scope. |
| Can Portal write a short-lived GCP token to a cache that Superset **app and Celery workers** can read? | Required for Variant B. If no, Variant A. |
| Peak concurrent embed users vs Workforce STS quota (**1,000 token exchanges per organization per minute**, [IAM quotas](https://cloud.google.com/iam/quotas); **VERIFIED** docs, confirm on our org in the console)? | Variant B ≈ `concurrent × (60 / guest_jwt_ttl_seconds)` exchanges/minute if refresh is uniform; a synchronized refresh is `concurrent` in one minute. Multiple client envs in the **same org share this quota**. If the projection does not fit, the levers are longer guest JWT TTL or caching the GCP token beyond one guest JWT — both worsen revocation. Do not pick a lever here; record the number. |

**Fail closed.** If a `jti` cannot be resolved to a credential, the query errors. Do not
fall back to a service account — any SA on that connection will have broader access than
the viewer.

Two audiences, never mixed:

| Name in this doc | What it is | Where it is checked |
|---|---|---|
| `guest_aud` | Guest JWT `aud` | Superset `parse_jwt_guest_token` vs `GUEST_TOKEN_JWT_AUDIENCE` |
| `oidc_aud` | OIDC ID-token `aud` (Portal's IdP client ID, typically) | Workforce provider `allowedAudiences` at STS |

---

## 0.5 ID token on refresh (cheapest kill switch)

**Do this before GCP wiring beyond a lab pool, and before the 3.0 spike.** It is a
Portal/IdP question. A bad answer kills both credential variants equally.

STS requires an IdP *subject token*. For OIDC providers that is an **ID token**, not an
access token. **VERIFIED:** [Obtain short-lived tokens for Workforce Identity Federation](https://cloud.google.com/iam/docs/workforce-obtaining-short-lived-credentials);
`subjectTokenType` = `urn:ietf:params:oauth:token-type:id_token` (OIDC) or
`urn:ietf:params:oauth:token-type:saml2` (SAML).

OAuth refresh often returns only an `access_token` unless the original grant included
`openid` (and, for a refresh token to exist at all, typically `offline_access` /
`access_type=offline`). **If refresh yields no ID token, there is nothing to exchange
once the first ID token expires.**

Verify **with the actual client config** per IdP, do not trust this table as production
fact:

| IdP | Refresh returns `id_token`? | Notes |
|---|---|---|
| Auth0 | **Documented yes**, if the original token's scope included `openid`. Refresh tokens require `offline_access` at consent. | [Auth0: Use Refresh Tokens](https://auth0.com/docs/secure/tokens/refresh-tokens/use-refresh-tokens). Still confirm on *our* tenant and grant types — rules that rewrite `scope` on refresh have stripped `id_token` in the wild. |
| Google | **ASSUMED / open.** Google's token docs describe refresh as returning the same token set when `openid` was granted; this is not confirmed against Portal's Google client (`access_type`, `prompt`, confidential vs SPA). | Section 0.5 lab: refresh and inspect the JSON. |
| Microsoft Entra ID | **ASSUMED / open.** Microsoft docs for the refresh grant include `id_token` when `openid` is in scope; SPA vs confidential client and v1/v2 endpoints differ. | Same lab. |

Also record, per IdP, **actual ID-token TTL** vs a realistic embed session (tens of
minutes to hours). Treat refresh as load-bearing, not an edge case. Guest JWT TTL
(~300s, **VERIFIED** default `GUEST_TOKEN_JWT_EXP_SECONDS`) is *not* the ID-token TTL.

If any in-use IdP cannot produce a fresh ID token for the session length, stop. Do not
compensate by putting the ID token in the guest JWT.

---

## 1. GCP / IAM (no Superset code)

1. Create (or confirm) a **workforce identity pool** per client environment that uses
   embed, and an **OIDC provider per IdP** (Google, Entra, Auth0) in that pool. Record
   `POOL_ID`, `PROVIDER_ID`, issuer, and the attribute mapping that produces
   `google.subject`.
2. **Provider audience (`oidc_aud`).** For each provider, set `allowedAudiences` to the
   Portal OAuth **client ID** used at login for that IdP. **VERIFIED:** workforce OIDC
   provider docs — if `allowedAudiences` is empty, STS expects the ID token `aud` to be
   the provider resource URI (`//iam.googleapis.com/locations/global/workforcePools/POOL/providers/PROVIDER`),
   which a Portal-issued ID token will not have. Do this explicitly; do not rely on the
   default.
3. Choose a **workforce pools user project** (quota/billing for the exchange;
   `options.userProject` / `workforce_pool_user_project`). The exchanging principal
   needs `serviceusage.services.use` on it. **VERIFIED** (STS workforce docs).
4. Grant BigQuery access **to the principals**, not to a query-path service account:
   - `roles/bigquery.jobUser` on the query project
   - `roles/bigquery.dataViewer` on datasets, scoped per group where possible
   - Prefer `principalSet://.../group/GROUP_ID` or attribute-based sets over per-user
     bindings
5. Row access policies grant to workforce principals, e.g.
   `GRANT TO ('principal://iam.googleapis.com/locations/global/workforcePools/POOL_ID/subject/SUBJECT')`.
   `SESSION_USER()` for a federated user is this full principal string, **not** an email.
   **ASSUMED** exact `SESSION_USER()` spelling until Section 1 step 7 records it from a
   real query.
6. Metadata identity: see 4.2.
7. **Prove the exchange outside Superset.** Take a real user's **ID token** from Portal
   login (the same client ID as `allowedAudiences`), POST
   `https://sts.googleapis.com/v1/token` with
   `grantType=urn:ietf:params:oauth:grant-type:token-exchange`,
   `audience=//iam.googleapis.com/locations/global/workforcePools/POOL/providers/PROVIDER`,
   `subjectTokenType=urn:ietf:params:oauth:token-type:id_token`,
   `requestedTokenType=urn:ietf:params:oauth:token-type:access_token`,
   `scope=https://www.googleapis.com/auth/bigquery` (or `cloud-platform` if required),
   and `options={"userProject":"..."}`. Run a query. Record `SESSION_USER()`. Repeat
   with a user who lacks dataset IAM and confirm it **fails**. Repeat with a token whose
   `oidc_aud` is *not* in `allowedAudiences` and confirm STS rejects.

No Superset work starts until step 7 passes for every in-use IdP.

---

## 2. Portal: mint the claim

Portal already signs guest tokens with the shared secret. Keep that. The JWT is a
**handle**, not a GCP credential.

| Claim | Role |
|---|---|
| `type` | `"guest"` — required by consume (**VERIFIED**, `get_guest_user_from_request`) |
| `user.username` | Stable WIF subject. Chart-cache identity. Must equal `user_subject`. |
| `user_subject` | Same stable WIF subject. Logging + equality check. **Not** an STS input. |
| `jti` | Credential handle. Unique per minted guest JWT. Mutator looks up the GCP token by this. **Required construction:** ≥128 bits of cryptographic randomness (UUIDv4 or equivalent CSPRNG). Never derived from user id, session id, subject, timestamp, or a counter. **VERIFIED-by-construction** — this is not an assumption about UUID libraries; Portal must mint it that way. Under Variant B a guessable `jti` is a live GCP access token. |
| `user_email` | Optional, logging / future Jinja. Never authorization. |
| `tenant` | Client environment key. Mutator verifies it matches the deployment; does not select a foreign pool. |
| `iss_idp` (or equivalent) | IdP issuer, if a deployment has more than one provider. Provider selection (3.5). Omit if single-provider. |
| `resources` | `[{ "type": "dashboard", "id": "<embedded uuid>" }]` |
| `rls_rules` | List; empty is fine; key must be present (**VERIFIED**) |
| `iat` / `exp` | Guest JWT lifetime. Keep short (~300s). This is **not** `oidc_aud` and not GCP token TTL. |
| `aud` | **`guest_aud`**: exact match for `GUEST_TOKEN_JWT_AUDIENCE`. Silent 401 on mismatch. |

Never put a GCP access token, IdP ID token, refresh token, or raw OIDC assertion in the
JWT. It is browser-visible (`X-GuestToken` / embed SDK) on every chart request.

Set `guest_aud` explicitly on both sides to a stable string (public Superset URL). Do
not depend on the `WEBDRIVER_BASEURL` fallback (**VERIFIED** default
`http://0.0.0.0:8080/` in stock config).

The embed SDK refresh callback must keep minting for the whole session. That loop is
load-bearing for Variant B and for guest JWT expiry in both variants. **ASSUMED:**
Portal's `fetchGuestToken` implementation calls a Portal endpoint with the live session
(cookie or BFF). Confirm.

---

## 3. Superset overlay (not core, unless 3.0 forces a fork)

Overlay on the fork: flags, JWT, validator hook, mutator, credential lookup. No
mutator source in this document.

Workers must load the same overlay (same image, same `PYTHONPATH`). Async charts and
screenshots rebuild `GuestUser` from the full `guest_token` dict in Celery
(**VERIFIED**: `async_query_manager.py`, `tasks/async_queries.py`, `dashboards/api.py`,
`tasks/thumbnails.py`). Extra claims (`jti`, `user_subject`) survive that dict.

### 3.0 Spike: inject a live client, and prove it does not leak across users

**After 0.5, before committing to "config-only."** Timebox it. Two questions, equal
weight: (1) does the documented inject path actually reach BigQuery as that user?
(2) can that `Client` be reused by a later request under a different identity?

#### What 6.1.0 already does (code, not spike)

**Engines are not reused.** `_get_sqla_engine` always ends in `return create_engine(...)`
with no memoization, `@cache`/`lru_cache`, or engine registry keyed by database id
(**VERIFIED**, `superset/models/core.py` 479–550, `create_engine` at 547–548).
`get_sqla_engine` is a context manager that yields that freshly built Engine
(426–477). `DB_CONNECTION_MUTATOR` runs on **every** construction, immediately before
`create_engine` (537–548), not on a cache miss.

Chart data takes that path: `ExploreMixin.query` → `Database.get_df` →
`_execute_sql_with_mutation_and_logging` → `get_raw_connection` → `get_sqla_engine`
(**VERIFIED**, `superset/models/helpers.py` 1149–1192; `superset/models/core.py`
671–705, 570–585, 762–770).

`nullpool` defaults to `True` and no caller in `superset/` passes `False`
(**VERIFIED**). `NullPool` is therefore the chart-data poolclass. That still would not
save you if the *Engine* were cached; it is not.

`get_extra` / `get_extra_params` does `json.loads(database.extra)` into a **new** dict
each call (**VERIFIED**, `superset/db_engine_specs/base.py` 2297–2315). Mutating
`engine_kwargs["connect_args"]` does not persist on the `Database` model. The
`Database.connect_args` property (core.py 376–377) re-parses extra; it is not a live
client slot.

`Database.get_db_engine_spec` is `@lru_cache` on the **spec class**, not an Engine
(**VERIFIED**, core.py 1026–1038). Flask vs Celery: same `_get_sqla_engine`. Celery's
`db.engine.dispose()` on worker start (`superset/tasks/celery_app.py` 43–47) disposes
the **metadata** Flask-SQLAlchemy engine, not data-plane BigQuery engines.

No module-level `bigquery.Client` in `superset/db_engine_specs/bigquery.py`
(**VERIFIED**).

**Therefore the instruction's Engine-cache leak does not apply at 6.1.0.** Do not add
`do_connect` / `jti`-keyed Engine cache to the estimate unless the spike finds the
dialect stashing the Client. Keep the BigQuery-side e2e (Section 6 case 14) as a
regression.

#### What the spike must still prove

sqlalchemy-bigquery **1.15.0** is pinned (**VERIFIED**, `requirements/development.txt`,
`pyproject.toml`). Documented inject path (README, "Supplying Your Own BigQuery Client"):

- URL query `user_supplied_client=True`
- `connect_args["client"]` = a `bigquery.Client` wrapping
  `google.oauth2.credentials.Credentials(token=<GCP access token>)`

The mutator receives `(sqlalchemy_url, engine_kwargs)` and can set both.

Spike that path, **not** `connect_args["credentials"]`. Also:

- `user_supplied_client=True` still wins when `encrypted_extra` has `credentials_info`.
- Two sequential `create_engine` calls with different Clients in one process: jobs run
  as the respective principals (dialect/module must not keep the first Client).
- `get_sqla_engine` does **not** call `engine.dispose()` on context exit
  (**VERIFIED**, core.py 426–477). Confirm an unreferenced Engine/Client is not
  reachable from dialect class state after the `with` block. Dispose-on-exit is
  hygiene, not a required fork, if that holds.

Outcomes:

- **Inject works and Clients do not leak** → config-only mutator, proceed.
- **Inject fails, or the dialect stashes the Client** → fork `BigQueryEngineSpec` /
  thin dialect, or move injection to connection scope. Re-estimate. Same class of
  estimate change as the existing fork fallback.

#### Siblings (not Engine reuse)

| Finding | Weight |
|---|---|
| `BigQueryEngineSpec._get_client` (bigquery.py 528–553) builds SA creds from `engine.dialect.credentials_info` or ADC. Ignores `connect_args["client"]`. Cost estimate, `get_default_catalog`, catalog listing. Guest chart data does **not** use it (`get_df` uses `get_sqla_engine`). Wrong identity (metadata SA / ADC), not A-then-B reuse. Fail-closed or disable those features for guests. | Already in plan; keep |
| `df_to_sql` (bigquery.py 500–525) reads `engine.dialect.credentials_info` **after** the `with get_engine` block. Uses SA JSON. Not an embed path. | Out of scope unless embed uploads |
| Metadata name lists (`get_all_table_names_in_schema`, `get_all_schema_names`, `get_all_catalog_names`, core.py 868–1018) are `memoized_func` keyed by **database id + catalog/schema**, not user. Shared table/schema names across guests. Not row data. Accept for v1 or key by subject later. | Low; named so it is not "missed" |
| No thread-local / app-level BQ client found. | None |

### 3.1 Flags and JWT

- `EMBEDDED_SUPERSET`: on.
- `CACHE_QUERY_BY_USER`: on. **VERIFIED** as `DEFAULT_FEATURE_FLAGS` in
  `superset/config.py`. Set it on the `FEATURE_FLAGS` overlay (merged on top of
  defaults). Putting it only as a top-level config key does nothing.
- `CACHE_IMPERSONATION` is not a substitute: it requires `database.impersonate_user`,
  and BigQuery's upstream impersonation is URL-username rewriting.
- `GUEST_TOKEN_JWT_SECRET` from env; refuse the default
  `test-guest-secret-change-me`.
- `GUEST_TOKEN_JWT_ALGO`: `HS256` until Section 10’s spike; then `RS256` if it passes.
  Encode and decode both read `GUEST_TOKEN_JWT_SECRET` (**VERIFIED**, `manager.py`
  3014–3015 and 3078–3079).
- `GUEST_TOKEN_JWT_AUDIENCE`: explicit **`guest_aud`**.
- `GUEST_TOKEN_JWT_EXP_SECONDS`: only affects tokens minted *by Superset*. Portal
  chooses guest JWT `exp`.
- `GUEST_ROLE_NAME`: product Guest role on the fork, else `Public`.

### 3.2 Reject Superset-minted guest tokens

`GUEST_TOKEN_VALIDATOR_HOOK` always false → issuance API returns 400. Portal-minted
tokens never hit this hook.

The route still exists; Admin still has `can_grant_guest_token`. The issuance schema
uses `unknown = EXCLUDE` (**VERIFIED**), so the API cannot set `jti` / `user_subject`.
An Admin-minted token has no Redis binding → mutator fail-closed. The hook is defence
in depth. Section 10 (RS256) is the way to make Superset unable to mint, without a
security-manager patch.

### 3.3 Mutator behaviour (Variant B, the recommendation)

Prose only; no source.

1. If the URI is not BigQuery → return unchanged.
2. If not a guest (`get_current_guest_user_if_guest()` is empty, including no `g.user`):
   - if `g.user.username` is the configured report executor (Section 9.2) → inject the
     **report** GCP SA credentials from env/secret
   - otherwise → leave the connection's metadata SA (4.2)
   Do not look up the guest cache.
3. Guest: read `jti`, `user.username`, `user_subject`, `tenant` from
   `g.user.guest_token` (the full decoded dict).
4. Missing `jti` → **raise**.
5. `username != user_subject` → **raise**.
6. `tenant` missing or not equal to this deployment's env tenant → **raise**.
7. If `iss_idp` is used, map it to a provider; unknown issuer → **raise**. (Mint already
   chose the provider; this is a consistency check, not a second STS.)
8. Look up the **binding** in the shared cache under the **namespaced** key (3.5), not
   bare `jti`. The value is `{ gcp_access_token, subject }`, written by Portal at mint
   from the authenticated session — not copied from the JWT. Missing or expired →
   **raise**. Do not call STS. Do not fall through to the metadata SA.
8b. Assert `binding.subject == user_subject`. Mismatch → **raise**. This is independent
   of step 5 (`username != user_subject`); both must pass. A secret-holder who forges
   their `jti` onto a victim's `user_subject` dies here instead of poisoning the
   victim's chart cache.
9. Inject per 3.0 (`user_supplied_client` + `connect_args["client"]`, or the fork
   equivalent). Do not rewrite the SQLAlchemy username.
10. Cache config (pool IDs, Redis, secrets) from env, never from `encrypted_extra`.

### 3.4 Credential variants

Workforce STS **cannot** mint from a `principal://…` string. **VERIFIED** (STS
`subjectToken` required). Both variants below start from Portal's IdP session. The
unviable idea of in-Superset STS without an IdP token is not a variant.

#### Variant A — broker with bound session

Portal retains the IdP refresh token in its existing session store (it already does this
for SSO). At guest-token mint, bind `jti` → `{ session, subject }` where `subject` is
taken from the authenticated Portal session, not from a client-supplied JWT field. Put
`jti` in the JWT.

On each cache miss, the mutator calls a Portal broker **server-to-server** with the
guest JWT or `jti` (not a raw subject). The broker: authenticates the caller as
Superset; looks up the binding; **refuses if `binding.subject` ≠ the JWT's
`user_subject`** (or omits `user_subject` from the request and returns `subject` with
the token so the mutator can check); refreshes the IdP token if needed; STS-exchanges;
returns **only** the short-lived GCP access token plus the bound subject. It must refuse
a subject-only request.

If Superset caches the GCP token, the cache value is `{ gcp_access_token, subject }`,
same as Variant B.

Network: broker reachable only from Superset (mTLS or mesh identity), not from browsers.
A stolen guest JWT plus a public broker would vend GCP tokens.

Superset may cache the returned GCP token in **its own** Redis under the namespaced
key (3.5). App and workers call the same broker; they need the overlay, not Portal's
Redis.

#### Variant B — mint-time exchange, no broker (recommended, with a precondition)

The embed SDK refresh callback already runs in the browser with the user's Portal
session and hits Portal's mint endpoint on the guest JWT cadence (~minutes). **That
callback is the refresh loop** — Variant B does not remove it; it piggybacks on it.

At mint (request already has the session): Portal gets a fresh ID token if needed
(0.5), STS-exchanges, writes `{ gcp_access_token, subject }` to the namespaced cache
key (3.5). `subject` is the WIF subject from the **session**, not from the JWT body.
Then it mints the guest JWT containing that `jti`. The mutator reads the binding and
runs step 8b.

Precondition, **ASSUMED until infra confirms:** Portal can write that key, and Superset
**app + Celery workers** can read it. Today Portal Redis and Superset Redis are
probably separate. This is either a shared cache, or Portal writing into Superset's
Redis over a private path. If that is more expensive than an internal HTTP API,
Variant A wins.

#### Comparison

| | Variant A (broker) | Variant B (mint-time Redis) |
|---|---|---|
| **What Portal retains at rest** | IdP refresh tokens in the session store (already required for SSO), plus `jti` → `{ session, subject }` for the guest JWT lifetime. Broker can use those bindings **without** the browser cookie — that is a new access path to refresh tokens. | Same session-store refresh tokens as today, used only during mint (cookie/BFF present). **New:** `{ gcp_access_token, subject }` in the shared cache, keyed by namespaced `jti`, TTL ≤ remaining guest JWT. No extra refresh-token access path. |
| **Long-lived secrets** | Refresh tokens are the long-lived object. Broker + binding is a high-value target even if it refuses raw subjects (stolen `jti` + network reach). | Refresh tokens stay behind the existing session. GCP tokens are short-lived. Shared Redis becomes a high-value target for those short tokens. |
| **Fewer long-lived credentials at rest?** | No — it adds a use of existing refresh tokens from a new caller. | **Yes**, relative to A. The only new at-rest secret is short-lived GCP tokens. |
| **Failure: dependency down** | Broker down → all embed queries fail, including in-flight dashboards, until it returns. | Shared cache down or key missing/expired → queries fail until the next successful mint/refresh (up to guest JWT TTL). Charts already on screen fail immediately. |
| **Revocation (user disabled mid-session)** | Next broker call that actually hits IdP/STS fails. If Superset also caches GCP tokens by `jti` for ~50 min, disable is delayed until that cache expires. Keep A’s GCP cache TTL ≤ guest JWT remaining, same as B, or revocation is worse than B. | Current `jti` keeps working until **min(Redis TTL, GCP token exp, guest JWT exp)**. New mint should refuse a dead session, so after at most one guest TTL the dashboard dies. Do **not** set Redis TTL to the ~1h GCP token lifetime. |
| **Guest JWT TTL vs GCP TTL (~1h)** | Independent if you cache by namespaced `jti` with guest-TTL. If you cache by subject for 1h you get fewer STS calls and slow revocation — do not. STS on every broker miss. | Mint/STS on every guest refresh (~5 min). Extra STS vs a 1h cache; acceptable. Redis TTL must follow **guest JWT**, not GCP TTL, or a dead guest JWT’s `jti` still has a live GCP token (unguessable `jti` is required in Section 2, still wrong to keep the token). |
| **Celery / screenshots** | Worker calls broker with `jti` from the reconstructed token. Works even if the job runs after a Portal Redis TTL, as long as the **session** still exists. Better for delayed jobs. | Worker must read the **same** cache. **VERIFIED** workers get the full `guest_token` dict. If the job runs after Redis TTL, fail-closed (correct, but screenshots/async break). TTL must cover worst-case queue delay **or** those features are skipped for embed. |
| **Mint latency** | Mint stays cheap (no STS). First chart pays STS (or cache). | Mint pays STS. Embed open waits on STS once per refresh. Usually fine; a slow STS is a slow dashboard open. |
| **New public-ish API** | Yes: token vending. Must be internal-only. | No. |

**Recommendation: Variant B**, provided the shared-cache precondition is true and 0.5
passes. Reasons: no new token-vending API; no cookie-less use of refresh tokens; tighter
default revocation (TTL = guest JWT); fewer moving parts on the query path; piggybacks
on a refresh loop that guest JWT expiry already requires.

Pick **Variant A** if Portal cannot write a cache Superset workers read, or if embed
screenshots/async jobs routinely outlive the guest JWT and you refuse to extend cache
TTL to cover them.

Do not pick A just because an earlier review proposed a broker. Do not pick B if it
implies GCP tokens sitting for an hour or a Redis that workers cannot see.

On GCP-token expiry mid-query: mid-flight BigQuery 401. Either variant: fail the chart
(fail-closed). Retry-once is optional and must not fall through to the metadata SA.
Write the choice down at implementation time.

### 3.5 Tenant, provider, and cache keys

- **Tenant:** one per deployment (Helm/env). JWT `tenant` is verified equal to that
  env. Mismatch → raise. Do not take `tenant` as “use this other client’s pool.”
- **Provider / IdP:** if the deployment has one provider, env is enough. If several
  IdPs share a pool, mint selects the provider from the user’s login issuer; JWT
  carries `iss_idp`; mutator (B) only verifies, because STS already happened at mint.
  Under Variant A the broker uses `iss_idp` + env to choose STS `audience`.
- **Credential-cache key (Variant B, and A if it caches GCP tokens):**
  `<env>:<tenant>:gcp:<jti>`. Value is `{ gcp_access_token, subject }`. Bare `jti` is
  forbidden. Costs nothing today; prevents cross-tenant reads if two deployments ever
  share a Redis.
- **May the credential cache share a Redis instance with Superset’s chart/data cache?**
  Yes, **instance** sharing is allowed if the key prefix cannot collide with
  `CACHE_KEY_PREFIX` (`superset_` in the Docker overlay, `docker/pythonpath_dev/superset_config.py`)
  and a cache **flush** of the chart DB is not applied to the credential DB. Prefer a
  **separate Redis logical DB index** (or a dedicated instance) so `FLUSHDB` on the
  chart cache cannot wipe live GCP tokens (fail-closed noise, not a leak). Must not
  store GCP tokens under the chart-cache prefix.

Unknown tenant or issuer → raise.

---

## 4. Database objects in Superset

### 4.1 Embedded BigQuery connections

- `impersonate_user` **off**. Upstream BigQuery impersonation is URL-username rewriting.
- No SIP-85 / `oauth2_client_info`. `BigQueryEngineSpec.supports_oauth2` is `False` in
  6.1.0 (**VERIFIED**).
- `CACHE_QUERY_BY_USER` actually on (3.1).

### 4.2 Metadata identity

Schema introspection, datasource editor, “sync columns from source,” and SQL Lab as
Admin run without a guest. They use a **dedicated low-privilege SA** on
`encrypted_extra`: metadata-level access, **no** grants that read rows behind a row
access policy. The mutator leaves non-guest, non-report-bot paths on this SA (3.3
step 2).

Prove this SA cannot read restricted data. Non-guest traffic that is **not** the
report executor uses this SA. The report GCP SA is a third identity (Section 9.2);
do not collapse the two.

### 4.3 Superset-side permissions

Grant the Guest role read on **all** embedded datasets, once. BigQuery is the only
per-user layer. Do not add Superset RLS on top.

Tradeoff: a mutator bug that fail-opens to the metadata SA is catastrophic if that SA
is over-granted — which is why 4.2 is strict and every unresolved guest branch raises.

---

## 5. Build order

| Step | Owner | Done when |
|---|---|---|
| 0. Design gate in writing | Product + security | ID-token, `oidc_aud` map, pool topology, no-grant behaviour, shared-cache vs broker, **STS quota vs peak concurrent embed users** |
| 0.5 ID-token-on-refresh lab per IdP | Portal | Each in-use IdP returns a usable ID token on refresh; TTLs recorded vs embed session; or the mechanism is rejected |
| 1. Pools, providers, `allowedAudiences`, IAM, RAPs | Infra | Standalone STS + query as the user; no-IAM user fails; wrong `oidc_aud` rejected |
| 2. Spike 3.0 injection **and** non-leak | Superset | Inject path works; two sequential Clients in one process do not cross; config-only vs fork decided |
| 3. Chosen variant | Portal + infra | B: Portal mint writes namespaced `jti` → `{ token, subject }` from the session; app **and workers** read it. A: broker bound to `jti`+subject, internal-only, subject-only rejected |
| 4. Secrets in app **and** worker | Infra | `guest_aud`, JWT secret, cache/broker creds, metadata SA |
| 5. Overlay: flags, validator hook, mutator | Superset | Unit tests in Section 6 |
| 6. Portal payload: CSPRNG `jti`, `user_subject` ≡ `username`, `tenant`, `guest_aud` | Portal | Decoded embed JWT shows them; no IdP/GCP token in the JWT; `jti` entropy test |
| 7. Staging e2e | Both | Section 6 |
| 8. Prod | Both | Same checks; old JWTs die within guest TTL |

Do not ship 6 without 5: a JWT with `jti` and no mutator queries as the metadata SA.

Do not start 3 before 0.5 and 1: mint-time or broker STS will fail in ways that look like
Superset bugs.

Do not start 5 before 2: a config-only estimate may be a lie.

---

## 6. Test plan

**Unit (mutator, Variant B):**

- Guest with namespaced `jti` present in cache, `binding.subject == user_subject` →
  client injected (mock cache).
- Guest `username != user_subject` → **raises**.
- Binding exists but `binding.subject != user_subject` → **raises** (cache-poison case).
- Guest missing `jti` → **raises**.
- Guest `jti` missing/expired in cache → **raises** (not metadata SA).
- Lookup with bare `jti` (no namespace) → miss → **raises**.
- Unknown/mismatched `tenant` → **raises**.
- Unknown `iss_idp` when required → **raises**.
- Non-BigQuery URI → unchanged.
- No `g.user` / non-guest, not report executor → metadata SA, no cache lookup.
- Non-guest whose username is the report executor → report SA credentials, no guest cache.
- Cache unreachable → **raises**.

**Portal mint:** a batch of guest JWTs has unique `jti` values; each is UUIDv4 (or
documented CSPRNG equivalent). Reject any mint that uses user id / session id /
subject / a counter as `jti`.

If Variant A is chosen, replace cache cases with broker: bound `jti` succeeds;
subject-only request from a test caller is **rejected** by the broker; broker down →
mutator raises.

**Staging e2e — two users, same embedded dashboard, different dataset IAM and RAPs:**

1. A sees A's rows; B sees B's or an error — never A's.
2. Same chart, both users, back to back: **B does not receive A's cached chart.**
   Highest-severity silent failure.
3. Flip B's IAM; next request after chart-cache TTL reflects it.
4. `POST /api/v1/security/guest_token/` as Admin → 400, and a handmade JWT without a
   cache binding → query **raises**, no SA data.
5. Wrong `guest_aud` → 401, no BigQuery.
6. Wrong `oidc_aud` at mint/STS → mint fails (B) or broker fails (A); no query as SA.
7. Async charts (if `GLOBAL_ASYNC_QUERIES` is on): worker resolves `jti`.
8. Dashboard screenshot as guest: same, or embed skips screenshots.
9. SQL Lab as Admin: metadata SA **cannot** read restricted rows.
10. **Expired / missing `jti` binding** mid-dashboard → charts error, not SA rows.
11. **IdP refresh failure** mid-session (revoke refresh token in the IdP) → next mint
    (B) or next broker STS (A) fails; remaining `jti` TTL behaves as in 3.4.
12. **User disabled mid-session** → same as 11; measure observed delay vs guest JWT TTL.
13. GCP token expiry mid-query: chart fails closed.
14. **BigQuery-side identity (same class as e2e 2).** User A loads a chart, user B loads
    the **same** chart in a separate session. Disable or bypass Superset chart cache for
    this case (`CACHE_QUERY_BY_USER` still on in production; this test must not rely on
    rendered rows). B's BigQuery job principal / `SESSION_USER()` is B, not A. A chart
    cache hit would mask an Engine/Client leak.
15. **`jti`/subject mismatch (cache poison).** Mint a valid token for A. Alter
    `username` / `user_subject` to B's subject, re-sign with the guest secret (HS256
    era) or with a stolen private key (RS256 era, should fail verify). Request a chart:
    mutator **raises**; B's chart cache is **not** populated.

**Load:** realistic chart count, cold vs warm `jti` cache. Record STS count per dashboard
open (B: ~1 per mint; not 1 per chart). Separately: **STS quota**. Compute
`peak_concurrent_embed_users × (60 / guest_jwt_ttl_seconds)` (uniform) and
`peak_concurrent_embed_users` (synchronized refresh). Compare both to the org's
Workforce STS quota (**1,000/min/org** default; confirm in console). Sum across every
embed environment in the org. If uncomfortable, record the tradeoff — longer guest JWT
TTL, or GCP-token TTL beyond one guest JWT — and do not adopt either in this plan.

**Negative:** mint for a subject with no BigQuery IAM → error, not data.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Cache serves one user's rows to another | `CACHE_QUERY_BY_USER` on as a **feature flag**; `username` ≡ `user_subject` ≠ `jti`; e2e case 2 |
| Guest-secret holder poisons another user's chart cache via `jti`/subject mismatch | Binding stores session `subject`; mutator step 8b; e2e case 15 |
| Supplied `Client` outlives the request and is reused across identities | **Not present at 6.1.0 Engine layer** (3.0). Spike must still rule out dialect/module stash. Regression: e2e case 14 (BigQuery job principal, not rows). If the spike finds stash, injection moves to connection scope or a fork — estimate changes. |
| Fail-open to metadata SA | Every unresolved guest branch raises; 4.2 SA cannot read RAP-protected rows |
| No ID token on refresh | 0.5 lab; stop if any in-use IdP fails |
| `oidc_aud` ≠ provider `allowedAudiences` | Gate + Section 1 step 2; e2e case 6 |
| `guest_aud` mismatch | Explicit config; e2e case 5 |
| Dialect ignores live client | Spike 3.0 on `user_supplied_client`; `_get_client` side path named |
| Variant B: workers cannot read Portal's cache | Precondition; e2e 7–8; otherwise Variant A |
| Variant B: Redis TTL = 1h GCP lifetime | TTL ≤ guest JWT remaining |
| Guessable `jti` | CSPRNG ≥128-bit, unique per JWT; mint unit test |
| Bare `jti` key on a shared Redis | Namespaced `<env>:<tenant>:gcp:<jti>`; separate logical DB from chart cache preferred |
| Workforce STS quota (1,000/min/org) | Gate projection vs peak concurrent embed; all client envs in the org share it |
| Variant A: broker reachable from browsers | Internal-only; mTLS; refuse subject-only |
| Variant A: cookie-less refresh-token use | Binding table is a high-value target; audit every STS |
| Delayed Celery job vs `jti` TTL | Cover queue delay or skip async/screenshots for embed |
| Mutator missing on worker | Same image; e2e 7–8 |
| Guest secret leak | Short guest `exp`; no GCP/IdP token in JWT; BQ IAM still required; binding-subject check; after Section 10, Superset cannot mint at all |
| Shared-cache compromise (B) | Short TTL; namespaced keys; no token logging |
| Wrong tenant's pool | Tenant from env; JWT only verifies |
| Report SA over-granted or confused with metadata SA | Distinct GCP SA; mutator step 2; Section 9 tests |
| Stock report sent to all recipients with no per-recipient WHERE | Do not enable reports until Portal/forked per-recipient loop exists (9.1, 9.3) |
| Metadata table/schema lists cached per database, not per user | Accept for v1; not row data |

Removed vs the previous draft: “broker compromise = token for any subject” as the
default shape (that was the subject-string broker). It returns if someone implements A
and forgets the `jti` binding.

---

## 8. Deferred

- Patching `GuestUser` for Jinja `current_user_email()`.
- Removing `can_grant_guest_token` from Admin (Section 10 is the preferred alternative).
- BigQuery engine-spec OAuth2 (unsupported in 6.1.0).
- Fixing `_get_client` / pandas-gbq to use the federated client, unless embed hits those
  paths.
- How the Portal backend authenticates to Superset's REST API (admin credentials today).
  Separate from guest-token signing (10.4).

Reports and asymmetric signing are no longer deferred; they are Sections 9 and 10.

---

## 9. Alert reports and scheduled delivery

**Status:** design settled; **not enabled**. Implement only after the enablement gate
(9.0) is green.

### 9.0 Enablement gate

Do **not** deliver RAP-protected datasets on a schedule until the RAP block is green.
Do **not** turn on stock `ALERT_REPORTS` at all until the Superset-path block is green.
This is a gate, not a backlog item.

**RAP-protected delivery (Portal loop, 9.3):**

| # | Required | Why |
|---|---|---|
| G1 | Mapping table exists (user/group → RAP dimension), same source the RAPs are generated from | R2; without it there is no honest per-recipient predicate |
| G2 | Portal delivery loop in production: one SQL query per recipient, predicate in `WHERE`, empty/missing predicate → zero rows / skip | Stock Superset cannot do this (9.1) |
| G4 | Dedicated report GCP SA, dataset-scoped; Portal uses it on the BQ client. Not the metadata SA, not embed | Privileged executor blast radius |
| G6 | Who may create a schedule and who may be a recipient is restricted in **Portal** (R3) | Recipients ≈ “may read everything the SA can read” |
| G7 | Section 9.5 tests pass, including “B's report matches B's embed” | Detects mapping drift before customers do |

**Superset-path reports** (stock `ALERT_REPORTS`, including the same-rows exception
below). Required before any Celery report runs `get_df` / screenshots:

| # | Required | Why |
|---|---|---|
| G3 | Mutator report-bot branch live (3.3 step 2) and covered by unit tests | Otherwise `override_user(report-bot)` still uses the metadata SA: empty RAP results, or someone over-grants 4.2 to “fix” it |
| G5 | `ALERT_REPORTS_EXECUTORS = [FixedExecutor("<report-bot>")]` and that `ab_user` exists with only the needed datasource perms | Default is `OWNER`; guests are not owners |
| G6b | Stock report UI restricted below Alpha (`ReportSchedule` is Alpha-only in 6.1.0) | A schedule aimed at a RAP dataset + G3 = one unfiltered payload to every recipient — a leak, not an empty result |

**Same-rows exception:** stock `ALERT_REPORTS` **may** run without G1–G2 only for
datasets where every recipient is allowed to see the **same** rows (no RAP, or RAP
that does not vary by recipient). Write that exception **per dataset**. G3, G5, G6b
still apply. Do not use this exception as a way to skip the Portal loop on RAP data.

**G3 does not make stock reports safe for RAP data.** Once the mutator injects the
report SA, a one-payload stock send is a full-table leak. Keep RAP datasets off
`ALERT_REPORTS` even after G3.

### 9.1 This is a different authorization model, not an extension of embed

The failure modes are inverted:

| | Embedded dashboards | Scheduled reports |
|---|---|---|
| Who enforces row visibility | BigQuery IAM + row access policies | Delivery-loop SQL (`WHERE` from the mapping table) |
| Identity on the query | The end user (WIF principal) | Report GCP service account |
| If the identity / filter layer breaks | No rows — **fails closed** | SA already fetched everything; a missing `WHERE` leaks — **fails open** |
| Evidence in BigQuery audit log | Per-user principal | One SA principal for all recipients |
| Delivery | One guest JWT → one user's charts | One schedule → **N queries**, one payload per recipient |

Reports run with no browser session and no live IdP token, so there is no user
credential to federate. A privileged executor plus a **per-recipient SQL loop** is
accepted deliberately — not as a shortcut, and not as “stock alerts with extra RLS.”

**Stock `ALERT_REPORTS` is one execution, one payload, N recipients.**
`AsyncExecuteReportScheduleCommand.run` picks a **single** executor via
`ALERT_REPORTS_EXECUTORS`, `override_user` once, builds **one**
`NotificationContent` (screenshot / CSV / dataframe), then `_send` that same content
to every recipient (**VERIFIED**, `superset/commands/report/execute.py` 614–753 and
1090–1100). Recipients are a notification list, not a query dimension.

That is the delivery-loop constraint. R1 and R2 cannot be satisfied by config. They
need a loop that issues a distinct SQL statement per recipient **before** anything is
sent.

### 9.2 Two identities, and the mutator branch

There is no `SELECTED_USER` executor type. **VERIFIED:** `ExecutorType` is
`FIXED_USER`, `CREATOR`, `CREATOR_OWNER`, `CURRENT_USER`, `MODIFIER`, `MODIFIER_OWNER`,
`OWNER` (`superset/tasks/types.py` 28–52). Default is
`ALERT_REPORTS_EXECUTORS = [ExecutorType.OWNER]` (`config.py` 1947). A fixed account is
`FixedExecutor("username")`, which `get_executor` returns as `FIXED_USER`
(`tasks/utils.py` 78–79).

`CREATOR` / `CREATOR_OWNER` are unusable for embed viewers: guests are not in `ab_user`.
`CURRENT_USER` is always `None` for Celery-initiated reports (`tasks/types.py` 43–44).

Two identities must both exist, or reports cannot read RAP data without wrecking 4.2:

| Identity | What it is | How it is selected |
|---|---|---|
| Superset user `<report-bot>` | `ab_user` row; becomes `g.user` during execution | `ALERT_REPORTS_EXECUTORS = [FixedExecutor("<report-bot>")]`. Datasource perms only; not Admin |
| Report GCP SA | BigQuery jobs identity | **Portal loop:** Portal’s BQ client uses this SA (G4). **Superset path:** mutator **3.3 step 2** — if not guest and `g.user.username` is `<report-bot>`, inject this SA from env/secret. Any other non-guest → metadata SA. Guests → WIF binding |

The mutator branch is the Superset-side half of G4. Without it, any
`override_user(report-bot)` still uses `encrypted_extra` (metadata SA). That SA is
forbidden from RAP rows (4.2), so stock/forked reports are empty — or someone
“fixes” it by granting the metadata SA data access and destroys SQL Lab / sync
isolation. The branch is required before G5’s executor ever runs a query; it is not
how the Portal loop authenticates to BigQuery (that is G4, in Portal).

Report GCP SA grants: only datasets actually distributed. Not `cloud-platform`, not
org-wide `bigquery.dataViewer`. RAPs do not constrain it (privileged executor). Damage
is bounded by dataset scope.

### 9.3 Delivery loop — where it lives, and the filter rules

The loop is: for each recipient, resolve the mapping-table predicate, run **one** SQL
query with that predicate in the `WHERE` (or skip/send-empty if the predicate is
missing), attach **that** result to **that** recipient, proceed. Never one fetch, then
split in memory. Portal issues those jobs on BigQuery with the report SA (G4). It does
not call `AsyncExecuteReportScheduleCommand` and does not use `get_df` under
`override_user(report-bot)` for RAP data.

#### Recommendation: Portal-side loop, not a Superset fork

**Choose Portal.** Do not fork `AsyncExecuteReportScheduleCommand` / notification
content generation to add a per-recipient re-query.

Reasons:

1. **The stock unit of work is the wrong shape.** Forking means changing “one
   `NotificationContent`, fan-out send” into “N queries, N contents, N sends” in the
   hottest report code (`execute.py`). That is a large, conflict-prone patch on every
   Superset upgrade. Portal already owns recipients, tenant, and (likely) the mapping
   table; a loop there does not sit on the upgrade path.
2. **Screenshots do not become honest by forking the send loop.** Stock dashboard/chart
   screenshots log in as the executor and capture whatever that user sees. Under 9.2
   that is the report-bot → mutator → report SA → **unfiltered RAP data** on screen.
   A fork that only re-queries CSV still emails a screenshot of everything. Making
   screenshots per-recipient would mean driving Selenium with a per-recipient filter
   injected into the live chart (guest-like RLS or SQL rewrite inside Explore). That
   is a second, larger fork. Portal should send **tables/CSV** for RAP datasets and
   not pretend a screenshot is row-safe.
3. **Fail-open lives in our code either way.** A filter bug leaks. Putting that bug in
   Portal keeps it next to the mapping table and out of `execute.py`, where a merge
   error on upgrade could silently revert to one-payload-for-all.
4. **Stock reports stay useful** for the 9.0 same-rows exception: ops dashboards,
   status emails. No fork required for that path. G3 must be live first, or those
   jobs hit the metadata SA.

Forked-Superset is the fallback only if product **requires** scheduled dashboard
screenshots that are RAP-correct per recipient. Budget it as a multi-sprint fork of
webdriver execution plus the send loop, re-applied on every upgrade. Do not start from
that.

#### Filter rules (apply inside the Portal loop)

They exist because the executor sees everything.

**R1 — Filter in SQL, never in memory.** The per-recipient predicate is in the `WHERE`
of the query issued for that recipient. Never `get_df()` once and subset a dataframe.
A missing, empty, or malformed predicate → **zero rows** (or skip send), never the
full table. The loop must treat “no predicate” as a hard failure of that recipient,
not as “no filter.”

**R2 — Same mapping table as the RAPs.** If RAPs are generated from user/group →
dimension, the loop reads that table. One definition, two consumers. A hand-written
report filter next to a generated RAP will diverge. No mapping table → G1 fails →
reports stay off (9.0).

**R3 — Recipients are an authorization decision.** Who may create a schedule and who
may be added as a recipient is equivalent to “who may read everything the report SA
can read.” `ReportSchedule` is Alpha-only in stock 6.1.0 (**VERIFIED**,
`ALPHA_ONLY_VIEW_MENUS`, `security/manager.py` 315–327). For Portal-owned delivery,
enforce the operator set and recipient review in Portal, not only in FAB. If stock
`ALERT_REPORTS` remains on for non-RAP datasets, still restrict that UI; Alpha is too
broad.

### 9.4 Rejected: reports as the real recipient

Running a report under the recipient's WIF identity would require Portal to store a
long-lived IdP refresh token per user, usable hours later with no session. That is a
worse posture than a scoped GCP SA: a durable, cookie-less path to user credentials
for a batch job. Rejected. Same class of risk as Variant A's cookie-less refresh-token
use.

### 9.5 Tests, when the gate is green

- Empty or null recipient predicate → zero rows / skip, not full table.
- Recipient with no mapping entry → not sent, or sent empty; never full.
- Report output for user B matches what B sees in the embedded dashboard for the same
  data. Divergence means R2 has already failed.
- Report SA cannot read datasets outside its declared scope.
- Mutator: report-bot username → report SA; other non-guest → metadata SA; guest →
  WIF binding. Report SA is none of the other two.
- Changing a mapping entry changes both the RAP/embed result and the report result.
- Stock `ALERT_REPORTS` one-payload path is not aimed at RAP-protected datasets.

---

## 10. Asymmetric guest-token signing (retires the shared secret)

**Status:** viable, likely config-only, needs a short spike. Defence in depth after the
binding-subject check; not a prerequisite for embed.

### 10.1 What the WIF redesign already fixed

Under DWD the guest token *was* authorization: an email claim determined BigQuery
results, so the signing secret was equivalent to data access.

That is no longer true. The token carries a `jti` that must resolve to a Portal-created
binding, and that binding's `subject` must match `user_subject`. A forged token yields
a `jti` with no binding, or a subject mismatch → mutator raises → no rows, and no
chart-cache write under the victim (e2e 15).

**What a leaked HS256 secret still buys:** Superset-side dashboard access as a guest
(resource list in the token), until expiry. Not BigQuery data, and not another user's
chart cache.

### 10.2 The change

Move guest tokens to **RS256**. Portal holds the private key and signs. Superset holds
only the public key and can verify but not mint.

- `GUEST_TOKEN_JWT_ALGO` is a free-form string passed to PyJWT (**VERIFIED**,
  `manager.py` 3015, 3079).
- Encode and decode both read `GUEST_TOKEN_JWT_SECRET` — no separate verify-key config
  (**VERIFIED**, 3014 and 3078).

Setting `ALGO = RS256` and putting the **public key PEM** in `GUEST_TOKEN_JWT_SECRET`
gives Superset verification only. Its encoder (`create_guest_access_token`) would break,
which is desired; issuance is already jammed by `GUEST_TOKEN_VALIDATOR_HOOK` (3.2).
This is what removing `can_grant_guest_token` from Admin would achieve, without a
security-manager patch.

### 10.3 Spike (before committing)

- PyJWT `decode` accepts a PEM public key in that config slot for RS256 at the pinned
  version. **ASSUMED** until run; PyJWT documents this, the spike is the pin.
- Nothing else in the guest path calls the encoder besides `create_guest_access_token`
  (**VERIFIED** call site: `security/api.py` 189). Issuance will fail at encode, not
  only at the validator hook — confirm a clean 4xx/5xx, not an uncaught 500 that hides
  other faults.
- `guest_aud`, `exp`, and required-claim checks behave the same under RS256.
- **Celery does not re-verify the JWT.** Async charts and screenshots stuff the
  already-decoded `guest_user.guest_token` **dict** into job metadata and rebuild
  `GuestUser` with `get_guest_user_from_token` (**VERIFIED**,
  `async_query_manager.py`, `tasks/async_queries.py`, `dashboards/api.py`). RS256
  matters on the HTTP `request_loader` path only. The spike should confirm workers are
  not accidentally re-encoding. This is existing trust of the dict, not introduced by
  RS256.
- Key rotation: no `kid`, no key ring (**VERIFIED** — one `GUEST_TOKEN_JWT_SECRET`).
  Rotation is a coordinated Portal-then-Superset deploy with a brief single-key window.
  Write the runbook.

If the spike fails, keep HS256 and rely on the binding-subject check plus secret
rotation. The plan remains sound either way.

### 10.4 Out of scope

How the Portal backend authenticates to Superset's REST API (dashboards, users, roles,
thumbnails) is a separate question, presumably admin credentials today. It does not
depend on this section and must not be bundled into it.

