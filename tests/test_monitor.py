import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from bupt_activity_notifier.monitor import read_seen, read_state, run_once
from bupt_activity_notifier.notifications import NotificationError


def event(event_id, *, demands=2, area=1):
    return {"id": event_id, "name": f"活动 {event_id}", "area": area, "demands": demands}


def mock_notifier(channels=("serverchan",)):
    n = Mock()
    n.channels = channels
    n.configured = bool(channels)
    return n


class MonitorTests(unittest.TestCase):
    def test_first_run_creates_baseline_without_sending(self):
        with tempfile.TemporaryDirectory() as folder:
            client = Mock()
            client.list_activities.return_value = [event(1)]
            notifier = mock_notifier()
            state = Path(folder) / "seen.json"
            result = run_once(client, notifier, state, output=lambda _: None)
            self.assertTrue(result.initialized)
            self.assertEqual(result.notified, 0)
            notifier.send_channel.assert_not_called()
            self.assertEqual(read_seen(state), {"1"})

    def test_only_new_matching_events_sent_once(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            client = Mock()
            notifier = mock_notifier()
            client.list_activities.return_value = [event(1)]
            run_once(client, notifier, state, output=lambda _: None)
            client.list_activities.return_value = [
                event(1), event(2), event(3, demands=6),
                event(4, area=0),
            ]
            result = run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(result.notified, 2)
            self.assertEqual(
                [c.args[1].id for c in notifier.send_channel.call_args_list],
                ["2", "3"],
            )
            run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(notifier.send_channel.call_count, 2)

    def test_activity_moving_to_shahe_triggers_notification(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            client = Mock()
            notifier = mock_notifier()
            client.list_activities.return_value = [event(1, area=0)]
            run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(read_seen(state), set())
            client.list_activities.return_value = [event(1, area=1, demands=6)]
            result = run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(result.notified, 1)

    def test_dry_run_does_not_write_state(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            client = Mock()
            client.list_activities.return_value = [event(1)]
            notifier = mock_notifier()
            run_once(client, notifier, state, output=lambda _: None, dry_run=True)
            self.assertFalse(state.exists())
            notifier.send_channel.assert_not_called()

    def test_failed_notification_is_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            client = Mock()
            client.list_activities.return_value = [event(1)]
            notifier = mock_notifier()
            run_once(client, notifier, state, output=lambda _: None)
            client.list_activities.return_value = [event(1), event(2)]
            notifier.send_channel.side_effect = NotificationError("mock failure")
            with self.assertRaises(NotificationError):
                run_once(client, notifier, state, output=lambda _: None)
            notifier.send_channel.side_effect = None
            result = run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(result.notified, 1)

    def test_persist_after_each_successful_activity(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            client = Mock()
            client.list_activities.return_value = [event(1)]
            notifier = mock_notifier()
            run_once(client, notifier, state, output=lambda _: None)
            client.list_activities.return_value = [event(1), event(2), event(3)]
            notifier.send_channel.side_effect = [None, NotificationError("mock failure")]
            with self.assertRaises(NotificationError):
                run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(read_seen(state), {"1", "2"})
            notifier.send_channel.side_effect = None
            run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(
                [call.args[1].id for call in notifier.send_channel.call_args_list],
                ["2", "3", "3"],
            )

    def test_multi_channel_partial_failure_resume_without_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            client = Mock()
            client.list_activities.return_value = []
            notifier = mock_notifier(("serverchan", "onebot_private"))
            run_once(client, notifier, state, output=lambda _: None)
            client.list_activities.return_value = [event(9)]

            calls = []
            def deliver(channel, activity):
                calls.append(channel)
                if channel == "onebot_private" and calls.count(channel) == 1:
                    raise NotificationError("fake")

            notifier.send_channel.side_effect = deliver
            with self.assertRaises(NotificationError):
                run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(calls, ["serverchan", "onebot_private"])
            self.assertEqual(read_seen(state), set())
            self.assertEqual(read_state(state).delivered["serverchan"], {"9"})

            result = run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(result.notified, 1)
            self.assertEqual(result.deliveries, 1)
            self.assertEqual(calls, ["serverchan", "onebot_private", "onebot_private"])
            self.assertEqual(read_seen(state), {"9"})

    def test_without_delivery_config_matches_remain_unseen(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            client = Mock()
            client.list_activities.return_value = []
            silent = mock_notifier(())
            run_once(client, silent, state, output=lambda _: None)
            client.list_activities.return_value = [event(2)]
            run_once(client, silent, state, output=lambda _: None)
            self.assertEqual(read_seen(state), set())
            notifier = mock_notifier()
            result = run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(result.notified, 1)

    def test_legacy_state_migration_baselines_newly_eligible_history(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            state.write_text('{"seen_ids":["1"]}', encoding="utf-8")
            client = Mock()
            client.list_activities.return_value = [event(1), event(2, demands=6)]
            notifier = mock_notifier()
            self.assertEqual(run_once(client, notifier, state, output=lambda _: None).notified, 0)
            self.assertEqual(read_seen(state), {"1", "2"})
            self.assertIn('"filter_policy": "shahe-area-only-v1"', state.read_text(encoding="utf-8"))
            notifier.send_channel.assert_not_called()
            client.list_activities.return_value.append(event(3, demands=None))
            self.assertEqual(run_once(client, notifier, state, output=lambda _: None).notified, 1)
            self.assertEqual(notifier.send_channel.call_args.args[1].id, "3")

    def test_migration_preserves_partially_delivered_notifications(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            state.write_text(
                '{"version":2,"seen_ids":["1"],'
                '"delivered":{"serverchan":["2"]}}',
                encoding="utf-8",
            )
            client = Mock()
            client.list_activities.return_value = [
                event(1), event(2, demands=6),
                event(3, demands=0),
            ]
            notifier = mock_notifier(("serverchan", "onebot_private"))
            result = run_once(client, notifier, state, output=lambda _: None)
            self.assertEqual(result.notified, 1)
            self.assertEqual(result.deliveries, 1)
            self.assertEqual(notifier.send_channel.call_count, 1)
            self.assertEqual(notifier.send_channel.call_args.args[0], "onebot_private")
            self.assertEqual(notifier.send_channel.call_args.args[1].id, "2")
            self.assertEqual(read_seen(state), {"1", "2", "3"})
            self.assertEqual(read_state(state).filter_policy, "shahe-area-only-v1")

    def test_unsupported_filter_state_fails_closed_without_notifications(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            state.write_text(
                '{"version":2,"filter_policy":"future-rule",'
                '"seen_ids":[],"delivered":{}}',
                encoding="utf-8",
            )
            client = Mock()
            client.list_activities.return_value = [event(5)]
            notifier = mock_notifier()
            with self.assertRaises(ValueError):
                run_once(client, notifier, state, output=lambda _: None)
            notifier.send_channel.assert_not_called()

    def test_corrupted_state_does_not_reset_or_repush(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "seen.json"
            state.write_text('{"seen_ids":[], "delivered":{"serverchan":"invalid"}}', encoding="utf-8")
            client = Mock()
            client.list_activities.return_value = [event(3)]
            notifier = mock_notifier()
            with self.assertRaises(ValueError):
                run_once(client, notifier, state, output=lambda _: None)
            notifier.send_channel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
