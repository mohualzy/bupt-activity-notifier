import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, call, patch

from bupt_activity_notifier.cli import main
from bupt_activity_notifier.notifications import NotificationError
from bupt_activity_notifier.auto_renew import RenewalError


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

    @patch("bupt_activity_notifier.cli.renew_if_due", return_value=True)
    @patch("bupt_activity_notifier.cli.make_client")
    def test_manual_renew_command_reports_validated_success(self, make_client, renew):
        with redirect_stdout(io.StringIO()) as output:
            result = main(["--renew-now"])
        self.assertEqual(result, 0)
        self.assertIn("passed read-only API validation", output.getvalue())
        renew.assert_called_once()
        self.assertTrue(renew.call_args.kwargs["force"])

    @patch("bupt_activity_notifier.cli.renew_if_due", side_effect=RenewalError("private detail"))
    @patch("bupt_activity_notifier.cli.make_client")
    def test_manual_renew_failure_does_not_disclose_error(self, make_client, renew):
        with redirect_stdout(io.StringIO()) as output:
            result = main(["--renew-now"])
        self.assertEqual(result, 1)
        self.assertNotIn("private detail", output.getvalue())

    @patch("bupt_activity_notifier.cli.time.sleep", side_effect=KeyboardInterrupt)
    @patch("bupt_activity_notifier.cli.run_once")
    @patch("bupt_activity_notifier.cli.send_auth_notice_if_needed")
    @patch("bupt_activity_notifier.cli._token_warning", return_value=None)
    @patch("bupt_activity_notifier.cli.make_client")
    @patch("bupt_activity_notifier.cli.renew_if_due", return_value=True)
    @patch("bupt_activity_notifier.cli.load_dotenv")
    @patch("bupt_activity_notifier.cli.Notifier.from_environment")
    def test_watch_switches_to_validated_renewed_client(
        self, get_notifier, load, renew, make_client, warning, notice, run_once, sleep
    ):
        old, fresh = Mock(), Mock()
        make_client.side_effect = [old, fresh]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--watch"]), 0)
        self.assertEqual(make_client.call_count, 2)
        self.assertIs(run_once.call_args.args[0], fresh)
        self.assertIs(notice.call_args.args[0], fresh)

    @patch("bupt_activity_notifier.cli.time.sleep", side_effect=KeyboardInterrupt)
    @patch("bupt_activity_notifier.cli.run_once")
    @patch("bupt_activity_notifier.cli.send_auth_notice_if_needed")
    @patch("bupt_activity_notifier.cli._token_warning", return_value=None)
    @patch("bupt_activity_notifier.cli.make_client")
    @patch("bupt_activity_notifier.cli.renew_if_due", side_effect=RenewalError("secret"))
    @patch("bupt_activity_notifier.cli.load_dotenv")
    @patch("bupt_activity_notifier.cli.Notifier.from_environment")
    def test_watch_renew_failure_continues_with_existing_client(
        self, get_notifier, load, renew, make_client, warning, notice, run_once, sleep
    ):
        prior = Mock()
        make_client.return_value = prior
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--watch"]), 0)
        self.assertIs(run_once.call_args.args[0], prior)
        self.assertNotIn("secret", output.getvalue())
        self.assertEqual(make_client.call_count, 1)

    @patch("bupt_activity_notifier.cli.renew_if_due")
    def test_dry_run_never_attempts_auto_login(self, renew):
        with (
            patch("bupt_activity_notifier.cli.time.sleep", side_effect=KeyboardInterrupt),
            patch("bupt_activity_notifier.cli.run_once"),
            patch("bupt_activity_notifier.cli.make_client"),
            patch("bupt_activity_notifier.cli.Notifier.from_environment"),
        ):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--watch", "--dry-run"]), 0)
        renew.assert_not_called()

    def test_setup_auto_renew_refuses_unattended_session(self):
        with patch("sys.stdin") as stdin:
            stdin.isatty.return_value = False
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["--setup-auto-renew"]), 2)
            self.assertIn("local interactive terminal", output.getvalue())

    @patch("bupt_activity_notifier.cli.renew_if_due", return_value=True)
    @patch("bupt_activity_notifier.cli.make_client")
    def test_visible_manual_trial_routes_headless_false(self, client, renew):
        # Simulate a real person's interactive terminal without real sign-in.
        with patch("sys.stdin.isatty", return_value=True), \
             patch("sys.stdout.isatty", return_value=True):
            self.assertEqual(main(["--renew-now", "--headed"]), 0)
        self.assertFalse(renew.call_args.kwargs["headless"])

    @patch("bupt_activity_notifier.cli.renew_if_due")
    def test_visible_manual_trial_refuses_remote_or_piped_console(self, renew):
        with patch("sys.stdin.isatty", return_value=False):
            self.assertEqual(main(["--renew-now", "--headed"]), 2)
        renew.assert_not_called()


if __name__ == "__main__":
    unittest.main()
