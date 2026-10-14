import unittest

from bupt_activity_notifier.filtering import (
    Activity,
    CHECK_IN,
    CHECK_OUT,
    SIGN_UP,
    matches_shahe,
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

    def test_shahe_includes_any_attendance_requirements(self):
        for flags in (0, SIGN_UP, CHECK_IN, CHECK_OUT,
                      CHECK_IN | CHECK_OUT, SIGN_UP | CHECK_IN | CHECK_OUT):
            with self.subTest(flags=flags):
                self.assertTrue(matches_shahe(self.record(1, flags)))

    def test_shahe_includes_missing_or_invalid_attendance_fields(self):
        for value in (None, "unknown", -1):
            with self.subTest(value=value):
                self.assertTrue(matches_shahe(self.record(1, value)))

    def test_all_other_and_unknown_campuses_rejected(self):
        for campus in (0, 2, 3, 100000000, None, "invalid"):
            with self.subTest(campus=campus):
                self.assertFalse(matches_shahe(self.record(campus, CHECK_IN)))

    def test_markdown_lines_are_separate_and_requirements_reflect_real_flags(self):
        activity = Activity.from_raw({
            "id": 13311, "name": "名家面对面｜AI时代，写作应该如何进行？",
            "area": 1, "demands": SIGN_UP | CHECK_IN,
            "location": "学生活动中心报告厅313",
            "activity_start_time": "2026-10-20T06:00:00Z",
            "activity_end_time": "2026-10-20T16:00:00Z",
        })
        body = render_activity(activity)
        self.assertTrue(body.startswith("### 名家面对面"))
        self.assertIn("\n\n- **校区**：沙河校区\n", body)
        self.assertIn("- **地点**：学生活动中心报告厅313\n", body)
        self.assertIn("- **开始时间（北京时间）**：2026-10-20 14:00\n", body)
        self.assertIn("- **结束时间（北京时间）**：2026-10-21 00:00\n", body)
        self.assertIn("- **报名**：需报名\n", body)
        self.assertIn("- **签到**：需签到\n", body)
        self.assertIn("- **签退**：无需签退\n", body)
        self.assertIn("**活动 ID**：`13311`", body)
        self.assertNotIn("校区：沙河校区 学生活动中心", body)

    def test_missing_requirements_are_unknown_not_implied(self):
        text = render_activity(self.record(demands=None))
        self.assertIn("报名未知", text)
        self.assertIn("签到未知", text)
        self.assertIn("签退未知", text)

    def test_checkout_and_no_checkin_are_reported_truthfully(self):
        text = render_activity(self.record(demands=CHECK_OUT))
        self.assertIn("无需报名", text)
        self.assertIn("无需签到", text)
        self.assertIn("需签退", text)

    def test_explicit_offset_converted_to_beijing(self):
        activity = Activity.from_raw({
            "id": 4, "area": 1, "demands": 2,
            "activity_start_time": "2026-10-16T20:50:00+09:00",
            "activity_end_time": "2026-10-16T22:00:00+09:00",
        })
        body = render_activity(activity)
        self.assertIn("**开始时间（北京时间）**：2026-10-16 19:50", body)
        self.assertIn("**结束时间（北京时间）**：2026-10-16 21:00", body)

    def test_naive_timestamp_is_not_assumed_utc(self):
        activity = Activity.from_raw({
            "id": 5, "area": 1, "demands": 2,
            "activity_start_time": "2026-10-16T18:50:00",
            "activity_end_time": "bad-time",
        })
        body = render_activity(activity)
        self.assertIn("**开始时间**：2026-10-16T18:50:00", body)
        self.assertIn("**结束时间**：bad-time", body)
        self.assertNotIn("北京时间", body)

    def test_empty_location_and_times_show_missing(self):
        body = render_activity(self.record())
        self.assertIn("**地点**：未公布", body)
        self.assertIn("**开始时间**：未公布", body)
        self.assertIn("**结束时间**：未公布", body)

    def test_untrusted_title_is_escaped_for_markdown(self):
        activity = Activity.from_raw({
            "id": 123, "name": "活动 <script> *星号* [链接]", "area": 1
        })
        body = render_activity(activity)
        self.assertNotIn("<script>", body)
        self.assertIn(r"\<script\>", body)
        self.assertIn(r"\*星号\*", body)
        self.assertIn(r"\[链接\]", body)

    def test_required_fields(self):
        with self.assertRaises(ValueError):
            Activity.from_raw({"area": 1, "demands": 2})


if __name__ == "__main__":
    unittest.main()
