#!/usr/bin/env python3
"""阶段 4 验收：用 5 条手挑样本真实调用，检查评分方向是否正确。

样本：2 条该选、2 条噪声、1 条边界（见 eval/samples-direction.json）。
每条跑 1 次预筛 + 2 次独立评分（与线上一致），比较平均分与信源分级门槛。

用法：
    python scripts/eval_prompt_direction.py --dry-run    # 默认：只打印将调用多少次
    python scripts/eval_prompt_direction.py --execute    # 需 MODEL_CALLS_ENABLED=true 和 LLM_API_KEY

报告写到 eval/report-prompt-direction.md。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from uxhot.config import load_config  # noqa: E402
from uxhot.llm import LLMClient, LLMCallsDisabled, load_llm_config  # noqa: E402
from uxhot.prompts import base_variables, render  # noqa: E402

SAMPLES_FILE = REPO_ROOT / "eval" / "samples-direction.json"
REPORT_FILE = REPO_ROOT / "eval" / "report-prompt-direction.md"


def material_block(sample: dict) -> str:
    """渲染后的提示词后面追加材料。提示词本身不含 title/body 占位符。"""
    return (
        f"\n\n---\n来源：{sample['sourceName']}（分级 {sample['tier']}）\n"
        f"标题：{sample['title']}\n"
        f"正文：\n{sample['body']}\n"
    )


def run(dry_run: bool) -> int:
    cfg = load_config()
    variables = base_variables(cfg)
    samples = json.loads(SAMPLES_FILE.read_text(encoding="utf-8"))["samples"]

    planned = len(samples) * 3
    print(f"样本 {len(samples)} 条，每条 1 次预筛 + 2 次评分 = 预计 {planned} 次调用")
    print(f"门槛：{cfg.selection.thresholds}")

    if dry_run:
        print("\n[dry-run] 不发起任何真实调用。加 --execute 才会调模型。")
        return 0

    client = LLMClient(load_llm_config(), allow_calls=True)
    try:
        client.ensure_ready()
    except LLMCallsDisabled as exc:
        print(f"\n✗ {exc}")
        return 2
    print(f"模型配置：{client.config.describe()}\n")

    results = []
    for i, s in enumerate(samples, 1):
        print(f"[{i}/{len(samples)}] {s['id']} {s['title'][:56]}…")
        material = material_block(s)

        pre = client.complete_json(
            render("prefilter", variables) + material, step="prefilter"
        )
        print(f"      预筛 {pre.get('label')}（{pre.get('reason')}）")

        scores = []
        for attempt in range(cfg.selection.scoreAttempts):
            out = client.complete_json(
                render("selection-score", variables) + material, step="score"
            )
            scores.append(int(out.get("attentionScore", -1)))
            print(f"      评分{attempt + 1} {scores[-1]}")

        avg = sum(scores) / len(scores)
        threshold = cfg.selection.thresholds.get(s["tier"])
        decision = "select" if (threshold is not None and avg >= threshold) else "reject"

        expect = s["expect"]
        if expect == "either":
            # 边界样本：只要不进高分区就算方向合理
            match = avg < 80
        else:
            match = decision == expect

        results.append(
            {
                "id": s["id"],
                "title": s["title"],
                "sourceName": s["sourceName"],
                "tier": s["tier"],
                "expect": expect,
                "why": s["why"],
                "prefilter": pre,
                "scores": scores,
                "avg": avg,
                "threshold": threshold,
                "decision": decision,
                "match": match,
                "url": s["url"],
            }
        )

    _write_report(results, client)
    _print_summary(results, client)
    return 0 if all(r["match"] for r in results) else 1


def _print_summary(results: list[dict], client: LLMClient) -> None:
    print("\n" + "=" * 78)
    print(f"{'id':<8}{'期望':<8}{'均分':>6}{'门槛':>6}{'判定':<9}{'预筛':<9}{'方向':<6}")
    print("-" * 78)
    for r in results:
        print(
            f"{r['id']:<8}{r['expect']:<8}{r['avg']:>6.1f}"
            f"{(r['threshold'] if r['threshold'] is not None else -1):>6}"
            f"{r['decision']:<9}{str(r['prefilter'].get('label')):<9}"
            f"{'✅' if r['match'] else '❌':<6}"
        )
    ok = sum(1 for r in results if r["match"])
    print("-" * 78)
    print(f"方向一致：{ok}/{len(results)}")
    usage = client.usage_summary()
    print(f"调用 {usage['calls']} 次（失败 {usage['failed']}），token {usage['total_tokens']}")


def _write_report(results: list[dict], client: LLMClient) -> None:
    usage = client.usage_summary()
    lines = [
        "# 阶段 4 · 提示词方向性验证报告",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"模型：`{client.config.model}`",
        f"调用次数：{usage['calls']}（失败 {usage['failed']}），"
        f"token 合计 {usage['total_tokens']}（输入 {usage['prompt_tokens']} / 输出 {usage['completion_tokens']}）",
        "",
        "样本取自真实信源的真实条目，正文抓自原文页。每条跑 1 次预筛 + 2 次独立评分。",
        "",
        "| id | 期望 | 预筛 | 评分1 | 评分2 | 均分 | 门槛 | 判定 | 方向 |",
        "|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for r in results:
        s = r["scores"]
        s1 = s[0] if len(s) > 0 else "-"
        s2 = s[1] if len(s) > 1 else "-"
        thr = r["threshold"] if r["threshold"] is not None else "—"
        lines.append(
            f"| {r['id']} | {r['expect']} | {r['prefilter'].get('label')} | {s1} | {s2} | "
            f"{r['avg']:.1f} | {thr} | {r['decision']} | {'✅' if r['match'] else '❌'} |"
        )
    lines += ["", "## 逐条依据", ""]
    for r in results:
        lines += [
            f"### {r['id']} · {r['title']}",
            "",
            f"- 来源：{r['sourceName']}（{r['tier']}）· [原文]({r['url']})",
            f"- 期望：**{r['expect']}** —— {r['why']}",
            f"- 预筛：`{r['prefilter'].get('label')}` —— {r['prefilter'].get('reason')}",
            f"- 两次评分：{r['scores']}，均分 {r['avg']:.1f}，门槛 {r['threshold']}",
            f"- 系统判定：**{r['decision']}**　方向：{'一致 ✅' if r['match'] else '不一致 ❌'}",
            "",
        ]
    ok = sum(1 for r in results if r["match"])
    lines += ["## 结论", "", f"方向一致 **{ok}/{len(results)}**。", ""]
    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已写入 {REPORT_FILE.relative_to(REPO_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True)
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    return run(dry_run=not args.execute)


if __name__ == "__main__":
    sys.exit(main())
