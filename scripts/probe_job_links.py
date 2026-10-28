#!/usr/bin/env python3
"""社招探测第三步：找阿里、百度岗位详情页的真实地址。

`probe_job_samples.py` 验证过其余 9 家的详情页；阿里的 positionUrl 打开超时、百度两个候选
都是空白页。这里换成普通浏览器的身份（读者点链接时就是这样），并且：

1. 再试一次候选地址（等 DOM 就绪、给足时间），记下最终地址、标题、正文里有没有岗位名；
2. 打开官网列表页、搜关键词、点第一个岗位，记下真正跳到的详情页地址；
3. 从前端脚本里找带 detail 的路由，作为兜底线索。

一次性工具，只写日志与运行摘要。
"""

from __future__ import annotations

import os
import re
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_jobs as pj  # noqa: E402

KEYWORD = "用户研究"
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

TARGETS = {
    "阿里巴巴": {
        "strategy": "alibaba",
        "list": "https://talent.alibaba.com/off-campus/position-list?lang=zh",
        "candidates": lambda j: [
            "https://talent.alibaba.com" + str(j.get("positionUrl") or ""),
            f"https://talent.alibaba.com/off-campus/position-detail?lang=zh&positionId={j.get('id')}",
            f"https://talent.alibaba.com/off-campus/position-detail?positionId={j.get('id')}",
        ],
    },
    "百度": {
        "strategy": "baidu",
        "list": "https://talent.baidu.com/jobs/social-list",
        "candidates": lambda j: [
            f"https://talent.baidu.com/jobs/detail/SOCIAL/{j.get('postId')}",
            f"https://talent.baidu.com/jobs/social-detail?postId={j.get('postId')}",
            f"https://talent.baidu.com/jobs/detail/SOCIAL/{j.get('jobId')}",
        ],
    },
}


def needle_of(title: str) -> str:
    return re.sub(r"[（(【\[].*?[）)】\]]", "", title).strip()[:6]


def visit(page, url: str, needle: str) -> str:
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(8_000)
        body = page.inner_text("body")
        ok = needle in body
        return (
            f"{'✅' if ok else '❌'} HTTP {resp.status if resp else '?'} → {page.url[:140]} "
            f"· 标题「{page.title()[:40]}」· 正文 {len(body)} 字 · 找「{needle}」"
        )
    except Exception as exc:  # noqa: BLE001
        return f"❌ {type(exc).__name__}: {str(exc).splitlines()[0][:120]} ← {url[:140]}"


def discover(context, list_url: str, title: str) -> list[str]:
    """在列表页搜关键词、点岗位名，记下跳到的地址。"""
    lines: list[str] = []
    page = context.new_page()
    try:
        page.goto(list_url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(6_000)
        boxes = page.locator("input:visible")
        if boxes.count():
            boxes.first.fill(KEYWORD)
            boxes.first.press("Enter")
            page.wait_for_timeout(6_000)
        hrefs = sorted({
            h for h in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            if re.search(r"detail|position", h, re.I)
        })
        lines.append(f"- 列表页里带 detail/position 的链接 {len(hrefs)} 个：" + "；".join(hrefs[:6]))
        target = page.get_by_text(needle_of(title), exact=False).first
        if target.count() == 0:
            lines.append(f"- 列表页里没找到「{needle_of(title)}」，正文前 200 字：{page.inner_text('body')[:200]!r}")
            return lines
        try:
            with context.expect_page(timeout=10_000) as new_page:
                target.click()
            opened = new_page.value
            opened.wait_for_load_state("domcontentloaded")
            opened.wait_for_timeout(5_000)
            lines.append(f"- 点岗位名打开了新标签页：{opened.url}")
        except Exception:  # noqa: BLE001 - 没开新标签就是同页跳转
            page.wait_for_timeout(5_000)
            lines.append(f"- 点岗位名后同页地址：{page.url}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"- 列表页探测失败：{type(exc).__name__}: {str(exc).splitlines()[0][:160]}")
    finally:
        page.close()
    return lines


def routes_in_bundles(list_url: str) -> str:
    """前端脚本里带 detail 的路由字符串。"""
    with httpx.Client(headers={"User-Agent": CHROME_UA}, timeout=20, follow_redirects=True) as client:
        html = client.get(list_url).text
        base = str(client.get(list_url).url)
        scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
        found: set[str] = set()
        for src in scripts[:15]:
            url = httpx.URL(base).join(src)
            try:
                js = client.get(url).text
            except httpx.HTTPError:
                continue
            found |= set(re.findall(r"""["'`](/[A-Za-z0-9_\-/:]*detail[A-Za-z0-9_\-/:?=]*)["'`]""", js, re.I))
    return "；".join(sorted(found)[:20]) or "（没找到）"


def main() -> int:
    from playwright.sync_api import sync_playwright

    out = ["# 阿里、百度详情页地址", ""]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(user_agent=CHROME_UA, locale="zh-CN", viewport={"width": 1280, "height": 900})
        for company, spec in TARGETS.items():
            print(f"… {company}", file=sys.stderr, flush=True)
            with httpx.Client(headers={"User-Agent": pj.USER_AGENT}, timeout=pj.TIMEOUT, follow_redirects=True) as client:
                res = pj.STRATEGIES[spec["strategy"]](client, KEYWORD, "")
            out.append(f"## {company}")
            if not res.jobs:
                out += [f"接口没拿到岗位：{res.note}", ""]
                continue
            job = res.jobs[0]
            title = next((str(job[k]) for k in pj.TITLE_KEYS if isinstance(job.get(k), str)), "")
            out.append(f"样例岗位：{title}")
            page = context.new_page()
            for url in spec["candidates"](job):
                out.append(f"- 候选 {visit(page, url, needle_of(title))}")
            page.close()
            out += discover(context, spec["list"], title)
            try:
                out.append(f"- 前端脚本里的 detail 路由：{routes_in_bundles(spec['list'])}")
            except httpx.HTTPError as exc:
                out.append(f"- 前端脚本读取失败：{type(exc).__name__}")
            out.append("")
        browser.close()

    text = "\n".join(out)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
