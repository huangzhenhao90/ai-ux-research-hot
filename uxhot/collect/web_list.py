"""网页列表采集（无 RSS 的信源）。

选择器来自 `config/sources.yaml` 的 `web_list` 字段，实测结果见 `eval/weblist-selectors.json`。

两个已知的坑（探测阶段踩过）：
- **链接可能带尾斜杠**（Maze 的 `/blog/xxx/`），写正则时不能要求以字母数字结尾；
- **item 本身可能就是那个 `<a>`**，此时 `linkSelector` 写成 `:scope`。
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser

from uxhot.collect.dates import DEFAULT_TZ, parse_date, resolve_published_at
from uxhot.collect.fetch import FetchResult, SourceState, extract_body, fetch
from uxhot.models import Item, Status, make_id
from uxhot.pipeline.normalize import canonicalize_url

# 明显不是文章详情页的路径片段
NON_ARTICLE_HINTS = (
    "/page/", "/category/", "/categories/", "/tag/", "/tags/", "/author/",
    "/authors/", "/about", "/contact", "/pricing", "/login", "/signup",
    "/events", "/webinars", "/podcast", "/privacy", "/terms", "/careers",
    "/people-nerds-categories/",
)


class WebListEntry:
    __slots__ = ("title", "url", "date_text", "published")

    def __init__(self, title: str, url: str, date_text: str | None, published: datetime | None):
        self.title = title
        self.url = url
        self.date_text = date_text
        self.published = published


def _is_article_link(url: str) -> bool:
    lowered = url.lower()
    return not any(hint in lowered for hint in NON_ARTICLE_HINTS)


def extract_entries(
    html: str,
    *,
    selectors: dict,
    base_url: str,
    source_tz: str | None = DEFAULT_TZ,
    now: datetime | None = None,
) -> list[WebListEntry]:
    """按选择器从列表页抽出条目。同 URL 去重（页面常有桌面/移动重复 DOM）。"""
    tree = LexborHTMLParser(html)
    item_selector = selectors["itemSelector"]
    title_selector = selectors.get("titleSelector")
    link_selector = selectors["linkSelector"]
    date_selector = selectors.get("dateSelector")

    entries: list[WebListEntry] = []
    seen: set[str] = set()

    for node in tree.css(item_selector):
        # linkSelector 为 :scope 表示 item 本身就是那个 <a>
        link_node = node if link_selector == ":scope" else node.css_first(link_selector)
        if link_node is None:
            continue
        href = link_node.attributes.get("href")
        if not href:
            continue

        url = urljoin(base_url, href)
        if url in seen or not _is_article_link(url):
            continue
        seen.add(url)

        title = ""
        if title_selector:
            title_node = node.css_first(title_selector)
            if title_node is not None:
                title = re.sub(r"\s+", " ", title_node.text(strip=True)).strip()
        if not title:
            title = re.sub(r"\s+", " ", link_node.text(strip=True)).strip()

        date_text = None
        if date_selector:
            date_node = node.css_first(date_selector)
            if date_node is not None:
                date_text = re.sub(r"\s+", " ", date_node.text(strip=True)).strip()

        published, _ = (
            resolve_published_at(date_text, source_tz, now=now) if date_text else (None, "no_date")
        )

        entries.append(WebListEntry(title=title, url=url, date_text=date_text, published=published))

    return entries


def fetch_entry_date(
    url: str, client, source_tz: str | None = DEFAULT_TZ, now: datetime | None = None
) -> datetime | None:
    """列表页没有日期时，抓正文页找日期。

    找 `<time datetime=...>` 或 `meta[property=article:published_time]`。
    """
    try:
        resp = client.get(url)
    except Exception:  # noqa: BLE001
        return None
    if resp.status_code != 200:
        return None

    html = resp.text
    patterns = (
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:published_time',
        r'<time[^>]+datetime=["\']([^"\']+)',
        r'"datePublished"\s*:\s*"([^"]+)"',
    )
    for pattern in patterns:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            published, _ = resolve_published_at(m.group(1), source_tz, now=now)
            if published is not None:
                return published
    return None


def build_items(
    entries: list[WebListEntry],
    *,
    source_id: str,
    source_name: str,
    tier: str,
    mode: str = "editorial",
    source_tz: str | None = DEFAULT_TZ,
    initial_backfill_limit: int = 8,
    fresh_hours: int = 48,
    first_import: bool = False,
    known_ids: set[str] | None = None,
    now: datetime | None = None,
) -> list[Item]:
    """把列表页条目转成 `Item`。状态规则与 RSS 采集一致。"""
    from uxhot.collect.dates import is_stale, now_utc

    reference = now or now_utc()
    known = known_ids or set()
    items: list[Item] = []
    seen: set[str] = set()

    candidates = entries[:initial_backfill_limit] if first_import else entries

    for entry in candidates:
        canonical = canonicalize_url(entry.url)
        if not canonical:
            continue
        item_id = make_id(canonical)
        if item_id in known or item_id in seen:
            continue
        seen.add(item_id)

        item = Item(
            id=item_id,
            sourceId=source_id,
            tier=tier,
            mode=mode,
            url=entry.url,
            canonicalUrl=canonical,
            title=entry.title,
            publishedAt=entry.published,
            discoveredAt=reference,
        )

        if entry.published is None:
            item.status = Status.UNKNOWN
            item.errors.append("列表页与正文页都没有可信日期")
        elif first_import:
            item.status = Status.ARCHIVED
            item.errors.append("首次导入的历史条目，已归档")
        elif is_stale(entry.published, fresh_hours, reference):
            item.status = Status.ARCHIVED
        else:
            item.status = Status.NEW

        items.append(item)

    return items
