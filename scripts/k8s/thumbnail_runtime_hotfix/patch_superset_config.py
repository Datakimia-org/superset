"""Idempotent patch of /app/config/superset_config.py for thumbnail runtime hotfix."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

CONFIG = Path("/app/config/superset_config.py")


def _ensure_ttl(text: str) -> str:
    if "THUMBNAIL_COMPUTE_STALE_TTL" in text:
        return text
    start = text.find("THUMBNAIL_CACHE_CONFIG: CacheConfig = {")
    if start < 0:
        raise SystemExit("THUMBNAIL_CACHE_CONFIG not found")
    i = text.find("{", start)
    depth = 0
    end = None
    for j, ch in enumerate(text[i:], i):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    if end is None:
        raise SystemExit("unbalanced THUMBNAIL_CACHE_CONFIG")
    insert = (
        "\n\n# Hotfix ephemeral: orphaned COMPUTING recovery\n"
        "THUMBNAIL_COMPUTE_STALE_TTL = 300\n"
    )
    return text[:end] + insert + text[end:]


def _ensure_rate_limits(text: str) -> str:
    if '"cache_dashboard_thumbnail"' in text:
        return text
    old = """    task_annotations = {
        "sql_lab.get_sql_results": {"rate_limit": "100/s"},
        "email_reports.send": {"rate_limit": "1/s", "time_limit": 120, "soft_time_limit": 150},
        "reports.scheduler": {"rate_limit": "1/s"},
    }"""
    new = """    task_annotations = {
        "sql_lab.get_sql_results": {"rate_limit": "100/s"},
        "email_reports.send": {"rate_limit": "1/s", "time_limit": 120, "soft_time_limit": 150},
        "reports.scheduler": {"rate_limit": "1/s"},
        # Per-worker Chromium throttle (N replicas => ~N x rate cluster-wide). Tune freely.
        "cache_dashboard_thumbnail": {"rate_limit": "1/m"},
        "cache_chart_thumbnail": {"rate_limit": "2/m"},
    }"""
    if old not in text:
        raise SystemExit("task_annotations block not found for rate_limit patch")
    return text.replace(old, new, 1)


def _ensure_mutator(text: str) -> str:
    if "thumbnail_cache_hotfix" in text:
        return text
    old = '''    def datakimia_flask_app_mutator(app: Flask) -> None:
        """Apply Datakimia app customizations after Superset initialization."""
        if callable(_previous_flask_app_mutator):
            _previous_flask_app_mutator(app)
        if not bigquery_cache_patch.apply_database_patch():
            logger.warning("BigQuery engine caching optimization was not applied")
'''
    new = '''    def datakimia_flask_app_mutator(app: Flask) -> None:
        """Apply Datakimia app customizations after Superset initialization."""
        if callable(_previous_flask_app_mutator):
            _previous_flask_app_mutator(app)
        if not bigquery_cache_patch.apply_database_patch():
            logger.warning("BigQuery engine caching optimization was not applied")
        try:
            import thumbnail_cache_hotfix

            thumbnail_cache_hotfix.apply()
        except Exception as hotfix_ex:  # pylint: disable=broad-except
            logger.warning("thumbnail_cache_hotfix failed: %s", hotfix_ex)
'''
    if old not in text:
        raise SystemExit("FLASK_APP_MUTATOR body not found for hotfix wiring")
    return text.replace(old, new, 1)


def main() -> None:
    text = CONFIG.read_text()
    text = _ensure_ttl(text)
    text = _ensure_rate_limits(text)
    text = _ensure_mutator(text)
    ast.parse(text)
    CONFIG.write_text(text)
    print("superset_config patched OK")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        raise
