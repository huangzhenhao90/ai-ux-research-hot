"""构造测试用的 Item。

时间都相对 `NOW`（北京 2026-10-21 11:00），这样「出刊日」「近 3 天窗口」可以断言成常量。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from uxhot.models import Item, Status, make_id

# 北京 11:00 → 出刊日 2026-10-21（08:00 出刊，11:00 已过线）
NOW = datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)
BJ = timezone(timedelta(hours=8))

# 这段文字代表「原文全文」，出现在任何产物里都算泄露
SECRET_BODY = "SECRET-BODY-原文全文不该出现在-web-public-里"

# 「没传这个参数」与「显式传 None」是两件事：前者用默认值，后者要真的清空字段。
# 缺了它就没法测「精选缺 titleZh」这类负例（传 None 会被默认值盖掉）。
_UNSET: Any = object()


# 每个 id 都从 URL 派生，保证和线上一致（id = sha1(规范化 URL) 前 16 位）
def url_of(idx: int) -> str:
    return f"https://example.com/post-{idx}"


def id_of(idx: int) -> str:
    return make_id(url_of(idx))


def make_item(
    idx: int,
    *,
    status: Status = Status.SELECTED,
    url: str | None = None,
    title: Any = _UNSET,
    titleZh: Any = _UNSET,
    summaryZh: Any = _UNSET,
    reason: Any = _UNSET,
    category: Any = _UNSET,
    tags: Any = _UNSET,
    entities: Any = _UNSET,
    itemType: Any = _UNSET,
    sourceId: str = "nngroup",
    tier: str = "T1",
    published: Any = _UNSET,
    discovered: Any = _UNSET,
    avgScore: Any = _UNSET,
    dupOf: str | None = None,
    relation: str | None = None,
    body: str = SECRET_BODY,
) -> Item:
    """造一条假资料。默认是「已精选、北京时间 10-21 上午发布」的形态。"""
    return Item(
        id=make_id(url or url_of(idx)),
        sourceId=sourceId,
        tier=tier,
        url=url or url_of(idx),
        title=f"English title {idx}" if title is _UNSET else title,
        titleZh=f"中文标题 {idx}" if titleZh is _UNSET else titleZh,
        summaryZh=(
            f"中文摘要 {idx}：一句话说清这条讲了什么。" if summaryZh is _UNSET else summaryZh
        ),
        reason=f"为什么值得看 {idx}" if reason is _UNSET else reason,
        category="tools" if category is _UNSET else category,
        tags=["工具发布", "AI 访谈"] if tags is _UNSET else tags,
        entities=["qualtrics"] if entities is _UNSET else entities,
        itemType="tool_launch" if itemType is _UNSET else itemType,
        publishedAt=NOW - timedelta(hours=2) if published is _UNSET else published,
        discoveredAt=NOW - timedelta(hours=1) if discovered is _UNSET else discovered,
        body=body,
        status=status,
        avgScore=80.0 if avgScore is _UNSET else avgScore,
        dupOf=dupOf,
        relation=relation,
    )


def sample_items() -> list[Item]:
    """一组覆盖各状态/各分类/各时间窗的假条目。

    时间线的设计意图：

    | 条目 | 北京时间 | 出刊日 | 说明 |
    |---|---|---|---|
    | 1 | 10-21 09:00 | 10-21 | 精选，进首页 |
    | 2 | 10-21 07:00 | **10-20** | 精选，卡在 08:00 边界之前，属于上一期 |
    | 3 | 10-19 13:00 | 10-19 | 精选，窗口最后一天 |
    | 4 | 10-17 13:00 | 10-17 | 只进全部动态，不进首页 |
    | 5 | — | — | BLOCKED，任何产物里都不该出现 |
    | 6 | — | — | UNKNOWN，任何产物里都不该出现 |
    | 7 | 10-21 10:00 | 10-21 | DUPLICATE，与 1 同事件，进「其他报道」 |
    | 8 | 10-21 08:00 | 10-21 | NEW，无可信发布时间，用发现时间归档 |
    """
    items = [
        # 1：精选头条。published 用 +08:00 输入，用来验证输出会被归一到 UTC
        make_item(
            1,
            published=datetime(2026, 10, 21, 9, 0, tzinfo=BJ),
            avgScore=88.0,
            tags=["工具发布", "AI 访谈"],
            entities=["qualtrics"],
        ),
        # 2：北京时间 07:00 发布 → 属于 10-20 那一期
        make_item(
            2,
            published=datetime(2026, 10, 20, 23, 0, tzinfo=timezone.utc),
            avgScore=80.0,
            category="methods",
            tags=["方法/实践", "合成用户"],
            entities=[],
            itemType="method_or_template",
        ),
        # 3：窗口最后一天
        make_item(
            3,
            published=datetime(2026, 10, 19, 5, 0, tzinfo=timezone.utc),
            avgScore=72.0,
            category="research",
            tags=["论文/研究"],
            entities=[],
            itemType="research_paper",
        ),
        # 4：四天前 → 在 all/ 里，但不在首页三天窗口
        make_item(
            4,
            published=datetime(2026, 10, 17, 5, 0, tzinfo=timezone.utc),
            status=Status.LISTED,
            avgScore=45.0,
            category="industry",
            tags=["行业动态"],
            entities=[],
            itemType="industry_event",
        ),
        # 5 / 6：不公开
        make_item(5, status=Status.BLOCKED, category=None, tags=[], avgScore=10.0),
        make_item(6, status=Status.UNKNOWN, category=None, tags=[], avgScore=None),
        # 7：与 1 同事件（dupOf 指向 1），进 1 的「其他报道」
        make_item(
            7,
            status=Status.DUPLICATE,
            published=datetime(2026, 10, 21, 2, 0, tzinfo=timezone.utc),
            sourceId="dovetail-blog",
            dupOf=id_of(1),
            relation="followup",
            avgScore=70.0,
        ),
        # 8：刚抓进来还没处理，没有发布时间 → 按发现时间归档
        make_item(
            8,
            status=Status.NEW,
            titleZh=None,
            summaryZh=None,
            reason=None,
            category=None,
            tags=[],
            entities=[],
            itemType=None,
            avgScore=None,
            published=None,
            discovered=datetime(2026, 10, 21, 0, 30, tzinfo=timezone.utc),
        ),
    ]
    return items
