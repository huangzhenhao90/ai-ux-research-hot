"""生成 `web/public/llms.txt`（计划 §5.3）。

llms.txt 是给语言模型读的站点摘要：站点是什么、有哪些入口、最新精选的
Markdown 列表（标题 + 链接 + 一句话摘要）。它比首页更省 token，比 RSS 更好解析，
所以这里刻意只放「一条一句」的信息，不放正文、不放长摘要。

不写构建时间戳：这个文件每次都重建，带上时间会让 git 每 4 小时提交一次空改动，
新鲜度由 RSS 的 lastBuildDate 承担。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from uxhot.config import ConfigBundle
from uxhot.models import Item
from uxhot.publish.build_site_data import (
    item_time,
    require_aware,
    sort_items,
    source_name_map,
)
from uxhot.publish.rss_out import RSS_FILE

LLMS_FILE = "llms.txt"

# 列表条数上限：llms.txt 是「站点摘要」，不是全量索引；全量给 /all/ 页面
DEFAULT_LIMIT = 30
SUMMARY_LIMIT = 120
TITLE_LIMIT = 100


def _inline(text: str | None, *, limit: int) -> str:
    """压成一行 Markdown 内联文本。

    换行会把一个列表项拆成两项；方括号会破坏 `[标题](链接)` 的语法，
    所以这两类字符必须在这里处理掉，而不是指望标题作者守规矩。
    """
    flat = re.sub(r"\s+", " ", text or "").strip()
    flat = flat.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
    if len(flat) > limit:
        flat = flat[: limit - 1].rstrip() + "…"
    return flat


def _date_only(dt: datetime | None) -> str:
    return dt.date().isoformat() if dt else ""


def build_llms_txt(
    config: ConfigBundle,
    items: Iterable[Item],
    *,
    now: datetime | None = None,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """站点简介 + 最新精选列表。"""
    site = config.site
    names = source_name_map(config)
    require_aware(now or datetime.now(timezone.utc), what="now")
    base = site.siteUrl.rstrip("/")

    selected = [i for i in items if i.is_public and i.is_selected]
    # 与首页同序：新的在前（llms.txt 关心「最近有什么」，不是分数榜）
    selected = sorted(sort_items(selected), key=lambda i: item_time(i), reverse=True)

    lines = [
        f"# {site.name} · {site.alias}",
        "",
        f"> {site.tagline}｜{site.subject}",
        "",
        f"{site.name}（{site.alias}）每天从研究工具官网、用研社区、HCI 学术与行业媒体收集"
        f"{site.subject}的动态，模型双评分筛出值得看的，按天排在精选里。站点是纯静态页面，"
        f"不调模型、不访问后端，页面上的链接都指向原文。",
        "",
        "入口：",
        "",
        f"- [精选]({base}/)：入选条目，按天排列",
        f"- [全部动态]({base}/all/)：含未入选的条目，按天排列",
        f"- [分类]({base}/categories/)：{site.subject}的六个方向",
        f"- [主题]({base}/topics/)：按公司与研究方向追踪",
        f"- [关于本站]({base}/about/)：做什么、怎么选、信源名单",
        f"- [RSS（精选）]({base}/{RSS_FILE})",
        "",
        "## 最新精选",
        "",
    ]

    rows = selected[:limit]
    for item in rows:
        title = _inline(item.display_title or item.title or item.id, limit=TITLE_LIMIT)
        summary = _inline(item.summaryZh or item.reason or "", limit=SUMMARY_LIMIT)
        source = _inline(names.get(item.sourceId, item.sourceId), limit=40)
        tail = f"（{source}"
        published = _date_only(item.publishedAt)
        tail += f"，{published}）" if published else "）"
        lines.append(f"- [{title}]({item.url})：{summary}{tail}")

    if not rows:
        lines.append("- 暂无精选。")
    elif len(selected) > len(rows):
        lines.append("")
        lines.append(f"（更多 {len(selected) - len(rows)} 条精选见 {base}/all/ 与 RSS。）")

    lines.append("")
    return "\n".join(lines)


def write_llms_txt(
    config: ConfigBundle,
    items: Iterable[Item],
    out_dir: Path,
    *,
    now: datetime | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Path:
    """写进发布根目录（`web/public/llms.txt`）。"""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / LLMS_FILE
    path.write_text(build_llms_txt(config, items, now=now, limit=limit), encoding="utf-8")
    return path
