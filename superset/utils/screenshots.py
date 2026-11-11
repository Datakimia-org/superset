# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import annotations

import base64
import logging
from datetime import datetime
from enum import Enum
from io import BytesIO
from typing import cast, TYPE_CHECKING, TypedDict

from flask import current_app as app

from superset import feature_flag_manager, thumbnail_cache
from superset.exceptions import (
    ScreenshotCapturedError,
    ScreenshotImageNotAvailableException,
)
from superset.extensions import event_logger
from superset.utils.hashing import md5_sha_from_dict
from superset.utils.urls import modify_url_query
from superset.utils.webdriver import (
    ChartStandaloneMode,
    DashboardStandaloneMode,
    WebDriver,
    WebDriverPlaywright,
    WebDriverSelenium,
    WindowSize,
)

logger = logging.getLogger(__name__)

DEFAULT_SCREENSHOT_WINDOW_SIZE = 800, 600
DEFAULT_SCREENSHOT_THUMBNAIL_SIZE = 400, 300
DEFAULT_CHART_WINDOW_SIZE = DEFAULT_CHART_THUMBNAIL_SIZE = 800, 600
DEFAULT_DASHBOARD_WINDOW_SIZE = 1600, 1200
DEFAULT_DASHBOARD_THUMBNAIL_SIZE = 800, 600

try:
    from PIL import Image
except ModuleNotFoundError:
    logger.info("No PIL installation found")

if TYPE_CHECKING:
    from flask_appbuilder.security.sqla.models import User
    from flask_caching import Cache


class StatusValues(Enum):
    PENDING = "Pending"
    COMPUTING = "Computing"
    UPDATED = "Updated"
    ERROR = "Error"


class ScreenshotCachePayloadType(TypedDict):
    image: str | None
    timestamp: str
    status: str


def get_pending_lock_ttl() -> int:
    """
    TTL (seconds) for transient PENDING/COMPUTING entries in THUMBNAIL_CACHE.

    These entries only act as a short-lived "task in flight" lock. They must never
    inherit THUMBNAIL_CACHE_CONFIG["CACHE_DEFAULT_TIMEOUT"] (≈10 years in our
    deployments): a worker that dies mid-task would otherwise leave the key stuck.
    """
    return max(1, int(app.config.get("THUMBNAIL_PENDING_LOCK_TTL", 300)))


def get_error_image_ttl() -> int:
    """TTL (seconds) for ERROR payloads that carry a diagnostic PNG."""
    return max(1, int(app.config.get("THUMBNAIL_ERROR_CACHE_TTL", 86400)))


class ScreenshotCachePayload:
    def __init__(
        self,
        image: bytes | None = None,
        status: StatusValues = StatusValues.PENDING,
        timestamp: str = "",
    ):
        self._image = image
        self._timestamp = timestamp or datetime.now().isoformat()
        # True only for payloads read back from THUMBNAIL_CACHE. A freshly built
        # payload (cache miss) must always trigger; a cached fresh PENDING is an
        # in-flight lock and must not re-enqueue.
        self._from_cache = False
        # Keep explicit ERROR even when a diagnostic PNG is attached.
        if status == StatusValues.ERROR:
            self.status = StatusValues.ERROR
        elif image:
            self.status = StatusValues.UPDATED
        else:
            self.status = status

    @classmethod
    def from_dict(cls, payload: ScreenshotCachePayloadType) -> ScreenshotCachePayload:
        return cls(
            image=base64.b64decode(payload["image"]) if payload["image"] else None,
            status=StatusValues(payload["status"]),
            timestamp=payload["timestamp"],
        )

    def to_dict(self) -> ScreenshotCachePayloadType:
        return {
            "image": base64.b64encode(self._image).decode("utf-8")
            if self._image
            else None,
            "timestamp": self._timestamp,
            "status": self.status.value,
        }

    def update_timestamp(self) -> None:
        self._timestamp = datetime.now().isoformat()

    def pending(self) -> None:
        self.update_timestamp()
        self._image = None
        self.status = StatusValues.PENDING

    def computing(self) -> None:
        self.update_timestamp()
        self._image = None
        self.status = StatusValues.COMPUTING

    def update(self, image: bytes) -> None:
        self.update_timestamp()
        self.status = StatusValues.UPDATED
        self._image = image

    def error(self, image: bytes | None = None) -> None:
        self.update_timestamp()
        self.status = StatusValues.ERROR
        if image is not None:
            self._image = image

    def get_image(self) -> BytesIO:
        if self._image is None:
            raise ScreenshotImageNotAvailableException()
        return BytesIO(cast(bytes, self._image))

    def get_timestamp(self) -> str:
        return self._timestamp

    def get_status(self) -> str:
        return self.status.value

    def mark_from_cache(self) -> ScreenshotCachePayload:
        self._from_cache = True
        return self

    def _age_seconds(self) -> float:
        try:
            return (
                datetime.now() - datetime.fromisoformat(self.get_timestamp())
            ).total_seconds()
        except (TypeError, ValueError):
            # Unparseable timestamp: treat as infinitely old so it never blocks.
            return float("inf")

    def is_error_cache_ttl_expired(self) -> bool:
        return self._age_seconds() > get_error_image_ttl()

    def is_computing_stale(self) -> bool:
        """Check if a COMPUTING status is stale (task likely failed or stuck)."""
        computing_ttl = app.config["THUMBNAIL_COMPUTE_STALE_TTL"]
        return self._age_seconds() >= computing_ttl

    def is_pending_stale(self) -> bool:
        """PENDING older than THUMBNAIL_PENDING_LOCK_TTL: enqueue was lost."""
        return self._age_seconds() >= get_pending_lock_ttl()

    def is_stale_transient(self) -> bool:
        """
        True for entries that must be treated as a cache miss: orphaned
        PENDING/COMPUTING locks and legacy ERROR stubs without image (written by
        older builds with the 10y default TTL).
        """
        if self.status == StatusValues.PENDING:
            return self.is_pending_stale()
        if self.status == StatusValues.COMPUTING:
            return self.is_computing_stale()
        if self.status == StatusValues.ERROR:
            return self._image is None
        return False

    def is_in_progress(self) -> bool:
        """A task for this key is queued or running (fresh lock in cache)."""
        if self.status == StatusValues.PENDING:
            return self._from_cache and not self.is_pending_stale()
        if self.status == StatusValues.COMPUTING:
            return not self.is_computing_stale()
        return False

    def _needs_compute(self) -> bool:
        return (
            self.status in (StatusValues.PENDING, StatusValues.COMPUTING)
            # ERROR without PNG: retry immediately. ERROR with diagnostic PNG: allow
            # the UI to serve it until THUMBNAIL_ERROR_CACHE_TTL expires.
            or (
                self.status == StatusValues.ERROR
                and (self._image is None or self.is_error_cache_ttl_expired())
            )
            or (self.status == StatusValues.UPDATED and self._image is None)
        )

    def should_trigger_task(self, force: bool = False) -> bool:
        """
        API side: should a new Celery task be enqueued?

        A fresh PENDING/COMPUTING lock means a task is already queued/running, so
        we do not enqueue duplicates. Stale locks (worker died) re-trigger.
        """
        return force or (not self.is_in_progress() and self._needs_compute())

    def should_compute(self, force: bool = False) -> bool:
        """
        Worker side: should this task run the screenshot?

        Unlike should_trigger_task, a cached PENDING is the marker written when
        *this* task was enqueued, so it must not make the worker skip. Only a fresh
        COMPUTING (another worker is already on it) or a usable image skips.
        """
        if force:
            return True
        if self.status == StatusValues.COMPUTING and not self.is_computing_stale():
            return False
        return self._needs_compute()


class BaseScreenshot:
    @property
    def driver_type(self) -> str:
        return app.config["WEBDRIVER_TYPE"]

    url: str
    digest: str | None
    screenshot: bytes | None
    thumbnail_type: str = ""
    element: str = ""
    window_size: WindowSize = DEFAULT_SCREENSHOT_WINDOW_SIZE
    thumb_size: WindowSize = DEFAULT_SCREENSHOT_THUMBNAIL_SIZE
    cache: Cache = thumbnail_cache

    def __init__(self, url: str, digest: str | None):
        self.digest = digest
        self.url = url
        self.screenshot = None

    def driver(self, window_size: WindowSize | None = None) -> WebDriver:
        window_size = window_size or self.window_size
        if feature_flag_manager.is_feature_enabled("PLAYWRIGHT_REPORTS_AND_THUMBNAILS"):
            return WebDriverPlaywright(self.driver_type, window_size)
        return WebDriverSelenium(self.driver_type, window_size)

    def get_screenshot(
        self, user: User, window_size: WindowSize | None = None
    ) -> bytes | None:
        driver = self.driver(window_size)
        self.screenshot = driver.get_screenshot(self.url, self.element, user)
        return self.screenshot

    def get_cache_key(
        self,
        window_size: bool | WindowSize | None = None,
        thumb_size: bool | WindowSize | None = None,
    ) -> str:
        window_size = window_size or self.window_size
        thumb_size = thumb_size or self.thumb_size
        args = {
            "thumbnail_type": self.thumbnail_type,
            "digest": self.digest,
            "type": "thumb",
            "window_size": window_size,
            "thumb_size": thumb_size,
        }
        return md5_sha_from_dict(args)

    def get_from_cache(
        self,
        window_size: WindowSize | None = None,
        thumb_size: WindowSize | None = None,
    ) -> ScreenshotCachePayload | None:
        cache_key = self.get_cache_key(window_size, thumb_size)
        return self.get_from_cache_key(cache_key)

    @classmethod
    def get_from_cache_key(cls, cache_key: str) -> ScreenshotCachePayload | None:
        logger.info("Attempting to get from cache: %s", cache_key)
        if payload := cls.cache.get(cache_key):
            # Initially, only bytes were stored. This was changed to store an instance
            # of ScreenshotCachePayload, but since it can't be serialized in all
            # backends it was further changed to a dict of attributes.
            if isinstance(payload, bytes):
                payload = ScreenshotCachePayload(payload)
            elif isinstance(payload, ScreenshotCachePayload):
                pass
            elif isinstance(payload, dict):
                payload = cast(ScreenshotCachePayloadType, payload)
                payload = ScreenshotCachePayload.from_dict(payload)
            payload = cast(ScreenshotCachePayload, payload).mark_from_cache()
            if payload.is_stale_transient():
                # Orphaned lock or legacy stub: treat as a miss and drop it so it
                # cannot sit in Redis with the long default TTL.
                logger.info(
                    "Discarding stale thumbnail entry (status=%s): %s",
                    payload.get_status(),
                    cache_key,
                )
                cls._discard_cache_key(cache_key)
                return None
            return payload
        logger.info("Failed at getting from cache: %s", cache_key)
        return None

    @classmethod
    def _discard_cache_key(cls, cache_key: str) -> None:
        try:
            cls.cache.delete(cache_key)
        except Exception as ex:  # pylint: disable=broad-except
            # Never mask the original failure; the short lock TTL is the backstop.
            logger.warning("Failed deleting thumbnail cache key %s: %s", cache_key, ex)

    @classmethod
    def _set_transient(cls, cache_key: str, payload: ScreenshotCachePayload) -> None:
        """Write a PENDING/COMPUTING lock with the short lock TTL."""
        cls.cache.set(cache_key, payload.to_dict(), timeout=get_pending_lock_ttl())

    def mark_pending(self, cache_key: str) -> ScreenshotCachePayload:
        """
        Write the PENDING marker right before enqueueing a Celery task.

        Uses THUMBNAIL_PENDING_LOCK_TTL (never the long image TTL): if the task is
        lost or the worker is killed, the key self-heals once the lock expires.
        """
        payload = ScreenshotCachePayload()
        self._set_transient(cache_key, payload)
        return payload

    def compute_and_cache(  # pylint: disable=too-many-arguments
        self,
        force: bool,
        user: User = None,
        window_size: WindowSize | None = None,
        thumb_size: WindowSize | None = None,
        cache_key: str | None = None,
    ) -> None:
        """
        Computes the thumbnail and caches the result

        :param user: If no user is given will use the current context
        :param cache: The cache to keep the thumbnail payload
        :param window_size: The window size from which will process the thumb
        :param thumb_size: The final thumbnail size
        :param force: Will force the computation even if it's already cached
        :return: Image payload
        """
        cache_key = cache_key or self.get_cache_key(window_size, thumb_size)
        cache_payload = self.get_from_cache_key(cache_key) or ScreenshotCachePayload()
        if not cache_payload.should_compute(force=force):
            logger.info(
                "Skipping compute - already processed for thumbnail: %s", cache_key
            )
            return

        window_size = window_size or self.window_size
        thumb_size = thumb_size or self.thumb_size
        logger.info("Processing url for thumbnail: %s", cache_key)
        cache_payload.computing()
        # Short-lived lock; refreshed here so the TTL counts from task start, not
        # from enqueue time.
        self._set_transient(cache_key, cache_payload)
        # Any exit path that does not write a terminal payload (unexpected
        # exception, Celery SoftTimeLimitExceeded outside the capture block, ...)
        # removes the lock in `finally`. A hard kill (SIGKILL/OOM/pod eviction)
        # cannot run `finally`; the lock TTL covers that case.
        terminal_written = False
        try:
            image, capture_failed = self._capture(user, window_size, thumb_size)

            if image and not capture_failed:
                with event_logger.log_context(
                    f"screenshot.cache.{self.thumbnail_type}"
                ):
                    cache_payload.update(image)
                logger.info("Caching thumbnail: %s", cache_key)
                # No timeout: keep the long CACHE_DEFAULT_TIMEOUT for good images.
                self.cache.set(cache_key, cache_payload.to_dict())
                terminal_written = True
                logger.info(
                    "Updated thumbnail cache; Status: %s", cache_payload.get_status()
                )
            elif image and capture_failed:
                # Diagnostic PNG (e.g. Playwright timeout): bounded TTL so it is
                # served for a while and then regenerated, never kept forever.
                cache_payload.error(image)
                self.cache.set(
                    cache_key, cache_payload.to_dict(), timeout=get_error_image_ttl()
                )
                terminal_written = True
                logger.info("Saved failed thumbnail screenshot for %s", cache_key)
            else:
                logger.info(
                    "Thumbnail generation failed without image; clearing %s",
                    cache_key,
                )
        finally:
            if not terminal_written:
                self._discard_cache_key(cache_key)

    def _capture(
        self,
        user: User | None,
        window_size: WindowSize,
        thumb_size: WindowSize,
    ) -> tuple[bytes | None, bool]:
        """Take and resize the screenshot. Returns (image, capture_failed)."""
        image = None
        capture_failed = False
        # Assuming all sorts of things can go wrong with Selenium/Playwright
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
                    # Keep the unresized diagnostic PNG only on capture failure.
                    capture_failed = True
                    image = None
        return image, capture_failed

    @classmethod
    def resize_image(
        cls,
        img_bytes: bytes,
        output: str = "png",
        thumb_size: WindowSize | None = None,
        crop: bool = True,
    ) -> bytes:
        thumb_size = thumb_size or cls.thumb_size
        img = Image.open(BytesIO(img_bytes))
        logger.debug("Selenium image size: %s", str(img.size))
        if crop and img.size[1] != cls.window_size[1]:
            desired_ratio = float(cls.window_size[1]) / cls.window_size[0]
            desired_width = int(img.size[0] * desired_ratio)
            logger.debug("Cropping to: %s*%s", str(img.size[0]), str(desired_width))
            img = img.crop((0, 0, img.size[0], desired_width))
        logger.debug("Resizing to %s", str(thumb_size))
        img = img.resize(thumb_size, Image.Resampling.LANCZOS)
        new_img = BytesIO()
        if output != "png":
            img = img.convert("RGB")
        img.save(new_img, output)
        new_img.seek(0)
        return new_img.read()


class ChartScreenshot(BaseScreenshot):
    thumbnail_type: str = "chart"
    element: str = "chart-container"

    def __init__(
        self,
        url: str,
        digest: str | None,
        window_size: WindowSize | None = None,
        thumb_size: WindowSize | None = None,
    ):
        # Chart reports are in standalone="true" mode
        url = modify_url_query(
            url,
            standalone=ChartStandaloneMode.HIDE_NAV.value,
        )
        super().__init__(url, digest)
        self.window_size = window_size or DEFAULT_CHART_WINDOW_SIZE
        self.thumb_size = thumb_size or DEFAULT_CHART_THUMBNAIL_SIZE


class DashboardScreenshot(BaseScreenshot):
    thumbnail_type: str = "dashboard"
    element: str = "standalone"

    def __init__(
        self,
        url: str,
        digest: str | None,
        window_size: WindowSize | None = None,
        thumb_size: WindowSize | None = None,
    ):
        # per the element above, dashboard screenshots
        # should always capture in standalone
        url = modify_url_query(
            url,
            standalone=DashboardStandaloneMode.REPORT.value,
        )
        super().__init__(url, digest)
        self.window_size = window_size or DEFAULT_DASHBOARD_WINDOW_SIZE
        self.thumb_size = thumb_size or DEFAULT_DASHBOARD_THUMBNAIL_SIZE

    def get_cache_key(
        self,
        window_size: bool | WindowSize | None = None,
        thumb_size: bool | WindowSize | None = None,
        permalink_key: str | None = None,
    ) -> str:
        window_size = window_size or self.window_size
        thumb_size = thumb_size or self.thumb_size
        args = {
            "thumbnail_type": self.thumbnail_type,
            "digest": self.digest,
            "type": "thumb",
            "window_size": window_size,
            "thumb_size": thumb_size,
            "permalink_key": permalink_key,
        }
        return md5_sha_from_dict(args)
