"""模型步骤的公共部分：渲染提示词、检查预算、调用、记录错误与提示词版本。

所有会调模型的步骤（预筛 / 评分 / 结构化 / 写作 / 去重）都走这里，
保证预算熔断与审计只有一个实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from uxhot.budget import Budget, BudgetExceeded
from uxhot.config import ConfigBundle
from uxhot.llm import LLMClient, LLMError
from uxhot.models import Item
from uxhot.prompts import base_variables, prompt_version, render


def material_block(item: Item, *, include_tier: bool = False) -> str:
    """把一条资料拼成给模型的材料。

    提示词本身不含 title/body 占位符，材料统一追加在渲染结果之后。
    `include_tier` 默认 False：评分提示词明确要求不提供分级信息，避免按来源抬分。
    """
    parts = [f"\n\n---\n来源：{item.sourceId}\n标题：{item.title}\n"]
    if include_tier:
        parts.append(f"分级：{item.tier}\n")
    if item.publishedAt:
        parts.append(f"发布时间：{item.publishedAt.isoformat()}\n")
    if item.body:
        parts.append(f"正文：\n{item.body}\n")
    return "".join(parts)


@dataclass
class StepContext:
    """一次运行里所有模型步骤共用的上下文。"""

    cfg: ConfigBundle
    budget: Budget
    client: LLMClient | None = None
    dry_run: bool = True
    variables: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.variables:
            self.variables = base_variables(self.cfg)

    # ── 预算 ──────────────────────────────────────────────────────────

    @property
    def can_call(self) -> bool:
        return self.budget.can_call(1)

    def plan_calls(self, n: int) -> None:
        """dry-run 时累加「将会调用多少次」，不真的调。"""
        self.budget.run_calls += n

    # ── 调用 ──────────────────────────────────────────────────────────

    def call(
        self,
        prompt_name: str,
        item: Item,
        *,
        step: str,
        include_tier: bool = False,
        temperature: float | None = None,
    ) -> dict[str, Any] | None:
        """渲染 + 调用一步。返回 None 表示跳过（预算用尽 / 调用失败）。

        失败只记进 `item.errors`，不抛出——一条资料失败不该中断整次运行。
        """
        if self.dry_run:
            self.plan_calls(1)
            return None

        if self.client is None:
            item.errors.append(f"{step}: 没有可用的 LLM 客户端")
            return None

        try:
            self.budget.charge(1)
        except BudgetExceeded as exc:
            item.errors.append(f"{step}: {exc}")
            return None

        prompt = render(prompt_name, self.variables) + material_block(
            item, include_tier=include_tier
        )

        # 记下这一步用的是哪一版提示词（改了提示词只影响之后的新资料）
        item.promptVersions[step] = prompt_version(prompt_name, self.variables)

        try:
            return self.client.complete_json(prompt, step=step, temperature=temperature)
        except LLMError as exc:
            item.errors.append(f"{step}: {exc}")
            return None


# ── 小工具 ─────────────────────────────────────────────────────────────


def clamp_score(value: Any) -> int | None:
    """把模型返回的分数夹到 0–100 的整数。"""
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, score))


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def apply_tag_synonyms(tags: list[str], cfg: ConfigBundle) -> list[str]:
    """按 taxonomy 的同义词表归并标签，避免同一概念多种写法。"""
    lookup: dict[str, str] = {}
    for canonical, variants in cfg.taxonomy.tagSynonyms.items():
        lookup[canonical.lower()] = canonical
        for variant in variants:
            lookup[variant.lower()] = canonical

    out: list[str] = []
    for tag in tags:
        normalized = lookup.get(tag.lower(), tag)
        if normalized not in out:
            out.append(normalized)
    return out


def keep_known_tags(tags: list[str], cfg: ConfigBundle) -> list[str]:
    """丢掉白名单之外的标签（模型偶尔会造标签）。"""
    allowed = (
        set(cfg.taxonomy.categoryTags)
        | set(cfg.taxonomy.topicTags)
        | set(cfg.taxonomy.entityTags)
    )
    return [t for t in tags if t in allowed]
