#!/usr/bin/env python3
"""生成**前端开发用的种子数据**。

为什么需要它：真实门槛（T1 60 / T2 76）下 21 条评分只选出 1 条，日报会是空刊，
前端的日报/周报/主题页就没有内容可渲染、无法验收。

做法：把已评分条目里分数最高的一批临时标为 `selected`，补出 `selectedAt`，
再生成日报与周报，最后发布。

⚠️ **这只改内存里的条目状态，不改 `config/selection.yaml`。**
真实门槛按计划 §2.6 只在阶段 8 用用户标注的金标评测结果重定。
阶段 8 之后跑一次真实流水线，本脚本的产物会被覆盖。

用法：
    python scripts/seed_dev_data.py --top 40 --days 10
    python scripts/seed_dev_data.py --top 40 --days 10 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from uxhot.collect.dates import parse_tz  # noqa: E402
from uxhot.config import ConfigError, load_config  # noqa: E402
from uxhot.models import Status, load_items, write_items  # noqa: E402
from uxhot.publish import PublishError, build_and_validate  # noqa: E402
from uxhot.report import build_daily, build_weekly  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
ITEMS_DIR = DATA_DIR / "items"
DAILY_DIR = DATA_DIR / "reports" / "daily"
WEEKLY_DIR = DATA_DIR / "reports" / "weekly"


def edition_date_for(dt: datetime, hour: int) -> str:
    tz = parse_tz("Asia/Shanghai")
    return (dt.astimezone(tz) + timedelta(hours=24 - hour)).strftime("%Y-%m-%d")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成前端开发用种子数据")
    parser.add_argument("--top", type=int, default=40, help="按均分取前 N 条标为精选")
    parser.add_argument("--days", type=int, default=10, help="补出最近 N 天的日报")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"✗ 配置错误：{exc}")
        return 2

    now = datetime.now(timezone.utc)
    hour = int(str(cfg.site.editions.get("daily", "08:00")).split(":")[0])

    # ── 读全部条目 ────────────────────────────────────────────────────
    items = []
    for path in sorted(ITEMS_DIR.glob("*.jsonl")):
        items.extend(load_items(path))
    if not items:
        print("没有条目，先跑 scripts/run_pipeline.py --dry-run")
        return 1

    scored = [i for i in items if i.avgScore is not None]
    print(f"条目 {len(items)} 条，其中已评分 {len(scored)} 条")

    # ── 先修正历史遗留：已标 selected 但缺中文摘要的，退回 listed ──────
    # （发布层会校验「精选必须有中文标题与摘要」，留着它们会让整次发布失败）
    demoted = 0
    for item in items:
        if item.status is Status.SELECTED and not (item.summaryZh or "").strip():
            item.status = Status.LISTED
            item.selectedAt = None
            demoted += 1
    if demoted:
        print(f"退回 {demoted} 条缺摘要的 selected → listed")

    # ── 取前 N 条标为精选 ─────────────────────────────────────────────
    # 两个硬条件：
    #   1. 必须有非空的 titleZh 与 summaryZh —— 发布层会校验「精选必须有中文标题与摘要」，
    #      否则首页会出现空卡片；
    #   2. 只取最近的条目 —— 否则会把 2020 年的老条目标成精选，补出一堆荒诞的日报期号。
    cutoff = now - timedelta(days=args.days)
    eligible = [
        i for i in scored
        if (i.titleZh or "").strip()
        and (i.summaryZh or "").strip()
        and (i.publishedAt or i.discoveredAt) >= cutoff
    ]
    skipped = len(scored) - len(eligible)
    print(f"符合条件的 {len(eligible)} 条（跳过 {skipped} 条：缺摘要或太旧）")

    ranked = sorted(eligible, key=lambda i: i.avgScore or 0, reverse=True)[: args.top]
    if not ranked:
        print(
            "没有符合条件的条目。种子数据需要「已评分 + 有中文摘要 + 近 N 天」的条目；\n"
            "先跑一次 --execute 让模型写摘要，或加大 --days。"
        )
        return 1

    for item in ranked:
        item.status = Status.SELECTED
        # selectedAt 决定它落在哪一期日报；用发布时间，让各期都有内容
        stamp = item.publishedAt or item.discoveredAt
        item.selectedAt = stamp
        if not item.titleZh:
            item.titleZh = item.title
        if item.summaryZh is None:
            item.summaryZh = ""

    print(f"已把 {len(ranked)} 条标为 selected（均分 {ranked[0].avgScore:.1f} – {ranked[-1].avgScore:.1f}）")

    # 其余已评分但没入选的，标成 listed，别让它们留在 scored 状态
    for item in scored:
        if item.status is Status.SCORED:
            item.status = Status.LISTED

    if args.dry_run:
        print("[dry-run] 不写文件。")
        return 0

    # ── 回写条目 ──────────────────────────────────────────────────────
    for path in sorted(ITEMS_DIR.glob("*.jsonl")):
        batch = [i for i in items if i.discoveredAt.strftime("%Y-%m") == path.stem]
        if batch:
            write_items(path, batch)

    # ── 补日报 ────────────────────────────────────────────────────────
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    dates = sorted({edition_date_for(i.selectedAt or i.discoveredAt, hour) for i in ranked})
    made_daily = 0
    for date_str in dates:
        report = build_daily(items, cfg, date_str, now=now)
        (DAILY_DIR / f"{date_str}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        made_daily += 1
    print(f"出日报 {made_daily} 期：{', '.join(dates)}")

    # ── 补周报 ────────────────────────────────────────────────────────
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    dailies = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(DAILY_DIR.glob("*.json"))
        if p.name != "index.json"
    ]
    weeks = sorted({f"{datetime.strptime(d, '%Y-%m-%d').isocalendar()[0]}-W{datetime.strptime(d, '%Y-%m-%d').isocalendar()[1]:02d}" for d in dates})
    made_weekly = 0
    for week in weeks:
        report = build_weekly(items, cfg, week, previous_dailies=dailies, llm=None, now=now)
        (WEEKLY_DIR / f"{week}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        made_weekly += 1
    print(f"出周报 {made_weekly} 期：{', '.join(weeks)}")

    # ── 发布 ──────────────────────────────────────────────────────────
    try:
        result = build_and_validate(items, cfg, now=now)
        print(f"发布完成：{result.counts}（replaced={result.replaced}）")
    except PublishError as exc:
        print(f"✗ 发布校验失败：{exc}")
        return 1

    print("\n⚠️ 这是前端开发用的种子数据。阶段 8 定门槛后跑真实流水线会覆盖它。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
