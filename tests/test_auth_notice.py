"""Synthetic expiry reminders; no real credentials or messages."""

import base64
import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock

from bupt_activity_notifier.api import ActivityClient, Credentials
from bupt_activity_notifier.auth_notice import send_auth_notice_if_needed
from bupt_activity_notifier.notifications import NotificationError


def fake_jwt(expires_at: int) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": 42, "exp": expires_at}).encode()
    ).decode().rstrip("=")
    return "header." + payload + ".fake"


def fake_client(seconds_from_now: int) -> ActivityClient:
    return ActivityClient(Credentials(fake_jwt(int(time.time()) + seconds_from_now)))


class AuthNoticeTests(unittest.TestCase):
    def setUp(self):
        self.output = lambda _: None

    def test_healthy_token_does_not_notify(self):
        with tempfile.TemporaryDirectory() as folder:
            notifier = Mock()
            notifier.configured = True
            notifier.channels = ("serverchan",)
            sent = send_auth_notice_if_needed(
                fake_client(30 * 3600), notifier, Path(folder) / "seen.json",
                output=self.output,
            )
            self.assertEqual(sent, 0)
            notifier.send_notice_channel.assert_not_called()
            self.assertFalse((Path(folder) / "auth_notices.json").exists())

    def test_warning_sent_once_per_expiration(self):
        with tempfile.TemporaryDirectory() as folder:
            client = fake_client(12 * 3600)
            notifier = Mock()
            notifier.configured = True
            notifier.channels = ("serverchan",)
            state = Path(folder) / "seen.json"
            self.assertEqual(send_auth_notice_if_needed(client, notifier, state, output=self.output), 1)
            self.assertEqual(send_auth_notice_if_needed(client, notifier, state, output=self.output), 0)
            notifier.send_notice_channel.assert_called_once()
            args = notifier.send_notice_channel.call_args.args
            self.assertEqual(args[0], "serverchan")
            self.assertIn("更新登录凭证", args[1])
            self.assertIn("北京时间", args[2])
            data = json.loads((Path(folder) / "auth_notices.json").read_text(encoding="utf-8"))
            self.assertEqual(data["receipts"]["expiring"], ["serverchan"])
            self.assertNotIn("token", str(data).lower())
            self.assertNotIn(client.credentials.token, str(data))

    def test_expired_token_notifies_once(self):
        with tempfile.TemporaryDirectory() as folder:
            client = fake_client(-2)
            notifier = Mock()
            notifier.configured = True
            notifier.channels = ("serverchan",)
            state = Path(folder) / "seen.json"
            self.assertEqual(send_auth_notice_if_needed(client, notifier, state, output=self.output), 1)
            self.assertEqual(send_auth_notice_if_needed(client, notifier, state, output=self.output), 0)
            self.assertIn("已过期", notifier.send_notice_channel.call_args.args[1])

    def test_channel_failure_does_not_repeat_success(self):
        with tempfile.TemporaryDirectory() as folder:
            client = fake_client(8 * 3600)
            notifier = Mock()
            notifier.configured = True
            notifier.channels = ("serverchan", "onebot_private")
            calls = []
            def deliver(channel, title, body):
                calls.append(channel)
                if channel == "onebot_private" and calls.count(channel) == 1:
                    raise NotificationError("synthetic")
            notifier.send_notice_channel.side_effect = deliver
            state = Path(folder) / "seen.json"
            with self.assertRaises(NotificationError):
                send_auth_notice_if_needed(client, notifier, state, output=self.output)
            self.assertEqual(send_auth_notice_if_needed(client, notifier, state, output=self.output), 1)
            self.assertEqual(calls, ["serverchan", "onebot_private", "onebot_private"])

    def test_no_channel_no_notice(self):
        with tempfile.TemporaryDirectory() as folder:
            notifier = Mock()
            notifier.configured = False
            notifier.channels = ()
            sent = send_auth_notice_if_needed(
                fake_client(12 * 3600), notifier, Path(folder) / "seen.json", output=self.output
            )
            self.assertEqual(sent, 0)
            notifier.send_notice_channel.assert_not_called()

    def test_invalid_receipts_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            (Path(folder) / "auth_notices.json").write_text('{"version":1,"expiry":1,"receipts":{"expiring":"bad"}}')
            notifier = Mock()
            notifier.configured = True
            notifier.channels = ("serverchan",)
            with self.assertRaises(ValueError):
                send_auth_notice_if_needed(fake_client(12 * 3600), notifier, state, output=self.output)
            notifier.send_notice_channel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
