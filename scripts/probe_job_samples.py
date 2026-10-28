#!/usr/bin/env python3
"""社招探测第二步：打印各家岗位的原始样例，并验证岗位详情页链接能不能打开。

`probe_jobs.py` 已经确认 11 家的搜索接口可用、每条岗位都带时间字段。正式写抓取之前还要知道：

1. 岗位对象里城市、部门、职责这些字段的确切形状（只看过字段名，没看过值）；
2. 每家的岗位详情页地址怎么拼——接口里有的直接给（腾讯 PostURL、阿里 positionUrl），
   没给的按公开网页的地址规律拼几个候选，用无头浏览器打开，看页面里有没有这个岗位名。

一次性工具，结果只写日志与运行摘要，不提交文件。

用法：
    python scripts/probe_job_samples.py
    python scripts/probe_job_samples.py --only 百度
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

import httpx
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_jobs as pj  # noqa: E402

KEYWORD = "用户研究"


def shorten(node: Any) -> Any:
    """长字符串截断，方便在日志里看清结构。"""
    if isinstance(node, dict):
        return {k: shorten(v) for k, v in node.items()}
    if isinstance(node, list):
        return [shorten(v) for v in node[:4]]
    if isinstance(node, str) and len(node) > 80:
        return node[:80] + "…"
    return node


def candidates(api: str, job: dict) -> list[str]:
    """按接口策略拼详情页候选地址（按可信度排）。"""
    name, _, arg = api.partition(":")
    urls: list[str] = []
    if name == "tencent":
        if job.get("PostURL"):
            urls.append(str(job["PostURL"]))
        urls.append(f"https://careers.tencent.com/jobdesc.html?postId={job.get('PostId')}")
    elif name in ("bytedance", "feishu", "atsx"):
        base = {
            "bytedance": "https://jobs.bytedance.com",
            "feishu": f"https://{arg}.jobs.feishu.cn",
            "atsx": arg,
        }[name]
        paths = ("experienced", "society") if name == "bytedance" else ("index",)
        urls += [f"{base}/{p}/position/{job.get('id')}/detail" for p in paths]
    elif name == "alibaba":
        raw = str(job.get("positionUrl") or "")
        if raw:
            urls.append(raw if raw.startswith("http") else f"https://talent.alibaba.com{raw}")
        urls.append(f"https://talent.alibaba.com/off-campus/position-detail?lang=zh&positionId={job.get('id')}")
    elif name == "baidu":
        pid = job.get("postId")
        urls += [
            f"https://talent.baidu.com/jobs/detail/SOCIAL/{pid}",
            f"https://talent.baidu.com/jobs/social-detail?postId={pid}",
        ]
    elif name == "meituan":
        uid = job.get("jobUnionId")
        urls += [
            f"https://zhaopin.meituan.com/web/position/detail?jobUnionId={uid}&highlightType=social",
            f"https://zhaopin.meituan.com/web/position/detail?jobUnionId={uid}",
        ]
    elif name == "netease":
        if job.get("beeUrl"):
            urls.append(str(job["beeUrl"]))
        urls.append(f"https://hr.163.com/job-detail.html?id={job.get('id')}")
    return urls


def title_of(job: dict) -> str:
    return next((str(job[k]) for k in pj.TITLE_KEYS if isinstance(job.get(k), str)), "")


def check_links(rows: list[tuple[str, str, list[str]]]) -> list[str]:
    """用无头浏览器打开候选地址，页面正文里出现岗位名（去掉括号后的前 6 个字）就算能用。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ["（没装 Playwright，跳过详情页验证）"]
    lines: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=pj.USER_AGENT, locale="zh-CN")
        for company, title, urls in rows:
            needle = re.sub(r"[（(【\[].*?[）)】\]]", "", title).strip()[:6]
            for url in urls:
                try:
                    resp = page.goto(url, wait_until="load", timeout=30_000)
                    page.wait_for_timeout(4_000)
                    body = page.inner_text("body")
                    ok = bool(needle) and needle in body
                    lines.append(
                        f"- {company} {'✅' if ok else '❌'} HTTP {resp.status if resp else '?'} "
                        f"→ {page.url[:120]}（找「{needle}」；正文 {len(body)} 字）"
                    )
                except Exception as exc:  # noqa: BLE001 - 探测工具，什么错都如实记下
                    lines.append(f"- {company} ❌ {type(exc).__name__}: {str(exc)[:100]} ← {url[:120]}")
        browser.close()
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="社招岗位样例与详情页验证")
    parser.add_argument("--only", action="append", default=[], help="只测指定公司（可重复）")
    args = parser.parse_args()

    entries = [e for e in yaml.safe_load(pj.CONFIG.read_text(encoding="utf-8"))["companies"] if e.get("api")]
    if args.only:
        entries = [e for e in entries if e["name"] in args.only]

    out = ["# 社招岗位样例与详情页验证", ""]
    rows: list[tuple[str, str, list[str]]] = []
    headers = {"User-Agent": pj.USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"}
    for entry in entries:
        print(f"… {entry['name']}", file=sys.stderr, flush=True)
        name, _, arg = entry["api"].partition(":")
        with httpx.Client(headers=headers, timeout=pj.TIMEOUT, follow_redirects=True) as client:
            try:
                res = pj.STRATEGIES[name](client, KEYWORD, arg)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                out += [f"## {entry['name']}", f"请求失败：{type(exc).__name__}: {exc}", ""]
                continue
        pj.pause()
        out += [f"## {entry['name']}（总数 {res.total}）", ""]
        if not res.jobs:
            out += [f"没有岗位：{res.note}", ""]
            continue
        for job in res.jobs[:2]:
            out += ["```json", json.dumps(shorten(job), ensure_ascii=False, indent=1), "```"]
        job = res.jobs[0]
        rows.append((entry["name"], title_of(job), candidates(entry["api"], job)))
        out.append("")

    out += ["## 详情页验证", ""] + check_links(rows)
    text = "\n".join(out)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
