import unittest
from unittest.mock import Mock

from bupt_activity_notifier.api import APIError, ActivityClient, Credentials, unwrap_activity_list


class APITests(unittest.TestCase):
    def test_payload_direct(self):
        self.assertEqual(unwrap_activity_list({"status": 0, "data": [{"id": 3}]}), [{"id": 3}])

    def test_payload_nested(self):
        self.assertEqual(unwrap_activity_list({"data": {"data": [{"id": 7}]}}), [{"id": 7}])

    def test_reject_invalid_payload(self):
        for bad in ({}, {"data": "not a list"}, {"data": [{"id": 1}, "bad"]}):
            with self.subTest(bad=bad), self.assertRaises(APIError):
                unwrap_activity_list(bad)

    def test_list_uses_discovered_query_and_get_only(self):
        response = Mock()
        response.json.return_value = {"status": 0, "data": [{"id": 3, "area": 1, "demands": 2}]}
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response
        c = Credentials("test-token", "7", "4", "2025", "9", "test-digest")
        client = ActivityClient(c, session=session)
        activities = client.list_activities()
        self.assertEqual(len(activities), 1)
        args, kwargs = session.get.call_args
        self.assertEqual(args[0], "https://dekt.bupt.edu.cn/api/v1/activity")
        self.assertEqual(kwargs["params"]["college_id"], "7")
        self.assertEqual(kwargs["params"]["is_group"], 0)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")
        session.post.assert_not_called()

    def test_other_hosts_forbidden(self):
        c = Credentials("x", "a", "b", "c", "d", "e")
        with self.assertRaises(ValueError):
            ActivityClient(c, base_url="https://example.com")


if __name__ == "__main__":
    unittest.main()
