"""金标评测（计划 §阶段 8 第 3 步）。

对每条金标重跑**预筛 + 两次独立评分**，比较模型判定与人工标注，输出指标与门槛曲线。

指标口径沿用 AIHOT `docs/selection.md`：

- **有效输出准确率**：只看成功得到入选决定的样本，判断模型答出来以后有多准。
- **查准率 / 查全率 / F1**：以 `select` 为正类。
- **覆盖率**：成功得到入选决定的样本占全部非 `either` 金标样本的比例。
- **完整准确率**：用全部非 `either` 样本作分母，**把模型失败也算作没答对**。
- **`either` 一律不进任何质量指标的分母**；单列计数。
- **`goldSelectRate`** 按全部非 `either` 金标算，所以同一批样本在不同模型间应当一致。

评测**不含**第 6 步的同事件去重：按「这条资料本身该不该选」标注，
不因为同一件事已经选过另一篇就标不该选。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from uxhot.config import ConfigBundle
from uxhot.gold import GoldCase, scored_cases
from uxhot.llm import LLMClient, LLMError
from uxhot.prompts import base_variables, render

# 门槛扫描范围（计划 §阶段 8：40–90，步长 2）
SWEEP_START = 40
SWEEP_END = 90
SWEEP_STEP = 2


# ── 结果 ────────────────────────────────────────────────────────────────


@dataclass
class CaseResult:
    caseId: str
    tier: str
    sourceName: str
    gold: str                     # select | reject | either
    stratum: str | None = None
    prefilter: str | None = None  # PASS | BLOCK | UNKNOWN
    scores: list[int] = field(default_factory=list)
    failed: bool = False          # 没拿到有效决定（调用失败 / 返回不合法）
    error: str | None = None

    @property
    def is_either(self) -> bool:
        return self.gold == "either"

    @property
    def avg(self) -> float | None:
        return sum(self.scores) / len(self.scores) if self.scores else None

    @property
    def total(self) -> int | None:
        """两次评分之和。门槛判定用的是这个（和 ≥ 2×门槛）。"""
        return sum(self.scores) if len(self.scores) >= 2 else None

    def predicts_select(self, threshold: int) -> bool | None:
        """在给定门槛下模型是否会选它。None 表示没拿到有效决定。"""
        if self.failed:
            return None
        if self.prefilter == "BLOCK":
            return False
        if self.total is None:
            return None
        return self.total >= 2 * threshold


# ── 调用（带缓存）────────────────────────────────────────────────────────


class ResponseCache:
    """按「模型 + 渲染后提示词」缓存模型返回，重复评测不重复花钱。

    ⚠️ 每个 key 存的是一个**列表**，不是单个返回。
    原因：评分这一步会用**同一个提示词**连续调两次（要求两次独立评分）。
    如果按 key 只存一个返回，第二次调用就会命中缓存拿到和第一次一样的结果 ——
    两次独立评分被悄悄合并成一次，评测出来的方差与一致性就全失真了。
    存成列表后，第 N 次相同调用取第 N 个返回值：既保证两次独立，重跑时又能完全复用。
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: dict[str, list[Any]] = {}
        self._used: dict[str, int] = {}   # 本次运行里每个 key 已经取到第几个
        self.hits = 0
        self.misses = 0
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                # 兼容旧格式（单值）：统一成列表
                self.entries = {
                    k: (v if isinstance(v, list) else [v]) for k, v in raw.items()
                }
            except Exception:  # noqa: BLE001 - 缓存坏了就当没有，不要卡住评测
                self.entries = {}

    @staticmethod
    def key(model: str, prompt: str) -> str:
        return hashlib.sha256(f"{model}\x00{prompt}".encode("utf-8")).hexdigest()

    def get(self, model: str, prompt: str) -> dict | None:
        cache_key = self.key(model, prompt)
        index = self._used.get(cache_key, 0)
        values = self.entries.get(cache_key, [])
        if index < len(values):
            self._used[cache_key] = index + 1
            self.hits += 1
            return values[index]
        self.misses += 1
        return None

    def put(self, model: str, prompt: str, value: dict) -> None:
        cache_key = self.key(model, prompt)
        values = self.entries.setdefault(cache_key, [])
        values.append(value)
        self._used[cache_key] = len(values)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def material_block_for_case(case: GoldCase) -> str:
    """把一条金标材料拼成给模型的文本，格式与线上流水线一致。"""
    parts = [f"\n\n---\n来源：{case.material.sourceName}\n标题：{case.material.title}\n"]
    if case.material.publishedAt:
        parts.append(f"发布时间：{case.material.publishedAt}\n")
    body = case.material.body
    if body:
        parts.append(f"正文：\n{body}\n")
    return "".join(parts)


@dataclass
class RunStats:
    calls: int = 0
    cache_hits: int = 0
    failures: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def evaluate_cases(
    cases: list[GoldCase],
    cfg: ConfigBundle,
    client: LLMClient | None,
    *,
    cache: ResponseCache | None = None,
    model: str | None = None,
    variables: dict[str, str] | None = None,
) -> tuple[list[CaseResult], RunStats]:
    """对每条金标跑预筛 + 两次评分。

    有缓存就用缓存；没缓存且没有客户端就记为失败（不会静默当成 reject）。
    """
    vars_ = variables or base_variables(cfg)
    use_model = model or (client.config.model if client else "unknown")
    stats = RunStats()
    results: list[CaseResult] = []
    started = time.monotonic()

    for case in cases:
        result = CaseResult(
            caseId=case.caseId,
            tier=case.sourceFacts.sourceTier,
            sourceName=case.material.sourceName,
            gold=case.gold.decision,
            stratum=case.samplingContext.samplingStratum,
        )
        material = material_block_for_case(case)

        # ── 预筛 ──────────────────────────────────────────────────────
        pre_prompt = render("prefilter", vars_) + material
        pre = _call(cache, client, use_model, pre_prompt, stats, step="prefilter")
        if pre is None:
            result.failed = True
            result.error = "预筛未拿到有效返回"
            results.append(result)
            continue

        label = str(pre.get("label", "")).strip().upper()
        if label not in ("PASS", "BLOCK", "UNKNOWN"):
            result.failed = True
            result.error = f"预筛返回非法 label：{label}"
            results.append(result)
            continue
        result.prefilter = label

        # BLOCK 的条目在线上不进评分，这里也一样
        if label == "BLOCK":
            results.append(result)
            continue

        # ── 两次独立评分 ──────────────────────────────────────────────
        score_prompt = render("selection-score", vars_) + material
        scores: list[int] = []
        for _ in range(cfg.selection.scoreAttempts):
            payload = _call(cache, client, use_model, score_prompt, stats, step="score")
            if payload is None:
                break
            value = payload.get("attentionScore")
            try:
                scores.append(max(0, min(100, int(round(float(value))))))
            except (TypeError, ValueError):
                result.error = f"评分返回非法：{value!r}"
                break

        result.scores = scores
        if len(scores) < cfg.selection.scoreAttempts:
            result.failed = True
            if result.error is None:
                result.error = "未拿到完整两次评分"
        results.append(result)

    stats.seconds = time.monotonic() - started
    return results, stats


def _call(
    cache: ResponseCache | None,
    client: LLMClient | None,
    model: str,
    prompt: str,
    stats: RunStats,
    *,
    step: str,
) -> dict | None:
    """先查缓存，再真调。失败返回 None（由调用方标 failed，不当成 reject）。"""
    if cache is not None:
        cached = cache.get(model, prompt)
        if cached is not None:
            stats.cache_hits += 1
            return cached

    if client is None:
        return None

    try:
        stats.calls += 1
        payload = client.complete_json(prompt, step=step)
    except LLMError:
        stats.failures += 1
        return None

    if cache is not None:
        cache.put(model, prompt, payload)
    return payload


# ── 指标 ────────────────────────────────────────────────────────────────


@dataclass
class Metrics:
    """一组指标。分母口径见模块开头。"""

    total: int = 0          # 全部样本（含 either）
    denominator: int = 0    # 非 either，所有指标的分母
    either: int = 0
    valid: int = 0          # 拿到有效决定的样本
    failed: int = 0
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    @property
    def coverage(self) -> float:
        return self.valid / self.denominator if self.denominator else 0.0

    @property
    def accuracy_valid(self) -> float:
        """有效输出准确率：只看答出来的。"""
        return (self.tp + self.tn) / self.valid if self.valid else 0.0

    @property
    def accuracy_full(self) -> float:
        """完整准确率：把失败也算错。"""
        return (self.tp + self.tn) / self.denominator if self.denominator else 0.0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "total": self.total,
            "denominator": self.denominator,
            "either": self.either,
            "valid": self.valid,
            "failed": self.failed,
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "coverage": round(self.coverage, 4),
            "accuracyValid": round(self.accuracy_valid, 4),
            "accuracyFull": round(self.accuracy_full, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


def compute_metrics(results: list[CaseResult], threshold: dict[str, int]) -> Metrics:
    """按给定门槛表算指标。"""
    metrics = Metrics(total=len(results))
    for r in results:
        if r.is_either:
            metrics.either += 1
            continue
        metrics.denominator += 1

        limit = threshold.get(r.tier)
        predicted = r.predicts_select(limit) if limit is not None else None

        if predicted is None:
            metrics.failed += 1
            continue
        metrics.valid += 1

        if predicted and r.gold == "select":
            metrics.tp += 1
        elif predicted and r.gold == "reject":
            metrics.fp += 1
        elif not predicted and r.gold == "select":
            metrics.fn += 1
        else:
            metrics.tn += 1
    return metrics


def gold_select_rate(results: list[CaseResult]) -> float:
    """金标里该选的比例。按全部非 either 算，跨模型应当一致。"""
    scored = [r for r in results if not r.is_either]
    if not scored:
        return 0.0
    return sum(1 for r in scored if r.gold == "select") / len(scored)


def sweep_by_tier(
    results: list[CaseResult],
    *,
    start: int = SWEEP_START,
    end: int = SWEEP_END,
    step: int = SWEEP_STEP,
) -> dict[str, list[tuple[int, Metrics]]]:
    """每个 tier 在 start..end（含）逐档扫，返回 {tier: [(threshold, metrics)]}。"""
    by_tier: dict[str, list[CaseResult]] = {}
    for r in results:
        by_tier.setdefault(r.tier, []).append(r)

    curves: dict[str, list[tuple[int, Metrics]]] = {}
    for tier, group in sorted(by_tier.items()):
        series: list[tuple[int, Metrics]] = []
        for threshold in range(start, end + 1, step):
            series.append((threshold, compute_metrics(group, {tier: threshold})))
        curves[tier] = series
    return curves


def recommend_threshold(
    curve: list[tuple[int, Metrics]], *, min_precision: float = 0.8
) -> tuple[int, Metrics] | None:
    """在曲线上按「查准率 ≥ min_precision，查全率尽量高」挑门槛。

    这正是计划 §阶段 8 第 5 步的目标。若没有一档达到查准率要求，返回 None，
    由人工决定（**不要**自动放宽标准）。
    """
    eligible = [(t, m) for t, m in curve if m.precision >= min_precision and m.valid > 0]
    if not eligible:
        return None
    return max(eligible, key=lambda item: (item[1].recall, item[1].f1, -item[0]))


# ── 报告 ────────────────────────────────────────────────────────────────


def build_report(
    *,
    label: str,
    split: str,
    model: str,
    results: list[CaseResult],
    threshold: dict[str, int],
    curves: dict[str, list[tuple[int, Metrics]]],
    stats: RunStats,
    generated_at: datetime | None = None,
) -> str:
    stamp = (generated_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    overall = compute_metrics(results, threshold)

    lines = [
        f"# 精选评测报告 · {label}",
        "",
        f"- 生成时间：{stamp}",
        f"- 样本集：`{split}`",
        f"- 模型：`{model}`",
        f"- 门槛：`{threshold}`",
        f"- 调用：{stats.calls} 次（缓存命中 {stats.cache_hits}，失败 {stats.failures}），"
        f"token {stats.total_tokens}（输入 {stats.prompt_tokens} / 输出 {stats.completion_tokens}），"
        f"耗时 {stats.seconds:.1f}s",
        "",
        "## 样本概览",
        "",
        f"- 全部样本：{overall.total}（其中 `either` {overall.either} 条，不进任何指标分母）",
        f"- 指标分母：{overall.denominator}",
        f"- **金标该选比例 `goldSelectRate`：{gold_select_rate(results):.3f}**",
        "  （按全部非 `either` 算，同一批样本在不同模型间应当一致）",
        f"- 没拿到有效决定的：{overall.failed}",
        "",
        "## 当前门槛下的指标",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| 有效输出准确率 | {overall.accuracy_valid:.3f} |",
        f"| 完整准确率（失败算错） | {overall.accuracy_full:.3f} |",
        f"| 覆盖率 | {overall.coverage:.3f} |",
        f"| 查准率 precision | {overall.precision:.3f} |",
        f"| 查全率 recall | {overall.recall:.3f} |",
        f"| F1 | {overall.f1:.3f} |",
        "",
        f"混淆矩阵：TP {overall.tp} · FP {overall.fp} · TN {overall.tn} · FN {overall.fn}",
        "",
    ]

    # 逐 tier 门槛曲线
    lines += ["## 门槛曲线（每个 tier 单独扫）", ""]
    for tier, series in curves.items():
        group = [r for r in results if r.tier == tier]
        denom = sum(1 for r in group if not r.is_either)
        lines += [
            f"### {tier}（分母 {denom}）",
            "",
            "| 门槛 | 有效准确率 | 完整准确率 | 覆盖率 | 查准率 | 查全率 | F1 |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for threshold_value, m in series:
            lines.append(
                f"| {threshold_value} | {m.accuracy_valid:.3f} | {m.accuracy_full:.3f} | "
                f"{m.coverage:.3f} | {m.precision:.3f} | {m.recall:.3f} | {m.f1:.3f} |"
            )
        best = recommend_threshold(series)
        lines.append("")
        if best is None:
            lines.append(
                "⚠️ 这一档没有任何门槛能让查准率达到 0.8 —— "
                "**先改评分标准的例子，再考虑动门槛**（计划 §阶段 8 第 4 步）。"
            )
        else:
            threshold_value, m = best
            lines.append(
                f"建议门槛 **{threshold_value}**（查准率 {m.precision:.3f}，查全率 {m.recall:.3f}）"
            )
        lines.append("")

    # 判错清单
    wrong = [
        r for r in results
        if not r.is_either and r.predicts_select(threshold.get(r.tier, 0)) is not None
        and r.predicts_select(threshold.get(r.tier, 0)) != (r.gold == "select")
    ]
    lines += [f"## 判错的样本（{len(wrong)} 条）", ""]
    if not wrong:
        lines.append("无。")
    else:
        lines += [
            "| caseId | 分级 | 金标 | 预筛 | 两次评分 | 均分 | 失败 |",
            "|---|---|---|---|---|---:|---|",
        ]
        for r in wrong:
            avg = f"{r.avg:.1f}" if r.avg is not None else "—"
            lines.append(
                f"| {r.caseId} | {r.tier} | {r.gold} | {r.prefilter or '—'} | "
                f"{r.scores or '—'} | {avg} | {r.error or ''} |"
            )
    lines.append("")

    failed = [r for r in results if r.failed]
    lines += [f"## 未拿到有效决定（{len(failed)} 条）", ""]
    if not failed:
        lines.append("无。")
    else:
        lines += ["| caseId | 分级 | 金标 | 预筛 | 原因 |", "|---|---|---|---|---|"]
        for r in failed:
            lines.append(
                f"| {r.caseId} | {r.tier} | {r.gold} | {r.prefilter or '—'} | {r.error or ''} |"
            )
    lines.append("")

    return "\n".join(lines)


# ── 结果落盘（便于跨轮对比）───────────────────────────────────────────────


def results_payload(
    results: list[CaseResult], threshold: dict[str, int], curves: dict[str, list[tuple[int, Metrics]]]
) -> dict:
    return {
        "threshold": threshold,
        "overall": compute_metrics(results, threshold).as_dict(),
        "goldSelectRate": round(gold_select_rate(results), 4),
        "cases": [
            {
                "caseId": r.caseId,
                "tier": r.tier,
                "gold": r.gold,
                "stratum": r.stratum,
                "prefilter": r.prefilter,
                "scores": r.scores,
                "avg": r.avg,
                "failed": r.failed,
                "error": r.error,
            }
            for r in results
        ],
        "curves": {
            tier: [(t, m.as_dict()) for t, m in series] for tier, series in curves.items()
        },
    }


def save_results(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
