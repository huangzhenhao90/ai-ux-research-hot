#!/usr/bin/env python3
"""用研社招同步：从公司招聘官网抓用研社招岗位，按滑动窗口维护（DECISIONS D17）。

写 `data/social/jobs.json`（状态）与 `web/content/social.json`（页面数据）。
距上次抓取不到 `minIntervalHours`（config/social.yaml）就跳过，所以定时任务每 4 小时
调用一次也只会一天真抓一次。

退出码：0 = 抓到了（哪怕有几家失败）或按间隔跳过；1 = 全部失败，什么都没写；
2 = data/social/manual.yaml 写错了（手动收录的 Boss 直聘 / 社群岗位），什么都没写。

用法：
    python scripts/sync_social.py
    python scripts/sync_social.py --force          # 不管间隔，立刻抓
    python scripts/sync_social.py --force --dump   # 另外把结果 JSON 打到标准输出（在 Actions 里取样用）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from uxhot.social.manual import ManualError  # noqa: E402
from uxhot.social.sync import CONTENT_PATH, STATE_PATH, load_social_config, sync  # noqa: E402


def describe_manual(report) -> str:
    """手动收录（Boss 直聘 / 社群）的情况；没有手动收录时返回空串。"""
    m = report.manual
    if not (m.shown or m.merged or m.expired or m.stale or m.dangling):
        return ""
    line = (
        f"手动收录：单独成卡 {len(m.shown)}、并进已有岗位 {len(m.merged)}、"
        f"满期移出 {len(m.expired)}、发布已超期未收 {len(m.stale)}"
    )
    if m.dangling:
        print(f"::warning title=手动收录的 officialId 对不上::{', '.join(m.dangling)} 指向的官网岗位不存在，已当作没指定")
    return line


def main() -> int:
    parser = argparse.ArgumentParser(description="用研社招同步")
    parser.add_argument("--force", action="store_true", help="忽略抓取间隔，立刻抓")
    parser.add_argument("--dump", action="store_true", help="把状态与页面数据打到标准输出")
    args = parser.parse_args()

    cfg = load_social_config()
    try:
        report = sync(cfg, force=args.force)
    except ManualError as exc:
        # 手动收录文件写错了：不写任何页面数据，沿用上一版，等人修
        print(f"::error title=data/social/manual.yaml 有问题::{exc}")
        return 2

    manual_line = describe_manual(report)
    if report.skipped:
        print(f"距上次抓取不到 {cfg.minIntervalHours:g} 小时，跳过（现有 {report.total} 个岗位）")
        if manual_line:
            print(manual_line)
        return 0
    w = report.window
    print(
        f"抓成功 {len(report.ok)} 家、失败 {len(report.failed)} 家；"
        f"新收 {len(w.added)}、更新 {len(w.updated)}、满 {cfg.window.keepDays} 天移出 {len(w.expired)}、"
        f"下线 {len(w.offline)}、超过 {cfg.window.admitDays} 天未收 {len(w.rejected)}；现有 {report.total} 个岗位"
    )
    if manual_line:
        print(manual_line)
    for name, error in report.failed.items():
        print(f"::warning title=社招抓取失败：{name}::{error}")
    if not report.ok:
        print("::warning title=社招全部抓取失败::沿用上一版 web/content/social.json")
        return 1
    if args.dump:
        for label, path in (("STATE", STATE_PATH), ("CONTENT", CONTENT_PATH)):
            print(f"===== {label} BEGIN =====")
            print(json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False))
            print(f"===== {label} END =====")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
