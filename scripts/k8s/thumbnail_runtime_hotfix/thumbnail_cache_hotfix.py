"""Ephemeral hotfix: save diagnostic PNG on thumbnail failure (Error + image)."""
from __future__ import annotations

import importlib.util
import logging
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _ensure_screenshot_captured_error():
    import superset.exceptions as exc

    if hasattr(exc, "ScreenshotCapturedError"):
        return exc.ScreenshotCapturedError

    class ScreenshotCapturedError(exc.SupersetException):
        def __init__(self, message: str, image: bytes | None = None):
            super().__init__(message)
            self.image = image

    exc.ScreenshotCapturedError = ScreenshotCapturedError
    return ScreenshotCapturedError


def _load_fixed_webdriver():
    path = Path("/app/config/_hotfix_webdriver.py")
    if not path.is_file():
        logger.warning("Missing %s — Playwright capture-on-timeout not patched", path)
        return None
    name = "superset.utils._hotfix_webdriver"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def apply() -> bool:
    from flask import current_app as app

    ScreenshotCapturedError = _ensure_screenshot_captured_error()

    from superset.extensions import event_logger
    from superset.utils.screenshots import (
        BaseScreenshot,
        ScreenshotCachePayload,
        StatusValues,
    )

    def __init__(
        self,
        image: bytes | None = None,
        status: StatusValues = StatusValues.PENDING,
        timestamp: str = "",
    ):
        self._image = image
        self._timestamp = timestamp or datetime.now().isoformat()
        if status == StatusValues.ERROR:
            self.status = StatusValues.ERROR
        elif image:
            self.status = StatusValues.UPDATED
        else:
            self.status = status

    def error(self, image: bytes | None = None) -> None:
        self.update_timestamp()
        self.status = StatusValues.ERROR
        if image is not None:
            self._image = image

    def is_computing_stale(self) -> bool:
        computing_ttl = app.config.get("THUMBNAIL_COMPUTE_STALE_TTL", 300)
        return (
            datetime.now() - datetime.fromisoformat(self.get_timestamp())
        ).total_seconds() >= computing_ttl

    def should_trigger_task(self, force: bool = False) -> bool:
        error_ttl = app.config.get("THUMBNAIL_ERROR_CACHE_TTL", 86400)
        error_expired = (
            datetime.now() - datetime.fromisoformat(self.get_timestamp())
        ).total_seconds() > error_ttl
        return (
            force
            or self.status == StatusValues.PENDING
            or (
                self.status == StatusValues.ERROR
                and (self._image is None or error_expired)
            )
            or (self.status == StatusValues.COMPUTING and self.is_computing_stale())
            or (self.status == StatusValues.UPDATED and self._image is None)
        )

    def compute_and_cache(  # pylint: disable=too-many-arguments
        self,
        force: bool,
        user=None,
        window_size=None,
        thumb_size=None,
        cache_key: str | None = None,
    ) -> None:
        cache_key = cache_key or self.get_cache_key(window_size, thumb_size)
        cache_payload = self.get_from_cache_key(cache_key) or ScreenshotCachePayload()
        if not cache_payload.should_trigger_task(force=force):
            logger.info(
                "Skipping compute - already processed for thumbnail: %s", cache_key
            )
            return

        window_size = window_size or self.window_size
        thumb_size = thumb_size or self.thumb_size
        logger.info("Processing url for thumbnail: %s", cache_key)
        cache_payload.computing()
        image = None
        capture_failed = False
        try:
            logger.info("trying to generate screenshot")
            with event_logger.log_context(f"screenshot.compute.{self.thumbnail_type}"):
                image = self.get_screenshot(user=user, window_size=window_size)
        except ScreenshotCapturedError as ex:
            logger.warning("Failed at generating thumbnail %s", ex, exc_info=True)
            image = ex.image
            capture_failed = True
        except Exception as ex:  # pylint: disable=broad-except
            logger.warning("Failed at generating thumbnail %s", ex, exc_info=True)
            capture_failed = True

        if image and window_size != thumb_size:
            try:
                image = self.resize_image(image, thumb_size=thumb_size)
            except Exception as ex:  # pylint: disable=broad-except
                logger.warning("Failed at resizing thumbnail %s", ex, exc_info=True)
                if not capture_failed:
                    capture_failed = True
                    image = None

        if image and not capture_failed:
            with event_logger.log_context(f"screenshot.cache.{self.thumbnail_type}"):
                cache_payload.update(image)
            logger.info("Caching thumbnail: %s", cache_key)
            self.cache.set(cache_key, cache_payload.to_dict())
            logger.info(
                "Updated thumbnail cache; Status: %s", cache_payload.get_status()
            )
        elif image and capture_failed:
            cache_payload.error(image)
            self.cache.set(cache_key, cache_payload.to_dict())
            logger.info("Saved failed thumbnail screenshot for %s", cache_key)
        else:
            cache_payload.error()
            self.cache.set(cache_key, cache_payload.to_dict())
            logger.info("Cached thumbnail error without image for %s", cache_key)

    ScreenshotCachePayload.__init__ = __init__
    ScreenshotCachePayload.error = error
    ScreenshotCachePayload.is_computing_stale = is_computing_stale
    ScreenshotCachePayload.should_trigger_task = should_trigger_task
    BaseScreenshot.compute_and_cache = compute_and_cache

    fixed = _load_fixed_webdriver()
    if fixed is not None:
        from superset.utils import webdriver as wd

        wd.WebDriverPlaywright.get_screenshot = fixed.WebDriverPlaywright.get_screenshot
        wd.WebDriverPlaywright._capture_failure_screenshot = (
            fixed.WebDriverPlaywright._capture_failure_screenshot
        )
        wd.WebDriverSelenium.get_screenshot = fixed.WebDriverSelenium.get_screenshot
        logger.info("Playwright/Selenium get_screenshot patched from hotfix file")

    logger.info("thumbnail_cache_hotfix applied (error+png)")
    return True
