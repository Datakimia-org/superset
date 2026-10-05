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
"""
Datakimia: thumbnail PENDING/COMPUTING locks must be short-lived.

Regression for keys stuck in THUMBNAIL_CACHE as
{image: None, status: "Pending"} with the ~10y default TTL after a failed or
killed cache_dashboard_thumbnail task.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from PIL import Image
from pytest_mock import MockerFixture

from superset.exceptions import ScreenshotCapturedError
from superset.utils.screenshots import (
    BaseScreenshot,
    DashboardScreenshot,
    ScreenshotCachePayload,
    StatusValues,
)

DASHBOARD_SCREENSHOT_PATH = "superset.utils.screenshots.DashboardScreenshot"
LONG_TTL = 315360000  # what CACHE_DEFAULT_TIMEOUT is in our deployments
CONFIG = {
    "THUMBNAIL_PENDING_LOCK_TTL": 300,
    "THUMBNAIL_COMPUTE_STALE_TTL": 300,
    "THUMBNAIL_ERROR_CACHE_TTL": 86400,
}


class RedisLikeCache:
    """
    Mimics flask_caching's RedisCache contract: timeout=None -> default timeout,
    explicit timeout -> that TTL. Expiry is simulated via `expire_older_than`.
    """

    def __init__(self, default_timeout: int = LONG_TTL):
        self.default_timeout = default_timeout
        self.store: dict[str, Any] = {}
        self.ttl: dict[str, int] = {}

    def set(self, key: str, value: Any, timeout: int | None = None) -> bool:
        self.store[key] = value
        self.ttl[key] = self.default_timeout if timeout is None else timeout
        return True

    def get(self, key: str) -> Any:
        return self.store.get(key)

    def delete(self, key: str) -> bool:
        self.ttl.pop(key, None)
        return self.store.pop(key, None) is not None


def _png(size: tuple[int, int] = (1600, 1200)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, "png")
    return buf.getvalue()


def _ts(seconds_ago: int) -> str:
    return (datetime.now() - timedelta(seconds=seconds_ago)).isoformat()


@pytest.fixture
def mock_app():
    with patch("superset.utils.screenshots.app") as app:
        app.config = dict(CONFIG)
        yield app


@pytest.fixture
def cache():
    original = BaseScreenshot.cache
    redis_like = RedisLikeCache()
    BaseScreenshot.cache = redis_like
    yield redis_like
    BaseScreenshot.cache = original


@pytest.fixture
def screenshot() -> DashboardScreenshot:
    return DashboardScreenshot("http://localhost/superset/dashboard/1/", "digest1")


@pytest.fixture
def user() -> MagicMock:
    return MagicMock(id=1)


class TestPendingLockWrite:
    def test_mark_pending_uses_lock_ttl_not_default(self, mock_app, cache, screenshot):
        key = screenshot.get_cache_key()
        screenshot.mark_pending(key)

        assert cache.get(key)["status"] == "Pending"
        assert cache.ttl[key] == 300
        assert cache.ttl[key] != LONG_TTL

    def test_mark_pending_honours_configured_ttl(self, mock_app, cache, screenshot):
        mock_app.config["THUMBNAIL_PENDING_LOCK_TTL"] = 42
        key = screenshot.get_cache_key()
        screenshot.mark_pending(key)
        assert cache.ttl[key] == 42

    def test_non_positive_ttl_never_means_forever(self, mock_app, cache, screenshot):
        # flask_caching treats timeout=0 as "never expire"; guard against it.
        mock_app.config["THUMBNAIL_PENDING_LOCK_TTL"] = 0
        key = screenshot.get_cache_key()
        screenshot.mark_pending(key)
        assert cache.ttl[key] >= 1


class TestComputeCleanup:
    def test_playwright_failure_leaves_no_pending_key(
        self, mock_app, cache, screenshot, user, mocker: MockerFixture
    ):
        """Validation #1: after a simulated Playwright failure no Pending remains."""
        key = screenshot.get_cache_key()
        screenshot.mark_pending(key)  # what the API does before .delay()
        mocker.patch(
            DASHBOARD_SCREENSHOT_PATH + ".get_screenshot",
            side_effect=TimeoutError("playwright: Timeout 120000ms exceeded"),
        )

        screenshot.compute_and_cache(user=user, force=False, cache_key=key)

        assert key not in cache.store

    def test_unexpected_exception_cleans_lock_and_propagates(
        self, mock_app, cache, screenshot, user, mocker: MockerFixture
    ):
        """Celery soft time limit outside the capture try still removes the lock."""
        key = screenshot.get_cache_key()
        screenshot.mark_pending(key)
        mocker.patch(
            DASHBOARD_SCREENSHOT_PATH + "._capture",
            side_effect=SoftTimeLimitExceeded(),
        )

        with pytest.raises(SoftTimeLimitExceeded):
            screenshot.compute_and_cache(user=user, force=False, cache_key=key)

        assert key not in cache.store

    def test_cleanup_failure_does_not_mask_original_error(
        self, mock_app, cache, screenshot, user, mocker: MockerFixture
    ):
        key = screenshot.get_cache_key()
        mocker.patch(
            DASHBOARD_SCREENSHOT_PATH + "._capture", side_effect=RuntimeError("boom")
        )
        mocker.patch.object(cache, "delete", side_effect=ConnectionError("redis"))

        with pytest.raises(RuntimeError, match="boom"):
            screenshot.compute_and_cache(user=user, force=True, cache_key=key)

    def test_computing_lock_is_short_lived(
        self, mock_app, cache, screenshot, user, mocker: MockerFixture
    ):
        key = screenshot.get_cache_key()
        seen: dict[str, Any] = {}

        def capture(*_args, **_kwargs):
            seen["status"] = cache.get(key)["status"]
            seen["ttl"] = cache.ttl[key]
            return _png()

        mocker.patch(DASHBOARD_SCREENSHOT_PATH + ".get_screenshot", side_effect=capture)

        screenshot.compute_and_cache(user=user, force=False, cache_key=key)

        assert seen == {"status": "Computing", "ttl": 300}

    def test_success_writes_usable_png_with_long_ttl(
        self, mock_app, cache, screenshot, user, mocker: MockerFixture
    ):
        """Validation #2: after success a usable PNG remains with the long TTL."""
        key = screenshot.get_cache_key()
        screenshot.mark_pending(key)
        mocker.patch(DASHBOARD_SCREENSHOT_PATH + ".get_screenshot", return_value=_png())

        screenshot.compute_and_cache(user=user, force=False, cache_key=key)

        assert cache.ttl[key] == LONG_TTL
        payload = screenshot.get_from_cache_key(key)
        assert payload is not None
        assert payload.get_status() == "Updated"
        img = Image.open(payload.get_image())
        assert img.format == "PNG"
        assert img.size == screenshot.thumb_size

    def test_diagnostic_png_uses_error_ttl(
        self, mock_app, cache, screenshot, user, mocker: MockerFixture
    ):
        key = screenshot.get_cache_key()
        mocker.patch(
            DASHBOARD_SCREENSHOT_PATH + ".get_screenshot",
            side_effect=ScreenshotCapturedError("timeout", image=_png()),
        )

        screenshot.compute_and_cache(user=user, force=False, cache_key=key)

        assert cache.get(key)["status"] == "Error"
        assert cache.ttl[key] == 86400

    def test_worker_runs_when_its_own_pending_marker_is_fresh(
        self, mock_app, cache, screenshot, user, mocker: MockerFixture
    ):
        """The API-side dedupe must not make the enqueued task skip itself."""
        key = screenshot.get_cache_key()
        screenshot.mark_pending(key)
        get_screenshot = mocker.patch(
            DASHBOARD_SCREENSHOT_PATH + ".get_screenshot", return_value=_png()
        )

        screenshot.compute_and_cache(user=user, force=False, cache_key=key)

        get_screenshot.assert_called_once()

    def test_worker_skips_when_another_is_computing(
        self, mock_app, cache, screenshot, user, mocker: MockerFixture
    ):
        key = screenshot.get_cache_key()
        cache.set(
            key,
            ScreenshotCachePayload(status=StatusValues.COMPUTING).to_dict(),
            timeout=300,
        )
        get_screenshot = mocker.patch(DASHBOARD_SCREENSHOT_PATH + ".get_screenshot")

        screenshot.compute_and_cache(user=user, force=False, cache_key=key)

        get_screenshot.assert_not_called()
        assert cache.get(key)["status"] == "Computing"  # untouched


class TestStalePendingIsAMiss:
    def test_legacy_stuck_pending_is_discarded_and_retriggers(
        self, mock_app, cache, screenshot
    ):
        """The exact poison seen in ephemeral: Pending, no image, 10y TTL."""
        key = screenshot.get_cache_key()
        cache.set(
            key,
            {"image": None, "status": "Pending", "timestamp": _ts(3 * 3600)},
        )
        assert cache.ttl[key] == LONG_TTL

        assert screenshot.get_from_cache_key(key) is None
        assert key not in cache.store  # self-healed, no manual DEL needed

        payload = screenshot.get_from_cache_key(key) or ScreenshotCachePayload()
        assert payload.should_trigger_task() is True

    def test_fresh_pending_does_not_reenqueue(self, mock_app, cache, screenshot):
        key = screenshot.get_cache_key()
        screenshot.mark_pending(key)

        payload = screenshot.get_from_cache_key(key)
        assert payload is not None
        assert payload.is_in_progress() is True
        assert payload.should_trigger_task() is False
        assert payload.should_trigger_task(force=True) is True

    def test_pending_exactly_at_lock_ttl_is_stale(self, mock_app, cache, screenshot):
        key = screenshot.get_cache_key()
        cache.set(key, {"image": None, "status": "Pending", "timestamp": _ts(300)}, 300)
        assert screenshot.get_from_cache_key(key) is None

    def test_cache_miss_always_triggers(self, mock_app):
        payload = ScreenshotCachePayload()  # not read from cache
        assert payload.is_in_progress() is False
        assert payload.should_trigger_task() is True

    def test_unparseable_timestamp_never_blocks(self, mock_app, cache, screenshot):
        key = screenshot.get_cache_key()
        cache.set(key, {"image": None, "status": "Pending", "timestamp": "garbage"})
        assert screenshot.get_from_cache_key(key) is None


def test_reopening_dashboard_list_regenerates_only_misses(mock_app, cache):
    """
    Validation #3: simulate the list view asking for 5 thumbnails and check
    which ones the API would enqueue.
    """
    dashboards = {
        name: DashboardScreenshot(f"http://localhost/d/{name}/", f"digest-{name}")
        for name in ("ok", "inflight", "stuck", "missing", "diag")
    }
    keys = {name: s.get_cache_key() for name, s in dashboards.items()}

    cache.set(keys["ok"], ScreenshotCachePayload(image=_png((8, 6))).to_dict())
    dashboards["inflight"].mark_pending(keys["inflight"])
    cache.set(
        keys["stuck"], {"image": None, "status": "Pending", "timestamp": _ts(7200)}
    )
    diag = ScreenshotCachePayload(image=b"diag")
    diag.error(b"diag")
    cache.set(keys["diag"], diag.to_dict(), timeout=86400)

    enqueued = []
    for name, shot in dashboards.items():
        payload = shot.get_from_cache_key(keys[name]) or ScreenshotCachePayload()
        if payload.should_trigger_task():
            shot.mark_pending(keys[name])
            enqueued.append(name)

    assert sorted(enqueued) == ["missing", "stuck"]
    # The good thumbnail is untouched and still on the long TTL.
    assert cache.ttl[keys["ok"]] == LONG_TTL
    # Every Pending written now is short-lived.
    for name in enqueued:
        assert cache.ttl[keys[name]] == 300
