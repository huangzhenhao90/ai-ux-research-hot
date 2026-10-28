"""RSS 2.0 输出（计划 §5.3）。

手写 XML 而不是引第三方库：这里只需要一个频道加若干条目，标准库足够，
少一个依赖就少一份 Actions 安装与升级成本。

只有一个 feed：`rss.xml`，**每条精选一个 item**，订阅者按文章读。

时间一律 RFC 822（`email.utils.format_datetime`），且必须是 tz-aware——naive 时间
在 RFC 822 里没有偏移可写，宁可构建失败也不要发出一个时区不明的 pubDate。
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

from uxhot.config import ConfigBundle
from uxhot.models import Item
from uxhot.publish.build_site_data import (
    item_time,
    require_aware,
    sort_items,
    source_name_map,
)

RSS_FILE = "rss.xml"

# 精选 feed 的条目上限：RSS 阅读器不需要无限历史，产物也别无限膨胀
DEFAULT_ITEM_LIMIT = 50


def rfc822(dt: datetime) -> str:
    """RFC 822 时间戳（`Tue, 21 Oct 2026 01:00:00 GMT`）。

    `format_datetime(usegmt=True)` 要求 UTC，所以先转 UTC；naive 直接抛错。
    """
    if dt.tzinfo is None:
        raise ValueError("pubDate 必须带时区（RFC 822 需要明确偏移）")
    return format_datetime(dt.astimezone(timezone.utc), usegmt=True)


def _text(value: str | None) -> str:
    """元素文本转义。& < > 交给标准库，引号在文本节点里不需要转。"""
    return escape(value or "")


def _attr(value: str | None) -> str:
    """属性值转义：属性里引号必须转，否则能把 XML 撑破。"""
    return escape(value or "", {'"': "&quot;"})


def _item_xml(
    *,
    title: str,
    link: str,
    guid: str,
    pub_date: datetime,
    description: str,
    categories: Iterable[str] = (),
) -> list[str]:
    lines = [
        "    <item>",
        f"      <title>{_text(title)}</title>",
        f"      <link>{_text(link)}</link>",
        f'      <guid isPermaLink="true">{_text(guid)}</guid>',
        f"      <pubDate>{_text(rfc822(pub_date))}</pubDate>",
        f"      <description>{_text(description)}</description>",
    ]
    for category in categories:
        if category:
            lines.append(f"      <category>{_text(category)}</category>")
    lines.append("    </item>")
    return lines


def _channel_xml(
    *,
    title: str,
    link: str,
    description: str,
    language: str,
    self_url: str,
    last_build: datetime,
    item_lines: list[str],
) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "  <channel>",
        f"    <title>{_text(title)}</title>",
        f"    <link>{_text(link)}</link>",
        f"    <description>{_text(description)}</description>",
        f"    <language>{_text(language)}</language>",
        f"    <lastBuildDate>{_text(rfc822(last_build))}</lastBuildDate>",
        f'    <atom:link href="{_attr(self_url)}" rel="self" type="application/rss+xml"/>',
        "    <generator>URHOT publish/rss_out.py</generator>",
        *item_lines,
        "  </channel>",
        "</rss>",
        "",
    ]
    return "\n".join(lines)


def build_rss(
    config: ConfigBundle,
    items: Iterable[Item],
    *,
    now: datetime | None = None,
    limit: int = DEFAULT_ITEM_LIMIT,
) -> str:
    """精选 feed：每条精选一个 item，新的在前。

    只收 `selected`——RSS 是「值得看的」，全部动态留给站内页面。
    """
    site = config.site
    names = source_name_map(config)
    reference = require_aware(now or datetime.now(timezone.utc), what="now")

    selected = [i for i in items if i.is_public and i.is_selected]
    selected = sorted(sort_items(selected), key=lambda i: item_time(i), reverse=True)

    item_lines: list[str] = []
    for item in selected[:limit]:
        item_lines.extend(
            _item_xml(
                title=item.display_title or item.title or item.id,
                link=item.url,
                guid=item.url,
                pub_date=item_time(item),
                description=item.summaryZh or item.reason or item.titleZh or item.title or "",
                categories=[names.get(item.sourceId, item.sourceId), item.category or ""],
            )
        )

    return _channel_xml(
        title=f"{site.name} · {site.alias}",
        link=site.siteUrl,
        description=site.description,
        language=site.locale,
        self_url=f"{site.siteUrl.rstrip('/')}/{RSS_FILE}",
        last_build=reference,
        item_lines=item_lines,
    )


def write_rss_files(
    config: ConfigBundle,
    items: Iterable[Item],
    out_dir: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Path]:
    """把 feed 写进发布根目录（`web/public/`）。"""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows = list(items)
    files = {
        RSS_FILE: build_rss(config, rows, now=now),
    }
    paths: dict[str, Path] = {}
    for name, content in files.items():
        path = root / name
        path.write_text(content, encoding="utf-8")
        paths[name] = path
    return paths
