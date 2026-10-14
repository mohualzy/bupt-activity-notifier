import unittest
from unittest.mock import Mock

import requests

from bupt_activity_notifier.filtering import Activity
from bupt_activity_notifier.notifications import Notifier, NotificationError


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.activity = Activity.from_raw({
            "id": 9,
            "name": "Synthetic Activity",
            "area": 1,
            "demands": 2,
        })

    def test_channels(self):
        self.assertFalse(Notifier().configured)
        self.assertEqual(Notifier(serverchan_key="fake").channels, ("serverchan",))
        self.assertEqual(
            Notifier(serverchan_key="fake", onebot_url="https://local.example",
                     onebot_user_id="2", onebot_group_id="3").channels,
            ("serverchan", "onebot_private", "onebot_group"),
        )

    def test_serverchan_success(self):
        response = Mock()
        response.json.return_value = {"code": 0, "message": "success"}
        session = Mock()
        session.post.return_value = response
        notifier = Notifier(serverchan_key="fake-key", session=session)
        notifier.send_channel("serverchan", self.activity)
        args, kwargs = session.post.call_args
        self.assertEqual(args[0], "https://sctapi.ftqq.com/fake-key.send")
        self.assertIn("Synthetic Activity", kwargs["data"]["desp"])

    def test_serverchan_receives_readable_multiline_markdown(self):
        response = Mock()
        response.json.return_value = {"code": 0}
        session = Mock()
        session.post.return_value = response
        notifier = Notifier(serverchan_key="fake-key", session=session)
        activity = Activity.from_raw({
            "id": 13311,
            "name": "名家面对面｜AI时代，写作应该如何进行？",
            "area": 1,
            "demands": 7,  # Signup, check-in AND check-out.
            "location": "学生活动中心报告厅313",
            "activity_start_time": "2026-10-20T06:00:00Z",
            "activity_end_time": "2026-10-20T16:00:00Z",
        })
        notifier.send_channel("serverchan", activity)
        payload = session.post.call_args.kwargs["data"]
        self.assertEqual(payload["title"], "北邮第二课堂｜沙河新活动")
        self.assertIn("### 名家面对面", payload["desp"])
        self.assertIn("\n\n- **校区**：沙河校区\n", payload["desp"])
        self.assertIn("\n- **地点**：学生活动中心报告厅313\n", payload["desp"])
        self.assertIn("**签到**：需签到", payload["desp"])
        self.assertIn("**签退**：需签退", payload["desp"])
        self.assertGreater(payload["desp"].count("\n"), 8)

    def test_serverchan_error_is_not_silent(self):
        response = Mock()
        response.json.return_value = {"code": 999}
        session = Mock()
        session.post.return_value = response
        with self.assertRaises(NotificationError):
            Notifier(serverchan_key="fake-key", session=session).send(self.activity)

    def test_serverchan_request_error_cannot_leak_sendkey(self):
        session = Mock()
        session.post.side_effect = requests.RequestException(
            "HTTPS failure at https://sctapi.ftqq.com/SCT-SUPERSECRET.send"
        )
        with self.assertRaises(NotificationError) as caught:
            Notifier(serverchan_key="SCT-SUPERSECRET", session=session).send(self.activity)
        self.assertNotIn("SCT-SUPERSECRET", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

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
        notifier.send_channel("onebot_private", self.activity)
        args, kwargs = session.post.call_args
        self.assertEqual(args[0], "http://127.0.0.1:3000/send_private_msg")
        self.assertEqual(kwargs["json"]["user_id"], 12345)
        self.assertTrue(kwargs["json"]["auto_escape"])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer fake-token")

    def test_onebot_group_message(self):
        response = Mock()
        response.json.return_value = {"status": "ok", "retcode": 0}
        session = Mock()
        session.post.return_value = response
        notifier = Notifier(onebot_url="https://test.invalid", onebot_group_id="999", session=session)
        notifier.send_channel("onebot_group", self.activity)
        self.assertEqual(session.post.call_args.kwargs["json"]["group_id"], 999)

    def test_onebot_reject_insecure_nonlocal_url(self):
        for url in ("http://example.org:3000", "http://127.0.0.1.evil.example", "ftp://site.example"):
            with self.subTest(url=url), self.assertRaises(NotificationError):
                Notifier(onebot_url=url, onebot_user_id="12345").send(self.activity)

    def test_onebot_reject_error_return(self):
        response = Mock()
        response.json.return_value = {"status": "failed", "retcode": 100}
        session = Mock()
        session.post.return_value = response
        with self.assertRaises(NotificationError):
            Notifier(
                onebot_url="https://example.org",
                onebot_group_id="1",
                session=session,
            ).send(self.activity)

    def test_onebot_reject_missing_status_even_http_200(self):
        response = Mock()
        response.json.return_value = {"retcode": 0}
        session = Mock()
        session.post.return_value = response
        with self.assertRaises(NotificationError):
            Notifier(onebot_url="https://example.org", onebot_group_id="1",
                     session=session).send(self.activity)

    def test_invalid_onebot_user_id_does_not_expose_value(self):
        with self.assertRaises(NotificationError) as caught:
            Notifier(onebot_url="https://example.org", onebot_user_id="bad-id").send(self.activity)
        self.assertNotIn("bad-id", str(caught.exception))

    def test_auth_expiry_notice_uses_distinct_title(self):
        response = Mock()
        response.json.return_value = {"code": 0}
        session = Mock()
        session.post.return_value = response
        notifier = Notifier(serverchan_key="fake-key", session=session)
        notifier.send_notice_channel("serverchan", "请更新登录凭证", "测试提醒，不含任何密钥")
        self.assertEqual(session.post.call_args.kwargs["data"]["title"], "请更新登录凭证")
        self.assertEqual(session.post.call_args.kwargs["data"]["desp"], "测试提醒，不含任何密钥")

    def test_auth_expiry_notice_redacts_request_error(self):
        session = Mock()
        session.post.side_effect = requests.RequestException("secret-in-URL")
        notifier = Notifier(serverchan_key="fake-key", session=session)
        with self.assertRaises(NotificationError) as caught:
            notifier.send_notice_channel("serverchan", "到期", "请重新登录")
        self.assertNotIn("secret-in-URL", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
