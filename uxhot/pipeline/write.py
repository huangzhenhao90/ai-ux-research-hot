"""写作（计划 §5.2 第 7 条）。

- 候选、或 `avgScore ≥ understandFloor` → `understand.md`（六字段：标题、摘要、推荐理由等）
- 其余 → `summarize-*.md`（便宜的标题摘要，进「全部动态」）

**防张冠李戴**：标题/摘要里出现的实体名必须在原文出现过；不过就重写一次，
仍不过就把那个名字去掉（不让模型凭空塞公司名）。
"""

from __future__ import annotations

import re

from uxhot.models import Item, Status
from uxhot.pipeline.common import StepContext, as_list
from uxhot.pipeline.score import passes_threshold

VALID_ITEM_TYPES = {
    "tool_launch", "method_or_template", "research_paper", "industry_event",
    "case_study", "opinion_analysis", "tutorial_explainer",
}
VALID_AUTHOR_ROLES = {"principal", "observer", "relayer"}


def should_write(item: Item) -> bool:
    if item.mode != "editorial":
        return False
    if item.tier == "EXCLUDE":
        return False
    return item.status in (Status.SCORED, Status.SELECTED, Status.LISTED) or bool(item.scores)


def uses_deep_write(item: Item, ctx: StepContext) -> bool:
    """够门槛的候选，或平均分高于 understandFloor 的，用精选写法。"""
    if passes_threshold(item, ctx):
        return True
    floor = ctx.cfg.selection.understandFloor
    return item.avgScore is not None and item.avgScore >= floor


# ── 行格式解析（summarize-*.md 输出 title_zh: / summary_zh:）──────────────


def parse_key_value(text: str, keys: tuple[str, ...]) -> dict[str, str]:
    """解析 `key: value` 形式的输出，支持值跨行到下一个 key 之前。"""
    pattern = re.compile(
        r"^\s*(" + "|".join(re.escape(k) for k in keys) + r")\s*[:：]\s*(.*)$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = (m.group(2) + "\n" + text[start:end]).strip()
        value = re.sub(r"\s*\n\s*", " ", value).strip()
        if value:
            out[m.group(1)] = value
    return out


# ── 实体校验（防张冠李戴）─────────────────────────────────────────────────


def entity_names(cfg, entity_ids: list[str]) -> list[tuple[str, str]]:
    """把 entity id 展开成 (id, 可匹配的名字) 列表。"""
    by_id = {e.id: e for e in cfg.taxonomy.entities}
    out: list[tuple[str, str]] = []
    for eid in entity_ids:
        entity = by_id.get(eid)
        if entity is None:
            continue
        for name in [entity.name, *entity.aliases]:
            if name and len(name) >= 2:
                out.append((eid, name))
    return out


def find_fabricated_entities(text: str, body: str, names: list[tuple[str, str]]) -> list[str]:
    """找出「出现在标题/摘要里、但原文没有」的实体名。"""
    if not text:
        return []
    body_lower = (body or "").lower()
    bad: list[str] = []
    for _eid, name in names:
        if name.lower() in text.lower() and name.lower() not in body_lower:
            if name not in bad:
                bad.append(name)
    return bad


def strip_entities(text: str, names: list[str]) -> str:
    """把编造的实体名从文案里去掉。"""
    out = text
    for name in names:
        out = re.sub(re.escape(name), "", out, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", out).strip(" ，,。；;、")


# ── 主流程 ────────────────────────────────────────────────────────────────


def run(items: list[Item], ctx: StepContext) -> list[Item]:
    for item in items:
        if not should_write(item):
            continue

        if uses_deep_write(item, ctx):
            _write_deep(item, ctx)
        else:
            _write_short(item, ctx)

        # 不管哪种写法，都做一次实体校验
        _verify_entities(item, ctx)

    return items


def _write_deep(item: Item, ctx: StepContext) -> None:
    result = ctx.call("understand", item, step="write")
    if result is None:
        return

    item_type = str(result.get("itemType", "")).strip()
    if item_type in VALID_ITEM_TYPES:
        item.itemType = item_type

    role = str(result.get("authorRole", "")).strip()
    if role in VALID_AUTHOR_ROLES:
        item.authorRole = role

    tags = as_list(result.get("tags"))
    if tags:
        from uxhot.pipeline.common import apply_tag_synonyms, keep_known_tags

        item.tags = keep_known_tags(apply_tag_synonyms(tags, ctx.cfg), ctx.cfg) or item.tags

    item.titleZh = (result.get("titleZh") or "").strip() or None
    item.summaryZh = (result.get("summaryZh") or "").strip() or None
    reason = (result.get("editorialJudgment") or "").strip()
    item.reason = reason or None


def _write_short(item: Item, ctx: StepContext) -> None:
    if not item.body.strip():
        item.titleZh = item.title
        item.summaryZh = ""
        return

    text = _call_text(ctx, "summarize-article", item, step="write")
    if text is None:
        return
    parsed = parse_key_value(text, ("title_zh", "summary_zh"))
    item.titleZh = parsed.get("title_zh") or item.title
    item.summaryZh = parsed.get("summary_zh") or ""


def _call_text(ctx: StepContext, prompt_name: str, item: Item, *, step: str) -> str | None:
    """走 StepContext 的预算与错误记录，但取纯文本输出。"""
    from uxhot.budget import BudgetExceeded
    from uxhot.llm import LLMError
    from uxhot.pipeline.common import material_block
    from uxhot.prompts import prompt_version, render

    if ctx.dry_run:
        ctx.plan_calls(1)
        return None
    if ctx.client is None:
        item.errors.append(f"{step}: 没有可用的 LLM 客户端")
        return None

    try:
        ctx.budget.charge(1)
    except BudgetExceeded as exc:
        item.errors.append(f"{step}: {exc}")
        return None

    prompt = render(prompt_name, ctx.variables) + material_block(item)
    item.promptVersions[step] = prompt_version(prompt_name, ctx.variables)
    try:
        return ctx.client.complete_text(prompt, step=step)
    except LLMError as exc:
        item.errors.append(f"{step}: {exc}")
        return None


def _verify_entities(item: Item, ctx: StepContext) -> None:
    """标题/摘要里的实体名必须在原文出现过；不过就重写一次，仍不过就删名。"""
    if not item.entities or not item.body:
        return

    names = entity_names(ctx.cfg, item.entities)
    if not names:
        return

    text = f"{item.titleZh or ''} {item.summaryZh or ''}"
    bad = find_fabricated_entities(text, item.body, names)
    if not bad:
        return

    item.errors.append(f"write: 标题/摘要出现原文没有的实体 {bad}，已重写一次")

    if uses_deep_write(item, ctx):
        _write_deep(item, ctx)
    else:
        _write_short(item, ctx)

    text = f"{item.titleZh or ''} {item.summaryZh or ''}"
    bad_again = find_fabricated_entities(text, item.body, names)
    if bad_again:
        item.errors.append(f"write: 重写后仍有 {bad_again}，已从文案中删除")
        item.titleZh = strip_entities(item.titleZh or "", bad_again) or item.title
        item.summaryZh = strip_entities(item.summaryZh or "", bad_again)


def summary(items: list[Item]) -> dict[str, int]:
    return {
        "written": sum(1 for i in items if i.titleZh),
        "deep": sum(1 for i in items if i.reason),
        "with_reason": sum(1 for i in items if i.reason),
    }
