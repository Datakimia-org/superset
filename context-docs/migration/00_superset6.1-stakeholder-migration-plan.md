# Superset 6.1 — Migration & Product Integration (conceptual / stakeholders)

**Audience:** client / stakeholders  
**Level:** conceptual overview — not an implementation plan.  
**Not in this doc:** technical design or implementation options. Engineering notes: [`03_superset6.1-technical-migration-notes.md`](./03_superset6.1-technical-migration-notes.md).

Rough complexity per area: **S** (small) · **M** (medium) · **L** (large)

---

## Executive summary

We are moving the product from our Superset **4.1.1** fork to **6.1**. Production stays on 4.1.x until stage 2 is accepted. We do **not** park production on 5 or 6.0.

**Strategy — two hops, one production target.** Go **4.1.1 → 5 in staging**, then **5 → 6.1 into production**. Two stages exist to **isolate blast radius** (login/embed, SQL/RLS, UI, and our fork patches fail in different ways). They are not required by the metadata upgrades. **5 is a waypoint**, not a release we sell. **MCP ships in 6.1 only**; there is nothing to turn on in stage 1.

Each client has its own Superset. Every hop is **pilot client → fleet**: N metadata upgrades, N config diffs, N acceptance passes, N cutover windows.

**Do now, before stage 1:** (1) rebase the fork to **4.1.4**; (2) prove that two embedded viewers with different tenancy cannot share a cached chart payload; (3) patch the PDF library we ship (`jspdf`) — it is behind upstream CVE pins. All three are independent of the 5 / 6.1 project.

**Critical points — these can break the product or a tenant if they are treated as side effects:**

1. **No metadata-database downgrade.** Rollback is snapshot restore, **re-apply the chart-ownership trigger**, then verify Admin ownership. Also export dashboards/charts/datasets as YAML before the hop. Time each upgrade on a production-sized copy.
2. **Embedded chart cache must not mix tenants.** We cache chart API responses for guest users. A cache hit returns data **without re-running the query**. Isolation depends on the guest token identifying the tenant uniquely. Prove this with an automated test **before** either hop; consider turning that cache off during cutover.
3. **Login, roles, and Portal embed must be re-proven on both hops.** SSO (Google / Microsoft / Auth0), custom roles (including Guest), and the Portal embed library move in lockstep with Superset. If this fails, users cannot open BI.
4. **Row-level security and generated SQL are the highest-risk query work**, concentrated in **stage 2** (6.0 replaces the SQL parser and reimplements RLS; 6.1 fixes double RLS on virtual datasets in embed). Acceptance is a **SQL + row-count diff** for known tenants, not “the dashboard loads.” Stopping on 6.0 is not attractive. This is separate from the embed **response** cache in point 2.
5. **Embedded drill-down in 6.0 is a tenancy/security change.** Drill to Detail / Drill By become available in embedded dashboards. Our Guest role is already relatively open (explore + CSV). Guest/embed roles must allow or deny drill-down **on purpose**.
6. **Fork features are sized; filter sets are not “drop by default.”** Most of the fork is config and small patches. Stage 1 custom work is **M–L**; stage 2 is **L** because the filter bar is rewritten. Saved **filter sets** live in the normal key-value store (no extra database migration). Confirm they are actually on per client, then **keep storage + API in stage 1** and **rebuild the UI in stage 2**. Inventory: [`01_fork-changes-vs-4.1.1.md`](./01_fork-changes-vs-4.1.1.md).
7. **MCP is a stage-2 product feature, not a flag.** It runs as the real Superset user. **Embedded guests do not get MCP.** Dev-only “run as a fixed user” must never reach a client environment.
8. **The 6.0 UI rewrite breaks old theming/CSS.** Thumbnail cache is stored for ~**10 years**; the 6.1 hash change rebuilds all of it at once — a fleet-wide cold Portal. White-label must be ported or replaced with managed themes. Embed iframe / HTML sanitization rules are a **stage-2 decision**, not a silent copy of today’s settings.
9. **Some chart types disappear in stage 1** (Event Flow, Sankey Loop) with no replacement. Audit client dashboards before the 5 hop. Spanish UI/locale is part of acceptance on both stages.

The rest of this document is the coarse work breakdown behind that strategy.

---

## 0. Before Stage 1 — 4.1.4, cache-isolation test, PDF library — **S**

The fork sits on **4.1.1**. **4.1.2, 4.1.3 and 4.1.4** followed in the same line and are mostly security work. That exposure is live today and is **independent of the migration**.

Material for this product includes: CVE fixes; harder validation when importing dashboards/charts/datasets; and, in embedded mode, **no longer returning the generated query** to guest users (on 4.1.1 that is SQL disclosure to client end users).

Also now: pin/upgrade **`jspdf`** (we ship `^2.5.1`; upstream 5.0 pinned v3 for known CVEs), and ship the **two-guest cache isolation test** so stage 1 has a gate.

This is a patch rebase, not a major upgrade. Do it **now**, not during Stage 1.

---

## Stage 1 — Land on Superset 5 (waypoint)

Get the fork and the current product working on Superset 5 in **staging**. There is **no MCP to enable** on 5 — the service does not exist in that release. Do not cut production over to 5: upstream support is already on the 6.x line.

### 1.1 Migrate Superset from 4.1.4 to 5 — **L**

Bring our fork onto the Superset 5 baseline. This includes:

- Moving the codebase and dependencies onto Superset 5
- Upgrading the Superset metadata database (time this on a production-sized copy; several models gain new identifiers)
- Rebuilding and validating images / local and deployed environments (runtime and frontend build change in this hop)
- Handling upstream breaking changes that affect how Superset runs

**Why it matters:** stage 2 is only safe if the product already works on 5 in staging.

### 1.2 Keep login and Portal↔Superset trust working — **L**

Users sign in via Google / Microsoft / Auth0 and the Portal talks to Superset on their behalf. After the upgrade we must re-validate that login, session continuity, and Portal→Superset access still work end to end.

### 1.3 Roles, permissions, and embedded “guest” access — **M–L**

We use custom roles (including Guest for embedded dashboards). These must be re-checked on Superset 5 so viewers still see only what they should.

**Drill to Detail** becomes always-on in the BI UI in 5 (the old on/off switch is retired). In this stage it is a logged-in-user concern, not yet an embedded one. Confirm it does not leak rows the tenant should not see.

### 1.4 Embedded dashboards in the Portal — **M**

Dashboards shown inside the Portal must keep loading correctly for normal (non-admin) users, including refresh of temporary access. The Portal embed library must be upgraded **in lockstep** with Superset.

### 1.5 Portal features that call Superset APIs — **M**

Portal screens that list dashboards, manage users/roles, show thumbnails, etc. depend on Superset APIs. Those integrations need a regression pass and likely small fixes where responses or behavior changed.

Concrete 5.0 deltas to check: older (pre-v1) dashboard routes are gone; the dashboard **list** payload no longer includes layout/CSS/metadata fields; data-upload endpoints and permissions changed.

### 1.6 Our custom Superset changes (fork features) — **M–L**

Beyond stock Superset we carry custom behavior (saved filter sets, calendar date picker, SSO/roles, response caches, BigQuery engine patch). For each: **re-apply on 5**, **replace with a simpler approach**, or **drop**. Inventory: [`01_fork-changes-vs-4.1.1.md`](./01_fork-changes-vs-4.1.1.md).

Most of this hop is configuration and small patches. The expensive pieces: **response caches** (isolation test in §0), **SSO/roles**, and replacing the **BigQuery monkey-patch** with the supported engine hook so we do not carry it into 6.0.

**Filter sets:** upstream deleted them in 4.0; we put them back in the **standard key-value store** (no extra Alembic chain). The flag defaults to **off** — confirm live use per client. If they are in use: **keep storage + API in this stage**; the costly part is the **filter-bar UI in stage 2**, not the data.

Also in this stage: automated tests that the fork almost does not have today (cache isolation, RLS SQL snapshots, role permission sets, guest embed, filter-set round-trip). Manual clicking will not catch a wrong cache key or a silently thinner role.

### 1.7 Generated SQL, virtual datasets, and row-level security — **M–L**

On 5, how charts become SQL already changes (filters are pushed into virtual datasets). That affects BigQuery cost, cache, and tenancy.

For a representative set of client charts (especially virtual-dataset + RLS): capture **generated SQL and returned row counts** before and after the hop, and diff. Acceptance is not “the dashboard loads.”

(The larger SQL-engine rewrite lands in stage 2.)

### 1.8 BigQuery catalogs and permissions — **M**

In BigQuery, a catalog is a GCP project. 5 starts treating catalogs as first-class (cache keys, saved queries, credentials). Plan a **permission-sync per client** and expect cache invalidation.

### 1.9 Thumbnails, downloads, and scheduled reports — **M**

Screenshots move off the old browser stack toward Playwright, run as background work, and use a different “who takes the picture” model. Anything the Portal relies on — thumbnails, PDF/PNG, scheduled reports — must be re-proven on 5. Thumbnail entries are kept for ~**10 years**; plan warm-up, not only “first load is slow.” Drop the custom PDF stack unless product still requires it.

### 1.10 Environments, images, and the 5 waypoint — **M**

New images, env vars, secrets. **5 is staging-only.** Roll out **pilot client → fleet**.

Rollback is **restore from snapshot → re-apply the Postgres chart-ownership trigger → verify Admin ownership**, plus a YAML export of dashboards / charts / datasets before the hop. There is **no supported metadata-DB downgrade**. Promoting assets between environments also changes (stricter import validation, encrypted fields) — regression-test import/export, do not assume it survives untouched.

First dashboard loads after cutover will be **cold cache**; say so to clients. Consider disabling the guest chart-response cache for the cutover window.

### 1.11 Product acceptance for stage 1 — **M**

End-to-end on 5: login, roles, catalog, embed, user admin, retained custom features, **Spanish UI/locale**, chart-render audit (especially time-comparison and remaining legacy chart types). **Event Flow** and **Sankey Loop** charts are gone with no replacement — audit client dashboards before this hop.

---

## Stage 2 — Move from 5 to 6.1 (production target)

Includes the **6.0** platform/UI overhaul and productizing **MCP**, which **ships in 6.1**.

### 2.1 Migrate Superset from 5 to 6.1 — **L**

Bring the 5-based fork onto **6.1** (this jump includes 6.0). This includes:

- Moving the codebase and dependencies onto 6.1
- Upgrading the Superset metadata database again (time this on a production-sized copy; security/login tables move with two framework upgrades)
- Rebuilding and validating images / environments (frontend toolchain moves again)
- Handling upstream breaking changes from 6.0 and 6.1 — including the new look-and-feel / theming, branding moving into the theme, and **all cached thumbnails and dashboard/chart digests rebuilding** (hash change)

**Why it matters:** this is the production runtime; MCP as a product capability is built here.

### 2.2 Enable and productize Superset MCP — **L**

MCP **ships in 6.1** (optional extra process; no extra DB migration). On 5 there is nothing to turn on. Turning it into a usable product capability means:

- Deciding how **Portal-authenticated users / agents** authenticate into MCP
- Deploying and securing the MCP service in our environments (own process)
- Making sure each AI action runs as the right **Superset user** (permissions and data access still apply)
- Connecting our product / AI clients to that service
- Adjusting or retiring the temporary MCP-related bridge we have in the Portal today
- Confirming we can see usage and failures (upstream already records MCP calls in the action log)

**Constraint (product, not a later surprise):** MCP binds to a real user in Superset. **Embedded guest tokens are not an MCP login.** Embedded viewers do not get MCP. Dev-only “run as a fixed user, no auth” must never reach a client environment.

**Why it matters:** without this work MCP is not a product feature, only an unused upstream capability.

### 2.3 Re-validate login, roles, and embed — **L**

Login, session continuity, custom roles (including Guest), and embedded dashboards must be re-checked after the 6.0 UI/platform changes. We already use OAuth (Google / Microsoft / Auth0); this is regression, not a change of identity provider. Custom role names must be audited — some row-level-security admin permissions were removed.

**Embedded drill-down is a security change:** 6.0 turns **Drill to Detail / Drill By** on for embedded dashboards. For a multi-tenant embed this can be a per-client row leak. If we do not want it, the Guest / embed roles must not have those permissions. Treat this as a named checklist item, not a side effect.

Upgrade the Portal embed library again. Two behaviours that can change the iframe with no config on our side: how the iframe sends referrer information, and the default embed theme (light, not “follow the OS”).

### 2.4 Portal features that call Superset APIs — **M**

Catalog, user/role admin, thumbnails, and similar Portal screens need another regression pass on 6.1 (role admin moved to the frontend in 6.0). Old share-by-link shortcuts are **permalinks only**. If we manage datasets as files, export filenames now include the dataset id.

### 2.5 Custom fork features that survived stage 1 — **L**

This hop is **L** because two features sit in the **filter bar**, which 6.0 rewrites — not because the fork is large overall.

- **Filter sets:** rebuild the UI against the 6.x filter bar; reuse the existing key-value records and API (no data migration).
- **Calendar date picker:** prefer an **upstream time-filter extension** rather than another patch.
- Do not carry the BigQuery monkey-patch here if stage 1 replaced it.

Also ask, per leftover custom feature: **rebuild as an upstream extension or a database-managed theme** instead of carrying a fork patch (see Opportunities below). Retest MapBox marker hack, bootstrap-data parser, and dashboard virtualization-off — likely drop.

### 2.6 SQL engine and row-level security — **L**

This is the **highest-risk backend item** in the whole migration.

6.0 **replaces the SQL parser** and **reimplements row-level security** on it. 6.1 then fixes **double RLS on virtual datasets in embedded mode** — a real defect on 6.0 in the configuration we use. Stopping on 6.0 is not attractive.

Same acceptance as 1.7, heavier: per-client **generated SQL + row counts** for known tenants, especially embedded + virtual datasets. If we filter tenants in SQL templates, re-test that path — template rendering now happens before the new parser runs.

### 2.7 Theming and white-label — **M–L**

6.0 **breaks** the old theme-override and custom-CSS approach (new design system, new class names). Branding and fonts move into the theme. Any fork UI that assumed the old look will not carry over.

Themes become **import/export database objects** with an admin UI. That may be a better per-client white-label mechanism than fork-level CSS — evaluate during 2.5 rather than blindly porting styles.

### 2.8 Thumbnails, downloads, and scheduled reports — **M**

Continue the screenshot-pipeline work: Chromium/Playwright in images and workers, tiled screenshots for large dashboards, and a full thumbnail cache rebuild after the 6.1 hash change. With a ~10-year thumbnail TTL that is a **fleet-wide Portal cold start** — warm up per client, or temporarily keep the old hash only for that cache.

### 2.9 Environments, MCP topology, and cutover to 6.1 — **M**

New images, env vars, deploy topology (including the MCP process), secrets. **Pilot → fleet** into production. Same rollback rule as 1.10: **snapshot restore → chart-ownership trigger → verify**, plus YAML export; no DB downgrade. Re-test asset import/export. Warn clients about **cold cache** after cutover. Guest chart-response cache off during the window unless the isolation test already passed on 6.1.

### 2.10 Security configuration for embed, SSO, and MCP — **M**

Confirm that login, embedded dashboards (including drill-down permissions), and the MCP access model are configured correctly for 6.1. Validate in staging before production.

**Decide, do not silently port:** how strictly we sanitize dashboard HTML, and how the iframe is allowed to be framed (today framing is effectively unrestricted). Named owner. Safer defaults exist on 6.x.

This is a **configuration + validation** step aligned with the upgrade, not a separate security project.

### 2.11 Product acceptance for stage 2 — **M**

Everything from stage 1, plus: 6.0 look-and-feel, embed theme/referrer behaviour, drill-down allow/deny in embed, RLS/SQL diffs, MCP success **and** denial paths, **Spanish UI/locale**.

### 2.12 Docs and client communication — **S–M**

Update internal runbooks and tell stakeholders what changes for them: new UI (including filter bar / auto-refresh / Explore behaviour), filter-set UI rebuilt if the feature is on, MCP available only to Portal users (not embed guests), thumbnail cold start, gone chart types.

---

## Opportunities (may shrink the fork)

These are not extra projects; they are options to **stop carrying fork code**:

- **Extensions (mature in 6.1):** calendar date picker is the first candidate; other UI/SQL Lab customizations can follow.
- **Database-managed themes:** per-client white-label as an importable asset.
- **User groups (6.0):** roles on groups rather than every individual user — useful at fleet scale.
- **New SQL template helpers** (current user roles / RLS rules): possible replacement for some custom tenancy logic — only after 2.6 passes.

---

## Suggested order (high level)

**Now**

1. Rebase the fork to **4.1.4**; upgrade `jspdf`
2. Two-guest **cache isolation test** (assert keys and payloads)
3. Inventory — done: [`01_fork-changes-vs-4.1.1.md`](./01_fork-changes-vs-4.1.1.md). Confirm live `DASHBOARD_FILTERS_SAVE` per client.

**Stage 1 (staging waypoint on 5)**

1. Automated suites (cache, RLS SQL, role permissions, guest embed, filter sets)
2. Migrate fork to Superset 5; replace BigQuery monkey-patch
3. Restore login / roles / embed; upgrade the Portal embed library
4. Portal catalog & admin regressions
5. Generated SQL / virtual datasets / RLS sample diffs; BigQuery catalog permission sync
6. Port filter-set **storage + API** if the flag is on; calendar picker as-is
7. Thumbnails / reports; snapshot + trigger + YAML; **do not** cut production to 5
8. Acceptance on 5 (including Spanish and chart-type audit)

**Stage 2 (production on 6.1)**

1. Migrate 5 → 6.1
2. Restore login / roles / embed after the 6.0 UI change; **embed drill-down permissions**; embed library again
3. SQL engine + RLS revalidation (the high-risk **query** hop) + cache isolation again
4. Theming / white-label; HTML/iframe posture
5. Rebuild filter-set **UI**; calendar picker as extension
6. Portal catalog & admin regressions
7. MCP as a product capability (Portal users only)
8. Embed / SSO / MCP config validation + fleet cutover + thumbnail warm-up + acceptance
