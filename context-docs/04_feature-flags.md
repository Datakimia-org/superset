# Superset Feature Flags

## Convention

- Superset flags are configured in `superset_config.py` under `FEATURE_FLAGS`.
- Flags are boolean and should have explicit values by environment.
- Canonical flag inventory and maturity is documented in `RESOURCES/FEATURE_FLAGS.md`.

## Usage Patterns

- **Progressive rollout**
  - Enable new capabilities in non-prod first.
  - Promote to production after validation and rollback planning.
- **Backward compatibility**
  - Prefer temporary flags for transitions and remove once stable.
- **Environment control**
  - Keep production defaults conservative for unstable features.

## Practical Categories

- **In development**: do not enable in production by default.
- **In testing**: can be enabled selectively with monitoring.
- **Stable**: safe baseline for most deployments.
- **Deprecated**: treat as migration debt; plan removal before major upgrades.

## Agent Guidance

- When changing behavior gated by a flag:
  - document purpose, default, and target environments
  - validate interaction with RBAC and API contracts
  - add/adjust notes in upgrade docs if default changes
- Avoid using flags as permanent config unless Superset explicitly treats them as runtime toggles.
