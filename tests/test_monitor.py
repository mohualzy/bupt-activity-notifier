import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from bupt_activity_notifier.monitor import run_once


def event(event_id, *, demands=2, area=1):
    return {"id": event_id, "name": f"活动 {event_id}", "area": area, "demands": demands}


class MonitorTests(unittest.TestCase):
    def test_first_run_creates_baseline_without_sending(self):
        with tempfile.TemporaryDirectory() as folder:
            client = Mock()
            client.list_activities.return_value = [event(1)]
            notifier = Mock(configured=True)
            state = Path(folder) / "seen.json"
            result = run_once(client, notifier, state, output=lambda _: None)
            self.assertTrue(result.initialized)
            self.assertEqual(result.notified, 0)
            notifier.send.assert_not_called()
            self.assertTrue(state.exists())

    def test_only_new_matching_events_sent_once(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            client = Mock()
            notifier = Mock(configured=True)
            client.list_activities.return_value = [event(1)]
            run_once(client, notifier, state, output=lambda _: None)
            client.list_activities.return_value = [event(1), event(2), event(3, demands=6)]
            result = run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(result.notified, 1)
            self.assertEqual(notifier.send.call_args.args[0].id, "2")
            run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(notifier.send.call_count, 1)

    def test_dry_run_does_not_write_state(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            client = Mock()
            client.list_activities.return_value = [event(1)]
            notifier = Mock(configured=True)
            run_once(client, notifier, state, output=lambda _: None, dry_run=True)
            self.assertFalse(state.exists())
            notifier.send.assert_not_called()

    def test_failed_notification_is_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            client = Mock()
            client.list_activities.return_value = [event(1)]
            notifier = Mock(configured=True)
            run_once(client, notifier, state, output=lambda _: None)
            client.list_activities.return_value = [event(1), event(2)]
            notifier.send.side_effect = RuntimeError("mock failure")
            with self.assertRaises(RuntimeError):
                run_once(client, notifier, state, output=lambda _: None)
            notifier.send.side_effect = None
            result = run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(result.notified, 1)


if __name__ == "__main__":
    unittest.main()
