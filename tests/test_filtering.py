import unittest

from bupt_activity_notifier.filtering import (
    Activity,
    CHECK_IN,
    CHECK_OUT,
    SIGN_UP,
    matches_shahe_checkin_no_checkout,
    render_activity,
)


class FilteringTests(unittest.TestCase):
    def record(self, area=1, demands=2):
        return Activity.from_raw({
            "id": 123,
            "name": "测试活动",
            "area": area,
            "demands": demands,
        })

    def test_shahe_only_check_in(self):
        self.assertTrue(matches_shahe_checkin_no_checkout(self.record(1, CHECK_IN)))
        self.assertTrue(matches_shahe_checkin_no_checkout(self.record(1, SIGN_UP | CHECK_IN)))

    def test_reject_checkout(self):
        self.assertFalse(matches_shahe_checkin_no_checkout(self.record(1, CHECK_IN | CHECK_OUT)))

    def test_reject_other_campus(self):
        self.assertFalse(matches_shahe_checkin_no_checkout(self.record(0, CHECK_IN)))

    def test_reject_unknown_fields(self):
        self.assertFalse(matches_shahe_checkin_no_checkout(self.record(1, None)))
        self.assertFalse(matches_shahe_checkin_no_checkout(self.record(None, CHECK_IN)))
        self.assertFalse(matches_shahe_checkin_no_checkout(self.record(1, "not-a-number")))

    def test_reject_no_check_in(self):
        self.assertFalse(matches_shahe_checkin_no_checkout(self.record(1, 0)))

    def test_reject_negative_flags(self):
        self.assertFalse(matches_shahe_checkin_no_checkout(self.record(1, -1)))

    def test_utc_timestamp_displays_beijing_time(self):
        activity = Activity.from_raw({
            "id": 13264,
            "name": "动员大会",
            "area": 1,
            "demands": 2,
            "activity_start_time": "2026-10-16T10:50:00Z",
            "activity_end_time": "2026-10-16T12:05:00Z",
        })
        text = render_activity(activity)
        self.assertIn("时间（北京时间）：2026-10-16 18:50 至 2026-10-16 20:05", text)
        self.assertNotIn("2026-10-16T10:50:00Z", text)

    def test_explicit_offset_converted_to_beijing(self):
        activity = Activity.from_raw({
            "id": 4, "area": 1, "demands": 2,
            "activity_start_time": "2026-10-16T20:50:00+09:00",
            "activity_end_time": "2026-10-16T22:00:00+09:00",
        })
        self.assertIn("2026-10-16 19:50 至 2026-10-16 21:00", render_activity(activity))

    def test_naive_timestamp_is_not_assumed_utc(self):
        activity = Activity.from_raw({
            "id": 5, "area": 1, "demands": 2,
            "activity_start_time": "2026-10-16T18:50:00",
            "activity_end_time": "bad-time",
        })
        text = render_activity(activity)
        self.assertIn("时间：2026-10-16T18:50:00 至 bad-time", text)
        self.assertNotIn("北京时间", text)

    def test_required_fields(self):
        with self.assertRaises(ValueError):
            Activity.from_raw({"area": 1, "demands": 2})


if __name__ == "__main__":
    unittest.main()
