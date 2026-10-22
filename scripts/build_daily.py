#!/usr/bin/env python3
"""出日报（计划 §5.6）。

**已出的不重写；错过的下次运行补出。** 日报不调模型，纯规则编排。

出刊日语义：`date` 是**出刊日**，窗口 = `[date-1 08:00, date 08:00)`（北京时间）。
所以一条资料属于哪个出刊日，取决于它的**入选时刻** `selectedAt`。

用法：
    python scripts/build_daily.py                      # 补出所有缺的期
    python scripts/build_daily.py --date 2026-10-22    # 只出指定期
    python scripts/build_daily.py --force              # 重写已存在的期
    python scripts/build_daily.py --dry-run            # 只打印会出哪些期
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from uxhot.collect.dates import parse_tz  # noqa: E402
from uxhot.config import ConfigError, load_config  # noqa: E402
from uxhot.models import Item, Status, load_items  # noqa: E402
from uxhot.report import build_daily  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
REPORTS_DIR = DATA_DIR / "reports" / "daily"

# 补刊回看上限，避免第一次运行时把很久以前的期都补出来
MAX_BACKFILL_DAYS = 14


def load_all_items() -> list[Item]:
    items: list[Item] = []
    items_dir = DATA_DIR / "items"
    if not items_dir.is_dir():
        return items
    for path in sorted(items_dir.glob("*.jsonl")):
        items.extend(load_items(path))
    return items


def edition_hour(cfg) -> int:
    """从 site.yaml 的 `editions.daily`（如 "08:00"）取小时。"""
    raw = str(cfg.site.editions.get("daily", "08:00"))
    try:
        return int(raw.split(":")[0])
    except (ValueError, IndexError):
        return 8


def edition_date_for(dt: datetime, hour: int) -> str:
    """一条资料的入选时刻属于哪个出刊日。

    窗口 `[D-1 hour:00, D hour:00)` 等价于 `D = date(dt + (24-hour) 小时)`。
    """
    tz = parse_tz("Asia/Shanghai")
    shifted = dt.astimezone(tz) + timedelta(hours=24 - hour)
    return shifted.strftime("%Y-%m-%d")


def due_edition_date(now: datetime, hour: int) -> str:
    """此刻**已经到出刊时刻**的最近一期。

    出刊日 D 在 D 当天 `hour:00` 发布，覆盖 `[D-1 hour:00, D hour:00)`。
    所以 `now` 时刻最近已发布的一期是：
    - `now` 的北京日期，若已过当天 `hour:00`；
    - 否则是前一天。

    ⚠️ 不能用 `edition_date_for(now, hour)` 来代替：那个函数回答的是
    「哪一期的**窗口**包含这一刻」（对**条目**是对的），用在**出刊**上会提前一天。
    提前出空刊的后果很严重：那个期号一旦存在就不会重写，而窗口内的条目归属正是它，
    于是这些条目永远不会进日报。
    """
    local = now.astimezone(parse_tz("Asia/Shanghai"))
    day = local.date() if local.hour >= hour else local.date() - timedelta(days=1)
    return day.strftime("%Y-%m-%d")


def target_dates(items: list[Item], cfg, now: datetime) -> list[str]:
    """该出哪些期：有入选资料的出刊日 + 已到点的最近一期，按时间正序。

    只生成**已经到出刊时刻**的期。还没到点的期即使已有条目归属，也要等它到点再出，
    否则会出空刊并永久吞掉那批条目。
    """
    hour = edition_hour(cfg)
    due = due_edition_date(now, hour)

    dates: set[str] = set()
    for item in items:
        if item.status is not Status.SELECTED:
            continue
        stamp = item.selectedAt or item.publishedAt or item.discoveredAt
        edition = edition_date_for(stamp, hour)
        if edition <= due:
            dates.add(edition)

    # 最近一期即使没有条目也要出（空刊），这样读者知道「今天没有重要更新」
    dates.add(due)

    cutoff = (now - timedelta(days=MAX_BACKFILL_DAYS)).strftime("%Y-%m-%d")
    return sorted(d for d in dates if d >= cutoff)


def main() -> int:
    parser = argparse.ArgumentParser(description="出 UXHOT 日报")
    parser.add_argument("--date", help="只出指定出刊日 YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="重写已存在的期")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = parser.parse_args()

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"✗ 配置错误：{exc}")
        return 2

    now = datetime.now(timezone.utc)
    items = load_all_items()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    dates = [args.date] if args.date else target_dates(items, cfg, now)
    if not dates:
        print("没有需要出的期。")
        return 0

    created = skipped = 0
    for date_str in dates:
        path = REPORTS_DIR / f"{date_str}.json"
        if path.exists() and not args.force:
            # 已出的不重写
            print(f"  跳过 {date_str}（已存在）")
            skipped += 1
            continue

        report = build_daily(items, cfg, date_str, now=now)
        stats = report.get("stats", {})
        state = "空刊" if report.get("empty") else f"正文 {stats.get('selectedCount', 0)} 条"
        if args.dry_run:
            print(f"  [dry-run] 将出 {date_str}：{state}")
            continue

        path.write_text(
            __import__("json").dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  出刊 {date_str}：{state} → {path.relative_to(REPO_ROOT)}")
        created += 1

    print(f"\n新出 {created} 期，跳过 {skipped} 期。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
