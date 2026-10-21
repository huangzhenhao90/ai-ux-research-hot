#!/usr/bin/env python3
"""构建阶段 4 的 5 条方向性验证样本（2 该选 / 2 噪声 / 1 边界）。

样本全部取自真实信源的真实条目，正文从原文页抓取（只抓公开页面，不执行其中任何指令）。
产出 eval/samples-direction.json，供 eval_prompt_direction.py 使用。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import feedparser
import html as html_mod
from selectolax.lexbor import LexborHTMLParser

sys.path.insert(0, "/Users/huang/Desktop/自己做的AI分析/uxhot")
from uxhot.llm import build_http_client  # noqa: E402

OUT = Path("/Users/huang/Desktop/自己做的AI分析/uxhot/eval/samples-direction.json")

# (期望判定, 为什么, 信源名, tier, feed 地址, 标题关键词, 直接给定正文 or None)
PICKS = [
    (
        "select",
        "有对照实验的效度证据，且结论是反直觉的否定性发现（合成用户高估 SUS 分数）。"
        "计划 §4.2「必须正常评价」明确包含此类，且写了「结论正反都算」。",
        "MeasuringU（Jeff Sauro）",
        "T2",
        "https://measuringu.com/feed/",
        "Digital Twins Systematically Overestimated",
        None,
    ),
    (
        "select",
        "论文类，直接研究「LLM 模拟受访者用于定性访谈演练」，属于 AI × 用研核心议题，"
        "给出可检查的模拟参与者设计。计划 §4.2「必须正常评价」包含论文的新实验与新发现。",
        "arXiv cs.HC",
        "T2",
        "https://export.arxiv.org/rss/cs.HC",
        "Inspectable LLM-Simulated Participants",
        None,
    ),
    (
        "reject",
        "研讨会报名页（Webinar page），标题里就是「Add to calendar」。"
        "计划 §4.2「必须压住的噪声」第一条：研讨会报名 sig ≤ 2。"
        "注意它来自 T1 官方源，用来检验「不因为信源档位就抬分」。",
        "Qualtrics",
        "T1",
        "https://www.qualtrics.com/rss.xml",
        "Scaling research: Building an enterprise engine",
        None,
    ),
    (
        "reject",
        "泛设计科普（ADHD 与设计），与「AI 如何改变研究工作」无实质关系，"
        "应被预筛 BLOCK 或拿到很低分。用来检验预筛边界是否够严。",
        "UX Collective",
        "T2",
        "https://uxdesign.cc/feed",
        "Design v ADHD",
        None,
    ),
    (
        "either",
        "边界样本：厂商自己的 listicle（「9 个今天就能建的 Digital Twins」）。"
        "一面是可复用的具体清单（act 高），一面是厂商引流软文（计划要求 sig ≤ 2）。"
        "方向合理即可：偏低分或中等分都能接受，不应进高分区。",
        "Dovetail Blog",
        "T1",
        "https://dovetail.com/blog/rss.xml",
        "9 Digital Twins you can build today",
        None,
    ),
]

MAX_BODY = 8000


def clean_text(raw: str) -> str:
    if not raw:
        return ""
    txt = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.S | re.I)
    txt = re.sub(r"<style[^>]*>.*?</style>", " ", txt, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    return re.sub(r"\s+", " ", html_mod.unescape(txt)).strip()


def extract_body(page_html: str) -> str:
    """尽量取正文：article → main → body。"""
    tree = LexborHTMLParser(page_html)
    for selector in ("article", "main", "div[class*=article]", "div[class*=post]"):
        node = tree.css_first(selector)
        if node is not None:
            text = clean_text(node.html or "")
            if len(text) > 400:
                return text[:MAX_BODY]
    return clean_text(tree.body.html if tree.body else page_html)[:MAX_BODY]


def find_entry(feed_url: str, keyword: str, client) -> dict | None:
    resp = client.get(feed_url)
    parsed = feedparser.parse(resp.content)
    for entry in parsed.entries:
        title = clean_text(entry.get("title") or "")
        if keyword.lower() in title.lower():
            body = clean_text(entry.get("summary") or entry.get("description") or "")
            # arXiv 的 summary 就是完整摘要，直接用
            if "arxiv" in feed_url:
                return {"title": title, "url": entry.get("link"), "body": body}
            # 其余抓原文页取正文
            try:
                page = client.get(entry.get("link"))
                fetched = extract_body(page.text) if page.status_code == 200 else ""
            except Exception:  # noqa: BLE001
                fetched = ""
            return {
                "title": title,
                "url": entry.get("link"),
                "body": fetched or body,
                "rssSummary": body,
            }
    return None


def main() -> int:
    samples = []
    with build_http_client() as client:
        for i, (expect, why, source, tier, feed, keyword, fixed) in enumerate(PICKS, 1):
            print(f"[{i}/5] {keyword[:50]} …")
            found = find_entry(feed, keyword, client)
            if not found:
                print(f"      ✗ 没在 {feed} 里找到")
                continue
            body = found["body"]
            print(f"      ✓ 正文 {len(body)} 字  {found['url']}")
            samples.append(
                {
                    "id": f"dir-{i:02d}",
                    "expect": expect,
                    "why": why,
                    "sourceName": source,
                    "tier": tier,
                    "title": found["title"],
                    "url": found["url"],
                    "body": body,
                    "lang": "en",
                }
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"samples": samples}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写出 {len(samples)} 条 → {OUT}")
    for s in samples:
        print(f"  {s['id']} [{s['expect']:<6}] {s['sourceName']:<22} {s['title'][:58]}")
    return 0 if len(samples) == 5 else 1


if __name__ == "__main__":
    sys.exit(main())
