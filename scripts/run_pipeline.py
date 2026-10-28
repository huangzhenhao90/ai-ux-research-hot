#!/usr/bin/env python3
"""一次完整运行：collect → prefilter → score → structure → write → dedupe → select。

默认 **dry-run**：抓取与机械步骤照做，模型步骤只打印将调用多少次，不发请求。
真调用需要同时满足：`--execute` + 有 `LLM_API_KEY` + `MODEL_CALLS_ENABLED=true`。

用法：
    python scripts/run_pipeline.py --dry-run
    python scripts/run_pipeline.py --dry-run --source dovetail-blog --source nngroup
    python scripts/run_pipeline.py --execute --limit 30
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from uxhot.config import ConfigError, load_config  # noqa: E402
from uxhot.llm import LLMClient, LLMCallsDisabled, load_llm_config  # noqa: E402
from uxhot.pipeline.runner import run_pipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="URHOT 流水线")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="默认。只抓取与机械步骤，模型步骤只统计调用次数")
    parser.add_argument("--execute", action="store_true",
                        help="真调模型（需 LLM_API_KEY 与 MODEL_CALLS_ENABLED=true）")
    parser.add_argument("--limit", type=int, default=None, help="每个信源最多取几条")
    parser.add_argument("--source", action="append", default=None,
                        help="只跑指定信源 id，可重复")
    args = parser.parse_args()

    dry_run = not args.execute

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"✗ 配置错误：{exc}")
        return 2

    llm = None
    if not dry_run:
        llm = LLMClient(load_llm_config(), allow_calls=True)
        try:
            llm.ensure_ready()
        except LLMCallsDisabled as exc:
            print(f"✗ {exc}")
            return 2
        print(f"模型：{llm.config.describe()}")

    mode = "dry-run" if dry_run else "execute"
    print(f"=== URHOT 流水线（{mode}）===")
    print(f"信源 {len(cfg.sources.sources)} 个；门槛 {cfg.selection.thresholds}")
    print(f"预算 本次 ≤{cfg.selection.budget['perRunCalls']}，"
          f"当日 ≤{cfg.selection.budget['perDayCalls']}")
    print()

    result = run_pipeline(cfg, dry_run=dry_run, limit=args.limit,
                          llm=llm, source_ids=args.source)

    print()
    print(f"=== 结果（{mode}）===")
    for step, stats in result.steps.items():
        print(f"  {step:<12} {stats}")
    if dry_run:
        print(f"  预计调用    {result.plannedCalls} 次（未真正调用）")
    else:
        print(f"  实际调用    {result.usage.get('calls', 0)} 次，"
              f"token {result.usage.get('total_tokens', 0)}")
    print(f"  累计条目    {result.itemCount}")
    if result.failed_sources:
        print(f"  ⚠️ 失败信源  {', '.join(result.failed_sources)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
