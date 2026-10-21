"""预筛（计划 §5.2 第 4 条）。

BLOCK 不公开；UNKNOWN 等补材料，最多再试 1 次后丢弃；PASS 继续评分。
EXCLUDE 分级与 hot_signal / isolated 模式不参与预筛与评分。
"""

from __future__ import annotations

from uxhot.models import Item, PrefilterResult, Status
from uxhot.pipeline.common import StepContext

VALID_LABELS = {"PASS", "BLOCK", "UNKNOWN"}


def should_prefilter(item: Item) -> bool:
    """哪些条目需要预筛。"""
    if item.mode != "editorial":
        return False
    if item.tier == "EXCLUDE":
        return False
    return item.status in (Status.NEW,)


def run(items: list[Item], ctx: StepContext) -> list[Item]:
    """就地更新条目状态，返回处理过的条目。"""
    for item in items:
        if not should_prefilter(item):
            continue

        result = ctx.call("prefilter", item, step="prefilter")

        if result is None:
            # dry-run 或调用失败：保持原状，下次再试
            continue

        label = str(result.get("label", "")).strip().upper()
        reason = str(result.get("reason", "")).strip()[:60]

        if label not in VALID_LABELS:
            item.errors.append(f"prefilter: 返回了非法 label「{label}」")
            continue

        item.prefilter = PrefilterResult(label=label, reason=reason)

        if label == "PASS":
            item.status = Status.PREFILTERED
        elif label == "BLOCK":
            # 不公开
            item.status = Status.BLOCKED
        else:
            item.status = Status.UNKNOWN

    return items


def summary(items: list[Item]) -> dict[str, int]:
    counts = {"PASS": 0, "BLOCK": 0, "UNKNOWN": 0}
    for item in items:
        if item.prefilter is not None:
            counts[item.prefilter.label] = counts.get(item.prefilter.label, 0) + 1
    return counts
