"""JWT expiry and private token rotation tests (synthetic credentials only)."""

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from bupt_activity_notifier.api import (
    ActivityClient,
    AuthenticationExpired,
    Credentials,
    token_seconds_remaining,
)


def token_with_exp(exp: int, sub: int = 42) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp, "sub": sub}).encode())
    return "header." + payload.decode().rstrip("=") + ".fake-signature"


class AuthTests(unittest.TestCase):
    def test_token_remaining(self):
        self.assertEqual(token_seconds_remaining(token_with_exp(1120), now=1000), 120)

    def test_reject_expired_before_network(self):
        session = Mock()
        expired = token_with_exp(100)
        with self.assertRaises(AuthenticationExpired):
            ActivityClient(Credentials(expired), session=session).list_activities()
        session.get.assert_not_called()

    def test_token_file_can_rotate_without_restarting_program(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "token.txt"
            first = token_with_exp(5000000000)
            second = token_with_exp(5000000100)
            with patch.dict(os.environ, {"SECONDCLASS_TOKEN_FILE": str(path),
                                         "SECONDCLASS_TOKEN": "ignore"}, clear=False):
                path.write_text(first, encoding="utf-8")
                self.assertEqual(Credentials.from_environment().token, first)
                path.write_text(second, encoding="utf-8")
                self.assertEqual(Credentials.from_environment().token, second)

    def test_token_file_errors_are_redacted(self):
        with patch.dict(os.environ, {"SECONDCLASS_TOKEN_FILE": "Z:/secret-path/token.txt"}, clear=False):
            with self.assertRaises(ValueError) as caught:
                Credentials.from_environment()
            self.assertNotIn("secret-path", str(caught.exception))

    def test_malformed_exp_does_not_crash(self):
        bad = "header." + base64.urlsafe_b64encode(
            json.dumps({"exp": {"bad": True}, "sub": 42}).encode()
        ).decode().rstrip("=") + ".fake"
        with self.assertRaises(AuthenticationExpired):
            token_seconds_remaining(bad)

    def test_missing_exp_delegates_expiration_to_server(self):
        jwt = "header." + base64.urlsafe_b64encode(
            b'{"sub":42}'
        ).decode().rstrip("=") + ".fake"
        self.assertIsNone(token_seconds_remaining(jwt))


if __name__ == "__main__":
    unittest.main()
