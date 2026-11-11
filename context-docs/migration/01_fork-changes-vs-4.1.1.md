# Datakimia fork vs Apache Superset 4.1.1

Inventory of product changes on top of upstream **4.1.1**. Use this to size the 5.x / 6.1 migration (carry, replace, or drop).

## Scope

| | |
|---|---|
| **Baseline** | Apache Superset tag `4.1.1` (`6264ff5165`, 2024-11-15) |
| **Fork snapshot** | `origin/master` (`d419417125`, 2026-07-17) |
| **Method** | `git diff 4.1.1...origin/master` plus commit history on that range |
| **Not in this inventory** | Upstream 4.1.2–6.1.0 changes, and docs-only work on `superset-migration-6.1` |

All 430 commits on `origin/master` after `4.1.1` are Datakimia work (no later Apache releases mixed in). ~299 non-merge commits. **125 files** changed: **+10,931 / −11,911** lines. Most of the volume is `package-lock.json` and deleted Apache GitHub workflows.

Core product code (excluding lockfile, CI deletions, and `context-docs/`) is roughly **~80 files** and **~6k lines added**.

---

## Migration triage

Default for the 5 → 6.1 upgrade: **re-apply only what the product still needs**. Grouping follows the stakeholder plan.

### Carry (custom code; no upstream equivalent)

| Area | Why it must be ported or rebuilt |
|---|---|
| Saved **filter sets** | Upstream removed this in 4.0. Reimplemented as API + UI on `KeyValueEntry` (no extra Alembic table). Flag default **off**. Stage 1: port storage+API; stage 2: rebuild filter-bar UI. |
| **Calendar date picker** | Replaces the stock dashboard time-range control. Stage 2: rebuild as Time Filter extension (#33829 / #36376). |
| **Custom SSO security manager** | Roles (`Guest`, `Default`, `Client_Admin`, `Datakimia_Public`), OAuth login-by-username helper, public-item JWT workaround. Recreated **every app start** — assert resulting permission sets. |
| **GuestUser DB id lookup** | Embedded guests get a real `ab_user.id` for logging. Default token username is `guest_user` if Portal omits one. |
| **API response caches** | Extra Redis cache on chart data/list/info, saved-query list, dashboard datasets. Guest key = **token** `username` + `resources` + `rls` (JWT `rls_rules`), not generated SQL. Hits **skip query validation**. Isolation test before either hop. |
| **GCP JSON logging + request IDs** | Custom configurator and middleware. |
| **OAuth popup → Portal handshake** | `postMessage('OAUTH2_SUCCESS')` when a Default-role user opens in a popup. |
| **Chart ownership trigger** | Postgres trigger: every Admin becomes owner of every slice. **Not in the Superset schema** — re-apply after every restore. Postgres-only. |
| **COOP/COEP/CORP headers** | `unsafe-none` / `cross-origin` so OAuth popups and embeds work. Until CSP `frame-ancestors` in stage 2. |

### Replace with config / theme / extensions (prefer not to keep as patches)

| Area | Upstream path on 5 / 6.1 |
|---|---|
| Feature flags, cache TTLs, WebDriver, CORS, OAuth providers | `superset_config` / env only |
| Hide logo for Public, empty-chart copy, color schemes | 6.0 DB-managed themes + tokens (`brandLogoUrl`, `brandAppName`) |
| Horizontal filter bar, embedding, thumbnails, dashboard RBAC, Jinja | Feature flags (already upstream); `HORIZONTAL_FILTER_BAR` flag **removed in 6.0** (always on) |
| **BigQuery engine cache + urllib3 pool** | 5.0 #30266 engine context manager. **Replace in stage 1**; do not carry the monkey-patch to 6.0 (#34177). |
| Calendar date picker | After stage-1 port: 6.0/6.1 Time Filter extension (#33829 / #36376); #37098 may shrink presets |
| Docker image, GCP Artifact Registry, compose logging labels | Deployment, not product code |

### Drop or decide explicitly

| Area | Note |
|---|---|
| **PDF stack (`jspdf`)** | Pin **v3 now** (CVE-2025-29907 / CVE-2025-25977; we ship `^2.5.1`). Then delete custom pipeline unless product still requires client-side PDF. |
| **Dashboard virtualization OFF** | Re-test on 5/6.1 (#36011, #35265); prefer fixing the bug over keeping the flag off. |
| **Talisman / HTML sanitization / CSRF / `ALLOWALL`** | Stage-2 named decision. CSRF already off. Prefer schema extensions + CSP `frame-ancestors`. |
| **MapBox init + bootstrap parser** | Retest on 6.1; likely obsolete. |
| **Hardcoded init admin password** | Restore `ADMIN_PASSWORD` env. |
| Apache **GitHub workflows** deleted | Do not restore upstream CI. |
| `KV_STORE` / `SCHEDULED_QUERIES` in `FEATURE_FLAGS` | `KV_STORE` **removed in 5.0**. `SCHEDULED_QUERIES` as a flag is **inert**. Filter-set `KeyValueEntry` is not legacy `/kv`. |

Nothing in this fork is “already upstream in 4.1.1” in the sense that we can delete our code and keep the behavior. Several **flags** we turn on *are* upstream features (embedding, thumbnails, RBAC, Jinja, horizontal filter bar).

---

## 1. Authentication and identity

**Files:** `docker/pythonpath_dev/superset_config.py`, `docker/pythonpath_dev/custom_sso_security_manager.py`, `superset/app.py`, `superset-frontend/src/views/App.tsx`

- Auth is **OAuth** (`AUTH_TYPE = AUTH_OAUTH`), not database login.
- Providers are selected with `OAUTH2_PROVIDERS` (comma-separated): **Google**, **Azure Entra ID** (v2.0), **Auth0**.
- Optional **domain whitelist** via `AUTH_USER_DOMAIN_WHITELIST`.
- Self-registration is on. Role at signup:
  - email ends with `@datakimia.com` → **Admin**
  - otherwise → **Default**
- `CUSTOM_SECURITY_MANAGER = CustomSsoSecurityManager`.
- Extra login route: `/login/<provider>/<username>` returns the user’s numeric id (lookup by username, then email) or 404. Used by the Portal, not by humans.
- After login in a **popup** (`window.opener`): if the user has **only** the `Default` role, the app posts `{ type: 'OAUTH2_SUCCESS' }` to the opener and keeps the session; otherwise it logs out. That is the Portal account-creation / guest handshake.
- CORS enabled for `CORS_FRONTEND_ORIGIN`; `X-Frame-Options: ALLOWALL` (not a spec value — browsers ignore it; replace with CSP `frame-ancestors` in stage 2); CSRF disabled (`WTF_CSRF_ENABLED = False`); Talisman disabled.
- Response headers: `Cross-Origin-Opener-Policy: unsafe-none`, `Cross-Origin-Embedder-Policy: unsafe-none`, `Cross-Origin-Resource-Policy: cross-origin` (OAuth popups + embedding).
- Workaround for [apache/superset#24837](https://github.com/apache/superset/issues/24837): `is_item_public` optionally parses a JWT so permalink / public access is not broken by leftover tokens.

---

## 2. Roles and permissions

Roles are created at security-manager init (every app start) from permission lists in `custom_sso_security_manager.py`.

| Role | Purpose |
|---|---|
| **Guest** | Embedded / guest-token users (`GUEST_ROLE_NAME`). Read dashboards/charts, filter state, permalinks, `explore_json`, CSV, recent activity. Filter-sets API is granted again in `docker-init.sh`. |
| **Default** | Self-registered non-Datakimia users. Broader than Guest (explore, export, menu access, guest-token grant, filter-set write). |
| **Client_Admin** | Client-side user/role admin (FAB user/role APIs and menus). Not a full Superset Admin. |
| **Datakimia_Public** | Template for `PUBLIC_ROLE_LIKE`. Public dashboard URLs: dashboard/permalink/explore_json, time-range API, tags, share. |

`docker-init.sh` also:

1. Runs `superset init`.
2. Grants Guest `can_get/post/put/delete` on `DashboardFilterSetsRestApi`.
3. Applies chart-ownership SQL (section 10).

---

## 3. Embedding, guest tokens, public dashboards

**Files:** `superset/security/guest_token.py`, `superset-frontend/src/utils/getBootstrapData.ts`, `superset-frontend/src/features/home/Menu.tsx`, FilterBar / FilterControls

- `EMBEDDED_SUPERSET = True`. Guest JWT TTL **2 hours**.
- `GuestUser.id` is resolved from `ab_user` by **username** (not the anonymous mixin). Logging and cache keys can use a real user id. Lookup failures are swallowed so auth still works. If the token omits `user.username`, GuestUser defaults to **`guest_user`** — then cache isolation depends entirely on `resources` + `rls`.
- `self.rls` is `token.get("rls_rules", [])` — token claims, **not** generated SQL.
- Embedded **bootstrap JSON** may arrive as a Python dict (`{'key': ...}`) or HTML-escaped attribute. `getBootstrapData.ts` unescapes entities and converts Python quotes to JSON.
- **Public** role users: navbar brand/logo hidden; filter bar shows **only the time filter**.
- Dashboard metadata / chart-configuration / label-color **PUTs are skipped** when `dash_edit_perm` is false (anonymous / guest must not persist dashboard JSON).
- Permalink filter-set **Save / Saved filters** buttons are hidden when the URL has a permalink key (those views are read-only).

---

## 4. Saved filter sets (largest product feature)

Upstream removed dashboard filter sets in 4.0. This fork puts them back, stored per user in the **key-value** table (`KeyValueEntry`, resource `filter_set_<dashboard_id>`), cap **20** sets (oldest dropped).

Flag: `DASHBOARD_FILTERS_SAVE` from env `DASHBOARD_FILTERS_SAVE` (default **false**). Frontend enum: `FeatureFlag.DashboardFiltersSave`.

| Layer | Paths |
|---|---|
| API | `GET/POST /api/v1/dashboard/<id>/filter_sets`, `PUT/DELETE .../filter_sets/<set_id>` |
| Commands | `superset/commands/dashboard/filter_sets/{create,get,update,delete}.py` |
| Registration | `superset/initialization/__init__.py` |
| UI | Filter bar **Save** + **Saved filters**; `SaveFilterModal.tsx`, `FilterSets.tsx` |

Payload per set: `id`, `timestamp`, `dataMask`, `appliedFilters`, optional `customLabel`.

**6.1 note:** no maintained upstream replacement. Storage is cheap and safe (`KeyValueEntry`, 20-set cap). **Confirm live `DASHBOARD_FILTERS_SAVE` per client** (git is not runtime). If on: port API+storage in stage 1; rebuild FilterBar UI in stage 2 against the same records.

---

## 5. Calendar date picker

**Files:** `CalendarDatePicker.tsx`, `calendarDatePickerPresets.ts`; `TimeFilterPlugin.tsx` swaps stock `DateFilterControl` for this picker.

Dashboard native **time** filters use a calendar UI plus presets, not the Explore-style advanced time control. **Stage 2:** rebuild as a Time Filter **extension** rather than patching `TimeFilterPlugin.tsx` again.

Presets (resolved by upstream `get_since_until`):

- No filter, Today, This week / month / year
- Previous week / month / year (calendar periods; week starts Monday)

Legacy rolling values (`Last week/month/year`) are normalized to the calendar equivalents on apply so old dashboards keep working.

Custom range handling is **UTC**; the inclusive end date is the last moment of the selected day. Several DP-1010–DP-1023 fixes live here.

---

## 6. Caching and BigQuery performance

### 6.1 Redis and endpoint caches

SQL Lab results backend is **Redis**, not the filesystem. Default cache TTL is `CACHE_DEFAULT_TIMEOUT` (env, default **86400s**).

Extra response caches (env-overridable):

| Endpoint | Default TTL | Cache key includes |
|---|---|---|
| `GET /api/v1/dashboard/<id>/datasets` | 300s | user id, or guest username+resources+RLS |
| `GET /api/v1/chart/` (list) | 300s | same |
| `GET /api/v1/chart/_info` | 60s | same + query string |
| `GET /api/v1/saved_query/` | 60s | same |
| `POST /api/v1/chart/data` | 120s, max 2 MB body | same + request body hash; only JSON/`full`, not `force` |

Guest payload hashed via `md5_sha_from_dict` (always **MD5**, independent of 6.1 `HASH_ALGORITHM`):

```python
{"username": ..., "resources": ..., "rls": ...}  # g.user from the guest JWT
```

Then `chart_data_api:{context}:{body_hash}`. Hits skip `ChartDataCommand.validate()` and return the stored JSON. **SQLGlot does not participate in this key.** Collision risk: two tenants with the same username (or default `guest_user`), same dashboard resources, and same/empty `rls_rules`, while tenancy is applied only in Jinja/catalog.

Metadata DB pool: `pool_size=10`, `max_overflow=20`, `pool_recycle=3600`, `pool_pre_ping`.

### 6.2 BigQuery client patch

`docker/pythonpath_dev/bigquery_cache_patch.py` (imported from `superset_config`):

1. Raises urllib3 `PoolManager` default `maxsize` **10 → 50** (only if the caller did not set it).
2. Caches `Database._get_sqla_engine` in-process, keyed by db id, schema, catalog, source, user, and a config hash.

This is a monkey-patch on `Database._get_sqla_engine`. **Replace in stage 1** with the 5.0 engine context manager (#30266). Do not carry it to 6.0 (#34177 refactor — fails at **runtime**, not merge). Catalog is already in the patch’s cache key (correct for 5.0+).

Celery: `worker_max_tasks_per_child = 10`; reports scheduler hourly (not every minute); rate limits on SQL Lab / email reports.

---

## 7. Thumbnails, screenshots, reports

Flags: `THUMBNAILS`, `THUMBNAILS_SQLA_LISTENERS`, `ALERT_REPORTS`. Config names in the fork: `THUMBNAIL_SELENIUM_USER = "admin"`, `THUMBNAIL_EXECUTE_AS = [ExecutorType.SELENIUM]` (upstream 5.0 removes these for `THUMBNAILS_EXECUTORS` / `FixedExecutor`). Thumbnail Redis TTL ≈ **10 years** (`THUMBNAIL_CACHE_CONFIG`).

WebDriver:

- Internal `WEBDRIVER_BASEURL` (default `http://superset:8088/`) — must **not** be the public URL (DP-1020: 499 / timeouts).
- Public `WEBDRIVER_BASEURL_USER_FRIENDLY` for email links.
- `SCREENSHOT_LOCATE_WAIT` / `SCREENSHOT_LOAD_WAIT` = **120s**.
- `PLAYWRIGHT_REPORTS_AND_THUMBNAILS` optional via env.

Extra logging around thumbnail cache keys and “forced / missing / dashboard modified” triggers.

---

## 8. PDF and image export

- Dependency: `jspdf` **`^2.5.1`**. Pin **v3 immediately** (CVE-2025-29907, CVE-2025-25977; upstream #32802). Then drop `customDomToPdf.ts` / `pdfUtils.ts` unless product still requires client-side PDF.
- `DownloadAsPdf` accepts `visible` (default **true**). DP-743 intended to hide PDF and keep image export; **current master still shows PDF**.
- Decide the product rule on 6.1, then either drop the custom PDF stack or wire `visible={false}` in the download menu.

---

## 9. Other UI behavior

| Change | Where |
|---|---|
| Empty chart title: “No data available to display” | `ChartRenderer.jsx` |
| Hide cross-filters in the filter bar (DP-667) | `FilterControls.tsx` |
| `DASHBOARD_VIRTUALIZATION = False` | Avoids re-fetch on scroll |
| `HORIZONTAL_FILTER_BAR = True` | Horizontal native filters |
| `ENABLE_JAVASCRIPT_CONTROLS = True` | JS in tooltips / controls |
| `ENABLE_TEMPLATE_PROCESSING = True` | Jinja in SQL |
| `HTML_SANITIZATION = False` | Needed by some client dashboards; security trade-off |
| MapBox markers missing until pan/zoom | `componentDidMount` + 300ms `forceUpdate` |
| Extra categorical palettes | `COLOR_SCHEMES` JSON env → `EXTRA_CATEGORICAL_COLOR_SCHEMES` |
| Dashboard layout JSON limit | `SUPERSET_DASHBOARD_POSITION_DATA_LIMIT = 131072` (DP-832) |
| FAB list page size | `FAB_API_MAX_PAGE_SIZE = 5000` |

---

## 10. Chart ownership (Postgres)

**Files:** `docker/01-create-chart-ownership-trigger.sql`, `docker/02-set-admins-as-chart-owners.sql`

On every `slices` insert/update, users whose role name matches `%Admin%` are attached as owners (after clearing previous Admin owners on that slice). Init also backfills all existing slices.

Admins can always edit every chart. The trigger is **Postgres-specific** and must be reapplied after metadata DB restore/migration.

---

## 11. Logging and observability

**Files:** `superset/utils/gcp_logging_configurator.py`, `superset/utils/request_tracking.py`, `superset/config.py`, `docker/run-server.sh`, `superset/stats_logger.py`

- `LOGGING_CONFIGURATOR = GCPLoggingConfigurator` — JSON logs for Cloud Logging.
- Request middleware: `request_id`, user, method, path, trace headers.
- Gunicorn access log disabled by default so Flask JSON logs are the source of truth (`ACCESS_LOG_FILE` can re-enable it).
- `ENABLE_PROXY_FIX = True` for real client IPs behind a proxy.
- Compose: `gcplogs` driver / labels per service (`superset_app`, `superset_worker`, …).

---

## 12. Docker, CI/CD, operations

Not product UX, but they are fork deltas vs 4.1.1.

| Change | Detail |
|---|---|
| Images | `us-central1-docker.pkg.dev/.../superset` instead of Apache Scarf images |
| Dockerfile | Pins `setuptools<75`; copies `docker/pythonpath_dev` → `/app/config/`; `postgresql-client` for init SQL |
| `SUPERSET_LOAD_EXAMPLES=no` | No example dashboards |
| Init admin password | Hardcoded in `docker-init.sh` (upstream used `ADMIN_PASSWORD`) |
| GH Actions | Apache workflows removed. Added `docker-build-push.yml` (Artifact Registry + WIF) and `database-migration.yml` |
| Scripts | `deploy_updated_version.sh`, `docker/migrate_database.sh`, `update_secrets.sh`, DB restore helper |
| Frontend deps | `jspdf`, `luxon` ^3.7.2, `PyAthena==3.9.0` |
| Async SQL Lab | `SQLLAB_ASYNC_TIME_LIMIT_SEC` 6h, `SQLLAB_TIMEOUT` 300s, `KV_STORE` + `SCHEDULED_QUERIES` on |

---

## 13. Feature flags (effective on the fork)

Set in `docker/pythonpath_dev/superset_config.py` unless noted.

| Flag | Fork | Upstream 4.1.1 docker default |
|---|---|---|
| `ALERT_REPORTS` | ON | ON |
| `KV_STORE` | ON | off |
| `SCHEDULED_QUERIES` | ON | off |
| `EMBEDDED_SUPERSET` | ON | off |
| `TAGGING_SYSTEM` | ON | off |
| `THUMBNAILS` / `THUMBNAILS_SQLA_LISTENERS` | ON | off |
| `DASHBOARD_RBAC` | ON | off |
| `ENABLE_TEMPLATE_PROCESSING` | ON | off |
| `DASHBOARD_VIRTUALIZATION` | **OFF** | on |
| `HORIZONTAL_FILTER_BAR` | ON | off |
| `ENABLE_JAVASCRIPT_CONTROLS` | ON | off |
| `HTML_SANITIZATION` | **OFF** | on |
| `TALISMAN_ENABLED` | **OFF** | on |
| `DASHBOARD_FILTERS_SAVE` | env, default **off** | n/a (fork-only) |
| `PLAYWRIGHT_REPORTS_AND_THUMBNAILS` | env, default off | off |

Confirm live values per environment; git history is not the runtime source of truth.

---

## 14. Tests

Only two integration tests exist (`_info?q=(keys:!(permissions))` on chart and dashboard). Filter sets, calendar picker, SSO, caches, and the BigQuery patch are untested. Stage 1 must add isolation / RLS / role-permission / guest-embed / filter-set suites before the 5 rebase.

---

## 15. File map (product code)

New (not in 4.1.1):

```
docker/pythonpath_dev/custom_sso_security_manager.py
docker/pythonpath_dev/bigquery_cache_patch.py
docker/01-create-chart-ownership-trigger.sql
docker/02-set-admins-as-chart-owners.sql
superset/dashboards/filter_sets/api.py
superset/commands/dashboard/filter_sets/{create,get,update,delete}.py
superset/utils/gcp_logging_configurator.py
superset/utils/request_tracking.py
superset-frontend/src/dashboard/components/nativeFilters/FilterBar/
  FilterSets.tsx, SaveFilterModal.tsx, filterSetsApi.ts, filterSetsStorage.ts
superset-frontend/src/filters/components/Time/CalendarDatePicker.tsx
superset-frontend/src/filters/components/Time/calendarDatePickerPresets.ts
superset-frontend/src/utils/customDomToPdf.ts
superset-frontend/src/utils/pdfUtils.ts
```

Heavily modified:

```
docker/pythonpath_dev/superset_config.py
docker/docker-init.sh
superset/config.py
superset/initialization/__init__.py
superset/app.py
superset/security/guest_token.py
superset/dashboards/api.py
superset/charts/data/api.py
superset/views/base_api.py
superset-frontend/src/dashboard/components/nativeFilters/FilterBar/index.tsx
superset-frontend/src/views/App.tsx
superset-frontend/src/utils/getBootstrapData.ts
```

---

## How to refresh this inventory

```bash
git fetch origin
git diff --stat 4.1.1...origin/master
git diff --name-status 4.1.1...origin/master
git log --no-merges --oneline 4.1.1..origin/master
```

If the product branch is no longer `origin/master`, replace it with the 4.1.1-based release branch. Do not diff `superset-migration-6.1` against `4.1.1` — that range includes Apache 5/6.1 as well as Datakimia patches.
