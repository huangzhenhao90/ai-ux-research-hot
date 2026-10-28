"""进精选与人工覆盖（计划 §5.2 第 8–9 条）。

两步：
1. **同事件去重**：候选与最近 7 天精选里标题最相近的 ≤3 条比较（`rapidfuzz` 取候选，
   不引向量服务），用 `group-pair.md` 判断。`same` 且无新信息 → `DUPLICATE`，只进全部动态。
2. **人工覆盖**：`config/overrides.yaml` 可强制 select / reject / 改分类 / 置顶。
"""

from __future__ import annotations

from datetime import datetime, timezone

from uxhot.models import Item, Status
from uxhot.pipeline.common import StepContext
from uxhot.pipeline.normalize import canonicalize_url, title_similarity
from uxhot.pipeline.score import passes_threshold

# 与最近精选比较的候选条数上限（计划 §5.2 第 8 条：≤3 条）
COMPARE_TOP_N = 3

VALID_RELATIONS = {"same", "followup", "different"}


def run(
    items: list[Item],
    ctx: StepContext,
    *,
    recent_selected: list[Item] | None = None,
    now: datetime | None = None,
) -> list[Item]:
    recent = recent_selected or []
    stamp = now or datetime.now(timezone.utc)

    for item in items:
        if item.status is not Status.SCORED:
            continue
        if not passes_threshold(item, ctx):
            item.status = Status.LISTED
            continue

        relation, has_new_info, compared = _compare_with_recent(item, recent, ctx)
        item.relation = relation
        item.hasNewInfo = has_new_info

        if relation == "same" and has_new_info is False and compared is not None:
            # 同一次发生且没有新信息 → 不进精选
            item.status = Status.DUPLICATE
            item.dupOf = compared.id
            item.errors.append(f"group: 与精选 {compared.id} 同一次发生且无新信息")
        else:
            item.status = Status.SELECTED
            # 记下入选时刻，供日报按「入选时间」分期（不是发布时间）
            item.selectedAt = stamp

    _apply_overrides(items, ctx)
    return items


def _compare_with_recent(
    item: Item, recent: list[Item], ctx: StepContext
) -> tuple[str | None, bool | None, Item | None]:
    """与最相近的最近精选比较。没有可比对象就当作不同的事。"""
    if not recent:
        return None, None, None

    ranked = sorted(
        recent,
        key=lambda r: title_similarity(item.title, r.title),
        reverse=True,
    )[:COMPARE_TOP_N]

    for candidate in ranked:
        if canonicalize_url(candidate.url) == canonicalize_url(item.url):
            return "same", False, candidate

        result = ctx.call("group-pair", item, step="group")
        if result is None:
            # dry-run 或失败：不因为比较失败就拦下这条
            return None, None, None

        relation = str(result.get("relation", "")).strip().lower()
        if relation not in VALID_RELATIONS:
            item.errors.append(f"group: 非法 relation「{relation}」")
            return None, None, None

        has_new = result.get("hasNewInfo")
        has_new_bool = bool(has_new) if isinstance(has_new, bool) else None

        if relation == "different":
            continue

        item.errors.append(
            f"group: 与 {candidate.id} 关系 {relation}，hasNewInfo={has_new_bool}"
        )
        return relation, has_new_bool, candidate

    return "different", None, None


# ── 人工覆盖 ────────────────────────────────────────────────────────────


def _match_override(item: Item, entry: dict) -> bool:
    url = entry.get("url")
    prefix = entry.get("urlPrefix")
    if url and canonicalize_url(url) == canonicalize_url(item.url):
        return True
    if prefix and canonicalize_url(item.url).startswith(canonicalize_url(prefix)):
        return True
    return False


def _apply_overrides(items: list[Item], ctx: StepContext) -> None:
    ov = ctx.cfg.overrides
    if not (ov.select or ov.reject or ov.category):
        return

    for item in items:
        if item.status in (Status.BLOCKED, Status.UNKNOWN):
            continue

        for entry in ov.reject:
            if _match_override(item, entry):
                item.status = Status.LISTED
                item.errors.append(f"override: 人工剔除（{entry.get('note', '')}）")
                break

        for entry in ov.select:
            if _match_override(item, entry):
                item.status = Status.SELECTED
                item.errors.append(f"override: 人工入选（{entry.get('note', '')}）")
                break

        for entry in ov.category:
            if _match_override(item, entry):
                item.category = entry.get("category") or item.category
                item.errors.append(f"override: 人工改分类为 {item.category}")

def summary(items: list[Item]) -> dict[str, int]:
    return {
        "selected": sum(1 for i in items if i.status is Status.SELECTED),
        "listed": sum(1 for i in items if i.status is Status.LISTED),
        "duplicate": sum(1 for i in items if i.status is Status.DUPLICATE),
    }
