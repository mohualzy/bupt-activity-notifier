"""No-login BUPT public source tests: no HTTP or notification network calls."""

from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from bupt_activity_notifier.notifications import NotificationError
from bupt_activity_notifier.public_sources import (
    PublicSource, SOURCES, parse_listing, eligible_lead, _publication_date,
)
from bupt_activity_notifier.public_monitor import run_public_poll, read_public_state


SRC = PublicSource("北邮学生处", "https://xsc.bupt.edu.cn/xgdt/tzgg.htm", "1022")
OLD_URL = "https://xsc.bupt.edu.cn/info/1022/2000.htm"
NEW_URL = "https://xsc.bupt.edu.cn/info/1022/2001.htm"
OTHER_URL = "https://xsc.bupt.edu.cn/info/1022/2002.htm"


def index_html(*items):
    links = "\n".join(
        f'<li><a href="../info/1022/{ident}.htm">{name}</a></li>'
        for ident, name in items
    )
    return f"<html><body><div>{links}</div></body></html>"


def article_html(*, date_text="发布日期：2026-10-14", text="沙河校区欢迎报名参加活动"):
    return (
        "<html><head><script>secondclass.tokenv3='not-a-token';</script></head>"
        f"<body><article><h2>通知公告</h2><p>{date_text}</p>"
        f"<p>{text}</p></article></body></html>"
    )


class Response:
    status_code = 200
    headers = {"content-type": "text/html; charset=utf-8"}
    encoding = "utf-8"
    apparent_encoding = "utf-8"

    def __init__(self, content, status=200):
        self.text = content
        self.content = content.encode("utf-8")
        self.status_code = status


class MemorySession:
    def __init__(self, files):
        self.files = files
        self.requested = []

    def get(self, address, **kwargs):
        self.requested.append((address, kwargs))
        return self.files[address]


class PublicSourcesTests(unittest.TestCase):
    def test_url_allowlist_and_title_extraction(self):
        html = (
            '<a href="../info/1022/2001.htm">关于报名沙河校区志愿活动</a>'
            '<a href="https://evil.example/info/1022/9999.htm">恶意活动</a>'
            '<a href="/api/v1/user/123">不能访问私人数据</a>'
        )
        result = parse_listing(SRC, html)
        self.assertEqual(result, {NEW_URL: "关于报名沙河校区志愿活动"})

    def test_correct_activity_lead(self):
        lead = eligible_lead(
            SRC, NEW_URL, "关于沙河校区志愿者招募活动",
            article_html(), today=date(2026, 10, 14),
        )
        self.assertIsNotNone(lead)
        self.assertIn("沙河", lead.reason)

    def test_stale_and_irrelevant_are_rejected(self):
        stale = eligible_lead(SRC, NEW_URL, "沙河活动",
                              article_html(date_text="发布日期：2026-07-15"),
                              today=date(2026, 10, 14))
        irrelevant = eligible_lead(SRC, NEW_URL, "疫苗报名通知",
                                   article_html(), today=date(2026, 10, 14))
        no_campus = eligible_lead(SRC, NEW_URL, "校园活动",
                                  article_html(text="没有提及任何校区"),
                                  today=date(2026, 10, 14))
        self.assertIsNone(stale)
        self.assertIsNone(irrelevant)
        self.assertIsNone(no_campus)

    def test_js_script_text_cannot_make_lead_relevant(self):
        html = '<script>沙河</script><p>发布日期：2026-10-14</p><p>未出现目标地点</p>'
        self.assertIsNone(eligible_lead(
            SRC, NEW_URL, "关于报名校园活动", html,
            today=date(2026, 10, 14),
        ))

    def test_article_date_parser(self):
        self.assertEqual(
            _publication_date(article_html()), date(2026, 10, 14)
        )

    def test_first_successful_poll_only_initializes_baseline(self):
        web = MemorySession({SRC.listing: Response(index_html((2000,"关于沙河校区讲座")))})
        notifier = Mock(channels=("serverchan",))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "public_seen.json"
            result = run_public_poll(notifier, path, sources=(SRC,), session=web)
            self.assertEqual(result.initialized, 1)
            self.assertEqual(result.delivered, 0)
            notifier.send_notice_channel.assert_not_called()
            self.assertIn(OLD_URL, read_public_state(path)["sources"][SRC.name]["seen"])
            self.assertEqual(len(web.requested), 1)

    def test_new_lead_is_sent_once_and_marked_delivered(self):
        web = MemorySession({
            SRC.listing: Response(index_html((2000,"旧通知"))),
            NEW_URL: Response(article_html()),
        })
        notifier = Mock(channels=("serverchan",))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "public_seen.json"
            run_public_poll(notifier, path, sources=(SRC,), session=web)
            web.files[SRC.listing] = Response(index_html(
                (2001,"关于沙河校区新生志愿活动报名"),
                (2000,"旧通知"),
            ))
            # Time is intentionally fixed by patching the date at the source.
            from unittest.mock import patch
            with patch("bupt_activity_notifier.public_sources.datetime") as dt:
                dt.now.return_value.date.return_value = date(2026, 10, 14)
                report = run_public_poll(notifier, path, sources=(SRC,), session=web)
                again = run_public_poll(notifier, path, sources=(SRC,), session=web)
            self.assertEqual(report.delivered, 1)
            self.assertEqual(again.delivered, 0)
            notifier.send_notice_channel.assert_called_once()
            self.assertIn("非二课核验", notifier.send_notice_channel.call_args.args[1])
            body = notifier.send_notice_channel.call_args.args[2]
            self.assertIn("签到和签退", body)
            self.assertIn(NEW_URL, read_public_state(path)["sources"][SRC.name]["seen"])

    def test_provider_failure_remains_retryable(self):
        web = MemorySession({
            SRC.listing: Response(index_html((2000,"旧通知"))),
            NEW_URL: Response(article_html()),
        })
        notifier = Mock(channels=("serverchan",))
        notifier.send_notice_channel.side_effect = [
            NotificationError("provider refused"), None,
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "public_seen.json"
            run_public_poll(notifier, path, sources=(SRC,), session=web)
            web.files[SRC.listing] = Response(index_html(
                (2001,"关于沙河校区新生志愿活动报名"), (2000,"旧通知")
            ))
            from unittest.mock import patch
            with patch("bupt_activity_notifier.public_sources.datetime") as dt:
                dt.now.return_value.date.return_value = date(2026, 10, 14)
                fail = run_public_poll(notifier, path, sources=(SRC,), session=web)
                succeed = run_public_poll(notifier, path, sources=(SRC,), session=web)
            self.assertEqual(fail.delivered, 0)
            self.assertEqual(succeed.delivered, 1)
            self.assertEqual(notifier.send_notice_channel.call_count, 2)

    def test_site_unavailable_never_resets_seen_state(self):
        web = MemorySession({SRC.listing: Response(index_html((2000, "旧通知")))})
        notifier = Mock(channels=("serverchan",))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "public_seen.json"
            run_public_poll(notifier, path, sources=(SRC,), session=web)
            old = path.read_text(encoding="utf-8")
            web.files[SRC.listing] = Response("", status=412)
            result = run_public_poll(notifier, path, sources=(SRC,), session=web)
            self.assertEqual(result.sources_failed, 1)
            self.assertEqual(path.read_text(encoding="utf-8"), old)

    def test_corrupted_state_does_not_rebaseline(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "public_seen.json"
            path.write_text("{invalid-json", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_public_state(path)

    def test_no_source_receives_auth_header(self):
        web = MemorySession({SRC.listing: Response(index_html((2000,"旧通知")))})
        notifier = Mock(channels=("serverchan",))
        with tempfile.TemporaryDirectory() as folder:
            run_public_poll(notifier, Path(folder)/"public_seen.json",
                            sources=(SRC,), session=web)
        for address, kwargs in web.requested:
            self.assertTrue(address.startswith("https://xsc.bupt.edu.cn/"))
            self.assertNotIn("Authorization", kwargs.get("headers", {}))


if __name__ == "__main__":
    unittest.main()
