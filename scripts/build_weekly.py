#!/usr/bin/env python3
"""出周报（计划 §5.6）。

周一汇编上周日报，按出现位置与分数取前 20 件，按分节分栏。
**模型只写总述**（`prompts/report-period.md`），且**默认不调模型**——用模板句。
只有 `--execute` + `LLM_API_KEY` + `MODEL_CALLS_ENABLED=true` 才让模型写总述；
名字/数字校验不过会自动换回模板句。

用法：
    python scripts/build_weekly.py                    # 补出所有缺的周
    python scripts/build_weekly.py --week 2026-W43
    python scripts/build_weekly.py --force
    python scripts/build_weekly.py --execute          # 让模型写总述
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from uxhot.config import ConfigError, load_config  # noqa: E402
from uxhot.llm import LLMClient, LLMCallsDisabled, load_llm_config  # noqa: E402
from uxhot.models import Item, load_items  # noqa: E402
from uxhot.report import build_weekly  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
DAILY_DIR = DATA_DIR / "reports" / "daily"
WEEKLY_DIR = DATA_DIR / "reports" / "weekly"

MAX_BACKFILL_WEEKS = 8


def load_all_items() -> list[Item]:
    items: list[Item] = []
    items_dir = DATA_DIR / "items"
    if not items_dir.is_dir():
        return items
    for path in sorted(items_dir.glob("*.jsonl")):
        items.extend(load_items(path))
    return items


def load_dailies() -> list[dict]:
    """读已出的日报，周报只从日报汇编。"""
    if not DAILY_DIR.is_dir():
        return []
    out: list[dict] = []
    for path in sorted(DAILY_DIR.glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 - 坏文件不该中断出刊
            continue
    return out


def target_weeks(dailies: list[dict], now: datetime) -> list[str]:
    """该出哪些周：有日报覆盖的 ISO 周 + 上周（周一 10:00 后）。"""
    weeks: set[str] = set()
    for report in dailies:
        date_str = report.get("date")
        if not date_str:
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        iso = dt.isocalendar()
        weeks.add(f"{iso[0]}-W{iso[1]:02d}")

    # 上周（周报是「周一汇编上周」）
    last_week_day = now - timedelta(days=7)
    iso = last_week_day.isocalendar()
    weeks.add(f"{iso[0]}-W{iso[1]:02d}")

    # 只保留最近 MAX_BACKFILL_WEEKS 周，避免首次运行补出一堆空周报
    cutoff = (now - timedelta(weeks=MAX_BACKFILL_WEEKS)).isocalendar()
    cutoff_key = f"{cutoff[0]}-W{cutoff[1]:02d}"
    return sorted(w for w in weeks if w >= cutoff_key)


def main() -> int:
    parser = argparse.ArgumentParser(description="出 UXHOT 周报")
    parser.add_argument("--week", help="只出指定 ISO 周，如 2026-W43")
    parser.add_argument("--force", action="store_true", help="重写已存在的周")
    parser.add_argument("--execute", action="store_true", help="允许模型写总述（默认只用模板句）")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = parser.parse_args()

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"✗ 配置错误：{exc}")
        return 2

    llm = None
    if args.execute:
        llm = LLMClient(load_llm_config(), allow_calls=True)
        try:
            llm.ensure_ready()
        except LLMCallsDisabled as exc:
            print(f"✗ {exc}")
            return 2
        print(f"模型：{llm.config.describe()}")
    else:
        print("未启用模型，周报总述用模板句（加 --execute 才让模型写）。")

    now = datetime.now(timezone.utc)
    items = load_all_items()
    dailies = load_dailies()
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)

    if not dailies:
        print("还没有日报，周报只从日报汇编，先跑 scripts/build_daily.py。")
        return 0

    weeks = [args.week] if args.week else target_weeks(dailies, now)
    created = skipped = 0

    for week in weeks:
        path = WEEKLY_DIR / f"{week}.json"
        if path.exists() and not args.force:
            print(f"  跳过 {week}（已存在）")
            skipped += 1
            continue

        report = build_weekly(items, cfg, week, previous_dailies=dailies, llm=llm, now=now)
        stats = report.get("stats", {})
        source = report.get("overviewSource")
        summary = f"{stats.get('itemCount', 0)} 件，总述来源 {source}"

        if args.dry_run:
            print(f"  [dry-run] 将出 {week}：{summary}")
            continue

        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  出刊 {week}：{summary} → {path.relative_to(REPO_ROOT)}")
        created += 1

    print(f"\n新出 {created} 期，跳过 {skipped} 期。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
