# Superset 6.1 — Technical migration notes

**Audience:** engineering  
**Companion to:** [`00_superset6.1-stakeholder-migration-plan.md`](./00_superset6.1-stakeholder-migration-plan.md) (same item numbers).  
**Do not duplicate:** fork inventory [`01_fork-changes-vs-4.1.1.md`](./01_fork-changes-vs-4.1.1.md) · raw changelogs [`02_changelogs-4.1.1-to-6.1.0.md`](./02_changelogs-4.1.1-to-6.1.0.md).

Sources: `UPDATING.md` @ tags `6.0.0` / `6.1.0`; MCP admin docs (Next); compiled changelog 4.1.1→6.1.0; fork inventory; fork source (`charts/data/api.py`, `guest_token.py`, `superset_config.py`).

SQLGlot / RLS rewrite is **6.0 → stage 2**, not stage 1. Stage 1 still has virtual-dataset SQL changes.

**Do not conflate:** the fork’s guest **response** cache key is token claims (`username` + `resources` + `rls`), hashed with `md5_sha_from_dict` (**always MD5**). 6.0 SQLGlot and 6.1 `HASH_ALGORITHM` do **not** rewrite that key. `HASH_ALGORITHM` SHA-256 invalidates **thumbnail/digest** caches (10-year TTL). Cross-tenant leak on `chart/data` is **key collision + skip validate**, e.g. shared `guest_user` username and empty `rls_rules` while tenancy is only in Jinja.

---

## Related docs

| File | Role |
|---|---|
| [`00_…stakeholder-migration-plan.md`](./00_superset6.1-stakeholder-migration-plan.md) | Product/scope, no config keys |
| [`01_fork-changes-vs-4.1.1.md`](./01_fork-changes-vs-4.1.1.md) | What we carry vs 4.1.1 |
| [`02_changelogs-4.1.1-to-6.1.0.md`](./02_changelogs-4.1.1-to-6.1.0.md) | Upstream changelog dump |
| This file | Config, APIs, PRs, acceptance that 00 omitted |

Official:

- [UPDATING.md @ 6.1.0](https://github.com/apache/superset/blob/6.1.0/UPDATING.md)
- [MCP server](https://superset.apache.org/admin-docs/configuration/mcp-server/)
- [Upgrading](https://superset.apache.org/admin-docs/installation/upgrading-superset)

---

## 0. Rebase fork to 4.1.4 + jspdf + cache test

Not a major. Cherry-pick / rebase `4.1.2`–`4.1.4` onto the fork.

| Release | Must-test for this product |
|---|---|
| **4.1.2** | #33435 CVEs · #32500 dashboard/chart/dataset **import validation** · #31024 SQLGlot DML check on datasets · #31198 extra ClickHouse functions disallowed · #32043 skip secondary perms during catalog migrations |
| **4.1.3** | #32240 / #33612 base image CVE bumps · #30858 **strip `query` from `/chart/data` for guest users** · `h11` / `marshmallow<4` pins |
| **4.1.4** | #32236 `cryptography` 43.0.3 → 44.0.1 |

`UPDATING.md` only lists #31198 and #31173 for 4.1.x. **#31173 is not a rebase blocker here:** `WTF_CSRF_ENABLED = False`. Optional smoke if Portal still calls `/csrf_token/`.

**Now, same bucket:** pin `jspdf` to **v3** (`package.json` has `^2.5.1`; CVE-2025-29907 / CVE-2025-25977; upstream #32802).

**Guest cache isolation test (gate for both hops).** Two guest tokens, different tenancy, same dashboard + filters:

1. Assert cache **keys** differ (log `chart_data_api:{context}:{body}` components).
2. Assert payloads differ.
3. “Dashboard looks right” is **not** enough (passes on a cold cache).

If `username` is missing, GuestUser uses `guest_user`. Isolation then depends on `resources` + `rls_rules`. If tenancy is only Jinja/`current_user_email`, keys can collide and a **HIT skips RLS entirely**.

During each cutover: **disable** `CHART_DATA_ENDPOINT` guest cache until the test is green on the target version.

---

## Stage 1 — 4.1.4 → 5 (staging)

### 1.1 Runtime, images, metadata

- Python: 3.9 deprecated; **3.11 recommended**; 3.10 still supported through 5.0. Standardise images on **3.11** (MCP later needs 3.11+).
- Docker: `uv pip install` instead of `pip` (#31262). Custom driver bootstrap scripts must follow.
- Translations not in default images unless `BUILD_TRANSLATIONS=true`.
- `dev` layer: Chromium only (no Firefox).
- React **16.13.1 → 17.0.2** (#31961); `superset-frontend` **TypeScript 5** (#31979). SQL Lab results grid → **AG Grid** in 5.0 (#29900) — conflicts if we patch that pane (calendar picker is Explore/dashboard time filter, not this grid).
- Metadata: #30398 `UUIDMixin` on most models (time on a prod-sized copy); #29649 Dataset constraint drop; #31959 upload-endpoint refactor.

Alembic is linear (`superset db upgrade` + `superset init`). Two stages are blast-radius only. **No `db downgrade`.** Rollback = snapshot + YAML export + **re-apply** `docker/01-create-chart-ownership-trigger.sql` / backfill + verify `%Admin%` owners. The trigger is **not** in the Superset schema. `setuptools<75` in our Dockerfile collides with `uv pip install`.

### 1.2 Login / Portal

Fork: `CUSTOM_SECURITY_MANAGER`, `AUTH_OAUTH`, extra `/login/<provider>/<username>`. 5.0 does not drop OAuth. CSRF validation is **off** — do not spend the hop on #31173. Still re-test sessions, cookies, popup `postMessage`.

### 1.3 Roles, guest, drill

- #31412 deprecates `DRILL_TO_DETAIL` — feature is **always on** in the BI UI. Embed drill lands in **6.0** (#34319).
- Guest already has `explore_json` + CSV + `DASHBOARD_RBAC = True` — closer to D2D than a stock embed role. Audit Guest against 6.0 D2D perms **explicitly**.
- Roles are **rebuilt every boot** from permission name lists. Missing names → silently thinner roles. Assert the **resulting permission set** per role; “init did not raise” is not a pass.
- Fork `GuestUser.id` lookup (`01` §3) must keep working. Check whether apache/superset#24837 (`is_item_public` JWT workaround) is fixed upstream before porting it.

### 1.4 Embed SDK (Portal lockstep)

Test on 5: #30858 guest query stripped; #31798 CSRF skipped for embedded dashboard download; #32646 `dashboardId` in `form_data`.

Package: `@superset-ui/embedded-sdk` (versioned independently).

### 1.5 Portal APIs

| Change | PR | Effect |
|---|---|---|
| `css`, `position_json`, `json_metadata` removed from `GET /api/v1/dashboard` **list** | #29121 | Catalog payloads shrink |
| Legacy dashboard endpoints removed | #31943 | Pre-v1 Portal routes break |
| Legacy CSS template endpoint removed | #31942 | If white-label used CSS templates |
| Data-upload endpoints replaced; perms simplified | #31959 | |
| Legacy `/kv` still works in 5; **permalinks only in 6.0** | #29163 | Stage-2 break. Filter-set `KeyValueEntry` is **not** this API. `FEATURE_FLAGS["KV_STORE"]` becomes unknown. |

### 1.6 Fork features

Triage is in `01`. This hop is **M–L**.

| Feature | Stage 1 | Stage 2 | Action |
|---|---|---|---|
| Filter sets (`KeyValueEntry`, no extra Alembic) | **M** port API+storage | **L** FilterBar AntD rewrite | Confirm live flag; keep records |
| BigQuery monkey-patch | **M** replace with #30266 context manager | **S** if replaced, **L** if carried | Do not take the patch to 6.0 |
| Response caches | **M** + isolation test | **M–L** | Carry; disable guest `chart/data` cache at cutover |
| Calendar picker | **S–M** port | **M** or **S** as extension | Extension in 6.1 |
| SSO + roles | **M** | **M–L** two FAB majors | Carry; permission-set test |
| GuestUser id | **S** | **S–M** | Carry |
| GCP logging | **S** | **S** | Carry |
| PDF / jspdf | **S** pin v3 | **drop** | Delete stack |
| MapBox / bootstrap parser | **S** | retest | Probably drop |
| Chart-ownership trigger | **S** | **S** | Carry; rollback runbook |

Also:

- Filter-set APIs vs #31754 (“apply to all panels” removed).
- `docker-init.sh`: `superset init` → Guest filter-set grants → ownership SQL. On 6.0 `init` is required for `FAB_ADD_SECURITY_API`; verify the sequence.
- `FEATURE_FLAGS["SCHEDULED_QUERIES"]` is inert (config key since 1.5).

**Five suites before the 5 rebase** (only two `_info` tests exist today):

| Suite | Assert |
|---|---|
| Cross-tenant cache isolation | Two guests → different keys and payloads |
| RLS generated SQL | Snapshot SQL + row counts, physical and virtual |
| Role bootstrap | Resulting FAB permission set per role |
| Guest token → embed | Issue, `ab_user.id`, render, filter-state PUTs refused |
| Filter sets round-trip | CRUD + 20-set eviction |

### 1.6b Config keys that die or move

| Fork setting | What happens | When |
|---|---|---|
| `THUMBNAIL_SELENIUM_USER` / `THUMBNAIL_EXECUTE_AS` | Use `THUMBNAILS_EXECUTORS` + `FixedExecutor` | 5.0 |
| `THUMBNAILS_EXECUTE_AS` / `ALERT_REPORTS_EXECUTE_AS` names in `UPDATING.md` | Renamed `*_EXECUTORS`; `CACHE_WARMUP_EXECUTORS` | 5.0 |
| `KV_STORE = True` in flags | Flag removed | 5.0 |
| `HORIZONTAL_FILTER_BAR = True` | Flag removed, feature always on | 6.0 |
| `HTML_SANITIZATION = False` | Default True; override must be explicit | 6.1 |
| `INCLUDE_CHROMIUM` | Default **false** on lean; Pillow required | 6.0 |
| `setuptools<75` | Collides with `uv pip` | 5.0 |
| `GLOBAL_ASYNC_QUERIES_REDIS_CONFIG` | → `GLOBAL_ASYNC_QUERIES_CACHE_BACKEND` | 5.0 |
| Public logo hide | Theme tokens `brandAppName` / `brandLogoUrl` | 6.1 |
| `ENVIRONMENT_TAG_CONFIG` | AntD semantic colours only | 6.0 |

### 1.7 Generated SQL / virtual datasets / RLS (5.0 only)

Not the parser rewrite.

- #31486 **predicates pushed into virtual datasets** — generated SQL, BigQuery bytes, cache.
- #30903 virtual dataset columns re-synced when SQL changes.
- #33337 metric quoting in sort-by when `normalize_columns` is on.

**Accept:** capture SQL + row counts per tenant for virtual-dataset + RLS charts before/after.

### 1.8 BigQuery catalogs

Catalog ≅ GCP project.

- Cache keys include catalog (#31910, #31948).
- Dataset/query catalog updated on DB changes (#32829).
- BigQuery returns no catalogs without credentials (#31837).
- Saved-query import schema gains catalog (#32775).

Permission-sync per client; expect cache miss.

### 1.9 Screenshots / reports

- `THUMBNAILS_EXECUTE_AS` → `THUMBNAILS_EXECUTORS`; `THUMBNAILS_SELENIUM_USER` **removed**; `FixedExecutor`; `CACHE_WARMUP_EXECUTORS`; `ALERT_REPORTS_EXECUTE_AS` → `ALERT_REPORTS_EXECUTORS` (#31844).
- Fork uses `THUMBNAIL_SELENIUM_USER = "admin"` and `THUMBNAIL_EXECUTE_AS = [ExecutorType.SELENIUM]` — map to `THUMBNAILS_EXECUTORS` / `FixedExecutor`.
- `THUMBNAIL_CACHE_CONFIG` TTL ≈ **10 years**. 6.1 SHA-256 rebuilds **this** cache (not the fork `chart_data_api` MD5 keys). Warm-up per client, or temporary `HASH_ALGORITHM = "md5"` **only as a thumbnail bridge**.
- Dashboard screenshots via Celery (#32193); Playwright empty-dashboard shots (#33107); configurable Selenium binary (#33103).
- `PLAYWRIGHT_REPORTS_AND_THUMBNAILS` already optional in our config.

### 1.10 Cutover / assets / cache

- Import validation already from 4.1.2 (#32500).
- 5.0: password masked on DB import (#33267); `encrypted_extra` importable (#32339).
- Full cache invalidation assumed (fork has extra Redis response caches).
- Log retention (#32572); `ENABLE_CORS` still on in the fork (6.0 will require the CORS extra explicitly).

### 1.11 Acceptance extras

Legacy charts removed (#31582): Area, Bar, Event Flow, Heatmap, Histogram, Line, Sankey, Sankey Loop → ECharts except **Event Flow** and **Sankey Loop** (gone). Time-compare migrations patched in 4.1.2 and 5.0 (#32538, #33592, #33710). Spanish: FAB `LocaleView` redirect (#31692).

---

## Stage 2 — 5 → 6.1 (includes 6.0)

### 2.1 Platform / 6.1-only breaks

**6.0**

- Flask-AppBuilder **5.0** in 6.1 cycle (#36086 → 5.0.2); 6.0 already realigns FKs to FAB 4.6 tables (#32759). `AUTH_OID` gone — we use `AUTH_OAUTH`, no provider migration, still a full login pass.
- List Roles → frontend; requires `FAB_ADD_SECURITY_API = True` and `superset init` (#32432).
- Ant Design v5 + Emotion; `THEME_OVERRIDES` **gone** (#31590).
- `ENVIRONMENT_TAG_CONFIG`: only `success` / `processing` / `error` / `warning` / `default`.
- Dockerfile `INCLUDE_CHROMIUM` default **`false`** (lean layer).
- Pillow **required**; `thumbnails` extra deprecated for **7.0**.
- `DISALLOWED_SQL_FUNCTIONS` expanded — existing SQL Lab / virtual SQL may fail.
- CSV export `utf-8-sig`.
- `x_axis_sort_series` → `x_axis_sort` migration (#33116) — can touch many charts.
- Dataset export filenames include dataset id.
- `ENABLE_CORS` requires installing the CORS extra (#32662).
- OpenStreetMap default deck.gl tiles.

**6.1**

- `APP_NAME` no longer sets browser title / frontend branding → theme token `brandAppName` (`APP_NAME` backend fallback).
- `CUSTOM_FONT_URLS` **removed** → per-theme `fontUrls`.
- Default hash **MD5 → SHA-256** (#35621): invalidates thumbnail / dashboard / chart digest / filter-option cache keys. Opt-out: `HASH_ALGORITHM = "md5"` (do not keep long-term).
- `HTML_SANITIZATION` reset default **True**. Fork has it **False** (`01` §9) — explicit decision, do not inherit the new default blindly.
- `clickhouse-connect >= 0.13.0` (only if we ship ClickHouse).
- `DISTRIBUTED_COORDINATION_CONFIG` (was `SIGNAL_CACHE_CONFIG`) for Redis production / Global Task Framework.
- GAQ WebSocket Docker: `docker/superset-websocket/config.json` gitignored; update volume.
- **Node 22** (`feat!` #37223); webpack → **SWC** (#35946); `thread-loader` removed. CI, `.nvmrc`, any custom webpack in the fork.
- `pandas` 2.1 required in 6.0 (#35912).

Metadata 6.0: theme tables, dataset-folders, `metric.currency` JSON, x-axis sort rename. 6.1: Global Task Framework tables (`GLOBAL_TASK_FRAMEWORK` off by default), dynamic currency, viz `form_data` as dict.

Time `UUIDMixin` (5) and FAB FK realignment (6.0) on a prod-sized metadata DB.

### 2.2 MCP (ships in 6.1 — #35877)

Docs “5.0+” is the **floor**, not the ship version. Code is `superset/mcp_service/`. Optional `fastmcp` / `apache-superset[fastmcp]`. **No DB migration.** Start: `superset mcp run --host 0.0.0.0 --port 5008`. Endpoint `/mcp`. Python **3.11+**. No `MCP_SERVICE` feature flag — process presence is enablement.

Guest JWT is **not** MCP auth. Resolver maps JWT → `ab_user.username`. Default `MCP_RBAC_ENABLED = True`. `execute_sql` needs `can_execute_sql_query` on SQLLab.

| Setting | Notes |
|---|---|
| `MCP_AUTH_ENABLED` | Production **True**. False + `MCP_DEV_USERNAME` is **dev only** |
| `MCP_JWT_ALGORITHM` | `RS256` or `HS256` |
| `MCP_JWKS_URI` / `MCP_JWT_PUBLIC_KEY` / `MCP_JWT_SECRET` | One of these |
| `MCP_JWT_ISSUER` / `MCP_JWT_AUDIENCE` | Audience **required** at start when JWT auth is on (6.1 `UPDATING.md`) |
| `MCP_REQUIRED_SCOPES` | e.g. `mcp:read`, `mcp:write` |
| `MCP_AUTH_FACTORY` / `MCP_USER_RESOLVER` | Custom; factory wins |
| `MCP_DISABLED_TOOLS` | Hide built-ins |
| `MCP_STORE_CONFIG` + `CACHE_REDIS_URL` | Multi-replica sessions |
| `MCP_SERVICE_URL` | Public URL behind proxy (not auto-detect) |
| `MCP_RBAC_ENABLED` | Leave `True` |

Action log: `mcp.<tool>.<phase>` with duration/success — no extra pipeline required for basic monitoring.

Compose: second service, same image/config, command `superset mcp run`.

### 2.3 Login, embed, drill, SDK

- #34319 Drill to Detail / Drill By **in Embedded and `DASHBOARD_RBAC`**. Deny = Guest/embed roles **without** D2D perms.
- #33670 seven `RowLevelSecurityFiltersModelView` permissions **deleted** — audit custom roles (`Guest`, `Default`, `Client_Admin`, `Datakimia_Public`).
- #36548 built-in Public role for anonymous dashboards; #37295 Public can read themes; #38474 `CurrentUserRestApi` read on Public defaults.
- #36195 `AUTH_RATE_LIMITED` actually works — watch SSO bursts.
- #39098 custom `auth_view` in security manager; #35290 `get_session` → session attribute — **direct hits** on `CustomSsoSecurityManager`.
- #27086 `@api` / `@has_access_api` on **all** `filter_state` methods — embed dashboards use filter state.
- SDK 6.0: #34273 theme alignment; #32735 forced iframe `referrerPolicy`; #32997 / #31331 `getDataMask`; #33673 `GUEST_TOKEN_JWT_AUDIENCE`; #33356 `SUPERSET_APP_ROOT` in embed URLs; #35454 guest `active`.
- SDK 6.1: #36125 `setThemeMode()`; #36924 `resolvePermalinkUrl`; #36237 `getChartDataPayloads` (SDK 0.3.0); #37537 `DISABLE_EMBEDDED_SUPERSET_LOGOUT`; #38644 embed defaults to **light** theme not OS; #38846 `hideTab` wired.

### 2.4 Portal APIs (6.x)

- Permalinks only (#29163 completed in 6.0).
- Dataset export filenames include id.
- #38952 access check on `SqlExecutionResultsCommand`; #38647 legacy datasource view access.
- 6.1 SQL execution API (#36529) and Explorable protocol (#36245) — prefer these over undocumented Portal routes (non-AI). Not a substitute for MCP.

### 2.5 Fork rebase hotspots (6.0)

#34177 deduplicated `sqla/models.py` and `models/helpers.py`. `parse_sql` / `is_select_query` removed (#33474 / #33457). **Do not carry `bigquery_cache_patch` into this hop** — it patches a private method that moves; replace in stage 1. Frontend `theme.colors.*` will not compile (#34732 / #34056).

Filter-set **UI** rebuild on AntD v5 FilterBar; reuse `KeyValueEntry`. Calendar picker → Time Filter extension (#33829, #36376).

Per leftover feature: re-apply, drop, or **extension** (`LOCAL_EXTENSIONS`, `apache-superset-extensions-cli`, code-first #38346).

### 2.6 SQLGlot + RLS (highest backend risk)

6.0 removed `sqlparse` and reimplemented SQL on SQLGlot:

| PR | What |
|---|---|
| #33456 / #33473 | limit extract/set |
| #33518 | CTEs |
| #33524 | **RLS** |
| #33525 | CVAS / CTAS |
| #33542 | SQL Lab |
| #33560 | adhoc subquery validation |
| #33564 | drop `sqlparse` |

SQLGlot bumped 26.x → 28.10 during the cycle.

RLS trail:

- 6.0: #33524, #33942 wrapper, #34374 subquery alias, #36061 **RLS in virtual datasets**, #34192 related-tables filter, #33670 perm deletions
- 6.1: #38683 table alias, **#37395 double RLS in virtual datasets (embedded)** — 6.0 bug in our config, #37941 batch RLS for digests

Jinja: `current_user_rls_rules()` (#33614), `current_user_roles()` (#32770). 6.1 #39207 renders Jinja **before** SQLGlot; #38984 passes datasource table for schema-aware render. Fork has `ENABLE_TEMPLATE_PROCESSING = True` — test tenant Jinja explicitly.

Other generated-SQL (same capture set):

- 6.0: #35890 double time filter in virtual datasets; #36215 adhoc quoting; #35342 adhoc `ORDER BY`; #32228 recursive metrics; #34360 catalog name in generated SQL; #35350 cross-catalog quoting
- 6.1: #38704 drop `WHERE 1 = 1` when temporal filter is “No filter” (cache key + BQ cost); #38183 parenthesize extras WHERE/HAVING

**Accept:** per-client generated SQL **and** row counts for known tenants; embed + virtual dataset is mandatory. Do not stop on 6.0.

This suite is **query/RLS**, not the fork response-cache key. Re-run the **token-claim** cache isolation test on 6.1 as well (parser bugs can still change **payloads** while keys stay the same).

### 2.7 Theming

- Break: `THEME_OVERRIDES`, Bootstrap/FA, `DeprecatedThemeColors` / `theme.colors.*`.
- Themes are **DB objects**: CRUD (#34182, #34560), import/export (#34850), seeding guards (#34433). 6.1 validation + fallback (#37378); Public can read themes (#37295); inline theme to avoid 403 (#38384).
- Fork `EXTRA_CATEGORICAL_COLOR_SCHEMES` / hide-logo CSS: re-express as theme tokens or DB themes.
- 6.1 `fontUrls` replaces `CUSTOM_FONT_URLS`.

### 2.8 Screenshots

- 6.0 tiled Playwright (#34561) default `SCREENSHOT_TILED_ENABLED = True` (20+ charts or height > 5000px); `SCREENSHOT_PLAYWRIGHT_WAIT_EVENT` default `domcontentloaded`; timeout 30→60s.
- 6.1 #35063 Playwright with Selenium fallback; timeouts → ERROR; SHA-256 digest rebuild.
- Lean image: set `INCLUDE_CHROMIUM=true` if we still screenshot in-cluster.
- Fork `WEBDRIVER_BASEURL` internal vs public (`01` §7) still applies.

### 2.9 Topology / cache / assets

- MCP process (or pod) beside web.
- Cache: 6.0 sanitises SQL before **upstream** cache keys (#35419); 6.1 `HASH_ALGORITHM` + thumbnail digest sort (#38079). Fork `chart_data_api:*` keys stay MD5 of token+body. Assume thumbnail **full invalidation**; do not assume guest chart-data keys rotate with SHA-256.
- Assets: 6.0 sparse import (#32670); 6.1 `masked_encrypted_extra` import/export (#38077 / #38078).
- Optional `GLOBAL_TASK_FRAMEWORK` (#36368) — not required to migrate; direction of travel for thumbnails/reports/SQL Lab.

### 2.10 Security checklist (config + validate)

- [ ] Guest/embed roles: D2D perms allow or deny **explicitly** (Guest is relatively open)
- [ ] Custom roles vs deleted RLS ModelView perms; **boot-time permission set** matches expected
- [ ] `FAB_ADD_SECURITY_API` + `superset init`; `docker-init.sh` order still grants Guest filter-sets
- [ ] MCP JWT audience set; `MCP_AUTH_ENABLED`; no `MCP_DEV_USERNAME` in client env
- [ ] `HTML_SANITIZATION` / Talisman: named owner; consider `HTML_SANITIZATION_SCHEMA_EXTENSIONS`
- [ ] Replace `X-Frame-Options: ALLOWALL` with CSP **`frame-ancestors`** listing Portal origins
- [ ] `GUEST_TOKEN_JWT_AUDIENCE` still matches Portal-minted tokens
- [ ] `filter_state` API still works for embed after #27086
- [ ] `AUTH_RATE_LIMITED` vs SSO
- [ ] Guest `chart/data` cache isolation green; cache off during cutover
- [ ] COOP/COEP/CORP still required until CSP is in place

### 2.11 / 2.12 Acceptance and client-visible behaviour

Spanish: async language pack (#34119), load-before-React (#36893), ES updates (#35070), corrupted ES strings removed (#37717).

Also ticket-class, not outage: horizontal filter bar always on (flag removed); #32870 filter panel hidden by default; #33781 row-limit warning (hidden in embed #34095); #37459 auto-refresh rework; #35418 Explore autotrigger removed; Matrixify; AG Grid table plugin (6.0+) vs SQL Lab AG Grid (already 5.0).

---

## Fork collisions to re-test on both hops

From `01`, items most likely to break against upstream 5/6.1:

| Fork piece | Why |
|---|---|
| `CustomSsoSecurityManager` | FAB 5, #39098, #35290, extra login routes |
| `GuestUser.id` lookup | Guest token consume still permissive; id/email still not stock |
| Filter sets (KV + API + FilterBar) | Native filters moved twice; 6.0 FilterBar UI rewrite |
| Calendar date picker | TimeFilterPlugin vs 6.0 filter bar / #37459 |
| `bigquery_cache_patch` | Catalog in engine identity; SQLGlot; urllib3 |
| Chart/dashboard Redis response caches | Token-claim keys; HIT skips validate; **not** SHA-256/SQLGlot |
| `getBootstrapData.ts` Python-dict parse | Theme bootstrap in 6.0; retest, probably drop |
| Thumbnail `THUMBNAIL_SELENIUM_USER` | `FixedExecutor` / Playwright; 10-year TTL + SHA-256 |
| `HTML_SANITIZATION = False` | 6.1 default True |
| `DASHBOARD_VIRTUALIZATION = False` | Re-test; prefer fix over keeping off |
| Postgres Admin-owner trigger | Re-apply after metadata migrate |
| `jspdf` PDF path | 6.0 screenshot/PDF stack; product still shows PDF menu |
| COOP/COEP headers | OAuth popup + embed |

---

## Opportunities (implementation pointers)

- Extensions: **calendar date picker first** (time filters #33829, registry #36376), then chart header (#34678), 6.1 code-first (#38346), SQL Lab API, `LOCAL_EXTENSIONS`, CLI.
- User groups (#32121) + React List Groups (#33301).
- DB themes import/export instead of fork CSS.
- Jinja `current_user_roles()` / `current_user_rls_rules()` only after 2.6 SQL/RLS suite is green.
- 5.0 `SUPERSET_CUSTOM_HTML` / injectable `<head>` (#29917) as a possible logo/script replacement.

---

## Suggested engineering sequence (maps to 00)

1. Rebase to **4.1.4**; pin **jspdf v3**; guest `/chart/data` query-strip; **cache isolation test**.
2. Five suites in §1.6; confirm live `DASHBOARD_FILTERS_SAVE`.
3. Stage 1: 5 + UUIDMixin timed on prod-sized DB; **replace BQ patch**; SQL/row-count sample; catalog perm-sync; `FixedExecutor`; guest cache off at cutover; no prod cutover.
4. Stage 2: 6.1 in staging; **SQLGlot + RLS + embed virtual datasets**; cache isolation again; FilterBar/filter-set UI; theme + CSP/`HTML_SANITIZATION`; MCP process+JWT; thumbnail warm-up; fleet.
