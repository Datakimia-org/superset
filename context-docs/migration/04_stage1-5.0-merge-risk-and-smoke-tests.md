# Stage 1 (4.1.4 → 5.0) — Merge risk register & smoke tests

**Audience:** engineering doing merge review / QA before ephemeral or client-x  
**Branch context:** `chore/rebase-5.0.0` (staged merge vs fork HEAD `0e237a21f9`)  
**Companion:** [`01_fork-changes-vs-4.1.1.md`](./01_fork-changes-vs-4.1.1.md) · [`03_superset6.1-technical-migration-notes.md`](./03_superset6.1-technical-migration-notes.md)

This document lists **where the 5.0 merge intentionally diverged from fork-only behavior**, what **Datakimia product feature** each area serves, and **how to verify** it still works.

---

## How to read the risk register

| Column | Meaning |
|--------|---------|
| **Fork feature** | Product capability documented in `01_fork-changes…` |
| **Merge resolution** | What the staged tree does (fork kept / 5.0 adapted / hybrid) |
| **Risk** | What could break for users |
| **Smoke** | Manual checks (minimum) |
| **Automated** | Commands already run or recommended |

**Risk levels:** 🔴 high (core product / security) · 🟡 medium (edge cases) · 🟢 low (perf/style)

---

## Already verified green (automated)

Run on mounted 5.0 code with `--no-deps` (avoid broken `superset-init` dependency chain during local dev):

```bash
# Unit — guest chart/data cache isolation (3 tests)
docker compose run --rm --no-deps \
  -e PYTHONPATH=/app \
  -e SUPERSET_CONFIG=tests.integration_tests.superset_test_config \
  --entrypoint pytest superset \
  tests/unit_tests/charts/data/test_guest_cache_isolation.py -q

# Integration — guest cache (1 test; needs redis + db upgraded)
docker compose up -d redis db
docker compose run --rm --no-deps \
  -e PYTHONPATH=/app \
  -e SUPERSET_CONFIG=tests.integration_tests.superset_test_config \
  -e SUPERSET_TESTENV=true \
  -e REDIS_HOST=redis \
  --entrypoint bash superset -c \
  "superset db upgrade && superset init && superset load-test-users && \
   pytest tests/integration_tests/charts/data/guest_cache_isolation_tests.py -q"
```

| Gate | Status |
|------|--------|
| Guest `/chart/data` cache key isolation | ✅ 3 unit + 1 integration passed on 5.0 tree |
| `cache_keys.py` / guest logic in `api.py` | ✅ unchanged vs fork |

---

## Risk register (by product area)

### 1. Embedded / guest tokens / chart data 🔴

| | |
|---|---|
| **Fork feature** | Guest JWT embed, RLS, `POST /api/v1/chart/data` response cache keyed by `{username, resources, rls}` + body hash |
| **Files** | `superset/charts/data/cache_keys.py` (unchanged), `superset/charts/data/api.py` (5.0 upstream refactors around it) |
| **Merge resolution** | **Hybrid:** guest cache helpers **kept**; upstream renamed `apply_post_process` → `apply_client_processing`, logging tweaks |
| **Risk** | Cache HIT skips validation — key collision = cross-tenant leak. Upstream processing rename could change chart JSON shape for guests. |
| **Smoke** | 1) Two embedded dashboards, different guest tokens (different `username` or `rls_rules`), same chart filters → different data. 2) Reload same guest → faster response / `X-Chart-Data-API-Cache: HIT`. 3) Guest CSV / explore_json if used in Portal. |
| **Automated** | Tests above; re-run after any edit to `api.py` |

---

### 2. OAuth / Portal handshake / roles 🔴

| | |
|---|---|
| **Fork feature** | OAuth (Google/Azure/Auth0), popup `postMessage('OAUTH2_SUCCESS')` for Default-only users, `/login/<provider>/<username>`, custom roles |
| **Files** | `docker/pythonpath_dev/superset_config.py`, `custom_sso_security_manager.py` (unchanged), `superset-frontend/src/views/App.tsx` (hybrid) |
| **Merge resolution** | **Fork config kept.** `App.tsx`: handshake logic **kept**; 5.0 added `Layout.Content` wrapper (UI shell only) |
| **Risk** | Popup login broken; wrong role assignment; Portal account creation flow fails |
| **Smoke** | 1) Login Google/Azure/Auth0 from Portal popup → `OAUTH2_SUCCESS` received, session OK. 2) New non-@datakimia.com user → Default role. 3) @datakimia.com → Admin. 4) `/login/google/<username>` returns user id or 404. 5) Client_Admin can manage users, not full Admin-only APIs. |
| **Automated** | None in CI (`docker-build-push` has no pytest). Optional: existing integration tests for security if run locally |

---

### 3. Saved filter sets 🔴

| | |
|---|---|
| **Fork feature** | Save/load filter combinations per user (`DASHBOARD_FILTERS_SAVE` env), API `filter_sets`, Guest grants in init |
| **Files** | `FilterBar/index.tsx` (hybrid), `filter_sets/api.py` (unchanged), `docker-init.sh` step 3.5 (unchanged) |
| **Merge resolution** | **Fork product code kept** (Save, Saved filters, FilterSets modal, permalink hide). **5.0 upstream** changes absorbed: see rows 4–5 |
| **Risk** | Save/load broken; guest cannot save in embed; permalink shows Save buttons |
| **Smoke** | 1) `DASHBOARD_FILTERS_SAVE=true` in env → Save + Saved filters visible. 2) Apply filters → Save → name set → reload → apply from Saved filters. 3) Embedded guest with flag on → save works (init granted Guest API perms). 4) Open dashboard via **permalink URL** → Save/Saved filters **hidden**. 5) Delete/rename filter set. |
| **Automated** | None dedicated; manual only |

---

### 4. Native filters UI (FilterBar) 🟡

| | |
|---|---|
| **Fork feature** | Filter bar with save actions, permalink detection, calendar date picker (unchanged files) |
| **Files** | `FilterBar/index.tsx`, `FilterControls.tsx`, `FiltersConfigModal.tsx` |
| **Merge resolution** | **Hybrid** |
| **Risk** | Subtle behavior changes when editing dashboard filters |

**Specific deltas vs fork-only:**

| Change | Source | Risk | Smoke |
|--------|--------|------|-------|
| Removed `dispatch(clearDataMask)` when filter **config** changes (type/target/default) | 5.0 | Stale filter state in edit mode | Edit mode: change filter type → confirm values reset sensibly |
| `FilterBarScrollContext` moved from `index.tsx` → `Vertical.tsx` | 5.0 | Scroll/dropdown glitches in vertical bar | Long filter list: open selects while scrolling |
| `FilterControls`: cross-filters always computed (no `DashboardCrossFilters` flag gate) | 5.0 | Cross-filter behavior always on | Dashboard with cross-filters + native filters |
| `FiltersConfigModal`: antd5 class names + **PATCH** filter changes API | 5.0 | Save filter layout from edit mode fails | Edit dashboard → add/reorder/remove native filter → save dashboard |

---

### 5. Calendar date picker 🟢

| | |
|---|---|
| **Fork feature** | Custom presets, UTC custom range, DP-1010–DP-1023 fixes |
| **Files** | `CalendarDatePicker/*` (**unchanged** vs fork) |
| **Merge resolution** | Fork kept |
| **Risk** | Low unless 5.0 global date libs broke integration |
| **Smoke** | Presets (Today, This week, Previous month…), custom range inclusive end date, legacy “Last week” normalized, dashboard filter apply refreshes charts |

---

### 6. API response caching (metadata) 🟡

| | |
|---|---|
| **Fork feature** | Redis caches for datasets list, chart list, chart `_info`, saved queries; guest-aware keys |
| **Files** | `superset/views/base_api.py` (+ `validate_feature_flags` from 5.0), `superset/dashboards/api.py` (`get_datasets_for_dashboard_cached` kept) |
| **Merge resolution** | **Fork caching kept** + 5.0 decorator helper |
| **Risk** | Guest sees another tenant’s metadata lists; stale lists after permission change |
| **Smoke** | 1) Two users open same dashboard → datasets load; check no cross-user leakage in embed. 2) Chart list navigation twice → acceptable freshness (TTL 300s). 3) After role change, wait TTL or force refresh. |
| **Automated** | Guest chart/data tests cover chart/data only, not list endpoints |

---

### 7. Thumbnails / screenshots / reports 🟡

| | |
|---|---|
| **Fork feature** | Thumbnails on, WebDriver internal URL (DP-1020), 120s waits, Firefox default, Lautaro log traces |
| **Files** | `superset_config.py`, `dashboards/api.py`, `models/dashboard.py` |
| **Merge resolution** | **Hybrid:** 5.0 screenshot/thumbnail **flow** (`get_cache_key`, `ScreenshotCachePayload`, `@validate_feature_flags`, PDF download endpoint); fork **WebDriver config** kept; Lautaro `********` logs reinserted + `force` wired on `thumbnail()` |
| **Risk** | 499/timeouts if `WEBDRIVER_BASEURL` points to public URL; thumbnails never generate; embed screenshot missing `guest_token` (5.0 keeps it) |
| **Smoke** | 1) Dashboard list shows thumbnails (wait/async 202). 2) Edit dashboard → logs `Dashboard modification` in worker. 3) Download dashboard PDF/PNG from menu. 4) Optional: report email link uses `WEBDRIVER_BASEURL_USER_FRIENDLY`. 5) Embed dashboard screenshot if product uses it. |
| **Automated** | `tests/integration_tests/thumbnails_tests.py` (heavy; needs Selenium stack) |

**Config mapping (5.0):**

```python
# Was: THUMBNAIL_SELENIUM_USER / THUMBNAIL_EXECUTE_AS
THUMBNAIL_EXECUTORS = [FixedExecutor("admin")]
ALERT_REPORTS_EXECUTORS = [FixedExecutor("admin")]
```

---

### 8. Client-side PDF export 🟡

| | |
|---|---|
| **Fork feature** | `customDomToPdf.ts` + `jspdf ^3.0.4` (PR-0 CVE pin) |
| **Files** | `customDomToPdf.ts` (unchanged), `dom-to-pdf.d.ts` (same as upstream; unused at runtime) |
| **Merge resolution** | Fork pipeline kept; 5.0 also has **server-side** dashboard screenshot/PDF |
| **Risk** | `npm ci` / build fail; PDF blank or missing charts |
| **Smoke** | Dashboard → ⋮ → Download as PDF; verify multi-page, maps excluded, header controls excluded |
| **Automated** | `DownloadAsPdf.test.tsx` (unit); frontend build in Docker |

---

### 9. Docker / runtime / init 🔴

| | |
|---|---|
| **Fork feature** | Registry image, gcplogs, `pythonpath_dev` → `/app/config`, hardcoded admin password, Guest filter_sets grant, chart ownership SQL |
| **Files** | `Dockerfile`, `docker-compose*.yml`, `docker-init.sh` |
| **Merge resolution** | **Hybrid** |

| Change | Source | Risk | Smoke |
|--------|--------|------|-------|
| Dockerfile: pip → **uv**, Node **20**, multi-stage, dev **without Firefox** by default | 5.0 | **Build fail**; thumbnail worker differs | `docker build --target dev -t superset-local:test .` |
| Compose: services wait for **`superset-init`** completion | 5.0 | Init failure blocks all services | `docker compose up` → init green → app/worker start |
| `x-superset-depends-on` anchor **orphaned** (unused) | merge artifact | Confusion only | Cleanup optional |
| `docker-init.sh`: Cypress path uses `load_test_users` | 5.0 | Cypress-only | N/A for prod |
| **`bigquery_cache_patch.py`** still imported at config load | fork | Init/import errors outside app context | Watch init logs; BQ-heavy env |

---

### 10. `superset_config.py` flags 🟡

| | |
|---|---|
| **Fork feature** | Feature flags, Redis, Celery, SQL Lab limits, CORS, CSRF off |
| **Merge resolution** | **Fork body kept** + 5.0 deltas below |

| Setting | Fork | Staged 5.0 | Smoke |
|---------|------|------------|-------|
| `KV_STORE` flag | ON | **Removed** (upstream dropped KV store) | If clients use Scheduled Queries UI, verify still works via remaining config |
| `THUMBNAIL_SELENIUM_USER` | `"admin"` | → `THUMBNAIL_EXECUTORS` | Thumbnails (above) |
| `WEBDRIVER_BASEURL` | internal + friendly split | **Kept fork version** | DP-1020 smoke |
| Cypress hook | absent | **Added** | Only when `CYPRESS_CONFIG=true` |

---

### 11. Files unchanged vs fork (safe baseline)

These carry fork product logic **byte-stable** in the merge — regression unlikely from merge itself (still smoke if touched later):

- `superset/security/guest_token.py`
- `superset/charts/data/cache_keys.py`
- `superset/dashboards/filter_sets/*`
- `docker/pythonpath_dev/custom_sso_security_manager.py`
- `docker/pythonpath_dev/bigquery_cache_patch.py` (logic unchanged; runtime fragile)
- `superset-frontend/src/utils/getBootstrapData.ts`
- `superset-frontend/src/utils/customDomToPdf.ts`
- `superset-frontend/.../CalendarDatePicker/*`

---

## Recommended smoke order (ephemeral / client-x)

Run in order; stop if 🔴 fails.

### Phase A — Infrastructure (blocking)

1. **Image build:** `docker build --target dev -t superset-local:test .`
2. **Compose up:** `docker compose -f docker-compose-image-tag.yml up -d` (or dev compose with build)
3. **Init logs:** no fatal errors; migrations OK; Guest filter_sets grant printed; chart ownership SQL applied
4. **Health:** `curl -f http://localhost:8088/health`

### Phase B — Auth & embed 🔴

5. OAuth login (each provider configured for client)
6. Portal popup → Default user → `OAUTH2_SUCCESS`
7. Embedded dashboard with guest token → charts load
8. Guest cache: repeat same chart request (network tab or logs)

### Phase C — Dashboard product 🔴

9. Native time filter + calendar presets
10. Filter sets (if `DASHBOARD_FILTERS_SAVE=true`): save / load / guest / permalink hide
11. Edit mode: add native filter, save dashboard (`FiltersConfigModal` PATCH path)
12. Cross-filter dashboard (if client uses it)

### Phase D — Export & thumbnails 🟡

13. Download as PDF (client-side)
14. Dashboard thumbnail appears in list
15. Optional: email report / server screenshot

### Phase E — SQL / data 🟡

16. SQL Lab async query (6h limit config)
17. BigQuery dataset explore (watch for patch/import issues)

---

## Quick reference — commands

```bash
# Frontend build sanity (inside repo)
cd superset-frontend && npm ci && npm run build

# Guest cache unit (fast)
docker compose run --rm --no-deps \
  -e PYTHONPATH=/app \
  -e SUPERSET_CONFIG=tests.integration_tests.superset_test_config \
  --entrypoint pytest superset \
  tests/unit_tests/charts/data/test_guest_cache_isolation.py -q

# Filter sets API smoke (manual curl — replace token, dashboard id)
# GET  /api/v1/dashboard/{id}/filter_sets
# POST /api/v1/dashboard/{id}/filter_sets
```

---

## Merge wiring audit (fork vs 5.0 init)

Compare against `origin/master` after resolving `superset/initialization/__init__.py` conflicts. Confirmed losses from stage-1 merge:

| Severity | Item | Symptom | Fix |
|----------|------|---------|-----|
| 🔴 CRITICAL | `DashboardFilterSetsRestApi` not in `add_api` | `GET/POST /api/v1/dashboard/{id}/filter_sets` → 404 | Re-add import + `appbuilder.add_api(DashboardFilterSetsRestApi)` |
| 🔴 CRITICAL | `FeatureFlag.DashboardFiltersSave` missing in `featureFlags.ts` | Save / Saved filters buttons hidden even with env flag | Re-add `DashboardFiltersSave = 'DASHBOARD_FILTERS_SAVE'` |
| 🟡 MEDIUM | `install_request_tracking()` dropped from `configure_middlewares` | GCP logs missing `request_id` / HTTP access correlation | Re-add call from `superset.utils.request_tracking` |

**Not losses (upstream 5.0 intentional):** `KV` view, `SliceAsync`, `CssTemplateAsyncModelView`, `KV_STORE` flag, `ShareQueriesViaKvStore` enum.

**Preserved fork code (verify behavior, not registration):** guest cache (`cache_keys.py`), `CustomSsoSecurityManager`, `CalendarDatePicker`, filter-set commands, `bigquery_cache_patch.py` (replace in stage 1 per plan).

Post-fix: restart app; confirm routes with `filter_sets` in url map; re-run `superset init` if Guest PVM warnings on `DashboardFilterSetsRestApi`.

---

## Review cleanup (non-blocking)

- Remove dead `x-superset-depends-on` anchor from compose files
- Consider removing unused `dom-to-pdf` npm dep + `.d.ts` in a later cleanup PR
- Replace `bigquery_cache_patch.py` per stage-1 notes (do not carry to 6.0)
- Document client-specific `DASHBOARD_FILTERS_SAVE` and `OAUTH2_PROVIDERS` in runbook

---

## Sign-off checklist

| Area | Reviewer | Date | Pass |
|------|----------|------|------|
| Docker build + init | | | |
| OAuth / embed | | | |
| Guest cache (auto + manual) | | | |
| Filter sets + permalink | | | |
| Native filters edit mode | | | |
| Calendar date picker | | | |
| PDF + thumbnails | | | |
| client-x / ephemeral deploy | | | |
