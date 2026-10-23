"""外部 JSON 信源适配器（D12：读 `ur-ai-papers` 的公开数据并入「论文」类）。

⚠️ `ur-ai-papers` 是**只读上游**：本项目只读它的公开 JSON，绝不修改、提交、推送或停用
（见其仓库 `AGENTS.md` 的不可破坏契约 1）。

数据来源（公开仓库的 raw URL，GitHub Actions 也能读）：
`https://raw.githubusercontent.com/huangzhenhao90/ur-ai-papers/main/web/public/data/papers.json`

字段：`id / doi / title / title_zh / journal / year / date / authors / url / pdf_url /
cited_by / ai_score / domain_score / ai_reason / tldr / topic_tags / ai_type_tags`。

⚠️ **未来日期**：`date` 会到 2027-01（期刊提前标期号）。这类日期不可信，
按「无可信日期」处理（不公开），否则会被当成「刚发布」全部涌上首页。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from uxhot.collect.dates import DEFAULT_TZ, now_utc, resolve_published_at
from uxhot.models import Item, Status, make_id
from uxhot.pipeline.normalize import canonicalize_url

UR_PAPERS_URL = (
    "https://raw.githubusercontent.com/huangzhenhao90/ur-ai-papers/"
    "main/web/public/data/papers.json"
)

# 期刊缩写 → 全名的映射（同一个只读上游仓库）。拿到它，卡片上就能显示
# 「Computers in Human Behavior」而不是「CHB」。
UR_JOURNALS_URL = (
    "https://raw.githubusercontent.com/huangzhenhao90/ur-ai-papers/"
    "main/config/journals.yaml"
)

# 只收近 N 天内、AI 相关性够高的论文；否则一次会灌进上千条
DEFAULT_MAX_AGE_DAYS = 30
DEFAULT_MIN_AI_SCORE = 4.0


@dataclass
class PaperEntry:
    external_id: str
    title: str
    title_zh: str | None
    url: str
    journal: str | None
    authors: list[str]
    published: datetime | None
    date_issue: str | None
    ai_score: float | None
    domain_score: float | None
    tldr: str
    ai_reason: str
    topic_tags: list[str]
    ai_type_tags: list[str]


def resolve_venue(journal: str | None, url: str, mapping: dict[str, str]) -> str:
    """一条论文的**原始出处**：arXiv、期刊全名，查不到就退回缩写。

    先看 URL 判断是不是预印本 —— arXiv 的 `journal` 字段常常是空的或不可靠，
    URL 比字段可信。
    """
    host = (url or "").lower()
    if "arxiv.org" in host:
        return "arXiv"

    abbr = (journal or "").strip()
    if not abbr:
        return ""
    return mapping.get(abbr, mapping.get(abbr.upper(), abbr))


def load_journal_names(client) -> dict[str, str]:
    """拉一次 journals.yaml，建 `缩写 → 英文全名`。

    拉失败**不能影响采集**：退回空映射，venue 就显示缩写。
    只读上游，绝不写回。
    """
    try:
        response = client.get(UR_JOURNALS_URL)
        if response.status_code != 200:
            print(f"  ⚠️ 期刊名映射拉取失败（HTTP {response.status_code}），venue 将显示缩写")
            return {}
        import yaml

        payload = yaml.safe_load(response.text) or {}
    except Exception as exc:  # noqa: BLE001 - 映射拿不到不该中断采集
        print(f"  ⚠️ 期刊名映射拉取失败（{type(exc).__name__}），venue 将显示缩写")
        return {}

    mapping: dict[str, str] = {}
    for row in payload.get("journals") or []:
        abbr = str(row.get("abbr") or "").strip()
        name = str(row.get("name_en") or "").strip()
        if abbr and name:
            mapping[abbr] = name
    return mapping


def parse_papers(payload: list[dict]) -> list[PaperEntry]:
    """把 papers.json 解析成条目。日期只做解析，不在这里判断新旧。"""
    entries: list[PaperEntry] = []
    for raw in payload:
        url = (raw.get("url") or "").strip()
        if not url:
            doi = (raw.get("doi") or "").strip()
            url = f"https://doi.org/{doi}" if doi else ""
        if not url:
            continue

        published, issue = resolve_published_at(str(raw.get("date") or ""), DEFAULT_TZ)

        entries.append(
            PaperEntry(
                external_id=str(raw.get("id") or ""),
                title=(raw.get("title") or "").strip(),
                title_zh=(raw.get("title_zh") or "").strip() or None,
                url=url,
                journal=(raw.get("journal") or None),
                authors=list(raw.get("authors") or []),
                published=published,
                date_issue=issue,
                ai_score=_to_float(raw.get("ai_score")),
                domain_score=_to_float(raw.get("domain_score")),
                tldr=(raw.get("tldr") or "").strip(),
                ai_reason=(raw.get("ai_reason") or "").strip(),
                topic_tags=list(raw.get("topic_tags") or []),
                ai_type_tags=list(raw.get("ai_type_tags") or []),
            )
        )
    return entries


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_items(
    entries: list[PaperEntry],
    *,
    source_id: str,
    tier: str,
    mode: str = "editorial",
    min_ai_score: float = DEFAULT_MIN_AI_SCORE,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    initial_backfill_limit: int = 8,
    first_import: bool = False,
    known_ids: set[str] | None = None,
    since: datetime | None = None,
    journal_names: dict[str, str] | None = None,
    now: datetime | None = None,
) -> list[Item]:
    """转成 `Item`。

    过滤（**硬跳过，不入库**）：
    - `ai_score` 低于阈值；
    - 发表超过 `max_age_days`。实测 1857 篇里有 1263 篇超过 30 天，
      若只标 ARCHIVED 仍会写进 data/items 把仓库撑大，所以直接跳过。

    首次导入只取前 `initial_backfill_limit` 条（与 RSS 采集一致，防旧文刷屏）。

    未来日期（`date_issue == "future_date"`）→ `UNKNOWN`，不公开，下次再试。
    """
    reference = now or now_utc()
    known = known_ids or set()
    items: list[Item] = []
    seen: set[str] = set()

    candidates = entries[:initial_backfill_limit] if first_import else entries

    for entry in candidates:
        if not entry.url:
            continue
        # 非首次导入时只收 since 之后的条目（含义见 rss.build_items）
        if since is not None and entry.published is not None and entry.published < since:
            continue
        if entry.ai_score is not None and entry.ai_score < min_ai_score:
            continue

        # 太老的论文对「每日热点」没有价值，直接不入库
        if entry.published is not None:
            if (reference - entry.published).days > max_age_days:
                continue

        canonical = canonicalize_url(entry.url)
        item_id = make_id(canonical)
        if item_id in known or item_id in seen:
            continue
        seen.add(item_id)

        item = Item(
            id=item_id,
            sourceId=source_id,
            tier=tier,
            mode=mode,
            url=entry.url,
            canonicalUrl=canonical,
            # 优先用已有人工/模型中文标题；正文用 tldr + 相关性说明，供评分与写作使用
            title=entry.title_zh or entry.title,
            author=", ".join(entry.authors[:3]) or None,
            lang="en",
            # 卡片上显示原始出处，而不是聚合库的名字
            venue=resolve_venue(entry.journal, entry.url, journal_names or {}) or None,
            publishedAt=entry.published,
            discoveredAt=reference,
        )
        body_parts = [p for p in (entry.tldr, entry.ai_reason) if p]
        item.set_body("\n".join(body_parts))

        if entry.published is None:
            item.status = Status.UNKNOWN
            reason = "未来日期，不可信" if entry.date_issue == "future_date" else "无可信发布日期"
            item.errors.append(reason)
        elif first_import:
            item.status = Status.ARCHIVED
            item.errors.append("首次导入的历史条目，已归档")
        else:
            item.status = Status.NEW

        # 论文来源已知：预置分类提示，避免结构化步骤再猜
        item.category = "research"

        items.append(item)

    return items
