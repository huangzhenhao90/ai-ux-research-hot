"""机械去重（计划 §5.2 第 3 条）。

只做机械判断，不调模型：
- 同 URL 合并在采集阶段就完成了（`id = sha1(规范化 URL)`）；
- 这里处理**标题近似**：`rapidfuzz` 相似度 ≥ 阈值且发布时间在 `windowHours` 内，视为重复。

保留哪一条：优先 T1 > T1_5 > T2，其次发布时间更早，最后 id 稳定排序。
被判定重复的条目状态置为 `DUPLICATE` 并记 `dupOf`，仍会进「全部动态」。
"""

from __future__ import annotations

from datetime import timedelta

from uxhot.models import Item, Status
from uxhot.pipeline.normalize import title_similarity

TIER_RANK = {"T1": 0, "T1_5": 1, "T2": 2, "EXCLUDE": 3}


def _sort_key(item: Item):
    """越小越优先保留。"""
    return (
        TIER_RANK.get(item.tier, 9),
        item.publishedAt or item.discoveredAt,
        item.id,
    )


def _within_window(a: Item, b: Item, window_hours: int) -> bool:
    ta = a.publishedAt or a.discoveredAt
    tb = b.publishedAt or b.discoveredAt
    return abs((ta - tb).total_seconds()) <= window_hours * 3600


def run(items: list[Item], *, threshold: int = 92, window_hours: int = 72) -> list[Item]:
    """就地标记重复条目，返回同一条列表。

    只对**还没被淘汰**的条目做比较（已 BLOCK/UNKNOWN 的不参与）。
    """
    pool = [
        item for item in items
        if item.status not in (Status.BLOCKED, Status.UNKNOWN)
    ]
    pool.sort(key=_sort_key)

    kept: list[Item] = []
    for item in pool:
        duplicate_of: Item | None = None
        for candidate in kept:
            if not _within_window(item, candidate, window_hours):
                continue
            if title_similarity(item.title, candidate.title) >= threshold:
                duplicate_of = candidate
                break

        if duplicate_of is None:
            kept.append(item)
        else:
            # 已经进入后续处理的结果保留，只标重复关系
            item.dupOf = duplicate_of.id
            if item.status in (Status.NEW, Status.PREFILTERED, Status.SCORED):
                item.status = Status.DUPLICATE
            item.errors.append(f"dedupe: 与 {duplicate_of.id} 标题近似，判为重复")

    return items


def summary(items: list[Item]) -> dict[str, int]:
    return {"duplicates": sum(1 for i in items if i.dupOf)}
