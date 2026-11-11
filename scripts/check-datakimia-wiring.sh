#!/usr/bin/env bash
# Fail when a Datakimia feature file still exists but its call site was dropped.
#
# "The file is in the tree" is not a passing check. Upstream merges that take
# `git checkout --theirs` on a shared file keep the Datakimia module and replace
# the import that uses it. Run this after every upstream merge, and before any
# push to ephemeral/**, client-x/**, or main.
#
# When a Datakimia call site is disconnected and this script did not catch it,
# add a require for that call site in the same change (see pre-push-pipeline.mdc).
#
# Do not resolve these paths with --theirs. Hand-merge them:
#   superset-frontend/src/filters/components/Time/TimeFilterPlugin.tsx
#   superset-frontend/src/views/App.tsx
#   superset-frontend/src/utils/downloadAsPdf.ts
#   superset-frontend/src/dashboard/components/nativeFilters/FilterBar/index.tsx
#   superset-frontend/src/dashboard/components/nativeFilters/FilterBar/ActionButtons/index.tsx
#   superset-frontend/src/dashboard/components/nativeFilters/FilterBar/FilterControls/FilterControls.tsx
#   superset-frontend/packages/superset-ui-core/src/utils/featureFlags.ts
#   superset/utils/webdriver.py
#   superset/utils/request_tracking.py
#   docker/pythonpath_dev/superset_config.py
#   docker/docker-init.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAIL=0

require() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if ! rg -q --fixed-strings "$pattern" "$ROOT/$file"; then
    echo "MISSING: $label"
    echo "  file: $file"
    echo "  expected: $pattern"
    echo
    FAIL=1
  fi
}

require \
  "superset-frontend/src/filters/components/Time/TimeFilterPlugin.tsx" \
  "from './CalendarDatePicker'" \
  "time filter imports the Datakimia calendar"

require \
  "superset-frontend/src/filters/components/Time/TimeFilterPlugin.tsx" \
  "?? CalendarDatePicker" \
  "time filter defaults to CalendarDatePicker"

require \
  "superset-frontend/src/views/App.tsx" \
  "OAUTH2_SUCCESS" \
  "OAuth popup posts OAUTH2_SUCCESS"

require \
  "superset-frontend/src/views/App.tsx" \
  "closeSession" \
  "OAuth popup closes the session when the user is not Default-only"

require \
  "superset-frontend/src/utils/downloadAsPdf.ts" \
  "customDomToPdf" \
  "dashboard PDF uses customDomToPdf"

require \
  "superset-frontend/src/dashboard/components/nativeFilters/FilterBar/index.tsx" \
  "<FilterSets" \
  "filter bar renders FilterSets"

require \
  "superset-frontend/src/dashboard/components/nativeFilters/FilterBar/index.tsx" \
  "<SaveFilterModal" \
  "filter bar renders SaveFilterModal"

require \
  "superset-frontend/src/dashboard/components/nativeFilters/FilterBar/ActionButtons/index.tsx" \
  "onHistory" \
  "filter bar exposes saved-filters action"

require \
  "superset-frontend/packages/superset-ui-core/src/utils/featureFlags.ts" \
  "DashboardFiltersSave" \
  "DASHBOARD_FILTERS_SAVE feature flag"

require \
  "superset-frontend/src/dashboard/components/nativeFilters/FilterBar/FilterControls/FilterControls.tsx" \
  "isPublicUser" \
  "public users are detected in filter controls"

require \
  "superset-frontend/src/dashboard/components/nativeFilters/FilterBar/FilterControls/FilterControls.tsx" \
  "filter_time" \
  "public users only see the time filter"

require \
  "superset-frontend/src/dashboard/components/nativeFilters/FilterBar/useFilterControlFactory.tsx" \
  "filterPredicate" \
  "public filter predicate is supported in useFilterControlFactory"

require \
  "superset/utils/webdriver.py" \
  "def _screenshot_dashboard" \
  "dashboard thumbnails use chart-container capture"

require \
  "superset/exceptions.py" \
  "class ScreenshotCapturedError" \
  "thumbnail diagnostics use ScreenshotCapturedError"

require \
  "superset/utils/hashing.py" \
  "def md5_sha_from_dict" \
  "chart-data cache keys use md5_sha_from_dict"

require \
  "superset/utils/request_tracking.py" \
  'getattr(flask.g, "request_id", None)' \
  "request id is generated when Flask g has none"

require \
  "docker/pythonpath_dev/superset_config.py" \
  "THEME_DARK = None" \
  "embedded dashboards stay on the light theme"

require \
  "docker/pythonpath_dev/superset_config.py" \
  "ENABLE_UI_THEME_ADMINISTRATION = False" \
  "DB theme administration does not override the light theme"

require \
  "docker/pythonpath_dev/superset_config.py" \
  "CUSTOM_SECURITY_MANAGER" \
  "SSO security manager stays configured"

require \
  "docker/pythonpath_dev/superset_config.py" \
  "FLASK_APP_MUTATOR" \
  "BigQuery patch stays on the Flask app mutator"

require \
  "docker/docker-init.sh" \
  "DashboardFilterSetsRestApi" \
  "Guest role keeps filter-set permissions"

require \
  "Dockerfile" \
  "postgresql-client" \
  "init image includes psql for chart-ownership SQL"

require \
  "superset/initialization/__init__.py" \
  "appbuilder.add_api(DashboardFilterSetsRestApi)" \
  "filter sets REST API is registered"

if [[ "$FAIL" -ne 0 ]]; then
  echo "Datakimia wiring check failed. A feature file can still exist while its call site was replaced."
  exit 1
fi

echo "Datakimia wiring check passed."
