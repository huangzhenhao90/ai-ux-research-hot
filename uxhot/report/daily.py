"""日报编排（计划 §5.4，**不调模型**，纯规则）。

窗口：北京时间「前一天 08:00 → 当天 08:00」，由 `day_bounds_bj` 给出（见 `daily_window`），
比较前一律转 UTC，结果不随运行机器时区变化。

规则（计划 §5.4 逐条）：

1. `importance = avgScore + 5×(同事件独立来源数 − 1)`，同事件来自 `group` 的
   `followup`/`same` 关系（`Item.relation` + `Item.dupOf`）；
2. 最近 7 期日报报过的事件，只有 `followup` 且非 commentary 类才进正文，否则进快讯；
3. 正文最多 12 条（头条 1 + 看点 3 + 分节条目），同一信源最多 2 条；
   之后最多 10 条一行快讯；
4. 报头统计入选条数与「N 款新工具」；正文为空时出空刊，不报错。

输出结构严格对齐 `docs/report-schema.md`（Lead 定的 JSON 契约），字段名不要改。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from uxhot.collect.dates import day_bounds_bj, to_utc
from uxhot.config import ConfigBundle
from uxhot.models import Item, Status

# ── 规则常量（计划 §5.4）────────────────────────────────────────────────
MAIN_LIMIT = 12          # 正文最多 12 条
HIGHLIGHT_LIMIT = 3      # 第 2–4 条是看点
FLASH_LIMIT = 10         # 之后最多 10 条一行快讯（briefs）
PER_SOURCE_LIMIT = 2     # 正文里同一信源最多 2 条
REPEAT_WINDOW = 7        # 回看最近 7 期日报，报过的事件不重复进正文
QUIET_TITLE = "今日无重要更新"

# 「N 款新工具」：分类 + 内容类型双条件（taxonomy.release.category / itemType）
RELEASE_ITEM_TYPE = "tool_launch"


# ══ 时间窗 ═══════════════════════════════════════════════════════════════


def daily_window(date_str: str) -> tuple[datetime, datetime]:
    """日报 `date_str` 的窗口 `[start, end)`（UTC）。

    计划 §5.4「覆盖前一天 08:00 到当天 08:00」里的「当天」是**出刊日**，也是期号：
    日报在 `date_str` 08:00（北京）出刊，覆盖此前 24 小时，所以
    `window = day_bounds_bj(date_str 的前一天)`。

    边界归属（测试断言过）：正好落在**前一天 08:00** 的条目归本期（起点闭）；
    正好落在**当天 08:00** 的条目归**下一期**（终点开）——相邻两期无缝且不重复。
    """
    day = date.fromisoformat(date_str)
    return day_bounds_bj((day - timedelta(days=1)).isoformat())


def item_timestamp(item: Item) -> datetime:
    """条目归期用的时间：优先发布时间，没有则用发现时间（都在模型判过之后）。

    为什么要有兜底：`selected` 的条目正常都有 `publishedAt`（无可信日期的不公开），
    但日报是纯规则编排，不能因为缺一个字段就抛异常。
    """
    return to_utc(item.publishedAt or item.discoveredAt)


def in_window(item: Item, start: datetime, end: datetime) -> bool:
    """条目时间是否落在 `[start, end)`（UTC 比较）。"""
    return start <= item_timestamp(item) < end


def _iso(value: datetime | None) -> str | None:
    """时间统一输出 ISO 8601（带时区）；没有就 null。"""
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("时间必须带时区（tz-aware）")
    return value.astimezone(timezone.utc).isoformat()


def _now_utc(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now 必须带时区（tz-aware）")
    return now.astimezone(timezone.utc)


# ══ 配置查询 ═════════════════════════════════════════════════════════════


def category_label(cfg: ConfigBundle, category: str | None) -> str:
    """分类 key → 显示名（`taxonomy.categories` 的 label）。"""
    for c in cfg.taxonomy.categories:
        if c.key == category:
            return c.label
    return category or ""


def commentary_categories(cfg: ConfigBundle) -> set[str]:
    """commentary 类（taxonomy 里 `commentary: true`，即 methods 与 opinion）。

    为什么单独抽出来：日报第 2 条规则要判断「非 commentary 类」。
    """
    return {c.key for c in cfg.taxonomy.categories if c.commentary}


def source_name(cfg: ConfigBundle, source_id: str) -> str:
    """信源 id → `config/sources.yaml` 的 name（查不到就退回 id，不让日报失败）。

    为什么不额外接 `source_names` 参数：`cfg` 本来就是权威来源，多一份 map 只会多一处
    可能过期的副本。
    """
    for source in cfg.sources.sources:
        if source.id == source_id:
            return source.name
    return source_id


# ══ 输出形状（docs/report-schema.md）═════════════════════════════════════

ITEM_REF_FIELDS = (
    "id",
    "titleZh",
    "summaryZh",
    "reason",
    "category",
    "categoryLabel",
    "sourceId",
    "sourceName",
    "tier",
    "url",
    "publishedAt",
    "avgScore",
    "importance",
    "tags",
    "relatedIds",
)

BRIEF_FIELDS = ("id", "titleZh", "url", "sourceId", "sourceName")


def item_ref(
    item: Item,
    cfg: ConfigBundle,
    *,
    importance: float | None = None,
    related_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """一条精选的 ItemRef（契约里的最小字段集，多一个字段都不要）。

    **不含 `body`**：报告是公开产物，不放原文全文（契约硬要求）。
    """
    return {
        "id": item.id,
        "titleZh": item.display_title,
        "summaryZh": item.summaryZh or "",
        "reason": item.reason or "",
        "category": item.category,
        "categoryLabel": category_label(cfg, item.category),
        "sourceId": item.sourceId,
        "sourceName": source_name(cfg, item.sourceId),
        "tier": item.tier,
        "url": item.url,
        "publishedAt": _iso(item.publishedAt),
        "avgScore": item.avgScore,
        "importance": float(importance) if importance is not None else float(item.avgScore or 0.0),
        "tags": list(item.tags),
        "relatedIds": [str(x) for x in related_ids],
    }


def brief_ref(item: Item, cfg: ConfigBundle) -> dict[str, Any]:
    """一条一行快讯（briefs）的字段集，比 ItemRef 更小。"""
    return {
        "id": item.id,
        "titleZh": item.display_title,
        "url": item.url,
        "sourceId": item.sourceId,
        "sourceName": source_name(cfg, item.sourceId),
    }


# ══ 事件归并 ═════════════════════════════════════════════════════════════


def _dup_parents(items: Iterable[Item]) -> dict[str, str]:
    """id → dupOf 的边表（用**全部**条目建，包含窗口外/未入选的原帖）。"""
    return {i.id: i.dupOf for i in items if i.dupOf}


def event_root(item_id: str, parents: Mapping[str, str]) -> str:
    """沿 `dupOf` 链找到事件根 id。

    为什么要跟着链走：`same`/`followup` 只指向一条已有精选，链式跟随后
    「原帖 + 多个跟进」会归到同一个事件，才谈得上「同事件独立来源数」。

    环保护：真出现互相指向时取环里最小的 id 当根，保证同一个环的成员算出同一个根
    （否则同事件会被拆成两组，重要性加成与去重都会错）。
    """
    seen = {item_id}
    current = item_id
    while True:
        nxt = parents.get(current)
        if not nxt:
            return current
        if nxt in seen:
            return min(seen)
        seen.add(nxt)
        current = nxt


class _Event:
    """一个事件在日报里的全部判断结果（排序、规则、输出形状一次算清）。"""

    def __init__(self, key: str, members: list[Item]) -> None:
        # 代表条目：分最高，其次最早发布，最后按 id 兜底（保证结果稳定可复现）
        members.sort(key=lambda i: (-(i.avgScore or 0.0), item_timestamp(i), i.id))
        self.key = key
        self.members = members
        self.rep = members[0]
        self.source_ids = {m.sourceId for m in members}
        # 计划 §5.4：同事件多一个独立来源，加 5 分
        self.importance = max((m.avgScore or 0.0) for m in members) + 5 * (
            len(self.source_ids) - 1
        )
        self.repeat = False
        self.eligible = True

    @property
    def related_ids(self) -> list[str]:
        """同一事件的其他条目 id（契约里的 relatedIds）。"""
        return [m.id for m in self.members[1:]]

    def mark(self, memory: set[str], commentary: set[str]) -> None:
        """判定「是否最近 7 期报过」与「能否进正文」（计划 §5.4 第 2 条）。"""
        self.repeat = any(
            m.id in memory or (m.dupOf is not None and m.dupOf in memory)
            for m in self.members
        )
        follow_up = any(m.relation == "followup" for m in self.members)
        is_commentary = self.rep.category in commentary
        # 没报过 → 可进正文；报过 → 只有 followup 且非 commentary 才可进正文，否则进快讯
        self.eligible = (not self.repeat) or (follow_up and not is_commentary)


def _events_of(selected: Sequence[Item], all_items: Sequence[Item]) -> list[_Event]:
    parents = _dup_parents(all_items)
    grouped: dict[str, list[Item]] = {}
    for item in selected:
        grouped.setdefault(event_root(item.id, parents), []).append(item)
    return [_Event(key, members) for key, members in grouped.items()]


# ══ 上一期记忆 ═══════════════════════════════════════════════════════════


def report_item_refs(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """一份日报里出现过的全部条目（headline + highlights + sections + briefs）。

    为什么要连 `relatedIds` 一起收（见 `memory_keys`）：正文里是原帖，下一期只有跟进
    条目时，靠上一期记下的同事件 id 才能认出「这个事件报过了」。
    """
    out: list[Mapping[str, Any]] = []
    headline = report.get("headline")
    if isinstance(headline, Mapping) and (headline.get("id") or headline.get("itemId")):
        out.append(headline)
    for group in ("highlights", "briefs"):
        out.extend(
            ref for ref in (report.get(group) or []) if isinstance(ref, Mapping)
        )
    for section in report.get("sections") or []:
        if isinstance(section, Mapping):
            out.extend(
                ref for ref in (section.get("items") or []) if isinstance(ref, Mapping)
            )
    return out


def memory_keys(
    previous_reports: Iterable[Mapping[str, Any]] | None,
    *,
    window: int = REPEAT_WINDOW,
) -> set[str]:
    """最近 `window` 期日报报过的事件标识（条目 id + 同事件的 relatedIds）。

    排序：有期号（`date`/`key`）就按期号倒序取最近 window 期；调用方给的顺序没有期号时
    按原顺序取（约定最近的在前），这样脚本和测试两种传法都成立。
    """
    reports = list(previous_reports or [])
    if reports and all(str(r.get("date") or r.get("key") or "") for r in reports):
        reports = sorted(reports, key=lambda r: str(r.get("date") or r.get("key")), reverse=True)

    keys: set[str] = set()
    for report in reports[:window]:
        for ref in report_item_refs(report):
            item_id = ref.get("id") or ref.get("itemId")
            if item_id:
                keys.add(str(item_id))
            for related in ref.get("relatedIds") or []:
                keys.add(str(related))
    return keys


# ══ 主流程 ═══════════════════════════════════════════════════════════════


def build_daily(
    items: Sequence[Item],
    cfg: ConfigBundle,
    date_str: str,
    *,
    previous_reports: Iterable[Mapping[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """生成一期日报（纯规则，不调模型），返回 `docs/report-schema.md` 的日报 JSON。

    参数：
    - `items`：全部条目（至少覆盖本窗口）；只有 `status == SELECTED` 的参与编排。
    - `date_str`：出刊日（北京，`YYYY-MM-DD`），也是期号，见 `daily_window`。
    - `previous_reports`：之前几期的日报内容（本函数的返回值即可），用于
      「最近 7 期报过的事件不重复进正文」。
    - `now`：`generatedAt` 的取值（默认取当前 UTC 时间），测试可注入固定值。

    「已出的不重写、错过的下次补出」由调用方（脚本/调度）按落盘文件判断，本函数只负责
    编排一期，不读盘也不写盘。
    """
    start, end = daily_window(date_str)
    selected = [i for i in items if i.status is Status.SELECTED and in_window(i, start, end)]

    commentary = commentary_categories(cfg)
    memory = memory_keys(previous_reports)

    events = _events_of(selected, items)
    for event in events:
        event.mark(memory, commentary)
    # 排序：重要性降序；同分时先出现的（发布更早）在前，最后按 id 兜底保证稳定
    events.sort(key=lambda e: (-e.importance, item_timestamp(e.rep), e.rep.id))

    main: list[_Event] = []
    rest: list[_Event] = []
    per_source: dict[str, int] = {}
    for event in events:
        source_id = event.rep.sourceId
        used = per_source.get(source_id, 0)
        if len(main) < MAIN_LIMIT and event.eligible and used < PER_SOURCE_LIMIT:
            main.append(event)
            per_source[source_id] = used + 1
        else:
            rest.append(event)

    # 正文 = 头条 + 看点 + 分节条目，三部分互不重复，合计 ≤ 12（契约 §日报）
    headline = main[0] if main else None
    highlight_events = main[1 : 1 + HIGHLIGHT_LIMIT]
    section_events = main[1 + HIGHLIGHT_LIMIT :]
    brief_events = rest[:FLASH_LIMIT]

    sections: list[dict[str, Any]] = []
    for category in cfg.taxonomy.category_keys:
        in_section = [e for e in section_events if e.rep.category == category]
        if in_section:
            sections.append(
                {
                    "key": category,
                    "label": category_label(cfg, category),
                    "items": [
                        item_ref(
                            e.rep,
                            cfg,
                            importance=e.importance,
                            related_ids=e.related_ids,
                        )
                        for e in in_section
                    ],
                }
            )

    # 空刊：没有正文（窗口内没有入选精选，或入选的全部是最近 7 期报过、只能进快讯的
    # 事件）→ 出「今日无重要更新」，数组全空，不报错（计划 §5.4）
    empty = headline is None
    release_cat = str(cfg.taxonomy.release.get("category", ""))
    new_tools = sum(
        1
        for i in selected
        if i.category == release_cat and i.itemType == RELEASE_ITEM_TYPE
    )

    return {
        "kind": "daily",
        "date": date_str,
        "siteName": cfg.site.name,
        "generatedAt": _now_utc(now).isoformat(),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "empty": empty,
        "stats": {
            "selectedCount": len(selected),   # 报头「入选条数」
            "newTools": new_tools,            # 报头「N 款新工具」（单位取 taxonomy.release.unit）
            "briefCount": len(brief_events) if not empty else 0,
        },
        "headline": (
            item_ref(
                headline.rep,
                cfg,
                importance=headline.importance,
                related_ids=headline.related_ids,
            )
            if headline
            else None
        ),
        "highlights": [
            item_ref(e.rep, cfg, importance=e.importance, related_ids=e.related_ids)
            for e in ([] if empty else highlight_events)
        ],
        "sections": [] if empty else sections,
        "briefs": [] if empty else [brief_ref(e.rep, cfg) for e in brief_events],
    }
