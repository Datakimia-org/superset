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

from unittest.mock import MagicMock

from flask import current_app
from pytest_mock import MockerFixture

from superset.utils import webdriver as webdriver_mod


class FakePlaywrightTimeout(Exception):
    pass


def _patch_playwright(
    mocker: MockerFixture,
    *,
    first_wait_side_effect=None,
    load_wait_side_effect=None,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    webdriver_mod.PlaywrightTimeout = FakePlaywrightTimeout
    webdriver_mod.PlaywrightError = Exception

    page = MagicMock()
    context = MagicMock()
    browser = MagicMock()
    playwright = MagicMock()
    playwright.chromium.launch.return_value = browser
    browser.new_context.return_value = context
    context.new_page.return_value = page

    cm = MagicMock()
    cm.__enter__.return_value = playwright
    cm.__exit__.return_value = False
    mocker.patch.object(
        webdriver_mod, "sync_playwright", return_value=cm, create=True
    )
    mocker.patch.object(webdriver_mod.WebDriverPlaywright, "auth", return_value=context)

    standalone = MagicMock(name="standalone")
    standalone.screenshot.return_value = b"png"
    page.screenshot.return_value = b"png"
    chart_container = MagicMock(name="chart-container")
    chart_container.all.return_value = []
    chart_container.first.wait_for.side_effect = first_wait_side_effect
    page.wait_for_function.side_effect = load_wait_side_effect

    locators = {
        ".standalone": standalone,
        ".chart-container": chart_container,
        ".loading": MagicMock(name="loading"),
    }
    locators[".loading"].all.return_value = []
    page.locator.side_effect = lambda selector: locators.get(selector, MagicMock())
    page.evaluate.return_value = []
    return page, standalone, chart_container


def test_playwright_waits_for_first_chart_container_when_all_is_empty(
    mocker: MockerFixture,
) -> None:
    page, standalone, chart_container = _patch_playwright(mocker)
    user = MagicMock()
    user.username = "admin"

    img = webdriver_mod.WebDriverPlaywright("chrome").get_screenshot(
        "http://example.com/dashboard/2/?standalone=3",
        "standalone",
        user,
    )

    chart_container.first.wait_for.assert_called_once_with(
        timeout=current_app.config["SCREENSHOT_LOCATE_WAIT"] * 1000
    )
    page.wait_for_function.assert_called_once()
    predicate = page.wait_for_function.call_args.args[0]
    assert "slice_container" in predicate
    assert ".loading" in predicate
    assert (
        page.wait_for_function.call_args.kwargs["timeout"]
        == current_app.config["SCREENSHOT_LOAD_WAIT"] * 1000
    )
    assert img == b"png"
    standalone.screenshot.assert_called_once()
    page.screenshot.assert_not_called()


def test_playwright_skips_screenshot_if_chart_container_never_appears(
    mocker: MockerFixture,
) -> None:
    _page, standalone, chart_container = _patch_playwright(
        mocker, first_wait_side_effect=FakePlaywrightTimeout()
    )
    user = MagicMock()
    user.username = "admin"

    img = webdriver_mod.WebDriverPlaywright("chrome").get_screenshot(
        "http://example.com/dashboard/2/?standalone=3",
        "standalone",
        user,
    )

    chart_container.first.wait_for.assert_called_once()
    standalone.screenshot.assert_not_called()
    assert img is None


def test_playwright_skips_screenshot_if_charts_never_finish_loading(
    mocker: MockerFixture,
) -> None:
    page, standalone, _chart_container = _patch_playwright(
        mocker, load_wait_side_effect=FakePlaywrightTimeout()
    )
    user = MagicMock()
    user.username = "admin"

    img = webdriver_mod.WebDriverPlaywright("chrome").get_screenshot(
        "http://example.com/dashboard/5/?standalone=3",
        "standalone",
        user,
    )

    page.wait_for_function.assert_called_once()
    page.screenshot.assert_not_called()
    standalone.screenshot.assert_not_called()
    assert img is None
