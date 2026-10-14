"""Offline browser-login safety checks: no school requests or actual credentials."""

import unittest
from unittest.mock import MagicMock, patch

from bupt_activity_notifier.auto_renew import RenewalError, browser_sign_in


class BrowserLoginSafetyTests(unittest.TestCase):
    @patch("playwright.sync_api.sync_playwright")
    def test_login_uses_official_web_form_without_stealth_options(self, playwright):
        manager = MagicMock()
        playwright.return_value.__enter__.return_value = manager
        browser = manager.chromium.launch.return_value
        page = browser.new_context.return_value.new_page.return_value
        page.evaluate.return_value = "synthetic-token"

        token = browser_sign_in("synthetic-user", "synthetic-password")
        self.assertEqual(token, "synthetic-token")
        manager.chromium.launch.assert_called_once_with(
            channel="msedge", headless=True,
        )
        page.goto.assert_called_once_with(
            "https://dekt.bupt.edu.cn/login",
            wait_until="domcontentloaded",
            timeout=20_000,
        )
        page.locator.assert_any_call("#username")
        page.locator.assert_any_call("#password")
        page.locator.return_value.first.click.assert_called_once()
        browser.close.assert_called_once()

    @patch("playwright.sync_api.sync_playwright")
    def test_manual_display_mode_uses_normal_edge(self, playwright):
        manager = MagicMock()
        playwright.return_value.__enter__.return_value = manager
        manager.chromium.launch.return_value.new_context.return_value.new_page.return_value.evaluate.return_value = "fake"
        browser_sign_in("synthetic-user", "synthetic-password", headless=False)
        manager.chromium.launch.assert_called_once_with(
            channel="msedge", headless=False,
        )

    @patch("playwright.sync_api.sync_playwright")
    def test_exception_is_sanitized_and_browser_closes(self, playwright):
        manager = MagicMock()
        playwright.return_value.__enter__.return_value = manager
        browser = manager.chromium.launch.return_value
        page = browser.new_context.return_value.new_page.return_value
        page.locator.return_value.fill.side_effect = RuntimeError(
            "invalid https://dekt.bupt.edu.cn/login?ticket=SYNTHETIC_PRIVATE"
        )

        with self.assertRaises(RenewalError) as caught:
            browser_sign_in("synthetic-user", "synthetic-password")
        self.assertNotIn("SYNTHETIC_PRIVATE", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        browser.close.assert_called_once()

    @patch("playwright.sync_api.sync_playwright")
    def test_missing_credentials_do_not_start_browser(self, playwright):
        with self.assertRaises(RenewalError):
            browser_sign_in("", "")
        playwright.assert_not_called()


if __name__ == "__main__":
    unittest.main()
