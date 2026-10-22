"""RSS / Atom 采集。

「旧文不刷屏」（计划 §5.2 第 2 条）：
- 新信源**首次导入**只取前 `initialBackfillLimit` 条，并全部标 `archived`；
- 之后只收首次导入之后新出现的条目；
- 发现时已发布超过 `freshHours` 的也标 `archived`（进全部动态，不进今天/日报）；
- 无可信日期的**不公开**，下次再试。
"""

from __future__ import annotations

from datetime import datetime

import feedparser

from uxhot.collect.dates import (
    is_future,
    DEFAULT_TZ,
    is_stale,
    now_utc,
    parse_feed_time,
    resolve_published_at,
)
from uxhot.models import Item, PrefilterResult, Status, make_id
from uxhot.pipeline.normalize import canonicalize_url

__all__ = ["parse_feed", "FeedEntry"]


class FeedEntry:
    """从 feed 里解析出来的一条原始条目。"""

    __slots__ = ("title", "link", "summary", "content", "author", "published", "date_issue")

    def __init__(self, title, link, summary, content, author, published, date_issue):
        self.title = title
        self.link = link
        self.summary = summary
        self.content = content
        self.author = author
        self.published = published
        self.date_issue = date_issue


def _clean_text(raw: str | None) -> str:
    """feed 里的 summary/content 常带 HTML，转成纯文本。"""
    if not raw:
        return ""
    from uxhot.collect.fetch import strip_html

    return strip_html(raw)


def parse_feed(raw_bytes: bytes, source_tz: str | None = DEFAULT_TZ,
               now: datetime | None = None) -> list[FeedEntry]:
    """解析 feed 内容成条目列表（不判断新旧，交给调用方）。"""
    parsed = feedparser.parse(raw_bytes)
    entries: list[FeedEntry] = []

    for entry in parsed.entries:
        link = entry.get("link") or ""
        if not link:
            continue

        # feedparser 已把 published/updated 归一到 UTC；优先 published
        published = parse_feed_time(entry.get("published_parsed"), source_tz)
        date_issue = None
        if published is None:
            published = parse_feed_time(entry.get("updated_parsed"), source_tz)
        if published is None:
            # 退回到原始字符串，按信源时区解析
            raw = entry.get("published") or entry.get("updated") or ""
            published, date_issue = resolve_published_at(raw, source_tz, now=now)
        elif is_future(published, now):
            # ⚠️ 走 published_parsed 的日期同样要挡未来日期（期刊提前标的期号），
            # 否则会被当成「刚发布」涌上首页。
            published, date_issue = None, "future_date"

        content = ""
        if entry.get("content"):
            content = " ".join(
                _clean_text(block.get("value")) for block in entry["content"]
            ).strip()
        if not content:
            content = _clean_text(entry.get("summary") or entry.get("description"))

        entries.append(
            FeedEntry(
                title=(entry.get("title") or "").strip(),
                link=link,
                summary=_clean_text(entry.get("summary") or entry.get("description")),
                content=content,
                author=(entry.get("author") or None),
                published=published,
                date_issue=date_issue,
            )
        )

    return entries


def build_items(
    entries: list[FeedEntry],
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
    since: datetime | None = None,
    now: datetime | None = None,
) -> list[Item]:
    """把 feed 条目转成 `Item`，并按「旧文不刷屏」定初始状态。

    Args:
        first_import: 该信源是否首次导入。首次导入只取前 N 条并全部归档。
        known_ids: 已存在的条目 id，用于跳过重复（省掉后续处理）。
        since: 只收**发布时间不早于**这一刻的条目。

            ⚠️ 这个参数不是可有可无的。`initial_backfill_limit` 只约束**首次导入**；
            之后的运行若不加时间下界，就会把整个 feed 重新灌一遍——实测某个
            「最新 8 条」的信源在第二次运行后变成 98 条，把 2017 年的旧文
            也拉进了「全部动态」。
    """
    reference = now or now_utc()
    known = known_ids or set()
    items: list[Item] = []
    seen: set[str] = set()

    candidates = entries[:initial_backfill_limit] if first_import else entries

    for entry in candidates:
        # 非首次导入时只收 since 之后的条目
        if since is not None and entry.published is not None and entry.published < since:
            continue

        canonical = canonicalize_url(entry.link)
        if not canonical:
            continue
        item_id = make_id(canonical)
        if item_id in known or item_id in seen:
            continue
        seen.add(item_id)

        body = entry.content or entry.summary
        item = Item(
            id=item_id,
            sourceId=source_id,
            tier=tier,
            mode=mode,
            url=entry.link,
            canonicalUrl=canonical,
            title=entry.title,
            author=entry.author,
            publishedAt=entry.published,
            discoveredAt=reference,
        )
        item.set_body(body)

        # ── 初始状态判定 ──────────────────────────────────────────────
        if entry.published is None:
            # 无可信日期 → 不公开，下次再试
            item.status = Status.UNKNOWN
            item.errors.append(f"无可信发布日期（{entry.date_issue or 'no_date'}）")
        elif first_import:
            # 首次导入的历史条目：全部归档，不进今天与日报
            item.status = Status.ARCHIVED
            item.errors.append("首次导入的历史条目，已归档")
        elif is_stale(entry.published, fresh_hours, reference):
            item.status = Status.ARCHIVED
        else:
            item.status = Status.NEW

        items.append(item)

    return items
