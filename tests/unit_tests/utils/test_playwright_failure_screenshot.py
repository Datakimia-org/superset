"""Unit tests for Playwright failure screenshot capture."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("playwright")

from superset.exceptions import ScreenshotCapturedError


class TestPlaywrightFailureScreenshot:
    def test_timeout_raises_captured_error_with_image(self):
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        from superset.utils.webdriver import WebDriverPlaywright

        driver = WebDriverPlaywright("chrome", (800, 600))
        page = MagicMock()
        page.screenshot.return_value = b"diag_png"

        with patch.object(
            driver,
            "_screenshot_dashboard",
            side_effect=Exception("layout failed"),
        ):
            img = driver._capture_failure_screenshot(page, "standalone")
        assert img == b"diag_png"
        page.screenshot.assert_called_with(full_page=True)

        with patch.object(
            driver, "_capture_failure_screenshot", return_value=b"partial"
        ) as capture:
            with pytest.raises(ScreenshotCapturedError) as exc_info:
                img = capture(page, "standalone")
                raise ScreenshotCapturedError(
                    "Timed out capturing screenshot for http://x",
                    image=img,
                ) from None
            assert isinstance(exc_info.value, ScreenshotCapturedError)
            assert not isinstance(exc_info.value, PlaywrightTimeout)
            assert exc_info.value.image == b"partial"
