"""Zero-login public notice discovery; supplementary leads only.

This module never accesses the Second Classroom JWT, login pages, or private
student endpoints. Sources are allowlisted BUPT public notice listings.

The extracted leads NEVER assert check-in/checkout eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit

import requests


@dataclass(frozen=True)
class PublicSource:
    name: str
    listing: str
    article_section: str


SOURCES: tuple[PublicSource, ...] = (
    PublicSource("北邮学生处", "https://xsc.bupt.edu.cn/xgdt/tzgg.htm", "1022"),
    PublicSource("北邮后勤部", "https://hq.bupt.edu.cn/tzgg.htm", "1010"),
)

BEIJING = timezone(timedelta(hours=8))
LATEST_DAYS = 21

ACTIVITY_TERMS = (
    "活动", "招募", "志愿", "报名", "讲堂", "讲座", "征集", "比赛",
    "竞赛", "交流", "体验", "工作坊", "辅导", "实践", "赛事",
)
RELEVANCE_TERMS = ("沙河", "第二课堂", "二课", "两校区", "两院校区")
EXCLUDED_TERMS = (
    "体检", "疫苗", "门诊", "报销", "医疗", "补助", "摸排",
    "公示", "资助", "申请认定", "信息采集", "材料提交",
    "圆满举办", "圆满落幕", "成功举办", "结果公布", "采购",
)


class PublicFetchError(RuntimeError):
    """An error safe for logs; never includes arbitrary webpage text."""


@dataclass(frozen=True)
class Lead:
    source: str
    title: str
    url: str
    published: str
    reason: str


class HTMLIndex(HTMLParser):
    """Tiny stdlib parser: collects <a href> and text without JavaScript."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._anchor_text: list[str] = []
        self._text: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("style", "script", "noscript"):
            self._ignored += 1
        if tag == "a" and self._href is None and self._ignored == 0:
            self._href = dict(attrs).get("href")
            self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script", "noscript") and self._ignored:
            self._ignored -= 1
        if tag == "a" and self._href is not None:
            title = " ".join(" ".join(self._anchor_text).split())
            self.links.append((self._href, title))
            self._href = None
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._ignored:
            return
        if data.strip():
            self._text.append(data.strip())
            if self._href is not None:
                self._anchor_text.append(data.strip())

    @property
    def plain(self) -> str:
        return " ".join(self._text)


def _only_article_url(source: PublicSource, href: str) -> str | None:
    if not href or href.startswith(("#", "javascript:", "data:")):
        return None
    address = urljoin(source.listing, href)
    parts = urlsplit(address)
    origin = urlsplit(source.listing)
    if (
        parts.scheme != "https" or parts.hostname != origin.hostname
        or parts.username or parts.password or parts.query or parts.fragment
        or not re.fullmatch(rf"/info/{source.article_section}/[0-9]+\.htm", parts.path)
    ):
        return None
    return address


def parse_listing(source: PublicSource, html: str) -> dict[str, str]:
    page = HTMLIndex()
    page.feed(html)
    result: dict[str, str] = {}
    for href, label in page.links:
        address = _only_article_url(source, href)
        if not address:
            continue
        # List-page links sometimes include date and synopsis. Most reliable
        # title is the first part after any date prefix.
        title = re.sub(r"^\s*\d{1,2}\s+\d{4}[.\-/]\d{1,2}\s*", "", label)
        title = title.split("详情→", 1)[0].strip()
        title = title[:170]
        if title and address not in result:
            result[address] = title
    return result


def _get(session: requests.Session, address: str) -> str:
    try:
        resp = session.get(
            address, headers={"Accept": "text/html", "User-Agent": "BUPT-Public-Notice-Observer/0.1"},
            timeout=15, allow_redirects=False,
        )
        if resp.status_code != 200:
            raise PublicFetchError("Public notice source unavailable.")
        if "html" not in resp.headers.get("content-type", "").lower():
            raise PublicFetchError("Public notice source is not HTML.")
        if len(resp.content) > 2_000_000:
            raise PublicFetchError("Public notice page exceeded size limit.")
        # requests guesses ISO-8859-1 on legacy CMS without charset; use
        # apparent_encoding only for that documented fallback.
        if resp.encoding and resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding
        return resp.text
    except PublicFetchError:
        raise
    except (requests.RequestException, UnicodeError):
        raise PublicFetchError("Public notice GET failed.") from None


def discover(source: PublicSource, session: requests.Session) -> dict[str, str]:
    return parse_listing(source, _get(session, source.listing))


def _publication_date(html: str) -> date | None:
    # The official detail pages publish e.g. 发布日期：2026-09-18 or
    # 发布时间：2026-07-06. Require an explicit article date, not the
    # unrelated dates embedded in event schedules and page footers.
    parser = HTMLIndex()
    parser.feed(html)
    text = parser.plain
    pattern = r"(?:发布日期|发布时间|发表日期)[：:\s]{0,10}(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})"
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        return date(*(int(s) for s in match.groups()))
    except ValueError:
        return None


def _article_text(html: str) -> str:
    parser = HTMLIndex()
    parser.feed(html)
    return parser.plain


def eligible_lead(
    source: PublicSource,
    article_url: str,
    listing_title: str,
    html: str,
    *,
    today: date | None = None,
) -> Lead | None:
    """Conservative, non-authoritative public *lead* classifier."""
    if _only_article_url(source, article_url) != article_url:
        return None
    today = today or datetime.now(BEIJING).date()
    published = _publication_date(html)
    if published is None or not (today - timedelta(days=LATEST_DAYS) <= published <= today):
        return None
    title = listing_title[:170]
    if not any(word in title for word in ACTIVITY_TERMS):
        return None
    if any(word in title for word in EXCLUDED_TERMS):
        return None
    body = _article_text(html)
    # A reference in the title or official article must mention a relevant
    # campus or Second Classroom. NEVER claim exact signup requirements.
    reasons = [x for x in RELEVANCE_TERMS if x in title or x in body]
    if not reasons:
        return None
    return Lead(
        source=source.name, title=title, url=article_url,
        published=published.isoformat(),
        reason=" / ".join(reasons[:2]),
    )


def read_candidate(
    source: PublicSource,
    article_url: str,
    listing_title: str,
    session: requests.Session,
    *,
    today: date | None = None,
) -> Lead | None:
    if _only_article_url(source, article_url) != article_url:
        raise PublicFetchError("Rejected external public notice link.")
    return eligible_lead(
        source, article_url, listing_title, _get(session, article_url),
        today=today,
    )
