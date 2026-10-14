"""Synthetic tests: no real account, no network, no persistent token."""

import base64
import json
import unittest
from unittest.mock import Mock

import requests

from bupt_activity_notifier.api import (
    APIError,
    ActivityClient,
    AuthenticationExpired,
    Credentials,
    unwrap_activity_list,
)


def dummy_jwt(sub: int = 42) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    return "fakeheader." + payload + ".fakesignature"


def api_response(payload: dict, status: int = 200):
    response = Mock()
    response.status_code = status
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


class APITests(unittest.TestCase):
    def setUp(self):
        self.credentials = Credentials(dummy_jwt())

    def test_live_envelope(self):
        payload = {
            "status": "ok",
            "data": [{"id": 3, "area": 1, "demands": 2}],
            "digest": ["opaque-digest"],
            "error": None,
        }
        self.assertEqual(unwrap_activity_list(payload), payload["data"])

    def test_reject_invalid_envelopes(self):
        bad = [
            {}, {"data": "not a list"}, {"data": [{"id": 1}, "bad"]},
            {"status": "error", "data": []}, {"status": "ok", "error": "no", "data": []},
        ]
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(APIError):
                unwrap_activity_list(payload)

    def test_user_info_then_list_with_digest(self):
        user = {
            "college_id": 7, "class_id": 4, "grade": 2025, "role_id": 9,
        }
        session = Mock()
        session.get.side_effect = [
            api_response({"status": "ok", "data": user, "digest": "opaque-user-digest", "error": None}),
            api_response({"status": "ok", "data": [{"id": 3, "area": 1, "demands": 2}], "error": None}),
        ]
        items = ActivityClient(self.credentials, session=session).list_activities()
        self.assertEqual(len(items), 1)
        self.assertEqual(session.get.call_count, 2)
        user_call, activity_call = session.get.call_args_list
        self.assertEqual(user_call.args[0], "https://dekt.bupt.edu.cn/api/v1/user/42")
        self.assertEqual(activity_call.args[0], "https://dekt.bupt.edu.cn/api/v1/activity")
        self.assertEqual(activity_call.kwargs["params"], {
            "college_id": "7", "class_id": "4", "grade": "2025",
            "role_id": "9", "digest": "opaque-user-digest", "is_group": 0,
        })
        self.assertEqual(user_call.kwargs["headers"]["Authorization"], "Bearer " + self.credentials.token)
        session.post.assert_not_called()

    def test_doctor_does_not_return_account_data(self):
        user = {"college_id": 7, "class_id": 4, "grade": 2025, "role_id": 9}
        session = Mock()
        session.get.side_effect = [
            api_response({"status": "ok", "data": user, "digest": "opaque"}),
            api_response({"status": "ok", "data": [{"id": 2, "name": "test", "area": 1, "demands": 2}]}),
        ]
        result = ActivityClient(self.credentials, session=session).validate_connection()
        self.assertEqual(result["activity_count"], 1)
        self.assertNotIn("digest", result)
        self.assertNotIn("token", result)
        self.assertEqual(result["http"], 200)

    def test_reject_invalid_token_without_request(self):
        session = Mock()
        with self.assertRaises(AuthenticationExpired):
            ActivityClient(Credentials("not-a-jwt"), session=session).list_activities()
        session.get.assert_not_called()

    def test_reject_missing_user_digest(self):
        session = Mock()
        session.get.return_value = api_response({
            "status": "ok",
            "data": {"college_id": 1, "class_id": 2, "grade": 2025, "role_id": 3},
        })
        with self.assertRaises(APIError):
            ActivityClient(self.credentials, session=session).list_activities()

    def test_http_auth_rejected(self):
        session = Mock()
        session.get.return_value = api_response({}, status=403)
        with self.assertRaises(AuthenticationExpired):
            ActivityClient(self.credentials, session=session).list_activities()

    def test_do_not_leak_request_errors(self):
        session = Mock()
        session.get.side_effect = requests.RequestException("secret-token")
        with self.assertRaises(APIError) as exc:
            ActivityClient(self.credentials, session=session).list_activities()
        self.assertNotIn("secret-token", str(exc.exception))

    def test_other_hosts_forbidden(self):
        with self.assertRaises(ValueError):
            ActivityClient(self.credentials, base_url="https://example.com")


if __name__ == "__main__":
    unittest.main()
