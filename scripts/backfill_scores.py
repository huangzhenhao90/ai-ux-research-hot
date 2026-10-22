#!/usr/bin/env python3
"""一次性校准支持：把各信源回填的条目送进评分，用来把金标样本池做大。

**这不是流水线的一部分。** 线上条目是靠新鲜度自然进入处理队列的，本脚本是
阶段 8 的一次性工具：`data/items` 里的条目大多已被 `strip_bodies()` 清掉正文，
且状态是 `archived`（不会进模型步骤），所以没法直接拿来抽金标。

做法：重新抓一遍信源（**拿回正文**），把每条标成 `NEW` 送去
预筛 → 评分 → 结构化 → 写作，然后**统一标成 `LISTED`**。

为什么最后要标 `LISTED` 而不是让它按门槛自然进精选：这些是历史条目，
让它们出现在首页「今日精选」里会误导读者。抽金标只看分数，不看状态，
所以标成 `LISTED` 对校准没有损失。

预算按 `config/selection.yaml` 的 `perRunCalls` 熔断（D9），用尽就停，
已完成的保留。想多跑就再来一次。

用法：
    python scripts/backfill_scores.py --max-items 75              # dry-run
    python scripts/backfill_scores.py --max-items 75 --execute    # 真跑
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from uxhot.budget import Budget  # noqa: E402
from uxhot.collect import external_json, rss, web_list  # noqa: E402
from uxhot.collect.fetch import SourceState, build_client, fetch  # noqa: E402
from uxhot.config import ConfigError, load_config  # noqa: E402
from uxhot.llm import LLMClient, LLMCallsDisabled, load_llm_config  # noqa: E402
from uxhot.models import (  # noqa: E402
    Item,
    Status,
    items_path,
    load_items,
    strip_bodies,
    write_items,
)
from uxhot.pipeline import prefilter, score, structure, write  # noqa: E402
from uxhot.pipeline.common import StepContext  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
RUNS_DIR = DATA_DIR / "runs"


def load_all() -> list[Item]:
    items: list[Item] = []
    for path in sorted((DATA_DIR / "items").glob("*.jsonl")):
        items.extend(load_items(path))
    return items


def collect_for_backfill(
    cfg, existing_ids: set[str], *, per_source: int, now: datetime
) -> list[Item]:
    """抓各信源的前 N 条（**不看新鲜度、不看首次导入**），带正文、标 NEW。"""
    collected: list[Item] = []
    with build_client() as client:
        for source in cfg.sources.sources:
            if source.mode != "editorial":
                continue
            try:
                result = fetch(source.url, client)
                if not result.ok:
                    print(f"  [FAIL] {source.id:<26} {result.error}")
                    continue
            except Exception as exc:  # noqa: BLE001
                print(f"  [FAIL] {source.id:<26} {type(exc).__name__}")
                continue

            if source.kind == "rss":
                entries = rss.parse_feed(result.text.encode("utf-8"), source.timezone, now=now)
                items = rss.build_items(
                    entries, source_id=source.id, source_name=source.name, tier=source.tier,
                    mode=source.mode, source_tz=source.timezone,
                    initial_backfill_limit=per_source, fresh_hours=10**9,  # 一律当新鲜
                    first_import=False, known_ids=existing_ids, now=now,
                )
            elif source.kind == "web_list":
                entries = web_list.extract_entries(
                    result.text, selectors=source.web_list.model_dump(),
                    base_url=source.url, source_tz=source.timezone, now=now,
                )
                for entry in entries:
                    if entry.published is None:
                        entry.published = web_list.fetch_entry_date(
                            entry.url, client, source.timezone, now
                        )
                items = web_list.build_items(
                    entries, source_id=source.id, source_name=source.name, tier=source.tier,
                    mode=source.mode, source_tz=source.timezone,
                    initial_backfill_limit=per_source, fresh_hours=10**9,
                    first_import=False, known_ids=existing_ids, now=now,
                )
            else:
                import json

                payload = json.loads(result.text)
                if isinstance(payload, dict):
                    payload = payload.get("papers") or payload.get("items") or []
                entries = external_json.parse_papers(payload)
                items = external_json.build_items(
                    entries, source_id=source.id, tier=source.tier, mode=source.mode,
                    initial_backfill_limit=per_source, first_import=False,
                    known_ids=existing_ids, now=now,
                )

            # web_list 的日期靠补抓，可能拿不到；没日期的条目评不了分
            usable = [i for i in items if i.publishedAt is not None][:per_source]
            for item in usable:
                item.status = Status.NEW
            collected.extend(usable)
            print(f"  [ ok ] {source.id:<26} {len(usable)} 条带正文")

    return collected


def main() -> int:
    parser = argparse.ArgumentParser(description="一次性回填评分，做大金标样本池")
    parser.add_argument("--max-items", type=int, default=75, help="本次最多评多少条")
    parser.add_argument("--per-source", type=int, default=6, help="每个信源最多取几条")
    parser.add_argument("--execute", action="store_true", help="真调模型")
    args = parser.parse_args()

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"✗ 配置错误：{exc}")
        return 2

    now = datetime.now(timezone.utc)
    existing = load_all()
    existing_ids = {i.id for i in existing}
    scored_before = sum(1 for i in existing if i.avgScore is not None)
    print(f"现有条目 {len(existing)} 条，其中已评分 {scored_before} 条")
    print(f"本次目标：再评最多 {args.max_items} 条（每信源 ≤{args.per_source} 条）\n")

    print("=== 采集（带正文）===")
    collected = collect_for_backfill(
        cfg, existing_ids, per_source=args.per_source, now=now
    )[: args.max_items]
    # 同一批里再去重一次
    seen: set[str] = set()
    batch: list[Item] = []
    for item in collected:
        if item.id not in seen:
            seen.add(item.id)
            batch.append(item)
    print(f"\n合计 {len(batch)} 条进入评分队列")

    if not batch:
        print("没有可评的条目（可能都已在库里）。")
        return 0

    budget = Budget(
        per_run_calls=cfg.selection.budget["perRunCalls"],
        per_day_calls=cfg.selection.budget["perDayCalls"],
        state_dir=RUNS_DIR, now=now,
    )
    planned = len(batch) * (1 + cfg.selection.scoreAttempts + 2)
    print(f"预算：本次 ≤{budget.per_run_calls}，当日 ≤{budget.per_day_calls}；"
          f"预计最多 {planned} 次调用")

    if not args.execute:
        print("\n[dry-run] 不发起真实调用。加 --execute 才真调模型。")
        return 0

    llm = LLMClient(load_llm_config(), allow_calls=True)
    try:
        llm.ensure_ready()
    except LLMCallsDisabled as exc:
        print(f"✗ {exc}")
        return 2
    print(f"模型：{llm.config.describe()}\n")

    ctx = StepContext(cfg=cfg, budget=budget, client=llm, dry_run=False)

    print("=== 预筛 ===")
    prefilter.run(batch, ctx)
    print(f"  {prefilter.summary(batch)}")
    print("=== 评分 ===")
    score.run(batch, ctx)
    print(f"  {score.summary(batch)}")
    print("=== 结构化 ===")
    structure.run(batch, ctx)
    print(f"  {structure.summary(batch)}")
    print("=== 写作 ===")
    write.run(batch, ctx)
    print(f"  {write.summary(batch)}")

    # 统一标 LISTED：历史条目不该出现在首页「今日精选」里
    listed = 0
    for item in batch:
        if item.status in (Status.SCORED, Status.SELECTED):
            item.status = Status.LISTED
            listed += 1

    # 合并回库
    by_id = {i.id: i for i in existing}
    for item in batch:
        by_id[item.id] = item
    all_items = sorted(by_id.values(), key=lambda i: (i.discoveredAt, i.id))

    stripped = strip_bodies(all_items)
    for path in sorted({items_path(DATA_DIR / "items", i.discoveredAt) for i in all_items}):
        write_items(path, [i for i in all_items if items_path(DATA_DIR / "items", i.discoveredAt) == path])
    budget.save()

    scored_now = sum(1 for i in batch if i.avgScore is not None)
    print(f"\n=== 结果 ===")
    print(f"本次拿到评分 {scored_now} 条（标为 listed {listed} 条）")
    print(f"实际调用 {llm.usage_summary()['calls']} 次，"
          f"token {llm.usage_summary()['total_tokens']}")
    print(f"预算：{budget.describe()}")
    print(f"清掉正文 {stripped} 条")
    total_scored = sum(1 for i in all_items if i.avgScore is not None)
    print(f"\n库里累计已评分 **{total_scored}** 条（此前 {scored_before}）")
    if total_scored < 150:
        print(f"距 150 还差 {150 - total_scored} 条 —— 再跑一次本脚本即可（受 perRunCalls 限制）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
