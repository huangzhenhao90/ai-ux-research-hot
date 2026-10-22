"""金标（gold）数据模型与读写。

字段沿用 AIHOT `docs/selection.md` 的定义，便于对照：

```json
{"caseId":"law-001",
 "material":{"title":"原文标题","originalTitle":null,"publishedAt":"2026-10-01T09:00:00+08:00",
             "sourceName":"信源名称","bodyZh":null,"bodyOriginal":"正文……"},
 "sourceFacts":{"sourceKind":"rss","sourceTier":"T1","firstParty":true,"language":"zh"},
 "samplingContext":{"benchmarkSplit":"development","samplingStratum":"regulation"},
 "gold":{"decision":"select"}}
```

三条关键约定（计划 §阶段 8）：

1. `gold.decision` 只有三个值：`select` 该选、`reject` 不该选、`either` 两可。
   **`either` 不计入任何质量指标的分母。**
2. `benchmarkSplit` 分 `development`（调提示词只看这份）与 `holdout`（最后只跑一次确认）。
   按 2:1 切分。
3. 标注的人必须是**以后读这个站的人**（D11：用户从零标注，执行模型不给建议）。

⚠️ 金标文件**不放进 `web/public`**，且 `eval/gold.jsonl` 已加进 `.gitignore`
（它含第三方文章正文）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Decision = Literal["select", "reject", "either"]
Split = Literal["development", "holdout"]

# 切分比例：development : holdout = 2 : 1
DEVELOPMENT_RATIO = 2


class GoldMaterial(BaseModel):
    """被判定的材料本身。"""

    title: str
    originalTitle: str | None = None
    publishedAt: str | None = None
    sourceName: str = ""
    # 中文正文放 bodyZh，原文放 bodyOriginal；有一个就行
    bodyZh: str | None = None
    bodyOriginal: str | None = None

    @property
    def body(self) -> str:
        return self.bodyZh or self.bodyOriginal or ""

    @property
    def language(self) -> str:
        return "zh" if self.bodyZh else "en"


class SourceFacts(BaseModel):
    """信源侧事实。`sourceTier` 决定用哪个门槛，所以必须准。"""

    sourceKind: str = "rss"
    sourceTier: str
    firstParty: bool = False
    language: str = "en"

    @field_validator("sourceTier")
    @classmethod
    def _known_tier(cls, v: str) -> str:
        if v not in ("T1", "T1_5", "T2", "EXCLUDE"):
            raise ValueError(f"未知信源分级：{v}")
        return v


class SamplingContext(BaseModel):
    """抽样上下文。`benchmarkSplit` 决定这条只用于开发还是留出确认。"""

    benchmarkSplit: Split
    samplingStratum: str | None = None


class GoldLabel(BaseModel):
    decision: Decision


class GoldCase(BaseModel):
    caseId: str
    material: GoldMaterial
    sourceFacts: SourceFacts
    samplingContext: SamplingContext
    gold: GoldLabel

    @property
    def is_scored(self) -> bool:
        """`either` 不计入质量指标的分母。"""
        return self.gold.decision != "either"

    @property
    def should_select(self) -> bool:
        return self.gold.decision == "select"


# ── 读写 ────────────────────────────────────────────────────────────────


def load_gold(path: Path) -> list[GoldCase]:
    """读 `eval/gold.jsonl`。坏行报错而不是静默跳过——金标数据不能悄悄少几条。"""
    if not path.is_file():
        raise FileNotFoundError(f"金标文件不存在：{path}")
    cases: list[GoldCase] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            cases.append(GoldCase.model_validate(json.loads(line)))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{path}:{lineno} 金标行不合法：{exc}") from exc
    if not cases:
        raise ValueError(f"金标文件为空：{path}")
    return cases


def save_gold(cases: list[GoldCase], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(case.model_dump_json() for case in cases) + "\n", encoding="utf-8"
    )


def filter_split(cases: list[GoldCase], split: Split) -> list[GoldCase]:
    return [c for c in cases if c.samplingContext.benchmarkSplit == split]


def scored_cases(cases: list[GoldCase]) -> list[GoldCase]:
    """参与质量指标分母的样本（去掉 `either`）。"""
    return [c for c in cases if c.is_scored]


# ── 切分 ────────────────────────────────────────────────────────────────


def assign_split(case_id: str, ratio: int = DEVELOPMENT_RATIO) -> Split:
    """按 caseId 的稳定哈希切分，保证同一条永远是同一份。

    用哈希而不是奇偶下标，是为了让「按顺序新增样本」不会整体打乱已有切分。
    """
    digest = hashlib.sha256(case_id.encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return "development" if value % (ratio + 1) < ratio else "holdout"


def summarize(cases: list[GoldCase]) -> dict:
    """给报告用的样本概览。"""
    by_decision: dict[str, int] = {}
    by_split: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    by_stratum: dict[str, int] = {}

    for case in cases:
        by_decision[case.gold.decision] = by_decision.get(case.gold.decision, 0) + 1
        by_split[case.samplingContext.benchmarkSplit] = (
            by_split.get(case.samplingContext.benchmarkSplit, 0) + 1
        )
        tier = case.sourceFacts.sourceTier
        by_tier[tier] = by_tier.get(tier, 0) + 1
        stratum = case.samplingContext.samplingStratum or "（未分组）"
        by_stratum[stratum] = by_stratum.get(stratum, 0) + 1

    scored = scored_cases(cases)
    select_rate = (
        sum(1 for c in scored if c.should_select) / len(scored) if scored else 0.0
    )

    return {
        "total": len(cases),
        "scored": len(scored),
        "either": len(cases) - len(scored),
        "selectRate": round(select_rate, 4),
        "byDecision": by_decision,
        "bySplit": by_split,
        "byTier": by_tier,
        "byStratum": by_stratum,
    }


def parse_decision(raw: str | None) -> Decision | None:
    """把标注表里的中文/英文写法归一成三个取值。"""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    mapping = {
        "select": "select", "选": "select", "该选": "select", "1": "select", "y": "select",
        "reject": "reject", "不选": "reject", "不该选": "reject", "0": "reject", "n": "reject",
        "either": "either", "两可": "either", "都可以": "either", "不确定": "either",
    }
    return mapping.get(text)  # type: ignore[return-value]


def iso_or_none(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


class CaseBuilder(BaseModel):
    """从一条 `Item` + 标注，构造 `GoldCase`。"""

    caseId: str
    material: GoldMaterial
    sourceFacts: SourceFacts
    samplingContext: SamplingContext
    gold: GoldLabel = Field(default_factory=lambda: GoldLabel(decision="either"))
