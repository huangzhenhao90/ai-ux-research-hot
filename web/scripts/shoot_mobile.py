#!/usr/bin/env python3
"""移动端布局实测 + 截图（Playwright）。

为什么不用 `chrome --headless --screenshot --window-size=390,844`：
那个不会真正改变布局视口，截出来的「手机图」是把桌面布局裁到 390px，
会把正常的响应式页面误判成横向溢出。这里用真实的移动端 viewport + deviceScaleFactor。

用法：
    python3 scripts/shoot_mobile.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("UXHOT_BASE", "http://127.0.0.1:4180/ai-ux-research-hot")
# 输出目录可用第一个参数覆盖（阶段 9 用 screenshots/final）
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "screenshots"

# (文件名, 路径, 视口宽, 视口高, 是否移动端)
PAGES = [
    ("home-mobile", "", 390, 844, True),
    ("daily-mobile", "daily/2026-10-22/", 390, 844, True),
    ("all-mobile", "all/", 390, 844, True),
    ("about-mobile", "about/", 390, 844, True),
    ("topics-mobile", "topics/", 390, 844, True),
    # 顺带用真实桌面视口重截几张，保证和手机是同一套渲染管线
    ("home", "", 1440, 1100, False),
    ("daily", "daily/2026-10-22/", 1440, 1100, False),
    ("all", "all/", 1440, 1100, False),
    ("item", "item/0f6df2ffe2a6818a/", 1440, 1100, False),
    ("weekly", "weekly/2026-W43/", 1440, 1100, False),
    ("topics", "topics/", 1440, 1100, False),
    ("search", "search/", 1440, 1100, False),
    ("about", "about/", 1440, 1100, False),
    ("category", "category/tools/", 1440, 1100, False),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            # 本机 Clash 代理会让 127.0.0.1 的请求也走代理，直接禁用
            args=["--no-proxy-server"],
        )
        for name, path, width, height, mobile in PAGES:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=2 if mobile else 1,
                is_mobile=mobile,
                has_touch=mobile,
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            page = context.new_page()
            errors: list[str] = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))

            page.goto(f"{BASE}/{path}", wait_until="networkidle")
            metrics = page.evaluate(
                """() => ({
                    innerWidth: window.innerWidth,
                    scrollWidth: document.documentElement.scrollWidth,
                    bodyScrollWidth: document.body.scrollWidth,
                })"""
            )
            overflow = metrics["scrollWidth"] > metrics["innerWidth"]
            flag = "❌ 横向溢出" if overflow else "✅"
            if overflow:
                failures.append(f"{name}: scrollWidth={metrics['scrollWidth']} > {metrics['innerWidth']}")
            console_note = f"  控制台错误 {len(errors)}" if errors else ""
            print(
                f"  {name:<14} {width:>5}px  inner={metrics['innerWidth']:<5} "
                f"scroll={metrics['scrollWidth']:<5} {flag}{console_note}"
            )

            page.screenshot(path=str(OUT / f"{name}.png"))
            context.close()

        browser.close()

    print(f"\n截图 {len(PAGES)} 张 → screenshots/")
    if failures:
        print("\n横向溢出：")
        for f in failures:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
