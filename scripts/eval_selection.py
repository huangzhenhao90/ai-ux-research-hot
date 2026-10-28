#!/usr/bin/env python3
"""金标评测（计划 §阶段 8 第 3 步）。

对每条金标重跑**预筛 + 两次独立评分**，输出指标与逐 tier 的门槛曲线。

用法：
    # 先看会跑多少条、大概花多少（默认什么都不调）
    python scripts/eval_selection.py --gold eval/gold.jsonl --split development --label v1

    # 真跑（需要 LLM_API_KEY 与 MODEL_CALLS_ENABLED=true）
    python scripts/eval_selection.py --gold eval/gold.jsonl --split development \
        --label v1 --execute

    # 只跑留出集（**只在最后确认时跑一次**，见计划 §阶段 8 第 5 步）
    python scripts/eval_selection.py --gold eval/gold.jsonl --split holdout --label holdout-确认 --execute

结果写到 `eval/report-<label>.md` 与 `eval/result-<label>.json`；
模型返回按「模型 + 提示词」缓存在 `eval/cache/`，重跑不再花钱。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from uxhot.config import ConfigError, load_config  # noqa: E402
from uxhot.evalrun import (  # noqa: E402
    ResponseCache,
    build_report,
    evaluate_cases,
    results_payload,
    save_results,
    sweep_by_tier,
)
from uxhot.gold import filter_split, load_gold, summarize  # noqa: E402
from uxhot.llm import LLMClient, LLMCallsDisabled, load_llm_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="URHOT 金标评测")
    parser.add_argument("--gold", default="eval/gold.jsonl", help="金标文件")
    parser.add_argument("--split", default="development", choices=["development", "holdout", "all"])
    parser.add_argument("--label", default="v1", help="这一版的标签，用于报告文件名")
    parser.add_argument("--execute", action="store_true", help="真调模型（默认只用缓存/dry-run）")
    parser.add_argument("--no-cache", action="store_true", help="不用缓存，全部重跑")
    parser.add_argument("--model", default=None, help="覆盖模型（用于同批样本比较不同模型）")
    parser.add_argument("--report", default=None, help="报告路径，默认 eval/report-<label>.md")
    args = parser.parse_args()

    gold_path = REPO_ROOT / args.gold
    cache_dir = REPO_ROOT / "eval" / "cache"

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"✗ 配置错误：{exc}")
        return 2

    try:
        cases = load_gold(gold_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"✗ {exc}")
        print("  先跑 scripts/sample_gold.py 导出标注表，标完后用 --convert 转成 gold.jsonl")
        return 2

    if args.split != "all":
        cases = filter_split(cases, args.split)  # type: ignore[arg-type]
    if not cases:
        print(f"✗ 这份切分里没有样本：{args.split}")
        return 2

    info = summarize(cases)
    print(f"=== 金标评测 · {args.label} ===")
    print(f"样本集 {args.split}：{info['total']} 条"
          f"（非 either {info['scored']}，either {info['either']}）")
    print(f"金标该选比例 {info['selectRate']:.3f}")
    print(f"分级分布 {info['byTier']}")

    cache = None if args.no_cache else ResponseCache(cache_dir / f"{args.label}.json")
    planned = info["total"] * (1 + cfg.selection.scoreAttempts)

    if not args.execute:
        print(f"\n[dry-run] 不发起真实调用。若全部未命中缓存，预计最多 {planned} 次调用。")
        print("           加 --execute 才会真调模型。")
        return 0

    llm = LLMClient(load_llm_config(), allow_calls=True)
    try:
        llm.ensure_ready()
    except LLMCallsDisabled as exc:
        print(f"\n✗ {exc}")
        return 2
    print(f"模型：{llm.config.describe()}")

    results, stats = evaluate_cases(
        cases, cfg, llm, cache=cache, model=args.model
    )
    if cache is not None:
        cache.save()

    curves = sweep_by_tier(results)
    report = build_report(
        label=args.label,
        split=args.split,
        model=args.model or llm.config.model,
        results=results,
        threshold=cfg.selection.thresholds,
        curves=curves,
        stats=stats,
    )

    report_path = Path(args.report) if args.report else REPO_ROOT / "eval" / f"report-{args.label}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    result_path = REPO_ROOT / "eval" / f"result-{args.label}.json"
    save_results(results_payload(results, cfg.selection.thresholds, curves), result_path)

    # 终端摘要
    from uxhot.evalrun import compute_metrics, gold_select_rate

    overall = compute_metrics(results, cfg.selection.thresholds)
    print()
    print(f"实际调用 {stats.calls} 次（缓存命中 {stats.cache_hits}，失败 {stats.failures}），"
          f"token {stats.total_tokens}")
    print(f"金标该选比例 {gold_select_rate(results):.3f}")
    print(f"有效准确率 {overall.accuracy_valid:.3f} · 完整准确率 {overall.accuracy_full:.3f} · "
          f"覆盖率 {overall.coverage:.3f}")
    print(f"查准率 {overall.precision:.3f} · 查全率 {overall.recall:.3f} · F1 {overall.f1:.3f}")
    print(f"混淆矩阵 TP {overall.tp} / FP {overall.fp} / TN {overall.tn} / FN {overall.fn}")
    if overall.failed:
        print(f"⚠️ 有 {overall.failed} 条没拿到有效决定（已计入完整准确率的分母）")
    print()
    print(f"报告 → {report_path.relative_to(REPO_ROOT)}")
    print(f"结果 → {result_path.relative_to(REPO_ROOT)}")

    if args.split == "holdout":
        print()
        print("⚠️ 记住：留出集只跑一次。别拿它反复调提示词，否则它就失去意义了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
