#!/usr/bin/env python3
"""逐个信源试抓并出报告（阶段 3 的 `scripts/check_sources.py` 雏形）。

用法：
    python scripts/probe_feeds.py            # 探测内置候选清单
    python scripts/probe_feeds.py --url URL  # 只探测一个地址

只读公开页面，不执行页面里的任何指令；不写任何文件（除非 --json）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import feedparser
import httpx

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
TIMEOUT = 25.0


def build_client() -> httpx.Client:
    """构造 HTTP 客户端。

    本机 Clash TUN 会把域名解析成 198.18.0.0/15 的假 IP，因此必须走本地代理；
    但环境里的 `NO_PROXY` 含 `[::1]`，httpx 无法把它当 URL 模式解析（会抛
    `Invalid port: ':1]'`）。所以这里关掉 `trust_env`，自己显式读代理设置。
    """
    proxy = (
        os.environ.get("https_proxy")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("HTTP_PROXY")
        or None
    )
    kwargs: dict = {
        "timeout": TIMEOUT,
        "follow_redirects": True,
        "headers": {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"},
        "trust_env": False,
    }
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.Client(**kwargs)


@dataclass
class ProbeResult:
    url: str
    ok: bool
    http_status: int | None
    entries: int
    dated_entries: int
    latest: str | None
    title: str | None
    error: str | None


def probe(url: str, client: httpx.Client) -> ProbeResult:
    try:
        resp = client.get(url)
    except Exception as exc:  # noqa: BLE001 - 探测脚本要如实报告任何失败
        return ProbeResult(url, False, None, 0, 0, None, None, f"{type(exc).__name__}: {exc}")

    if resp.status_code != 200:
        return ProbeResult(url, False, resp.status_code, 0, 0, None, None, f"HTTP {resp.status_code}")

    parsed = feedparser.parse(resp.content)
    entries = parsed.entries or []
    dated = 0
    latest_dt: datetime | None = None
    for entry in entries:
        for key in ("published_parsed", "updated_parsed"):
            tm = entry.get(key)
            if tm:
                dated += 1
                dt = datetime(*tm[:6], tzinfo=timezone.utc)
                if latest_dt is None or dt > latest_dt:
                    latest_dt = dt
                break

    return ProbeResult(
        url=url,
        ok=bool(entries),
        http_status=resp.status_code,
        entries=len(entries),
        dated_entries=dated,
        latest=latest_dt.isoformat() if latest_dt else None,
        title=(parsed.feed.get("title") or "").strip() or None,
        error=None if entries else "feed 解析成功但没有条目",
    )


CANDIDATES = [
    # --- T1 研究工具与机构官方 ---
    "https://dovetail.com/blog/rss.xml",
    "https://www.nngroup.com/feed/rss/",
    "https://maze.co/blog/feed.xml",
    "https://maze.co/feed.xml",
    "https://www.usertesting.com/blog/feed",
    "https://www.userinterviews.com/blog/feed.xml",
    "https://www.optimalworkshop.com/blog/feed.xml",
    "https://greatquestion.co/blog/feed.xml",
    "https://www.listenlabs.com/blog/feed.xml",
    "https://www.qualtrics.com/articles/feed/",
    "https://www.esomar.org/feed",
    "https://www.mrs.org.uk/rss/news",
    "https://www.sprig.com/blog/rss.xml",
    "https://www.medallia.com/feed/",
    # --- T2 学术 ---
    "https://export.arxiv.org/rss/cs.HC",
    "https://dl.acm.org/action/showFeed?type=etoc&feed=rss&jc=JTOCI",
    "https://dl.acm.org/action/showFeed?type=etoc&feed=rss&jc=JCHI",
    "https://uxpajournal.org/feed/",
    # --- T2 行业媒体与个人 ---
    "https://www.quirkos.com/blog/feed/",
    "https://www.greenbook.org/rss",
    "https://www.research-live.com/rss/news",
    "https://www.mrweb.com/rss/news.xml",
    "https://www.insightsassociation.org/rss",
    "https://dscout.com/people-nerds/rss.xml",
    "https://www.producttalk.org/feed/",
    "https://uxdesign.cc/feed",
    "https://www.rosenfeldmedia.com/feed/",
    # --- hot_signal ---
    "https://www.reddit.com/r/UXResearch/.rss",
    "https://www.reddit.com/r/userexperience/.rss",
    "https://hnrss.org/newest?q=user+research",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", action="append", default=None)
    parser.add_argument("--json", default=None, help="把结果写成 JSON")
    args = parser.parse_args()

    urls = args.url or CANDIDATES
    results: list[ProbeResult] = []
    with build_client() as client:
        for url in urls:
            res = probe(url, client)
            results.append(res)
            mark = "OK  " if res.ok else "FAIL"
            latest = (res.latest or "-")[:19]
            print(f"{mark} entries={res.entries:<4} dated={res.dated_entries:<4} latest={latest:<20} {url}")
            if res.error:
                print(f"      └─ {res.error}")

    ok = sum(1 for r in results if r.ok)
    print(f"\n通过 {ok}/{len(results)}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump([asdict(r) for r in results], fh, ensure_ascii=False, indent=2)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
