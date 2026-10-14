import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

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


if __name__ == "__main__":
    unittest.main()
