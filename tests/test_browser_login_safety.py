"""Offline browser-login safety checks: no school requests or actual credentials."""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from bupt_activity_notifier.auto_renew import RenewalError, browser_sign_in


class BrowserLoginSafetyTests(unittest.TestCase):
    def setUp(self):
        # This dependency is an OPTIONAL runtime extra. CI executes safety
        # unit tests without installing a browser or the Playwright package.
        package = types.ModuleType("playwright")
        package.__path__ = []
        submodule = types.ModuleType("playwright.sync_api")
        submodule.sync_playwright = MagicMock()
        package.sync_api = submodule
        modules = patch.dict(
            sys.modules, {"playwright": package, "playwright.sync_api": submodule}
        )
        modules.start()
        self.addCleanup(modules.stop)

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


    @patch("bupt_activity_notifier.auto_renew.time.monotonic", side_effect=[0, 29])
    @patch("playwright.sync_api.sync_playwright")
    def test_auth_challenge_reports_safe_stage_without_body_access(self, playwright, clock):
        manager = MagicMock()
        playwright.return_value.__enter__.return_value = manager
        page = manager.chromium.launch.return_value.new_context.return_value.new_page.return_value
        page.evaluate.return_value = ""
        response = MagicMock()
        response.url = "https://dekt.bupt.edu.cn/api/v1/auth/sessions"
        response.request.method = "POST"
        response.headers = {"x-real-status": "420"}
        response.status = 200

        def on_goto(*args, **kwargs):
            listener = page.on.call_args.args[1]
            listener(response)
            return MagicMock(status=200)

        page.goto.side_effect = on_goto
        with self.assertRaises(RenewalError) as caught:
            browser_sign_in("fake", "fake")
        self.assertEqual(caught.exception.code, "verification_required")
        response.body.assert_not_called()
        response.json.assert_not_called()
        response.text.assert_not_called()

    @patch("playwright.sync_api.sync_playwright")
    def test_transient_navigation_error_does_not_abort_success(self, playwright):
        manager = MagicMock()
        playwright.return_value.__enter__.return_value = manager
        page = manager.chromium.launch.return_value.new_context.return_value.new_page.return_value
        page.evaluate.side_effect = [RuntimeError("navigation in progress"), "fake.jwt.secret"]
        result = browser_sign_in("synthetic-user", "synthetic-password")
        self.assertEqual(result, "fake.jwt.secret")
        self.assertEqual(page.evaluate.call_count, 2)

    def test_renewal_failure_code_is_from_fixed_set(self):
        from bupt_activity_notifier.auto_renew import RenewalError
        error = RenewalError("potentially unsafe detail", code="MY_RAW_SECRET_VALUE")
        self.assertEqual(error.code, "browser_error")


if __name__ == "__main__":
    unittest.main()
