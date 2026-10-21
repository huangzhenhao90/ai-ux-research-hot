"""结构化（计划 §5.2 第 6 条，与评分可并行）。

输出 `category / tags / subjects / scope / fact`。
主体（subjects）要落成 taxonomy 里的 entity id，白名单之外的丢掉。
"""

from __future__ import annotations

from uxhot.models import Item, Status
from uxhot.pipeline.common import (
    StepContext,
    apply_tag_synonyms,
    as_list,
    keep_known_tags,
)


def should_structure(item: Item) -> bool:
    if item.mode != "editorial":
        return False
    if item.tier == "EXCLUDE":
        return False
    # 预筛 PASS 之后就做，不必等评分（两者独立）
    return item.status in (Status.PREFILTERED, Status.SCORED) or bool(item.scores)


def run(items: list[Item], ctx: StepContext) -> list[Item]:
    valid_categories = set(ctx.cfg.taxonomy.category_keys)
    valid_entities = ctx.cfg.taxonomy.entity_ids

    for item in items:
        if not should_structure(item):
            continue

        result = ctx.call("structure", item, step="structure")
        if result is None:
            continue

        category = result.get("category")
        if category in valid_categories:
            item.category = category
        elif category is not None:
            item.errors.append(f"structure: 未知分类「{category}」，已丢弃")

        raw_tags = as_list(result.get("tags"))
        item.tags = keep_known_tags(apply_tag_synonyms(raw_tags, ctx.cfg), ctx.cfg)
        if len(raw_tags) != len(item.tags):
            dropped = [t for t in raw_tags if t not in item.tags]
            if dropped:
                item.errors.append(f"structure: 白名单外标签已丢弃 {dropped}")

        subjects = as_list(result.get("subjects"))
        item.entities = [s for s in subjects if s in valid_entities]

        scope = result.get("scope")
        item.scope = scope if scope in ("single", "composite", "unknown") else None

        fact = result.get("fact")
        item.fact = fact if isinstance(fact, dict) else None

    return items


def summary(items: list[Item]) -> dict[str, int]:
    return {
        "categorized": sum(1 for i in items if i.category),
        "with_entities": sum(1 for i in items if i.entities),
    }
