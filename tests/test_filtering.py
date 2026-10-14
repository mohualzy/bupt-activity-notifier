import unittest

from bupt_activity_notifier.filtering import (
    Activity,
    CHECK_IN,
    CHECK_OUT,
    SIGN_UP,
    matches_shahe_checkin_no_checkout,
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

    def test_required_fields(self):
        with self.assertRaises(ValueError):
            Activity.from_raw({"area": 1, "demands": 2})


if __name__ == "__main__":
    unittest.main()
