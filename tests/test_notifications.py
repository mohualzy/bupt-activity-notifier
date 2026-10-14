import unittest
from unittest.mock import Mock

from bupt_activity_notifier.filtering import Activity
from bupt_activity_notifier.notifications import Notifier


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.activity = Activity.from_raw({
            "id": 9,
            "name": "Synthetic Activity",
            "area": 1,
            "demands": 2,
        })

    def test_unconfigured_notifier(self):
        self.assertFalse(Notifier().configured)

    def test_serverchan_success(self):
        response = Mock()
        response.json.return_value = {"code": 0, "message": "success"}
        session = Mock()
        session.post.return_value = response
        notifier = Notifier(serverchan_key="fake-key", session=session)
        notifier.send(self.activity)
        args, kwargs = session.post.call_args
        self.assertEqual(args[0], "https://sctapi.ftqq.com/fake-key.send")
        self.assertIn("Synthetic Activity", kwargs["data"]["desp"])

    def test_serverchan_error_is_not_silent(self):
        response = Mock()
        response.json.return_value = {"code": 999}
        session = Mock()
        session.post.return_value = response
        with self.assertRaises(RuntimeError):
            Notifier(serverchan_key="fake-key", session=session).send(self.activity)

    def test_onebot_private_message(self):
        response = Mock()
        response.json.return_value = {"status": "ok", "retcode": 0}
        session = Mock()
        session.post.return_value = response
        notifier = Notifier(
            onebot_url="http://127.0.0.1:3000",
            onebot_token="fake-token",
            onebot_user_id="12345",
            session=session,
        )
        notifier.send(self.activity)
        args, kwargs = session.post.call_args
        self.assertEqual(args[0], "http://127.0.0.1:3000/send_private_msg")
        self.assertEqual(kwargs["json"]["user_id"], 12345)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer fake-token")

    def test_onebot_reject_insecure_nonlocal_url(self):
        with self.assertRaises(ValueError):
            Notifier(
                onebot_url="http://example.org:3000",
                onebot_user_id="12345",
            ).send(self.activity)

    def test_onebot_reject_error_return(self):
        response = Mock()
        response.json.return_value = {"status": "failed", "retcode": 100}
        session = Mock()
        session.post.return_value = response
        with self.assertRaises(RuntimeError):
            Notifier(
                onebot_url="https://example.org",
                onebot_group_id="1",
                session=session,
            ).send(self.activity)


if __name__ == "__main__":
    unittest.main()
