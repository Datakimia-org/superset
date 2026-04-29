# Superset Data Model Rules

## Source of Truth

- Metadata models and migrations in Superset are the source of truth for platform state.
- Application metadata is separate from analytical warehouse schemas.

## Core Modeling Principles

- Keep Superset metadata DB scoped to BI application concerns:
  - users/roles/permissions
  - datasets/charts/dashboards
  - SQL Lab state, reports, logs
- Keep business/analytics data in external engines, accessed via configured database connections.
- Treat engine-specific behavior through DB engine specs rather than ad-hoc SQL forks.

## Required Sequence for Metadata Changes

1. Define model change and migration impact.
2. Create and review migration for backward compatibility.
3. Validate on representative metadata DB engine (Postgres/MySQL as applicable).
4. Assess lock/downtime risk for large tables.
5. Add upgrade notes to `UPDATING.md` when behavior is incompatible or risky.

## Deployment Rules

- Always run metadata migrations before rolling out app code requiring new schema.
- For potentially locking migrations, schedule maintenance windows.
- Maintain rollback path (backup/restore or tested downgrade strategy).

## Data Boundary Rules

- Do not store raw warehouse data in metadata DB.
- Do not couple dashboard/chart behavior to warehouse-specific hacks when an engine spec abstraction exists.
- Prefer semantic definitions (metrics, columns, time grains) over repeated SQL per chart.
