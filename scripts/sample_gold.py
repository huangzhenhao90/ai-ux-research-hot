#!/usr/bin/env python3
"""阶段 8 金标抽样与标注表导出（计划 §阶段 8 第 1、2 步）。

做三件事，互相独立：

1. **抽样**（默认模式）：从已评分条目（`item.avgScore is not None`）里分层抽样，
   导出 `eval/gold_candidates.xlsx` 供用户标注。
2. **补抓正文**：`data/items` 里已处理条目的正文被 `strip_bodies` 清空了，
   而 `eval_selection.py` 重跑评分需要正文，所以按 URL 回原文页补抓（截断 8000 字），
   写进正文缓存。这是本脚本唯一会访问网络的地方，用 `--no-fetch` 关掉。
3. **转换**（`--convert`）：读回标注好的 xlsx，产出 `eval/gold.jsonl`。

⚠️ D11（用户明确选定）：**从零标注，执行模型不给任何建议**。因此导出的表里
**不得出现**「模型均分」「模型建议」「模型写的中文摘要（summaryZh / titleZh）」——
这些都会锚定标注。抽样逻辑内部**可以**用 `avgScore` 做分层（计划要求「门槛附近 ±10」），
只是不把它写进表里。

⚠️ 现实约束：仓库里已评分条目远少于目标 150 条，且多数历史条目没有 `category`。
所以本脚本的策略是：**约束尽量满足、缺口如实报告**，绝不静默少抽或重复凑数
（`report["gaps"]` / `report["notes"]` 会把「目标 vs 实际」的缺口逐条列出来，
`render_gap_report()` 负责打印成人能看的表）。

用法：

```bash
# 抽样 + 补抓正文 + 导出标注表
.venv/bin/python scripts/sample_gold.py

# 离线/测试：不抓正文
.venv/bin/python scripts/sample_gold.py --no-fetch

# 用户标完后转金标
.venv/bin/python scripts/sample_gold.py --convert
```
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

# 允许直接 `python scripts/sample_gold.py` 运行（与 scripts/ 下其他脚本一致）
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from openpyxl import Workbook, load_workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: E402

from uxhot.config import ConfigBundle, load_config  # noqa: E402
from uxhot.gold import (  # noqa: E402
    GoldCase,
    GoldLabel,
    GoldMaterial,
    SamplingContext,
    SourceFacts,
    assign_split,
    parse_decision,
    save_gold,
    summarize,
)
from uxhot.models import BODY_LIMIT, Item, load_items  # noqa: E402

# ── 默认值（计划 §阶段 8 第 1 步）──────────────────────────────────────

DEFAULT_TARGET = 150
DEFAULT_MIN_PER_CATEGORY = 15
DEFAULT_MIN_NEAR_THRESHOLD = 30
DEFAULT_NEAR_WINDOW = 10          # 门槛 ±10 算「贴着门槛」
DEFAULT_EXCERPT_CHARS = 500       # 标注表里正文摘录的长度

# 门槛的兜底值：只用于拿不到配置时（如单元测试直接调 sample_cases 又没传 thresholds）。
# 正常路径一律从 config/selection.yaml 读，避免这里的数字和配置漂移。
DEFAULT_THRESHOLDS: dict[str, int] = {"T1": 60, "T1_5": 65, "T2": 76}

# 标注表列顺序：**严格按 D11 之后的约定**，不要随意增删或调序。
COLUMNS: tuple[str, ...] = (
    "序号", "caseId", "原标题", "来源", "分级", "发布时间",
    "正文摘录", "原文链接", "该选吗", "备注",
)
DECISION_COLUMN = "该选吗"
DECISION_OPTIONS: tuple[str, ...] = ("select", "reject", "either")
SHEET_MAIN = "候选标注"
SHEET_GUIDE = "说明"

# ⚠️ D11：这些词一旦出现在表里就说明混进了执行模型的产出，会锚定标注。
# 测试会扫全表所有单元格，命中即失败。
FORBIDDEN_MARKERS: tuple[str, ...] = (
    "均分", "avgScore", "attentionScore", "模型建议", "建议选", "建议不选",
    "summaryZh", "titleZh", "推荐理由", "理由",
)

# 分层名的前缀。写成 `category:tools` 而不是 `tools`，是为了让
# `GoldCase.samplingContext.samplingStratum` 自带语义，报告里一眼看出是什么分层。
STRATUM_NEAR = "near-threshold"
STRATUM_CATEGORY = "category"
STRATUM_TIER = "tier"
STRATUM_OTHER = "other"


# ══ 分层抽样 ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class StratumTarget:
    """一个分层的「目标 vs 实际」。

    `met` 只看实际是否达到目标；达不到时汇总进 `report["gaps"]`，
    调用方**必须**把缺口打印出来（这是计划要求的「如实报告」）。
    """

    key: str
    target: int
    actual: int

    @property
    def met(self) -> bool:
        return self.actual >= self.target

    @property
    def gap(self) -> int:
        return max(0, self.target - self.actual)


@dataclass(frozen=True)
class SampleCase:
    """抽样结果的一条。携带抽样元信息，供导出与转金标共用。"""

    item: Item
    source_name: str
    case_id: str
    stratum: str
    distance: float | None       # |avgScore - 该 tier 门槛|，无门槛时为 None
    near_threshold: bool
    threshold: int | None
    note: str = ""               # 正文缺失等如实说明，写进标注表「备注」列
    # 补抓回来的正文（截断 8000 字）。**不能直接用 `item.body`**：
    # data/items 里已处理条目的正文被 strip_bodies 清空了。
    body: str = ""

    @property
    def display_body(self) -> str:
        """优先用补抓的正文，退回条目自带的（还没被清空的条目才有）。"""
        return self.body or self.item.body


@dataclass
class SamplePlan:
    """一次抽样的完整结果。`report` 给终端/JSON 用，`cases` 给导出用。"""

    cases: list[SampleCase]
    report: dict[str, Any]
    by_key: dict[str, StratumTarget] = field(default_factory=dict)


def _stratum_key(prefix: str, value: str) -> str:
    return f"{prefix}:{value}"


def allocate_quota(total: int, groups: Sequence[str], minimum: int) -> dict[str, int]:
    """把 `total` 个名额分给 `groups`，每个至少 `minimum`，余数按「最大余数法」分。

    为什么要用最大余数法而不是整除：目标 150 / 6 类 = 25，整除会剩 0；
    但 `--target 16` 时 16/6 = 2 余 4，需要把多出来的 4 个名额分出去，
    否则总和凑不满 target，最后只能靠「剩余填充」补，分层就不均衡了。
    """
    if not groups:
        return {}
    if total < minimum * len(groups):
        raise ValueError(
            f"名额不足：{len(groups)} 个分组各需 ≥{minimum}，共需 {minimum * len(groups)}，"
            f"但 target={total}"
        )
    base = minimum
    rest = total - base * len(groups)
    share, extra = divmod(rest, len(groups))
    quota = {g: base + share for g in groups}
    # 余数按固定顺序（groups 的顺序，即配置里的顺序）分，保证结果可复现
    for g in list(groups)[:extra]:
        quota[g] += 1
    return quota


def _distance(item: Item, thresholds: dict[str, int]) -> float | None:
    """条目均分到「它所在 tier 的门槛」的距离。tier 没有门槛时返回 None。

    ⚠️ 这个值只在脚本内部用于排序与分层，**绝不写进标注表**（D11）。
    """
    if item.avgScore is None:
        return None
    threshold = thresholds.get(item.tier)
    if threshold is None:
        return None
    return abs(float(item.avgScore) - float(threshold))


def _sort_key(item: Item, thresholds: dict[str, int]) -> tuple:
    """排序键：先按离门槛近（难例优先），再按 tier、均分、id 保证可复现。"""
    distance = _distance(item, thresholds)
    return (
        distance if distance is not None else float("inf"),
        item.tier,
        item.avgScore if item.avgScore is not None else -1.0,
        item.id,
    )


def sample_cases(
    items: Sequence[Item],
    *,
    thresholds: dict[str, int],
    categories: Sequence[str],
    target: int = DEFAULT_TARGET,
    min_per_category: int = DEFAULT_MIN_PER_CATEGORY,
    min_near_threshold: int = DEFAULT_MIN_NEAR_THRESHOLD,
    near_window: int = DEFAULT_NEAR_WINDOW,
) -> SamplePlan:
    """从已评分条目里分层抽样。

    约束（计划 §阶段 8 第 1 步）：

    - 6 个分类各 ≥`min_per_category`；
    - T1 与 T2 都要有；
    - 门槛附近（均分 ±`near_window`）≥`min_near_threshold`；
    - 难例优先：贴着门槛的比「一眼能判断」的优先。

    分配策略（**刻意做成优先级分配，而不是静默截断**）：

    1. 先按「门槛附近 → 分类 → tier」的优先级贪心填约束，每条候选去满足它
       能填的、优先级最高且还没满的那个约束；
    2. 约束都填满后，剩下的一律按「难例优先」补进来，直到 `target`；
    3. 最后**按优先级重新归属**每条的分层——一条候选可能同时满足「门槛附近」
       和某个分类，归属给优先级最高的那个，这样同一层不会既算 A 又算 B。

    达不到目标时**不报错、不重复凑数**：约束级别的缺口写进 `report["gaps"]`，
    候选池不够、分类缺条等写进 `report["notes"]`，由调用方打印出来。
    """
    if min_per_category * len(categories) > target:
        raise ValueError(
            f"--min-per-category={min_per_category} × {len(categories)} 个分类 "
            f"= {min_per_category * len(categories)}，已超过 --target={target}，"
            "无法同时满足；请调大 target 或调小 min-per-category"
        )

    scored = [item for item in items if item.avgScore is not None]
    ordered = sorted(scored, key=lambda i: _sort_key(i, thresholds))

    def is_near(item: Item) -> bool:
        distance = _distance(item, thresholds)
        return distance is not None and distance <= near_window

    # 门槛附近候选：只在「该 tier 有门槛」且距离 ≤ window 时算数
    near = [item for item in ordered if is_near(item)]

    category_quota = allocate_quota(target, list(categories), min_per_category)
    # tier 名额不设下限（计划只要求「T1 与 T2 都要有」），按候选池里实际出现的
    # tier 均分；某个 tier 只有 1 条也能拿到名额，从而满足「都要有」。
    tiers_present = sorted({item.tier for item in ordered})
    tier_quota = allocate_quota(target, tiers_present, 0) if tiers_present else {}

    # 约束：分层 key → 名额。tier 是兜底约束（名额只是「尽量」，不强制填满）。
    quota: dict[str, int] = {_stratum_key(STRATUM_NEAR, "all"): min_near_threshold}
    for key, count in category_quota.items():
        quota[_stratum_key(STRATUM_CATEGORY, key)] = count
    for key, count in tier_quota.items():
        quota[_stratum_key(STRATUM_TIER, key)] = count

    def constraints_of(item: Item) -> list[str]:
        """按优先级从高到低列出这条候选能填的约束 key。"""
        keys: list[str] = []
        if is_near(item):
            keys.append(_stratum_key(STRATUM_NEAR, "all"))
        if item.category in category_quota:
            keys.append(_stratum_key(STRATUM_CATEGORY, item.category))
        if item.tier in tier_quota:
            keys.append(_stratum_key(STRATUM_TIER, item.tier))
        return keys

    # ── 第 1 步：填约束（`target` 是硬上限，填满就不再往池子里加）──
    filled: dict[str, int] = Counter()
    selected_set: set[str] = set()
    for item in ordered:
        if len(selected_set) >= target:
            break
        for key in constraints_of(item):
            if filled[key] < quota.get(key, 0):
                filled[key] += 1
                selected_set.add(item.id)
                break

    # ── 第 2 步：难例优先补齐到 target ──
    for item in ordered:
        if len(selected_set) >= target:
            break
        selected_set.add(item.id)

    # ── 第 3 步：按优先级重新归属分层（一条候选只算进一层）──
    selected = [item for item in ordered if item.id in selected_set]
    stratum_of: dict[str, str] = {}
    for item in selected:
        keys = constraints_of(item)
        stratum_of[item.id] = keys[0] if keys else _stratum_key(STRATUM_OTHER, "unstratified")

    actual_counts = Counter(stratum_of.values())
    by_key: dict[str, StratumTarget] = {}
    for key, need in quota.items():
        by_key[key] = StratumTarget(key=key, target=need, actual=actual_counts.get(key, 0))
    if actual_counts.get(_stratum_key(STRATUM_OTHER, "unstratified")):
        by_key[_stratum_key(STRATUM_OTHER, "unstratified")] = StratumTarget(
            key=_stratum_key(STRATUM_OTHER, "unstratified"),
            target=0,
            actual=actual_counts[_stratum_key(STRATUM_OTHER, "unstratified")],
        )

    # 分层表回答「这一层抽了几条」；约束满足情况另算一份，因为
    # 「门槛附近 ≥30」问的是「抽到几条贴着门槛的」，而不是「有几条归到该层」。
    constraint_actuals: dict[str, int] = {
        _stratum_key(STRATUM_NEAR, "all"): sum(1 for i in selected if is_near(i)),
        **{
            _stratum_key(STRATUM_CATEGORY, key): sum(1 for i in selected if i.category == key)
            for key in category_quota
        },
        **{
            _stratum_key(STRATUM_TIER, key): sum(1 for i in selected if i.tier == key)
            for key in tier_quota
        },
    }

    by_tier = Counter(item.tier for item in selected)
    by_category = Counter(item.category or "（无分类）" for item in selected)
    tier_covered = {t: by_tier.get(t, 0) for t in ("T1", "T1_5", "T2") if by_tier.get(t)}

    report: dict[str, Any] = {
        "scoredPool": len(scored),
        "selected": len(selected),
        "target": target,
        "nearThresholdAvailable": len(near),
        "nearThresholdSelected": constraint_actuals[_stratum_key(STRATUM_NEAR, "all")],
        "tierCovered": tier_covered,
        "byTier": dict(by_tier),
        "byCategory": dict(by_category),
        "byStratum": dict(actual_counts),
        "byKey": {
            key: {"target": s.target, "actual": s.actual, "met": s.met, "gap": s.gap}
            for key, s in by_key.items()
        },
        "constraints": {
            key: {"target": quota.get(key, 0), "actual": actual}
            for key, actual in constraint_actuals.items()
        },
        "gaps": [
            {
                "key": key,
                "target": quota.get(key, 0),
                "actual": actual,
                "gap": max(0, quota.get(key, 0) - actual),
            }
            for key, actual in constraint_actuals.items()
            # tier 只是「尽量覆盖」（计划只要求 T1/T2 都要有，由 notes 单独检查），
            # 不列入缺口；门槛附近与各分类下限才是硬要求。
            if not key.startswith(f"{STRATUM_TIER}:") and actual < quota.get(key, 0)
        ],
        "notes": [],
    }
    report["unmetConstraints"] = len(report["gaps"])
    if len(selected) < target:
        report["notes"].append(
            f"已评分条目只有 {len(scored)} 条，抽不满 target={target}，"
            f"实际抽到 {len(selected)} 条"
        )
    if len(near) < min_near_threshold:
        report["notes"].append(
            f"门槛附近（±{near_window}）全库只有 {len(near)} 条，"
            f"达不到 min_near_threshold={min_near_threshold}"
        )
    missing_categories = [c for c in categories if by_category.get(c, 0) < min_per_category]
    if missing_categories:
        report["notes"].append(
            "这些分类不足 "
            f"{min_per_category} 条：{missing_categories}"
            "（历史条目多数没有 category，见 DECISIONS D11 与计划 §阶段 8）"
        )
    if "T1" not in tier_covered or "T2" not in tier_covered:
        report["notes"].append(
            f"T1/T2 未同时覆盖：{tier_covered or '（无）'}（候选池里可能本来就缺一个 tier）"
        )

    cases = [
        SampleCase(
            item=item,
            source_name="",           # 由调用方按 config 的 sources 填
            case_id="",               # 由调用方按顺序编号
            stratum=stratum_of[item.id],
            distance=_distance(item, thresholds),
            near_threshold=is_near(item),
            threshold=thresholds.get(item.tier),
        )
        for item in selected
    ]
    return SamplePlan(cases=cases, report=report, by_key=by_key)


def render_gap_report(report: dict[str, Any]) -> str:
    """把「目标 vs 实际」渲染成给人看的文本。缺口必须显式说出来。

    分两段：第一段是**约束**（计划明确要求的：门槛附近 ≥30、6 类各 ≥15），
    第二段是**分层归属**（每条候选只算进一层，用于 gold.jsonl 的 samplingStratum）。
    两者数字不同不是 bug——一条候选可以同时「贴着门槛」且属于某分类，
    约束段两边都算，分层段只归给优先级高的那层。
    """
    lines: list[str] = []
    lines.append("── 分层抽样结果：目标 vs 实际 ──")
    lines.append(
        f"已评分候选池 {report['scoredPool']} 条 → 实际抽出 {report['selected']} 条"
        f"（target={report['target']}）"
    )
    lines.append("约束满足情况（tier 行只是「尽量覆盖」，不算缺口）：")
    for key, info in report["constraints"].items():
        met = info["actual"] >= info["target"]
        best_effort = key.startswith(f"{STRATUM_TIER}:")
        if met:
            flag = "OK  "
        elif best_effort:
            flag = "尽量"
        else:
            flag = "缺口"
        suffix = "" if met or best_effort else f"  缺 {info['target'] - info['actual']}"
        lines.append(
            f"  [{flag}] {key:26} 目标 {info['target']:>3} / 实际 {info['actual']:>3}{suffix}"
        )
    lines.append("分层归属（每条只算一层）：")
    for key, info in report["byKey"].items():
        if info["target"] == 0 and info["actual"] == 0:
            continue
        lines.append(f"         {key:26} {info['actual']:>3} 条")
    lines.append(f"tier 覆盖：{report['tierCovered'] or '（无）'}")
    lines.append(f"分类分布：{report['byCategory']}")
    gaps = report["gaps"]
    if gaps:
        lines.append(f"⚠️ 有 {len(gaps)} 个约束没达到目标（如实报告，未静默凑数）：")
        for gap in gaps:
            lines.append(
                f"    - {gap['key']}：目标 {gap['target']}，实际 {gap['actual']}，缺 {gap['gap']}"
            )
    else:
        lines.append("✅ 所有约束均达到目标")
    for note in report["notes"]:
        lines.append(f"说明：{note}")
    return "\n".join(lines)


# ══ 条目读取与元信息 ═══════════════════════════════════════════════════


def load_items_path(path: Path) -> list[Item]:
    """`--items` 既可以是目录（读里面全部 `*.jsonl`），也可以是单个 jsonl 文件。"""
    if path.is_dir():
        items: list[Item] = []
        for file in sorted(path.glob("*.jsonl")):
            items.extend(load_items(file))
        return items
    return load_items(path)


def source_name_map(cfg: ConfigBundle) -> dict[str, str]:
    """`sourceId` → 信源名。标注表里给用户看的是名字而不是 id。"""
    return {source.id: source.name for source in cfg.sources.sources}


def source_kind_map(cfg: ConfigBundle) -> dict[str, str]:
    """`sourceId` → 采集方式，写进 `sourceFacts.sourceKind`。

    这里直接取配置里的 kind（rss / web_list / external_json），
    而不是猜——猜错了评测报告里的分组就不可信。
    """
    return {source.id: source.kind for source in cfg.sources.sources}


def make_case_id(index: int) -> str:
    """稳定编号：`uxhot-0001`。序号由抽样顺序（难例优先）决定，可复现。"""
    return f"uxhot-{index:04d}"


def build_sample_cases(
    items: Sequence[Item],
    *,
    thresholds: dict[str, int],
    categories: Sequence[str],
    source_names: dict[str, str],
    target: int = DEFAULT_TARGET,
    min_per_category: int = DEFAULT_MIN_PER_CATEGORY,
    min_near_threshold: int = DEFAULT_MIN_NEAR_THRESHOLD,
    near_window: int = DEFAULT_NEAR_WINDOW,
) -> SamplePlan:
    """`sample_cases` 之上补 caseId 与信源名（导出的两条信息来自配置，不属于抽样逻辑）。"""
    plan = sample_cases(
        items,
        thresholds=thresholds,
        categories=categories,
        target=target,
        min_per_category=min_per_category,
        min_near_threshold=min_near_threshold,
        near_window=near_window,
    )
    plan.cases = [
        SampleCase(
            item=case.item,
            source_name=source_names.get(case.item.sourceId, case.item.sourceId),
            case_id=make_case_id(index),
            stratum=case.stratum,
            distance=case.distance,
            near_threshold=case.near_threshold,
            threshold=case.threshold,
            note=case.note,
        )
        for index, case in enumerate(plan.cases, start=1)
    ]
    return plan


def excerpt(text: str, limit: int = DEFAULT_EXCERPT_CHARS) -> str:
    """正文摘录。**原文**截断，不做任何翻译或改写。"""
    text = (text or "").strip()
    return text[:limit]


# ══ 正文补抓 ═══════════════════════════════════════════════════════════


def load_body_cache(path: Path) -> dict[str, str]:
    """读正文缓存。缓存键是 `item.id`，值是已截断到 BODY_LIMIT 的正文。

    为什么要缓存：抽样（写标注表）和 `--convert`（写 gold.jsonl）是两次运行，
    没有缓存就得抓两遍；而且用户标注期间可能等好几天，缓存能让转换阶段完全离线。
    """
    cache: dict[str, str] = {}
    if not path.is_file():
        return cache
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        item_id = record.get("id")
        if item_id:
            cache[str(item_id)] = str(record.get("body") or "")
    return cache


def save_body_cache(cache: dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"id": item_id, "body": body}, ensure_ascii=False)
        for item_id, body in cache.items()
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def fetch_body_from_source(item: Item, sources_by_id: dict) -> str:
    """兜底：从信源自己的 RSS / 外部 JSON 里，按规范化 URL 找回这条的原文。

    为什么需要：`strip_bodies()` 会把已处理条目的正文清掉（为了让 `data/items`
    能安全提交进 public 仓库），所以补抓正文时只能去抓文章页。
    但 Medium、SAGE、Taylor & Francis 这类站点对非浏览器客户端一律 403 ——
    实测 curl 也拿不到。

    问题在于：**线上流水线当初是从 RSS 拿到正文的**，那些源并不封我们。
    所以只抓文章页会让这批样本在评测时缺材料，模型看到的信息比线上少，
    评出来的分数系统性地偏低，门槛就会被定歪。

    这里回到信源本身去捞，拿到的才是当初真正喂给模型的那份内容。
    """
    source = sources_by_id.get(item.sourceId)
    if source is None:
        return ""

    from uxhot.collect.dates import DEFAULT_TZ
    from uxhot.collect.fetch import build_client, strip_html
    from uxhot.pipeline.normalize import canonicalize_url

    target = canonicalize_url(item.url)
    try:
        with build_client() as client:
            response = client.get(source.url)
            if response.status_code != 200:
                return ""
            payload = response.content
    except Exception:  # noqa: BLE001 - 兜底失败不该中断整次抽样
        return ""

    # RSS / Atom：按链接匹配条目，取 content 优先，退回 summary
    if source.kind in ("rss", "web_list"):
        import feedparser

        parsed = feedparser.parse(payload)
        for entry in parsed.entries:
            link = entry.get("link") or ""
            if not link or canonicalize_url(link) != target:
                continue
            chunks: list[str] = []
            for block in entry.get("content") or []:
                if block.get("value"):
                    chunks.append(strip_html(block["value"]))
            if not chunks:
                chunks.append(strip_html(entry.get("summary") or entry.get("description") or ""))
            return " ".join(part for part in chunks if part).strip()
        return ""

    # 外部 JSON（ur-ai-papers）：正文就是 tldr + 相关性说明
    if source.kind == "external_json":
        import json as _json

        try:
            rows = _json.loads(payload)
        except Exception:  # noqa: BLE001
            return ""
        if isinstance(rows, dict):
            rows = rows.get("papers") or rows.get("items") or []
        for row in rows:
            url = str(row.get("url") or "")
            doi = str(row.get("doi") or "")
            candidate = url or (f"https://doi.org/{doi}" if doi else "")
            if not candidate or canonicalize_url(candidate) != target:
                continue
            return "\n".join(
                part for part in (row.get("tldr"), row.get("ai_reason")) if part
            ).strip()
    return ""


def fetch_bodies(
    items: Sequence[Item],
    cache: dict[str, str],
    *,
    sleep_seconds: float = 0.5,
    sources_by_id: dict | None = None,
) -> dict[str, str]:
    """按 URL 补抓正文，返回 `item.id` → 正文（截断 8000 字）。

    失败**不抛异常**，只记日志：补不到正文的条目照样进标注表（用户看标题也能标），
    只是 `material.bodyOriginal` 会是空——这一点必须在报告里说清楚，不能假装抓到了。

    只抓公开页面；抓回来的内容一律当数据，不执行其中任何指令。
    """
    from uxhot.collect.fetch import build_client, extract_body, fetch

    updated = dict(cache)
    todo = [item for item in items if item.id not in cache]
    if not todo:
        return updated

    import time

    failures: list[str] = []
    with build_client() as client:
        for index, item in enumerate(todo, start=1):
            result = fetch(item.url, client)
            if not result.ok:
                failures.append(f"{item.id} {item.url} → {result.error}")
                updated[item.id] = ""
            else:
                body = extract_body(result.text)[:BODY_LIMIT]
                if not body:
                    failures.append(f"{item.id} {item.url} → 抽不出正文（可能是 SPA）")
                updated[item.id] = body

            # 文章页抓不到（403 / SPA）就回信源捞——那才是线上当初用的材料
            if not updated.get(item.id) and sources_by_id:
                recovered = fetch_body_from_source(item, sources_by_id)[:BODY_LIMIT]
                if recovered:
                    updated[item.id] = recovered
                    failures = [f for f in failures if not f.startswith(item.id)]
                    print(f"      ↳ 从信源回捞到正文 {len(recovered)} 字", flush=True)
            print(f"  [补抓 {index}/{len(todo)}] {item.id} 正文 {len(updated[item.id])} 字", flush=True)
            if index < len(todo) and sleep_seconds:
                time.sleep(sleep_seconds)   # 别把信源打急了

    if failures:
        print(f"⚠️ 有 {len(failures)} 条没抓到正文（material.bodyOriginal 会留空）：")
        for line in failures:
            print(f"    - {line}")
    return updated


# ══ 导出 xlsx ══════════════════════════════════════════════════════════

GUIDE_LINES: tuple[str, ...] = (
    "这个表是干什么的",
    "  阶段 8 金标标注表。你要对每一条候选自己判断「这条该不该进精选」，",
    "  为后面的提示词校准和门槛制定提供人类金标。",
    "  ⚠️ 表里刻意不含任何模型产出（没有均分、没有建议、没有模型写的中文摘要），",
    "     就是为了不锚定你的判断（D11）。抽样时用均分做的分层不写进表里。",
    "",
    "「该选吗」三个选项的含义",
    "  select  该选：这条值得进精选。读者会因此多知道一件有用的事。",
    "  reject  不该选：噪声、软文、无新事实、与研究/洞察工作无实质关系。",
    "  either  两可：选或不选都说得过去，你自己也拿不准。",
    "          ⚠️ either 不计入任何质量指标的分母，但会如实记进 gold.jsonl。",
    "",
    "怎么算标完",
    "  在「该选吗」列给每条选一个值（真实下拉，不是文字提示）。",
    "  留空 = 还没标，转换时会被跳过并单独报告，不会被当成 either。",
    "  「备注」列留给你自己写理由，脚本不读这一列。",
    "  判断标准只看：如果这条进了精选，读者（用户研究员 / 市场与消费者洞察从业者 /",
    "  自己做研究的产品经理与设计师）会不会觉得有用。",
    "",
    "标注完运行哪条命令",
    "  .venv/bin/python scripts/sample_gold.py --convert",
    "  它会读回本表，生成 eval/gold.jsonl（按 caseId 稳定哈希 2:1 分",
    "  development / holdout），并打印各 decision / split / tier / stratum 分布与 selectRate。",
    "",
    "其他",
    "  正文摘录是原文前 500 字（英文就是英文），完整正文（最多 8000 字）在转换时写入",
    "  material.bodyOriginal。留空表示没抓到，备注列会说明。",
    "  默认路径：--items data/items --out eval/gold_candidates.xlsx --gold eval/gold.jsonl",
)

HEADER_FILL = PatternFill("solid", fgColor="DDEBF7")
COLUMN_WIDTHS: dict[str, int] = {
    "序号": 6, "caseId": 12, "原标题": 46, "来源": 22, "分级": 8,
    "发布时间": 22, "正文摘录": 60, "原文链接": 48, "该选吗": 12, "备注": 26,
}


def _safe_cell(value: Any) -> Any:
    """防 Excel 把文本当公式。抓来的标题理论上可能以 = 开头。"""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def write_candidates_xlsx(cases: Sequence[SampleCase], out: Path) -> Path:
    """写 `eval/gold_candidates.xlsx`：候选标注表 + 说明 sheet。

    ⚠️ `该选吗` 列**全部留空**——预填 `either` 会让用户以为已经标完了。
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_MAIN

    sheet.append(list(COLUMNS))
    for index, case in enumerate(cases, start=1):
        item = case.item
        sheet.append(
            [
                index,
                case.case_id,
                _safe_cell(item.title),
                _safe_cell(case.source_name),
                item.tier,
                item.publishedAt.isoformat() if item.publishedAt else "",
                _safe_cell(excerpt(case.display_body)),
                _safe_cell(item.url),
                "",                       # 该选吗：留给用户，绝不预填
                _safe_cell(case.note),
            ]
        )

    # 表头：加粗 + 底色 + 冻结首行
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
    sheet.freeze_panes = "A2"

    # 列宽（列宽不匹配的列保持默认）
    for column_index, name in enumerate(COLUMNS, start=1):
        width = COLUMN_WIDTHS.get(name)
        if width:
            letter = sheet.cell(row=1, column=column_index).column_letter
            sheet.column_dimensions[letter].width = width

    # 正文摘录自动换行
    excerpt_index = COLUMNS.index("正文摘录") + 1
    for row in range(2, len(cases) + 2):
        sheet.cell(row=row, column=excerpt_index).alignment = Alignment(
            wrap_text=True, vertical="top"
        )

    # 真实下拉（openpyxl DataValidation 会写进 xlsx 的 dataValidation 节点，
    # Excel / Numbers / WPS 打开都是可点的下拉，不是文字提示）
    decision_index = COLUMNS.index(DECISION_COLUMN) + 1
    decision_letter = sheet.cell(row=1, column=decision_index).column_letter
    validation = DataValidation(
        type="list",
        formula1='"' + ",".join(DECISION_OPTIONS) + '"',
        allow_blank=True,
        showDropDown=False,      # ⚠️ openpyxl 语义与直觉相反：False 才是「显示下拉箭头」
    )
    validation.error = "只能填 select / reject / either，或留空表示还没标"
    validation.errorTitle = "取值不合法"
    validation.prompt = "选 select / reject / either；留空表示还没标"
    validation.promptTitle = "该选吗"
    validation.showErrorMessage = True
    sheet.add_data_validation(validation)
    if cases:
        validation.add(f"{decision_letter}2:{decision_letter}{len(cases) + 1}")

    # 说明 sheet
    guide = workbook.create_sheet(SHEET_GUIDE)
    guide.column_dimensions["A"].width = 100
    guide["A1"] = "金标候选标注表 · 说明"
    guide["A1"].font = Font(bold=True, size=14)
    for offset, line in enumerate(GUIDE_LINES, start=3):
        guide.cell(row=offset, column=1, value=line)
    guide["A2"] = f"生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}"

    out.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(out)

    # 分层写到 **sidecar 文件**，不写进 xlsx。
    #
    # 分层值是从模型均分推出来的（`near-threshold:all` 就等于告诉标注的人
    # 「这条贴着门槛」）。放进标注表里，即使只在说明页，也是把模型判断泄漏
    # 给了正在标注的人 —— D11 要的是「从零标注、不给任何建议」。
    # 所以它只活在旁路文件里：--convert 读它，标注的人看不到它。
    strata_path = stratum_sidecar(out)
    strata_path.parent.mkdir(parents=True, exist_ok=True)
    strata_path.write_text(
        json.dumps({case.case_id: case.stratum for case in cases},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def read_candidates_xlsx(path: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    """读回标注表，返回 (数据行, caseId → samplingStratum)。

    按表头名取列，避免列顺序变化时静默读错。第二个返回值来自「说明」sheet 里的
    隐藏映射：`该选吗` 旁边不能加「分层」列（列顺序是约定死的，而且分层里带
    `near-threshold` 会暗示这条贴着门槛），但 `gold.jsonl` 的
    `samplingContext.samplingStratum` 又该有值，所以挪到说明页的机器可读区。
    """
    if not path.is_file():
        raise FileNotFoundError(f"标注表不存在：{path}（先跑一次不带 --convert 的抽样导出）")
    workbook = load_workbook(path, data_only=True)
    if SHEET_MAIN not in workbook.sheetnames:
        raise ValueError(f"{path} 里没有「{SHEET_MAIN}」sheet，实际有：{workbook.sheetnames}")
    sheet = workbook[SHEET_MAIN]

    header = [str(cell.value).strip() if cell.value is not None else "" for cell in sheet[1]]
    missing = [name for name in COLUMNS if name not in header]
    if missing:
        raise ValueError(f"{path} 缺少列：{missing}（实际表头：{header}）")
    index_of = {name: header.index(name) for name in COLUMNS}

    rows: list[dict[str, str]] = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if row is None or all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        def cell(name: str) -> str:
            position = index_of[name]
            value = row[position] if position < len(row) else None
            return "" if value is None else str(value).strip()

        rows.append({name: cell(name) for name in COLUMNS})

    return rows, _read_stratum_map(path)


def stratum_sidecar(xlsx_path: Path) -> Path:
    """分层旁路文件的路径（与标注表同目录，名字挂在它后面）。

    不放 `eval/cache/` 是为了让「删掉标注表重来」时旁路文件也跟着一起明确处理，
    而不是散在两个目录里。
    """
    return xlsx_path.with_suffix(xlsx_path.suffix + ".strata.json")


def _read_stratum_map(xlsx_path: Path) -> dict[str, str]:
    """从 sidecar 读 `caseId → 分层`。

    分层**刻意不写进 xlsx**：它由模型均分推出（`near-threshold:all` 等于暗示
    「这条贴着门槛」），出现在标注表里就是把模型判断泄漏给标注的人，违反 D11。
    """
    path = stratum_sidecar(xlsx_path)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 旁路文件坏了不该让转换失败
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


# ══ 转换：xlsx → eval/gold.jsonl ═══════════════════════════════════════


def build_gold_cases(
    rows: Sequence[dict[str, str]],
    *,
    bodies: dict[str, str] | None = None,
    case_ids: dict[str, str] | None = None,
    source_kinds: dict[str, str] | None = None,
    name_to_source_id: dict[str, str] | None = None,
    strata: dict[str, str] | None = None,
) -> tuple[list[GoldCase], dict[str, Any]]:
    """把标注行转成 `GoldCase`。

    - `该选吗` 留空的**跳过**（不是 either），并统计跳过了多少；
    - `benchmarkSplit` 用 `assign_split(caseId)`（2:1，稳定哈希）；
    - `sourceFacts.firstParty`：tier == "T1" 时 true；
    - `sourceFacts.language`：正文看着像中文用 zh，否则 en。

    `case_ids` 是 caseId → `item.id`（用来从正文缓存里取正文）。
    `source_kinds` 是 `sourceId` → kind，能拿到就用配置里的真值。
    `strata` 是 caseId → 分层，来自标注表「说明」sheet 的机器可读区。
    正文拿不到就留空——这时必须如实报告，不能假装有正文。
    """
    bodies = bodies or {}
    source_kinds = source_kinds or {}
    item_id_by_case = case_ids or {}
    strata = strata or {}

    cases: list[GoldCase] = []
    skipped: list[str] = []
    unknown: list[dict[str, str]] = []
    body_missing: list[str] = []

    for row in rows:
        case_id = row.get("caseId", "").strip()
        raw_decision = row.get(DECISION_COLUMN, "")
        decision = parse_decision(raw_decision)
        if decision is None:
            # 留空（或写了脚本不认识的值）都算「还没标」——按计划要求跳过，不当 either
            skipped.append(case_id or "（无 caseId）")
            if raw_decision.strip():
                unknown.append({"caseId": case_id, "value": raw_decision})
            continue

        tier = row.get("分级", "").strip()
        # 表里没有 sourceId 列（列顺序是约定死的），只能按信源名反查 kind；
        # 反查不到就退回 "rss"——`sourceKind` 只影响评测报告的分组，不影响金标判定。
        source_id = (name_to_source_id or {}).get(row.get("来源", "").strip(), "")
        item_id = item_id_by_case.get(case_id, "")
        body = bodies.get(item_id, "") if item_id else ""
        if not body:
            # 只对**真的要写进金标**的条目报警：正文缺失会让 eval_selection.py 缺材料。
            # 被跳过的条目缺不缺正文无所谓，所以这里只统计要写进金标的那些。
            body_missing.append(case_id)

        published = row.get("发布时间", "").strip() or None
        cases.append(
            GoldCase(
                caseId=case_id,
                material=GoldMaterial(
                    title=row.get("原标题", "").strip(),
                    originalTitle=None,          # 原标题就是原文标题，没有单独的中文标题
                    publishedAt=published,
                    sourceName=row.get("来源", "").strip(),
                    bodyZh=None,
                    bodyOriginal=body or None,
                ),
                sourceFacts=SourceFacts(
                    sourceKind=source_kinds.get(source_id, "rss"),
                    sourceTier=tier,
                    firstParty=tier == "T1",
                    language="zh" if _looks_zh(body) else "en",
                ),
                samplingContext=SamplingContext(
                    benchmarkSplit=assign_split(case_id),
                    # 分层值藏在说明页的机器可读区，不在主表露脸——
                    # `near-threshold:*` 出现在用户眼前就等于暗示「这条贴着门槛」。
                    samplingStratum=strata.get(case_id) or None,
                ),
                gold=GoldLabel(decision=decision),
            )
        )

    report: dict[str, Any] = {
        "rows": len(rows),
        "converted": len(cases),
        "skipped": len(skipped),
        "skippedCaseIds": skipped,
        "unknownValues": unknown,
        "bodyMissing": body_missing,
    }
    return cases, report


def _looks_zh(text: str) -> bool:
    """粗略判断正文是不是中文：CJK 字符占比够高就算。

    为什么不用 `Item.lang`：历史条目 lang 多为空，转换阶段又只读得到 xlsx，
    所以只能看正文本身。宁可粗一点，也不要凭空断言语言。
    """
    if not text:
        return False
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    return cjk / max(1, len(text)) > 0.05


def convert_xlsx_to_gold(
    xlsx_path: Path,
    gold_path: Path,
    *,
    bodies: dict[str, str] | None = None,
    case_ids: dict[str, str] | None = None,
    source_kinds: dict[str, str] | None = None,
    name_to_source_id: dict[str, str] | None = None,
    strata: dict[str, str] | None = None,
) -> tuple[list[GoldCase], dict[str, Any]]:
    rows, sheet_strata = read_candidates_xlsx(xlsx_path)
    cases, report = build_gold_cases(
        rows,
        bodies=bodies,
        case_ids=case_ids,
        source_kinds=source_kinds,
        name_to_source_id=name_to_source_id,
        # 优先用调用方显式给的（测试用），否则用表里「说明」sheet 的机器可读区
        strata=strata if strata is not None else sheet_strata,
    )
    if not cases:
        raise ValueError(
            "没有任何一行填了「该选吗」，没有可写的金标。"
            f"（共读到 {len(rows)} 行，全部留空）"
        )
    save_gold(cases, gold_path)
    report["goldPath"] = str(gold_path)
    report["summary"] = summarize(cases)
    return cases, report


def render_convert_report(report: dict[str, Any]) -> str:
    lines: list[str] = [
        "── 转换结果 ──",
        f"读回 {report['rows']} 行，写出 {report['converted']} 条金标 → {report['goldPath']}",
        f"跳过（该选吗 留空）{report['skipped']} 条：{report['skippedCaseIds']}",
    ]
    if report["unknownValues"]:
        lines.append(f"⚠️ 有 {len(report['unknownValues'])} 行写了无法识别的值（已按未标注跳过）：")
        for entry in report["unknownValues"]:
            lines.append(f"    - {entry['caseId']}：{entry['value']!r}")
    if report["bodyMissing"]:
        lines.append(
            f"⚠️ 有 {len(report['bodyMissing'])} 条没拿到正文"
            f"（material.bodyOriginal 为空，eval_selection.py 重跑评分会缺材料）："
            f"{report['bodyMissing']}"
        )
    lines.append("")
    summary = report["summary"]
    lines.append("── 金标概览 summarize() ──")
    lines.append(f"总数 {summary['total']}，计入分母 {summary['scored']}，either {summary['either']}")
    lines.append(f"selectRate（不含 either）= {summary['selectRate']}")
    lines.append(f"decision 分布：{summary['byDecision']}")
    lines.append(f"split 分布：{summary['bySplit']}")
    lines.append(f"tier 分布：{summary['byTier']}")
    lines.append(f"stratum 分布：{summary['byStratum']}")
    return "\n".join(lines)


# ══ 主流程 ═════════════════════════════════════════════════════════════


def export_candidates(
    *,
    items_path: Path,
    out_path: Path,
    body_cache_path: Path,
    cfg: ConfigBundle,
    target: int = DEFAULT_TARGET,
    min_per_category: int = DEFAULT_MIN_PER_CATEGORY,
    min_near_threshold: int = DEFAULT_MIN_NEAR_THRESHOLD,
    near_window: int = DEFAULT_NEAR_WINDOW,
    no_fetch: bool = False,
    fetch_sleep: float = 0.5,
    report_path: Path | None = None,
) -> SamplePlan:
    """默认模式：读条目 → 分层抽样 → 补抓正文 → 写标注表。"""
    items = load_items_path(items_path)
    if not items:
        raise SystemExit(f"没读到任何条目：{items_path}")

    thresholds = dict(cfg.selection.thresholds)
    categories = cfg.taxonomy.category_keys
    plan = build_sample_cases(
        items,
        thresholds=thresholds,
        categories=categories,
        source_names=source_name_map(cfg),
        target=target,
        min_per_category=min_per_category,
        min_near_threshold=min_near_threshold,
        near_window=near_window,
    )

    print(render_gap_report(plan.report))
    if not plan.cases:
        raise SystemExit("没有可抽的已评分条目（item.avgScore is not None），无法导出标注表")

    # ── 正文：先读缓存，缓存没有再按 URL 补抓 ──
    cache = load_body_cache(body_cache_path)
    if no_fetch:
        print(f"（--no-fetch：跳过补抓正文，直接用缓存 {len(cache)} 条）")
    else:
        print(f"开始补抓正文（{len(plan.cases)} 条候选，已缓存 {len(cache)} 条）……")
        cache = fetch_bodies(
            [case.item for case in plan.cases],
            cache,
            sleep_seconds=fetch_sleep,
            # 文章页抓不到时回信源捞（Medium/SAGE/T&F 一律 403，但它们的 RSS 不封我们）
            sources_by_id={source.id: source for source in cfg.sources.sources},
        )
        save_body_cache(cache, body_cache_path)
        print(f"正文缓存已写入 {body_cache_path}")

    missing_body = [case.case_id for case in plan.cases if not cache.get(case.item.id)]
    plan.cases = [
        SampleCase(
            item=case.item,
            source_name=case.source_name,
            case_id=case.case_id,
            stratum=case.stratum,
            distance=case.distance,
            near_threshold=case.near_threshold,
            threshold=case.threshold,
            # 正文缺失如实写进备注列（用户在表里就能看到，不用翻日志）
            note="未抓到原文正文（bodyOriginal 会留空）"
            if not cache.get(case.item.id)
            else case.note,
            # 补抓到的正文挂在 case 上：`item.body` 已被 strip_bodies 清空，
            # 不这么做标注表的「正文摘录」会全是空的。
            body=cache.get(case.item.id, "") or case.item.body,
        )
        for case in plan.cases
    ]
    plan.report["bodyMissing"] = missing_body
    if missing_body:
        print(f"⚠️ {len(missing_body)} 条没有正文，已写进备注列：{missing_body}")

    write_candidates_xlsx(plan.cases, out_path)
    print(f"标注表已写入 {out_path}（{len(plan.cases)} 行 × {len(COLUMNS)} 列）")
    print("列顺序：" + " | ".join(COLUMNS))
    print("⚠️ 表里没有均分/建议/模型中文摘要列（D11：从零标注，不给任何建议）")
    print("下一步：在「该选吗」列逐条选择，然后运行 "
          "`.venv/bin/python scripts/sample_gold.py --convert`")

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(plan.report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"抽样报告已写入 {report_path}")
    return plan


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="阶段 8 金标分层抽样、导出标注表、转 eval/gold.jsonl（D11：不给模型建议）",
    )
    parser.add_argument("--items", default="data/items", help="条目目录或 jsonl 文件（默认 data/items）")
    parser.add_argument("--out", default="eval/gold_candidates.xlsx", help="标注表输出路径")
    parser.add_argument("--gold", default="eval/gold.jsonl", help="金标输出路径（--convert 用）")
    parser.add_argument("--body-cache", default="eval/cache/gold_bodies.jsonl",
                        help="正文缓存路径（补抓结果，--convert 复用）")
    parser.add_argument("--convert", action="store_true", help="读回标注好的 xlsx，产出 gold.jsonl")
    parser.add_argument("--no-fetch", action="store_true", help="跳过补抓正文（离线/测试用）")
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET,
                        help=f"抽样条数（默认 {DEFAULT_TARGET}）")
    parser.add_argument("--min-per-category", type=int, default=DEFAULT_MIN_PER_CATEGORY,
                        help=f"每个分类至少几条（默认 {DEFAULT_MIN_PER_CATEGORY}）")
    parser.add_argument("--min-near-threshold", type=int, default=DEFAULT_MIN_NEAR_THRESHOLD,
                        help=f"门槛附近至少几条（默认 {DEFAULT_MIN_NEAR_THRESHOLD}）")
    parser.add_argument("--near-threshold-window", type=int, default=DEFAULT_NEAR_WINDOW,
                        help=f"「门槛附近」的窗口，均分 ±N（默认 {DEFAULT_NEAR_WINDOW}）")
    parser.add_argument("--fetch-sleep", type=float, default=0.5, help="补抓间隔秒数（默认 0.5）")
    parser.add_argument("--report", default=None, help="把抽样报告 JSON 写到这个路径")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = load_config()

    if args.convert:
        xlsx_path = Path(args.out)
        rows, strata = read_candidates_xlsx(xlsx_path)
        # 正文缓存的键是 item.id，而表里只有 caseId 和原文链接，
        # 所以按链接把 caseId 对回条目 id，再取缓存里的正文。
        url_by_case = {row["caseId"]: row.get("原文链接", "") for row in rows}
        id_by_url = {item.url: item.id for item in load_items_path(Path(args.items))}
        case_ids = {
            case_id: id_by_url[url]
            for case_id, url in url_by_case.items()
            if url in id_by_url
        }
        unmatched = [c for c, url in url_by_case.items() if url and url not in id_by_url]
        if unmatched:
            print(f"⚠️ 有 {len(unmatched)} 条的原文链接在 {args.items} 里找不到对应条目，"
                  f"这些条目的 material.bodyOriginal 会留空：{unmatched}")
        cache = load_body_cache(Path(args.body_cache))
        cases, report = convert_xlsx_to_gold(
            xlsx_path,
            Path(args.gold),
            bodies=cache,
            case_ids=case_ids,
            source_kinds=source_kind_map(cfg),
            name_to_source_id={name: sid for sid, name in source_name_map(cfg).items()},
            strata=strata,
        )
        print(render_convert_report(report))
        return 0

    export_candidates(
        items_path=Path(args.items),
        out_path=Path(args.out),
        body_cache_path=Path(args.body_cache),
        cfg=cfg,
        target=args.target,
        min_per_category=args.min_per_category,
        min_near_threshold=args.min_near_threshold,
        near_window=args.near_threshold_window,
        no_fetch=args.no_fetch,
        fetch_sleep=args.fetch_sleep,
        report_path=Path(args.report) if args.report else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
