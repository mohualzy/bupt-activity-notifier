"""Offline, fake-token tests for opt-in browser credential renewal."""

import base64
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from bupt_activity_notifier import auto_renew
from bupt_activity_notifier.api import ActivityClient, Credentials
from bupt_activity_notifier.win_credentials import SecretStoreError, _write


def fake_token(subject=42, lifetime=3 * 86400):
    claims = {"sub": subject, "exp": int(time.time()) + lifetime}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return "fake." + payload + ".signature"


class RenewalTests(unittest.TestCase):
    def setUp(self):
        self.initial = fake_token(lifetime=2 * 3600)
        self.new = fake_token(lifetime=3 * 86400)
        self.client = ActivityClient(Credentials(self.initial))
        self.context = patch.dict("os.environ", {"SECONDCLASS_AUTO_RENEW": "1"})
        self.context.start()
        self.addCleanup(self.context.stop)

    @patch("bupt_activity_notifier.auto_renew.read_renewed_token")
    def test_choose_newer_token(self, read_token):
        read_token.return_value = self.new
        self.assertEqual(auto_renew.choose_token(self.initial), self.new)

    @patch("bupt_activity_notifier.auto_renew.read_renewed_token")
    def test_choose_rejects_other_student(self, read_token):
        read_token.return_value = fake_token(subject=43)
        self.assertEqual(auto_renew.choose_token(self.initial), self.initial)

    @patch("bupt_activity_notifier.auto_renew.read_renewed_token")
    def test_choose_rejects_older_cache(self, read_token):
        read_token.return_value = fake_token(lifetime=3600)
        self.assertEqual(auto_renew.choose_token(self.initial), self.initial)

    @patch("bupt_activity_notifier.auto_renew.read_renewed_token")
    def test_disabled_does_not_read_password_or_cache(self, read_token):
        with patch.dict("os.environ", {"SECONDCLASS_AUTO_RENEW": "0"}):
            self.assertEqual(auto_renew.choose_token(self.initial), self.initial)
        read_token.assert_not_called()

    @patch("bupt_activity_notifier.auto_renew.ActivityClient")
    def test_candidate_is_verified_against_student_api(self, client_class):
        auto_renew.verify_candidate(self.new, self.initial)
        self.assertEqual(client_class.call_count, 1)
        client_class.return_value.validate_connection.assert_called_once()

    @patch("bupt_activity_notifier.auto_renew.ActivityClient")
    def test_reject_other_account_before_network(self, client_class):
        with self.assertRaises(auto_renew.RenewalError):
            auto_renew.verify_candidate(fake_token(subject=77), self.initial)
        client_class.assert_not_called()

    @patch("bupt_activity_notifier.auto_renew.ActivityClient")
    def test_reject_unchanged_expiry_before_network(self, client_class):
        with self.assertRaises(auto_renew.RenewalError):
            auto_renew.verify_candidate(fake_token(lifetime=2 * 3600), self.initial)
        client_class.assert_not_called()

    @patch("bupt_activity_notifier.auto_renew.ActivityClient")
    def test_reject_near_expiring_new_token(self, client_class):
        with self.assertRaises(auto_renew.RenewalError):
            auto_renew.verify_candidate(fake_token(lifetime=23 * 3600), self.initial)
        client_class.assert_not_called()

    @patch("bupt_activity_notifier.auto_renew.save_renewed_token")
    @patch("bupt_activity_notifier.auto_renew.verify_candidate")
    @patch("bupt_activity_notifier.auto_renew.browser_sign_in")
    @patch("bupt_activity_notifier.auto_renew.read_login")
    def test_force_renew_validated_before_saving(self, read_login, browser, verify, save):
        read_login.return_value = ("fake-user", "fake-password")
        browser.return_value = self.new
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(auto_renew.renew_if_due(self.client, Path(d) / "seen.json", force=True))
        verify.assert_called_once_with(self.new, self.initial)
        save.assert_called_once_with(self.new)

    @patch("bupt_activity_notifier.auto_renew.save_renewed_token")
    @patch("bupt_activity_notifier.auto_renew.browser_sign_in")
    @patch("bupt_activity_notifier.auto_renew.read_login")
    def test_automatic_login_cooldown_after_failure(self, read_login, browser, save):
        read_login.return_value = ("fake-user", "fake-password")
        browser.side_effect = auto_renew.RenewalError("captcha required")
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "seen.json"
            with self.assertRaises(auto_renew.RenewalError):
                auto_renew.renew_if_due(self.client, state)
            self.assertTrue((Path(d) / auto_renew.RETRY_STATE_FILENAME).exists())
            self.assertFalse(auto_renew.renew_if_due(self.client, state))
            self.assertEqual(browser.call_count, 1)
        save.assert_not_called()

    @patch("bupt_activity_notifier.auto_renew.save_renewed_token")
    @patch("bupt_activity_notifier.auto_renew.verify_candidate")
    @patch("bupt_activity_notifier.auto_renew.browser_sign_in")
    @patch("bupt_activity_notifier.auto_renew.read_login")
    def test_success_clears_cooldown(self, read_login, browser, verify, save):
        read_login.return_value = ("fake-user", "fake-password")
        browser.return_value = self.new
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "seen.json"
            self.assertTrue(auto_renew.renew_if_due(self.client, state))
            self.assertFalse((Path(d) / auto_renew.RETRY_STATE_FILENAME).exists())
        save.assert_called_once()

    @patch("bupt_activity_notifier.auto_renew.read_login")
    def test_healthy_token_does_not_touch_credentials(self, read_login):
        healthy = ActivityClient(Credentials(fake_token(lifetime=30 * 3600)))
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(auto_renew.renew_if_due(healthy, Path(d) / "seen.json"))
        read_login.assert_not_called()

    @patch("bupt_activity_notifier.auto_renew.read_login")
    def test_disabled_never_logs_in(self, read_login):
        with patch.dict("os.environ", {"SECONDCLASS_AUTO_RENEW": "0"}):
            with tempfile.TemporaryDirectory() as d:
                self.assertFalse(auto_renew.renew_if_due(self.client, Path(d) / "seen.json"))
        read_login.assert_not_called()

    @patch("bupt_activity_notifier.auto_renew.read_login")
    def test_corrupt_retry_receipt_blocks_login(self, read_login):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "seen.json"
            (Path(d) / auto_renew.RETRY_STATE_FILENAME).write_text("{garbage", encoding="utf-8")
            self.assertFalse(auto_renew.renew_if_due(self.client, state))
        read_login.assert_not_called()

    @patch("bupt_activity_notifier.auto_renew.save_renewed_token")
    @patch("bupt_activity_notifier.auto_renew.browser_sign_in")
    @patch("bupt_activity_notifier.auto_renew.read_login")
    def test_verification_challenge_stops_all_unattended_retries(self, read_login, browser, save):
        read_login.return_value = ("synthetic-user", "synthetic-password")
        browser.side_effect = auto_renew.RenewalError(
            "Official verification required.", code="verification_required"
        )
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            with self.assertRaises(auto_renew.RenewalError):
                auto_renew.renew_if_due(self.client, state)
            guard = json.loads(
                (Path(folder) / auto_renew.RETRY_STATE_FILENAME).read_text(encoding="utf-8")
            )
            self.assertTrue(guard["manual_required"])
            # Even after the normal 12h cooldown, do not retry this challenge.
            far_future = guard["retry_after"] + 365 * 86400
            self.assertFalse(auto_renew._retry_allowed(state, far_future))
            self.assertFalse(auto_renew.renew_if_due(self.client, state))
            self.assertEqual(browser.call_count, 1)
        save.assert_not_called()

    def test_windows_store_rejects_missing_data_without_calling_os(self):
        with self.assertRaises(SecretStoreError):
            _write("fake", "", "password")
        with self.assertRaises(SecretStoreError):
            _write("fake", "username", "")

    @patch("bupt_activity_notifier.auto_renew.ActivityClient")
    @patch("bupt_activity_notifier.auto_renew.save_renewed_token")
    @patch("bupt_activity_notifier.auto_renew.browser_sign_in")
    @patch("bupt_activity_notifier.auto_renew.read_login")
    def test_invalid_api_token_never_persists(self, read_login, browser, save, client_class):
        read_login.return_value = ("u", "p")
        browser.return_value = self.new
        client_class.return_value.validate_connection.side_effect = ValueError("synthetic data")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(auto_renew.RenewalError):
                auto_renew.renew_if_due(self.client, Path(d) / "seen.json")
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
