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
Tests for screenshot cache retry behavior:
1. Failed generations without PNG delete the key (no Pending/Error stub)
2. Stale PENDING/COMPUTING / legacy ERROR are treated as cache misses
3. Successful UPDATED thumbnails still cache with the long default TTL
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from pytest_mock import MockerFixture

from superset.utils.screenshots import (
    BaseScreenshot,
    ScreenshotCachePayload,
    StatusValues,
)

BASE_SCREENSHOT_PATH = "superset.utils.screenshots.BaseScreenshot"


class MockCache:
    """A class to manage screenshot cache for testing."""

    def __init__(self):
        self._cache = {}
        self.timeouts = {}

    def set(self, key, value, timeout=None):
        """Set the cache with a new value (timeout mirrors flask_caching)."""
        self._cache[key] = value
        self.timeouts[key] = timeout

    def get(self, key):
        """Get the cached value."""
        return self._cache.get(key)

    def delete(self, key):
        """Delete a cached value."""
        self._cache.pop(key, None)
        self.timeouts.pop(key, None)

    def clear(self):
        """Clear all cached values."""
        self._cache.clear()


@pytest.fixture
def mock_user():
    """Fixture to create a mock user."""
    user = MagicMock()
    user.id = 1
    return user


@pytest.fixture
def screenshot_obj():
    """Fixture to create a BaseScreenshot object."""
    url = "http://example.com"
    digest = "sample_digest"
    return BaseScreenshot(url, digest)


class TestCacheFailurePersistence:
    """Failed captures persist Error (+ optional diagnostic PNG)."""

    def _setup_mocks(self, mocker: MockerFixture, screenshot_obj):
        mocker.patch(BASE_SCREENSHOT_PATH + ".get_from_cache_key", return_value=None)
        get_screenshot = mocker.patch(
            BASE_SCREENSHOT_PATH + ".get_screenshot", return_value=b"image_data"
        )
        mocker.patch(
            BASE_SCREENSHOT_PATH + ".resize_image", return_value=b"resized_image_data"
        )
        BaseScreenshot.cache = MockCache()
        return get_screenshot

    def test_cache_error_without_image_when_screenshot_fails(
        self, mocker: MockerFixture, screenshot_obj, mock_user
    ):
        mocker.patch(BASE_SCREENSHOT_PATH + ".get_from_cache_key", return_value=None)
        mocker.patch(
            BASE_SCREENSHOT_PATH + ".get_screenshot",
            side_effect=Exception("Screenshot failed"),
        )
        BaseScreenshot.cache = MockCache()
        cache_key = screenshot_obj.get_cache_key()

        screenshot_obj.compute_and_cache(user=mock_user, force=True)

        assert BaseScreenshot.cache.get(cache_key) is None

    def test_cache_error_with_image_on_captured_error(
        self, mocker: MockerFixture, screenshot_obj, mock_user
    ):
        from superset.exceptions import ScreenshotCapturedError

        mocker.patch(BASE_SCREENSHOT_PATH + ".get_from_cache_key", return_value=None)
        mocker.patch(
            BASE_SCREENSHOT_PATH + ".get_screenshot",
            side_effect=ScreenshotCapturedError("timeout", image=b"partial_png"),
        )
        mocker.patch(
            BASE_SCREENSHOT_PATH + ".resize_image", return_value=b"resized_partial"
        )
        BaseScreenshot.cache = MockCache()
        cache_key = screenshot_obj.get_cache_key()

        screenshot_obj.compute_and_cache(
            user=mock_user, force=True, window_size=(800, 600), thumb_size=(400, 300)
        )

        cached_value = BaseScreenshot.cache.get(cache_key)
        assert cached_value is not None
        assert cached_value["status"] == "Error"
        assert cached_value["image"] is not None
        # Round-trip keeps Error + image
        payload = ScreenshotCachePayload.from_dict(cached_value)
        assert payload.get_status() == "Error"
        assert payload.get_image().read() == b"resized_partial"

    def test_cache_saved_only_when_image_generated(
        self, mocker: MockerFixture, screenshot_obj, mock_user
    ):
        self._setup_mocks(mocker, screenshot_obj)

        screenshot_obj.compute_and_cache(user=mock_user, force=True)

        cache_key = screenshot_obj.get_cache_key()
        cached_value = BaseScreenshot.cache.get(cache_key)
        assert cached_value is not None
        assert cached_value["status"] == "Updated"
        assert cached_value["image"] is not None

    def test_computing_lock_uses_short_ttl_during_capture(
        self, mocker: MockerFixture, screenshot_obj, mock_user
    ):
        """While capturing, only a short-TTL COMPUTING lock may exist."""
        mocker.patch(BASE_SCREENSHOT_PATH + ".get_from_cache_key", return_value=None)
        BaseScreenshot.cache = MockCache()
        cache_key = screenshot_obj.get_cache_key()

        def check_cache_during_screenshot(*args, **kwargs):
            cached_value = BaseScreenshot.cache.get(cache_key)
            assert cached_value["status"] == "Computing"
            assert BaseScreenshot.cache.timeouts[cache_key] == 300
            return b"image_data"

        mocker.patch(
            BASE_SCREENSHOT_PATH + ".get_screenshot",
            side_effect=check_cache_during_screenshot,
        )
        mocker.patch(
            BASE_SCREENSHOT_PATH + ".resize_image", return_value=b"resized_image_data"
        )

        screenshot_obj.compute_and_cache(user=mock_user, force=True)

        cached_value = BaseScreenshot.cache.get(cache_key)
        assert cached_value["status"] == "Updated"
        # Successful image keeps the cache default (long) TTL.
        assert BaseScreenshot.cache.timeouts[cache_key] is None


class TestShouldTriggerTask:
    """Test the should_trigger_task method improvements."""

    @patch("superset.utils.screenshots.app")
    def test_trigger_on_stale_computing_status(self, mock_app):
        """Test that stale COMPUTING status triggers recomputation."""
        mock_app.config = {"THUMBNAIL_COMPUTE_STALE_TTL": 300}

        old_timestamp = (datetime.now() - timedelta(seconds=400)).isoformat()
        payload = ScreenshotCachePayload(
            status=StatusValues.COMPUTING, timestamp=old_timestamp
        )

        assert payload.should_trigger_task(force=False) is True

    @patch("superset.utils.screenshots.app")
    def test_no_trigger_on_fresh_computing_status(self, mock_app):
        """Test that fresh COMPUTING status does not trigger recomputation."""
        mock_app.config = {"THUMBNAIL_COMPUTE_STALE_TTL": 300}

        fresh_timestamp = (datetime.now() - timedelta(seconds=100)).isoformat()
        payload = ScreenshotCachePayload(
            status=StatusValues.COMPUTING, timestamp=fresh_timestamp
        )

        assert payload.should_trigger_task(force=False) is False

    def test_trigger_on_updated_without_image(self):
        """Test that UPDATED status without image triggers recomputation."""
        payload = ScreenshotCachePayload(image=None, status=StatusValues.UPDATED)

        assert payload.should_trigger_task(force=False) is True

    def test_no_trigger_on_updated_with_image(self):
        """Test that UPDATED status with image does not trigger recomputation."""
        payload = ScreenshotCachePayload(image=b"valid_image_data")

        assert payload.should_trigger_task(force=False) is False

    def test_trigger_on_pending_status(self):
        """Test that PENDING status triggers task."""
        payload = ScreenshotCachePayload(status=StatusValues.PENDING)

        assert payload.should_trigger_task(force=False) is True

    def test_trigger_on_error_without_image(self):
        """ERROR without PNG retries immediately."""
        fresh_timestamp = (datetime.now() - timedelta(seconds=1)).isoformat()
        payload = ScreenshotCachePayload(
            status=StatusValues.ERROR, timestamp=fresh_timestamp
        )

        assert payload.should_trigger_task(force=False) is True

    @patch("superset.utils.screenshots.app")
    def test_no_trigger_on_fresh_error_with_image(self, mock_app):
        """ERROR with diagnostic PNG is servable until TTL expires."""
        mock_app.config = {"THUMBNAIL_ERROR_CACHE_TTL": 300}
        fresh_timestamp = (datetime.now() - timedelta(seconds=1)).isoformat()
        payload = ScreenshotCachePayload(
            image=b"diag_png",
            status=StatusValues.ERROR,
            timestamp=fresh_timestamp,
        )

        assert payload.get_status() == "Error"
        assert payload.should_trigger_task(force=False) is False

    @patch("superset.utils.screenshots.app")
    def test_trigger_on_expired_error_with_image(self, mock_app):
        mock_app.config = {"THUMBNAIL_ERROR_CACHE_TTL": 300}
        old_timestamp = (datetime.now() - timedelta(seconds=400)).isoformat()
        payload = ScreenshotCachePayload(
            image=b"diag_png",
            status=StatusValues.ERROR,
            timestamp=old_timestamp,
        )

        assert payload.should_trigger_task(force=False) is True

    def test_force_always_triggers(self):
        """Test that force=True always triggers task regardless of status."""
        payload_updated = ScreenshotCachePayload(image=b"image_data")
        assert payload_updated.should_trigger_task(force=True) is True

        payload_computing = ScreenshotCachePayload(status=StatusValues.COMPUTING)
        assert payload_computing.should_trigger_task(force=True) is True


class TestIsComputingStale:
    """Test the is_computing_stale method."""

    @patch("superset.utils.screenshots.app")
    def test_computing_is_stale(self, mock_app):
        """Test that old COMPUTING status is detected as stale."""
        mock_app.config = {"THUMBNAIL_COMPUTE_STALE_TTL": 300}

        old_timestamp = (datetime.now() - timedelta(seconds=400)).isoformat()
        payload = ScreenshotCachePayload(
            status=StatusValues.COMPUTING, timestamp=old_timestamp
        )

        assert payload.is_computing_stale() is True

    @patch("superset.utils.screenshots.app")
    def test_computing_is_not_stale(self, mock_app):
        """Test that fresh COMPUTING status is not stale."""
        mock_app.config = {"THUMBNAIL_COMPUTE_STALE_TTL": 300}

        fresh_timestamp = (datetime.now() - timedelta(seconds=100)).isoformat()
        payload = ScreenshotCachePayload(
            status=StatusValues.COMPUTING, timestamp=fresh_timestamp
        )

        assert payload.is_computing_stale() is False

    @patch("superset.utils.screenshots.app")
    def test_computing_exactly_at_ttl(self, mock_app):
        """Test boundary condition at exactly TTL."""
        mock_app.config = {"THUMBNAIL_COMPUTE_STALE_TTL": 300}

        exact_timestamp = (datetime.now() - timedelta(seconds=300)).isoformat()
        payload = ScreenshotCachePayload(
            status=StatusValues.COMPUTING, timestamp=exact_timestamp
        )

        assert payload.is_computing_stale() is True

    @patch("superset.utils.screenshots.app")
    def test_computing_just_past_ttl(self, mock_app):
        """Test boundary condition just past TTL."""
        mock_app.config = {"THUMBNAIL_COMPUTE_STALE_TTL": 300}

        past_ttl_timestamp = (datetime.now() - timedelta(seconds=301)).isoformat()
        payload = ScreenshotCachePayload(
            status=StatusValues.COMPUTING, timestamp=past_ttl_timestamp
        )

        assert payload.is_computing_stale() is True


class TestIntegrationCacheBugFix:
    """Integration tests combining both fixes."""

    def test_failed_screenshot_does_not_pollute_cache(
        self, mocker: MockerFixture, screenshot_obj, mock_user
    ):
        """Failed screenshot leaves no stub and still allows regeneration."""
        mocker.patch(
            BASE_SCREENSHOT_PATH + ".get_screenshot",
            side_effect=Exception("Network error"),
        )
        BaseScreenshot.cache = MockCache()
        cache_key = screenshot_obj.get_cache_key()
        BaseScreenshot.cache.set(cache_key, ScreenshotCachePayload().to_dict())

        screenshot_obj.compute_and_cache(user=mock_user, force=True)

        assert BaseScreenshot.cache.get(cache_key) is None

        # Subsequent compute succeeds and caches UPDATED
        mocker.patch(
            BASE_SCREENSHOT_PATH + ".get_screenshot", return_value=b"recovered_image"
        )
        mocker.patch(
            BASE_SCREENSHOT_PATH + ".resize_image", return_value=b"resized_image"
        )
        screenshot_obj.compute_and_cache(user=mock_user, force=False)

        cached_value = BaseScreenshot.cache.get(cache_key)
        assert cached_value is not None
        assert cached_value["status"] == "Updated"
        assert cached_value["image"] is not None

    @patch("superset.utils.screenshots.app")
    def test_stale_computing_triggers_retry(
        self, mock_app, mocker: MockerFixture, screenshot_obj, mock_user
    ):
        """Stale COMPUTING status should trigger retry to recover from stuck tasks."""
        mock_app.config = {"THUMBNAIL_COMPUTE_STALE_TTL": 300}
        BaseScreenshot.cache = MockCache()

        old_timestamp = (datetime.now() - timedelta(seconds=400)).isoformat()
        stale_payload = ScreenshotCachePayload(
            status=StatusValues.COMPUTING, timestamp=old_timestamp
        )
        cache_key = screenshot_obj.get_cache_key()
        BaseScreenshot.cache.set(cache_key, stale_payload.to_dict())

        mocker.patch(
            BASE_SCREENSHOT_PATH + ".get_screenshot", return_value=b"recovered_image"
        )
        mocker.patch(
            BASE_SCREENSHOT_PATH + ".resize_image", return_value=b"resized_image"
        )

        assert stale_payload.should_trigger_task() is True

        screenshot_obj.compute_and_cache(user=mock_user, force=False)

        cached_value = BaseScreenshot.cache.get(cache_key)
        assert cached_value is not None
        assert cached_value["status"] == "Updated"
        assert cached_value["image"] is not None

    def test_legacy_error_entry_allows_retry(
        self, mocker: MockerFixture, screenshot_obj, mock_user
    ):
        """A leftover ERROR entry from older builds must not block regeneration."""
        BaseScreenshot.cache = MockCache()
        cache_key = screenshot_obj.get_cache_key()
        error_payload = ScreenshotCachePayload(status=StatusValues.ERROR)
        BaseScreenshot.cache.set(cache_key, error_payload.to_dict())

        assert error_payload.should_trigger_task(force=False) is True

        mocker.patch(
            BASE_SCREENSHOT_PATH + ".get_screenshot", return_value=b"recovered_image"
        )
        mocker.patch(
            BASE_SCREENSHOT_PATH + ".resize_image", return_value=b"resized_image"
        )

        screenshot_obj.compute_and_cache(user=mock_user, force=False)

        cached_value = BaseScreenshot.cache.get(cache_key)
        assert cached_value is not None
        assert cached_value["status"] == "Updated"
