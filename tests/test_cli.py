import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, call, patch

from bupt_activity_notifier.cli import main
from bupt_activity_notifier.notifications import NotificationError


class CLITests(unittest.TestCase):
    @patch("bupt_activity_notifier.cli.Notifier.from_environment")
    def test_test_push_without_channels_sends_nothing(self, get_notifier):
        get_notifier.return_value = Mock(configured=False)
        with redirect_stdout(io.StringIO()):
            result = main(["--test-push"])
        self.assertEqual(result, 2)
        get_notifier.return_value.send.assert_not_called()

    @patch("bupt_activity_notifier.cli.Notifier.from_environment")
    def test_test_push_with_mock_channel(self, get_notifier):
        notifier = get_notifier.return_value = Mock(configured=True)
        with redirect_stdout(io.StringIO()) as output:
            result = main(["--test-push"])
        self.assertEqual(result, 0)
        notifier.send.assert_called_once()
        self.assertEqual(notifier.send.call_args.args[0].id, "synthetic-test")
        self.assertIn("accepted", output.getvalue())

    @patch("bupt_activity_notifier.cli.Notifier.from_environment")
    def test_test_push_failure_reports_sanitized_message(self, get_notifier):
        notifier = get_notifier.return_value = Mock(configured=True)
        notifier.send.side_effect = NotificationError("hidden credentials")
        with redirect_stdout(io.StringIO()) as output:
            result = main(["--test-push"])
        self.assertEqual(result, 1)
        self.assertNotIn("hidden credentials", output.getvalue())

    @patch("bupt_activity_notifier.cli.time.sleep", side_effect=KeyboardInterrupt)
    @patch("bupt_activity_notifier.cli.run_once")
    @patch("bupt_activity_notifier.cli.send_auth_notice_if_needed")
    @patch("bupt_activity_notifier.cli._token_warning", return_value=None)
    @patch("bupt_activity_notifier.cli.make_client")
    @patch("bupt_activity_notifier.cli.load_dotenv")
    @patch("bupt_activity_notifier.cli.Notifier.from_environment")
    def test_watch_reloads_dotenv_and_issues_safe_expiry_notice(
        self, get_notifier, load_dotenv, make_client, warn,
        send_auth_notice, run_once, sleep,
    ):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--watch"]), 0)
        self.assertIn(call(override=True), load_dotenv.call_args_list)
        self.assertEqual(get_notifier.call_count, 2)
        send_auth_notice.assert_called_once()
        run_once.assert_called_once()

    @patch("bupt_activity_notifier.cli.time.sleep", side_effect=KeyboardInterrupt)
    @patch("bupt_activity_notifier.cli.run_once")
    @patch("bupt_activity_notifier.cli.send_auth_notice_if_needed")
    @patch("bupt_activity_notifier.cli._token_warning", return_value=None)
    @patch("bupt_activity_notifier.cli.make_client")
    @patch("bupt_activity_notifier.cli.load_dotenv")
    @patch("bupt_activity_notifier.cli.Notifier.from_environment")
    def test_watch_dry_run_never_sends_auth_notice(
        self, get_notifier, load_dotenv, make_client, warn,
        send_auth_notice, run_once, sleep,
    ):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--watch", "--dry-run"]), 0)
        send_auth_notice.assert_not_called()
        run_once.assert_called_once()


if __name__ == "__main__":
    unittest.main()
