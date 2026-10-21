"""评分（计划 §5.2 第 5 条）。

同一份评分标准**独立打两次**（两次调用不共享上下文），两次之和 ≥ 2×门槛 才成为候选。
门槛按信源分级不同（`config/selection.yaml` 的 `thresholds`）。

⚠️ 门槛数字**只在阶段 8 按用户标注的金标评测结果改**，不要在这里硬编码。
"""

from __future__ import annotations

from uxhot.models import Item, Status
from uxhot.pipeline.common import StepContext, clamp_score


def should_score(item: Item) -> bool:
    """哪些条目需要评分。

    只有预筛 PASS 的才评分；EXCLUDE 分级、hot_signal / isolated 模式不评分。
    """
    if item.mode != "editorial":
        return False
    if item.tier == "EXCLUDE":
        return False
    return item.status in (Status.PREFILTERED, Status.NEW)


def threshold_for(item: Item, ctx: StepContext) -> int | None:
    return ctx.cfg.selection.thresholds.get(item.tier)


def passes_threshold(item: Item, ctx: StepContext) -> bool:
    """两次之和 ≥ 2 × 门槛。"""
    threshold = threshold_for(item, ctx)
    if threshold is None or not item.scores:
        return False
    return sum(item.scores) >= 2 * threshold


def run(items: list[Item], ctx: StepContext) -> list[Item]:
    """对每个候选跑 `scoreAttempts` 次独立评分。"""
    attempts = ctx.cfg.selection.scoreAttempts

    for item in items:
        if not should_score(item):
            continue

        # dry-run：把「两次独立评分」如实算进预计调用数。
        # 不能靠调用返回 None 来 break，否则只会算成 1 次，低估预算。
        if ctx.dry_run:
            ctx.plan_calls(attempts)
            continue

        scores: list[int] = []
        for _ in range(attempts):
            result = ctx.call("selection-score", item, step="score")
            if result is None:
                # 预算用尽或调用失败：保留已拿到的分数，下次再补
                break
            score = clamp_score(result.get("attentionScore"))
            if score is None:
                item.errors.append("score: 返回里没有合法的 attentionScore")
                break
            scores.append(score)

        if not scores:
            continue

        item.scores = scores
        item.avgScore = sum(scores) / len(scores)

        # 只有拿到全部两次评分才判定，避免用一次分数就放行
        if len(scores) < attempts:
            continue

        item.status = Status.SCORED

    return items


def candidates(items: list[Item], ctx: StepContext) -> list[Item]:
    """过了门槛、可以进入写作与去重的条目。"""
    return [
        item for item in items
        if item.status is Status.SCORED and passes_threshold(item, ctx)
    ]


def summary(items: list[Item]) -> dict[str, int]:
    scored = [i for i in items if i.scores]
    return {
        "scored": len(scored),
        "two_attempts": sum(1 for i in scored if len(i.scores) >= 2),
    }
