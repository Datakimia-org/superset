# Superset Best Practices

## Architecture

- Keep Superset metadata concerns separate from warehouse data concerns.
- Use engine specs and official extension points before custom forks.
- Keep deployment stateless at web tier; externalize metadata DB, cache, and workers.

## API and Security

- Apply least privilege through standard roles and custom roles only when necessary.
- Validate permission impacts whenever endpoints are migrated or removed.
- Use strong, non-default `SECRET_KEY` and secure session/cookie settings.

## Configuration and Flags

- Keep `superset_config.py` explicit and environment-scoped.
- Manage feature flags with lifecycle discipline: test, promote, then retire deprecated flags.
- Review `UPDATING.md` on every version bump and codify required config changes.

## Data and Querying

- Model reusable semantics at dataset level (metrics, columns, time grains).
- Use caching strategically for high-load dashboards and SQL Lab patterns.
- Keep warehouse credentials and network access scoped minimally.

## Reliability and Delivery

- Treat metadata migrations as release-critical steps with rollback plans.
- Validate breaking changes and potential downtime notes before deployment.
- Run focused tests for touched backend/frontend/plugin paths and smoke-test core BI flows.

## Agent Guidelines

- Make minimal, targeted changes and keep docs aligned with behavior.
- Prefer compatibility-preserving refactors in shared layers.
- Document operational impact (migrations, flags, permissions, logging) in the same change set.
