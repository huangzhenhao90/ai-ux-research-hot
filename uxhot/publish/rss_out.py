"""RSS 2.0 输出（计划 §5.3）。

手写 XML 而不是引第三方库：这里只需要一个频道加若干条目，标准库足够，
少一个依赖就少一份 Actions 安装与升级成本。

两个 feed 的分工：

- `rss.xml`：**每条精选一个 item**，订阅者按文章读；
- `rss-daily.xml`：**每期日报一个 item**，指向 `/daily/<date>/`，描述是当天精选的
  链接列表，订阅者按天读。

**已知局限（Lead 已知悉）**：`rss-daily.xml` 从 Item 推、不读 `data/reports/daily/`，
所以「空刊」（当天没有精选、日报只有一句「今日无重要更新」）不会出现在这个 feed 里；
需要空刊的订阅者请看日报页面本身。这么换的是：日报还没生成时 feed 也可用，
且分日口径与 `latest.json` 完全一致。

时间一律 RFC 822（`email.utils.format_datetime`），且必须是 tz-aware——naive 时间
在 RFC 822 里没有偏移可写，宁可构建失败也不要发出一个时区不明的 pubDate。
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

from uxhot.collect.dates import parse_tz
from uxhot.config import ConfigBundle
from uxhot.models import Item
from uxhot.publish.build_site_data import (
    edition_day,
    edition_hour,
    item_time,
    require_aware,
    sort_items,
    source_name_map,
)

RSS_FILE = "rss.xml"
RSS_DAILY_FILE = "rss-daily.xml"

# 精选 feed 的条目上限：RSS 阅读器不需要无限历史，产物也别无限膨胀
DEFAULT_ITEM_LIMIT = 50
# 日报 feed 的期数上限（约两个月）
DEFAULT_DAY_LIMIT = 60


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
        "    <generator>UXHOT publish/rss_out.py</generator>",
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


def build_rss_daily(
    config: ConfigBundle,
    items: Iterable[Item],
    *,
    now: datetime | None = None,
    limit: int = DEFAULT_DAY_LIMIT,
) -> str:
    """日报 feed：每期一个 item，按出刊日分组，新的在前。

    为什么从 Item 推而不是读 report 模块的日报 JSON：这个 feed 的形状只需要
    「哪天出了哪几条」，而报告 schema 归 `report/` 模块所有；从 Item 推可以
    在日报还没生成时也给出可用 feed，且分日口径与 `latest.json` 完全一致。
    """
    site = config.site
    names = source_name_map(config)
    reference = require_aware(now or datetime.now(timezone.utc), what="now")
    tz = parse_tz(site.timezone)
    hour = edition_hour(config)
    today = edition_day(reference, tz, hour)

    by_day: dict[str, list[Item]] = {}
    for item in items:
        if not (item.is_public and item.is_selected):
            continue
        day = edition_day(item_time(item), tz, hour)
        if day <= today:
            by_day.setdefault(day.isoformat(), []).append(item)

    item_lines: list[str] = []
    for day in sorted(by_day, reverse=True)[:limit]:
        rows = sort_items(by_day[day])
        url = f"{site.siteUrl.rstrip('/')}/daily/{day}/"
        # 出刊时刻 = 该日 08:00 本地时间（`day_bounds` 的起点）
        published = datetime.fromisoformat(f"{day}T{hour:02d}:00:00").replace(tzinfo=tz)
        rows_html = "".join(
            f'<li><a href="{_attr(i.url)}">{_text(i.display_title or i.title or i.id)}</a>'
            f"（{_text(names.get(i.sourceId, i.sourceId))}）</li>"
            for i in rows
        )
        item_lines.extend(
            _item_xml(
                title=f"{site.name} 日报 {day}｜{len(rows)} 条精选",
                link=url,
                guid=url,
                pub_date=published,
                description=f"<ul>{rows_html}</ul>",
                categories=[],
            )
        )

    return _channel_xml(
        title=f"{site.name} · {site.alias} 日报",
        link=f"{site.siteUrl.rstrip('/')}/daily/",
        description=f"{site.alias}的每日精选，{site.editions.get('daily', '08:00')} 后出刊。",
        language=site.locale,
        self_url=f"{site.siteUrl.rstrip('/')}/{RSS_DAILY_FILE}",
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
    """把两个 feed 写进发布根目录（`web/public/`）。"""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows = list(items)
    files = {
        RSS_FILE: build_rss(config, rows, now=now),
        RSS_DAILY_FILE: build_rss_daily(config, rows, now=now),
    }
    paths: dict[str, Path] = {}
    for name, content in files.items():
        path = root / name
        path.write_text(content, encoding="utf-8")
        paths[name] = path
    return paths
