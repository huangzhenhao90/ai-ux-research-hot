"""生成前端要读的静态 JSON（计划 §5.3）。

产物落在 `web/public/data/`。两条硬约束：

1. **只放公开字段白名单**（`PUBLIC_FIELDS`）。`web/public/` 会提交进 public 仓库并由
   GitHub Pages 直接分发，原文全文（`body`）落盘就等于再分发他人内容，所以这里用
   白名单**正向**选取，而不是「排除 body」的反向写法——反向写法在模型将来新增字段时会
   静默泄露，正向写法最多让前端少一个字段。
2. **BLOCK 与 UNKNOWN 不公开**（`Item.is_public`），在写入前就过滤掉；`validate.py`
   再兜一次底，两道都拦。

时间：内部一律 UTC，输出 ISO 8601 带时区。「天」按 `site.timezone` 的**出刊日**切分
（日报 08:00 出刊，所以 10-21 那一期覆盖 10-20 08:00 – 10-21 08:00），这样首页分组、
日报窗口、RSS 分日三处口径一致，不会出现同一条内容今天在首页、明天又在日报里。
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

from uxhot.collect.dates import parse_tz
from uxhot.config import REPO_ROOT, ConfigBundle
from uxhot.models import Item, month_key

# 发布根目录（与 rss.xml / llms.txt 同级）
PUBLIC_DIR = REPO_ROOT / "web" / "public"
DATA_DIRNAME = "data"
REPORTS_DIR = REPO_ROOT / "data" / "reports"

# 首页「近 3 天精选」
LATEST_WINDOW_DAYS = 3
DEFAULT_EDITION_HOUR = 8

# 公开字段白名单。加字段前先问：这条字段放上公网、进 public 仓库合适吗？
PUBLIC_FIELDS: tuple[str, ...] = (
    "id",
    "sourceId",
    "sourceName",
    # 原始出处（期刊全名 / arXiv）。聚合源（ur-ai-papers）的条目靠它显示真出处，
    # 一手信源留空，前端用 sourceName 即可。
    "venue",
    "tier",
    "url",
    "title",
    "titleZh",
    "summaryZh",
    "reason",
    "category",
    "tags",
    "entities",
    "itemType",
    "publishedAt",
    "discoveredAt",
    "avgScore",  # 仅 site.showScore 为真时出现
    "status",
    "dupOf",
    "relation",
)

# 详情页额外字段（同一事件的其他报道）。列表页不带，省体积。
DETAIL_EXTRA_FIELDS: tuple[str, ...] = ("related",)

# 带时区的日期字段：校验层用同一个约定（validate.py 里也认 *At 结尾的键）
_JSON_KWARGS: dict[str, Any] = {"ensure_ascii": False, "indent": 2}


# ── 小工具 ─────────────────────────────────────────────────────────────


def iso_utc(dt: datetime | None) -> str | None:
    """ISO 8601 + 时区偏移，内部一律 UTC。

    naive 直接抛错而不是补时区：补时区会让产物随运行机器时区变化，
    而这条数据是要写进公开文件的，宁可构建失败也不要写出一条错的时间。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        raise ValueError("时间必须带时区才能发布（naive datetime）")
    return dt.astimezone(timezone.utc).isoformat()


def require_aware(dt: datetime, *, what: str) -> datetime:
    if dt.tzinfo is None:
        raise ValueError(f"{what} 必须带时区（naive datetime）")
    return dt


def base_path_of(site_url: str) -> str:
    """siteUrl 的路径部分，就是 Next.js 的 basePath（D7：/ai-ux-research-hot）。

    部署在根域名时返回空串（不是 "/"），前端 `${basePath}/all/` 才不会拼出 `//all/`。
    """
    return urlsplit(site_url).path.rstrip("/")


def edition_hour(config: ConfigBundle) -> int:
    """从 `site.editions.daily`（"08:00"）取出刊小时，解析不出来就按 8 点。"""
    raw = str(config.site.editions.get("daily", "")).strip()
    head = raw.split(":")[0]
    return int(head) if head.isdigit() else DEFAULT_EDITION_HOUR


def edition_day(dt: datetime, tz, hour: int = DEFAULT_EDITION_HOUR) -> date:
    """一条内容属于哪一期（出刊日）。

    出刊日 D 的那一期覆盖 `[D-1 hour, D hour)`（本地时间），所以要找的是
    「包含 dt 的那个窗口」的右端点日期：

        D = date(dt + (24 - hour) 小时)

    例（北京时间、hour=8）：10-21 07:00 落在窗口 [10-20 08:00, 10-21 08:00) → **10-21 期**；
    10-21 09:00 落在窗口 [10-21 08:00, 10-22 08:00) → **10-22 期**。

    ⚠️ 这里必须与报告层一致：`uxhot/report/daily.py` 的 `date` 就是出刊日，
    窗口为 `day_bounds_bj(date - 1 天)`。算错一天会让首页分组与 /daily/<date>/ 对不上。
    """
    return (dt.astimezone(tz) + timedelta(hours=24 - hour)).date()


def item_time(item: Item) -> datetime:
    """列表排序与归档用的时间：优先发布时间，没有就用发现时间。"""
    return item.publishedAt or item.discoveredAt


def sort_items(items: Iterable[Item]) -> list[Item]:
    """列表顺序：分高的在前，同分新的在前，最后按 id 兜底保证稳定。

    稳定顺序很重要：产物每次重建都要能 diff 出「真的变了」，
    顺序抖动会让 CI 每 4 小时提交一次无意义的改动。
    """
    return sorted(
        items,
        key=lambda i: (
            -(i.avgScore if i.avgScore is not None else -1.0),
            -item_time(i).timestamp(),
            i.id,
        ),
    )


def dedupe_by_id(items: Iterable[Item]) -> list[Item]:
    """按 id 去重（先出现的胜出）。

    上游 upsert 已按 id 合并，理论上不会有重复；这里只是不让上游的小毛病
    把整次发布拖垮——真重复了，`validate.py` 也会拦下来。
    """
    seen: dict[str, Item] = {}
    for item in items:
        seen.setdefault(item.id, item)
    return list(seen.values())


def source_name_map(config: ConfigBundle) -> dict[str, str]:
    return {s.id: s.name for s in config.sources.sources}


def display_source(item: Item, names: dict[str, str]) -> str:
    """条目在页面上显示的来源名。

    ⚠️ **所有出口都必须走这里。** 曾经有三处各算各的
    （`public_item` / `_ref` / `search-index`），我改 `public_item` 用 venue 之后，
    另外两处没跟上，产物里同一条 id 的 `sourceName` 不一致，被发布校验拦下 ——
    校验器是对的：同一个 id 在所有文件里必须一致。
    """
    return item.venue or names.get(item.sourceId, item.sourceId)


def public_item(item: Item, *, source_name: str, show_score: bool = False) -> dict[str, Any]:
    """把一条 Item 压成公开字段。字段顺序 = `PUBLIC_FIELDS` 的顺序。

    `sourceName` 优先用条目自己的 `venue`：聚合库（ur-ai-papers）不是出处，
    读者要看到的是「Computers in Human Behavior」或「arXiv」，
    而不是「ur-ai-papers（用户与交互 AI 论文库）」。
    """
    display_source = item.venue or source_name
    data: dict[str, Any] = {
        "id": item.id,
        "sourceId": item.sourceId,
        "sourceName": display_source,
        "venue": item.venue,
        "tier": item.tier,
        "url": item.url,
        "title": item.title,
        "titleZh": item.titleZh,
        "summaryZh": item.summaryZh,
        "reason": item.reason,
        "category": item.category,
        "tags": list(item.tags),
        "entities": list(item.entities),
        "itemType": item.itemType,
        "publishedAt": iso_utc(item.publishedAt),
        "discoveredAt": iso_utc(item.discoveredAt),
        "status": item.status.value,
        "dupOf": item.dupOf,
        "relation": item.relation,
    }
    if show_score:
        data["avgScore"] = item.avgScore
    return data


def _ref(item: Item, *, names: dict[str, str]) -> dict[str, Any]:
    """「同一事件的其他报道」用的小引用，只留点得进去的字段。"""
    return {
        "id": item.id,
        "title": item.title,
        "titleZh": item.titleZh,
        "sourceName": display_source(item, names),
        "url": item.url,
        "publishedAt": iso_utc(item.publishedAt),
    }


def related_refs(items: list[Item], names: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    """按「事件」把条目成组，给出每条的其他报道。

    事件键 = `dupOf or id`：`group` 步骤判定重复时把后来的条目指向已有精选，
    所以同一事件的成员共享同一个 dupOf。详情页靠它回答「这件事还有谁在报」。
    """
    groups: dict[str, list[Item]] = {}
    for item in items:
        groups.setdefault(item.dupOf or item.id, []).append(item)

    out: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        members = groups.get(item.dupOf or item.id, [])
        out[item.id] = [
            _ref(other, names=names)
            for other in sort_items(members)
            if other.id != item.id
        ]
    return out


def write_json(path: Path, payload: Any) -> None:
    """写 JSON：缩进 2 空格 + 结尾换行。

    产物要提交进 git，缩进让 diff 逐字段可读；`ensure_ascii=False` 保留中文，
    前端和人都少一层转义。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, **_JSON_KWARGS) + "\n", encoding="utf-8")


# ── 主题页归属 ─────────────────────────────────────────────────────────


def _entity_labels(topic, config: ConfigBundle) -> set[str]:
    """实体主题页要认的标签写法：实体名 + 别名 + 主题名。

    `structure` 步骤输出的 subjects 是实体 id（落在 `Item.entities`），
    而标签白名单里是展示名（落在 `Item.tags`），两种写法都得认。
    """
    labels = {topic.name}
    for entity in config.taxonomy.entities:
        if entity.id == topic.entityId:
            labels.update(entity.aliases)
            labels.add(entity.name)
    return labels


def topic_items(topic, public_items: list[Item], config: ConfigBundle) -> list[Item]:
    """主题页收哪些条目：命中 entityId 或命中主题标签。"""
    wanted_tags = set(topic.tags)
    labels = _entity_labels(topic, config) if topic.entityId else set()
    out: list[Item] = []
    for item in public_items:
        hit_entity = bool(topic.entityId) and (
            topic.entityId in item.entities or bool(labels & set(item.tags))
        )
        hit_tag = bool(wanted_tags & set(item.tags))
        if hit_entity or hit_tag:
            out.append(item)
    return out


# ── 报告透传 ───────────────────────────────────────────────────────────


def _guess_count(doc: Any, kind: str) -> int | None:
    """从报告 JSON 里取条目数，取不到就给 None（不编数字）。

    按 `docs/report-schema.md`：日报看 `stats.selectedCount`，周报看 `stats.itemCount`；
    再兜底认几个同义键，最后才数数组。报告 schema 归 `report/` 模块，这里只读不算。
    """
    if not isinstance(doc, dict):
        return None
    stats = doc.get("stats")
    if isinstance(stats, dict):
        key = "selectedCount" if kind == "daily" else "itemCount"
        value = stats.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    for key in ("count", "itemCount", "total"):
        value = doc.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    for key in ("items", "entries"):
        value = doc.get(key)
        if isinstance(value, list):
            return len(value)
    return None


def _guess_title(doc: Any) -> str | None:
    if isinstance(doc, dict):
        title = doc.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    return None


def copy_reports(
    reports_dir: Path | None,
    data_dir: Path,
    *,
    site_url: str,
    stamp: str,
) -> dict[str, int]:
    """把日报/周报 JSON 原样搬进公开目录，并生成索引。

    为什么透传而不是重排字段：报告的 schema 归 `report/` 模块所有，publish 只负责
    「公开边界」——能不能解析、有没有夹带 body、文件名是不是日期。这样报告改版
    不会连带改发布层。索引里的 `count`/`title` 取不到就给 null。
    """
    counts: dict[str, int] = {}
    for kind, key, path_seg in (("daily", "date", "daily"), ("weekly", "week", "weekly")):
        out_dir = data_dir / "reports" / path_seg
        out_dir.mkdir(parents=True, exist_ok=True)
        entries: list[dict[str, Any]] = []
        src_dir = (reports_dir / path_seg) if reports_dir is not None else None
        if src_dir is not None and src_dir.is_dir():
            for src in sorted(src_dir.glob("*.json")):
                if src.name == "index.json" or src.name.startswith("."):
                    continue
                name = src.stem
                if not _report_name_ok(name, kind):
                    # 非报告文件（临时文件、别的产物）不进公开目录
                    continue
                try:
                    doc = json.loads(src.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    # 解析不了的报告由校验层报错，这里照搬原文，让问题暴露而不是被吞
                    out_dir.joinpath(src.name).write_bytes(src.read_bytes())
                    entries.append(_report_entry(key, name, site_url, None, None))
                    continue
                out_dir.joinpath(src.name).write_text(
                    json.dumps(doc, **_JSON_KWARGS) + "\n", encoding="utf-8"
                )
                entries.append(
                    _report_entry(
                        key, name, site_url, _guess_count(doc, kind), _guess_title(doc)
                    )
                )
        entries.sort(key=lambda e: e[key], reverse=True)
        write_json(
            out_dir / "index.json",
            {"generatedAt": stamp, "kind": kind, "count": len(entries), "entries": entries},
        )
        counts[kind] = len(entries)
    return counts


def _report_name_ok(name: str, kind: str) -> bool:
    """报告文件名必须是日期/周号，别的东西（临时文件、别的产物）不进公开目录。"""
    pattern = r"\d{4}-\d{2}-\d{2}" if kind == "daily" else r"\d{4}-W\d{2}"
    return re.fullmatch(pattern, name) is not None


def _report_entry(
    key: str, name: str, site_url: str, count: int | None, title: str | None
) -> dict[str, Any]:
    """索引项。url 是站点上的页面地址（带尾斜杠，前端 trailingSlash 约定）。"""
    segment = "daily" if key == "date" else "weekly"
    return {
        key: name,
        "url": f"{site_url.rstrip('/')}/{segment}/{name}/",
        "count": count,
        "title": title,
    }


# ── 主入口 ─────────────────────────────────────────────────────────────


def build_site_data(
    items: Iterable[Item],
    config: ConfigBundle,
    out_dir: Path,
    *,
    reports_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """写出 `web/public/data/` 全套 JSON，返回写入数量统计。

    `out_dir` 是**发布根目录**（`web/public` 那种），不是 `data/` 本身：这样
    「临时目录 → 校验 → 整体替换」能一次覆盖 JSON + RSS + llms.txt（见 `validate.py`）。

    `now` 显式传入是为了可测试：三天窗口、出刊日分组都相对它计算。
    """
    out_root = Path(out_dir)
    data_dir = out_root / DATA_DIRNAME
    reference = require_aware(now or datetime.now(timezone.utc), what="now")
    stamp = iso_utc(reference)
    site = config.site
    tz = parse_tz(site.timezone)
    hour = edition_hour(config)
    show_score = site.showScore
    names = source_name_map(config)

    def dump(item: Item) -> dict[str, Any]:
        return public_item(item, source_name=names.get(item.sourceId, item.sourceId),
                           show_score=show_score)

    public_items = sort_items(dedupe_by_id(i for i in items if i.is_public))
    selected = [i for i in public_items if i.is_selected]

    # ── site.json：站点配置，前端 basePath / 文案都从这里取 ──────────────
    write_json(
        data_dir / "site.json",
        {
            "name": site.name,
            "alias": site.alias,
            "subject": site.subject,
            "siteUrl": site.siteUrl,
            "basePath": base_path_of(site.siteUrl),
            "homeTitle": site.homeTitle,
            "description": site.description,
            "tagline": site.tagline,
            "reasonLabel": site.reasonLabel,
            "showScore": site.showScore,
            "locale": site.locale,
            "timezone": site.timezone,
            "editions": dict(site.editions),
            "credit": site.credit,
        },
    )

    # ── latest.json：近 3 期（出刊日）精选，首页直接读这个 ────────────────
    today = edition_day(reference, tz, hour)
    window = {today - timedelta(days=n) for n in range(LATEST_WINDOW_DAYS)}
    by_day: dict[date, list[Item]] = {}
    for item in selected:
        day = edition_day(item_time(item), tz, hour)
        if day in window and day <= today:
            by_day.setdefault(day, []).append(item)
    days = [
        {"date": day.isoformat(), "count": len(rows), "items": [dump(i) for i in rows]}
        for day, rows in sorted(by_day.items(), reverse=True)
    ]
    write_json(
        data_dir / "latest.json",
        {
            "generatedAt": stamp,
            "windowDays": LATEST_WINDOW_DAYS,
            "editionHour": hour,
            "days": days,
        },
    )

    # ── all/YYYY-MM.json：全部公开动态（含未精选）───────────────────────
    by_month: dict[str, list[Item]] = {}
    for item in public_items:
        by_month.setdefault(month_key(item_time(item)), []).append(item)
    months = sorted(by_month, reverse=True)
    for month in months:
        write_json(
            data_dir / "all" / f"{month}.json",
            {
                "month": month,
                "count": len(by_month[month]),
                "items": [dump(i) for i in by_month[month]],
            },
        )
    write_json(
        data_dir / "all" / "index.json",
        {
            "generatedAt": stamp,
            "total": len(public_items),
            "months": [
                {"month": m, "count": len(by_month[m]), "path": f"data/all/{m}.json"}
                for m in months
            ],
        },
    )

    # ── items/<id>.json：详情（含同一事件的其他报道）─────────────────────
    related = related_refs(public_items, names)
    for item in public_items:
        write_json(
            data_dir / "items" / f"{item.id}.json",
            {**dump(item), "related": related.get(item.id, [])},
        )

    # ── categories/<key>.json：按分类（空分类也写，前端 generateStaticParams 要用）
    by_category: dict[str, list[Item]] = {}
    for item in public_items:
        if item.category:
            by_category.setdefault(item.category, []).append(item)
    category_index: list[dict[str, Any]] = []
    for category in config.taxonomy.categories:
        rows = by_category.get(category.key, [])
        write_json(
            data_dir / "categories" / f"{category.key}.json",
            {
                "key": category.key,
                "label": category.label,
                "section": category.section,
                "commentary": category.commentary,
                "count": len(rows),
                "items": [dump(i) for i in rows],
            },
        )
        category_index.append(
            {
                "key": category.key,
                "label": category.label,
                "section": category.section,
                "commentary": category.commentary,
                "count": len(rows),
            }
        )
    write_json(
        data_dir / "categories" / "index.json",
        {"generatedAt": stamp, "categories": category_index},
    )

    # ── topics/<slug>.json：主题页（实体页按 entityId，领域页按标签）──────
    topic_index: list[dict[str, Any]] = []
    for topic in config.topics.topics:
        rows = sort_items(topic_items(topic, public_items, config))
        write_json(
            data_dir / "topics" / f"{topic.slug}.json",
            {
                "slug": topic.slug,
                "name": topic.name,
                "group": topic.group,
                "definition": topic.definition,
                "count": len(rows),
                "items": [dump(i) for i in rows],
            },
        )
        topic_index.append(
            {
                "slug": topic.slug,
                "name": topic.name,
                "group": topic.group,
                "definition": topic.definition,
                "count": len(rows),
            }
        )
    write_json(
        data_dir / "topics" / "index.json",
        {
            "generatedAt": stamp,
            "groups": [g.model_dump() for g in config.topics.groups],
            "topics": topic_index,
        },
    )

    # ── search-index.json：本地搜索（标题 + 摘要 + 标签）────────────────
    # 不带 generatedAt：这个文件最大，带上时间戳会让每次构建都产生无意义 diff
    search_items = [
        {
            "id": item.id,
            "title": item.title,
            "titleZh": item.titleZh,
            "summaryZh": item.summaryZh,
            "tags": list(item.tags),
            "entities": list(item.entities),
            "category": item.category,
            "sourceName": display_source(item, names),
            "url": item.url,
            "publishedAt": iso_utc(item.publishedAt),
        }
        for item in public_items
    ]
    write_json(
        data_dir / "search-index.json",
        {"count": len(search_items), "items": search_items},
    )

    # ── reports/：report 模块的产物透传 ────────────────────────────────
    report_counts = copy_reports(
        reports_dir if reports_dir is not None else REPORTS_DIR,
        data_dir,
        site_url=site.siteUrl,
        stamp=stamp,
    )

    # ── data/index.json：清单，前端不必猜有哪些文件 ─────────────────────
    counts = {
        "public": len(public_items),
        "selected": len(selected),
        "months": len(months),
        "categories": len(category_index),
        "topics": len(topic_index),
        "searchIndex": len(search_items),
        "dailyReports": report_counts["daily"],
        "weeklyReports": report_counts["weekly"],
    }
    write_json(
        data_dir / "index.json",
        {
            "generatedAt": stamp,
            "counts": counts,
            "months": months,
            "latestDays": [d["date"] for d in days],
        },
    )
    return counts


# 让调用方少 import 一个模块名
BuildFn = Callable[[Path], dict[str, int]]
