"""周报编排（计划 §5.5）。

周一汇编**上一周**的日报：把日报里出现过的条目按「出现位置 + 分数」排序取前 20 件，
按分类分节；**模型只写总述**（`prompts/report-period.md`），名字/数字校验不过就换成按
模板生成的一句，不报错。

为什么默认不调模型：计划 §2.3 的零成本默认。只有调用方显式传入**已就绪**的
`LLMClient`（`allow_calls=True`）才会走模型；其余情况（`llm=None`、`--no-model`、
dry-run、预算用尽、模型失败、校验不过）一律用模板句，且 `overviewSource` 只能是
`"model"` 或 `"template"`（契约）。

输出结构严格对齐 `docs/report-schema.md`（Lead 定的 JSON 契约），字段名不要改。
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from uxhot.budget import Budget, BudgetExceeded
from uxhot.collect.dates import day_bounds_bj
from uxhot.config import ConfigBundle
from uxhot.llm import LLMError
from uxhot.models import Item
from uxhot.prompts import base_variables, render
from uxhot.report.daily import (
    category_label,
    item_ref,
    source_name,
)

# ── 规则常量（计划 §5.5）────────────────────────────────────────────────
WEEKLY_LIMIT = 20        # 一周取前 20 件
OVERVIEW_CHARS = 160     # 总述长度上限（与 report-period.md 的 {{chars}} 一致）

# 出现位置 → 加分：头条 > 看点 > 正文 > 快讯（「按出现位置与分数」）
POSITION_BONUS: dict[str, int] = {"lead": 6, "highlight": 3, "main": 1, "flash": 0}

# report-period.md 的 {{kindName}} / {{span}} / {{sentences}} / {{chars}}
BRIEF: dict[str, str] = {
    "kindName": "周报",
    "span": "一周",
    "sentences": "三句话",
    "chars": str(OVERVIEW_CHARS),
}

WEEK_RE = re.compile(r"^(\d{4})-?W(\d{1,2})$", re.IGNORECASE)


# ══ 周区间 ═══════════════════════════════════════════════════════════════


def week_range(week_str: str) -> tuple[str, str]:
    """`2026-W43` → (`2026-10-19`, `2026-10-25`)（ISO 周一…周日）。

    用标准库 `date.fromisocalendar`，不引依赖，也不受运行机器时区影响。
    """
    match = WEEK_RE.match((week_str or "").strip())
    if not match:
        raise ValueError(f"周号格式应为 YYYY-Www（如 2026-W43）：{week_str!r}")
    year, week = int(match.group(1)), int(match.group(2))
    try:
        monday = date.fromisocalendar(year, week, 1)
    except ValueError as exc:  # 第 53 周在有些年份不存在
        raise ValueError(f"不存在的 ISO 周号：{week_str!r}（{exc}）") from exc
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def weekly_window(week_str: str) -> tuple[str, str]:
    """周报窗口 `[start, end)`（UTC）：周一 08:00 → 下周一 08:00（北京）。

    与日报同口径（都用 `day_bounds_bj` 给出北京 08:00 日界），所以周窗口正好盖住
    这一周日报的出刊时刻。
    """
    monday, _ = week_range(week_str)
    start, _ = day_bounds_bj(monday)
    return start.isoformat(), (start + timedelta(days=7)).isoformat()


def _report_date(report: Mapping[str, Any]) -> str:
    """日报期号（北京日期）。`date` 优先，其次 `key`，都没有就空串。"""
    raw = report.get("date") or report.get("key") or ""
    return str(raw)[:10]


# ══ 从日报里取条目出现位置 ═══════════════════════════════════════════════


def _positions(report: Mapping[str, Any]) -> list[tuple[str, str]]:
    """一份日报里 `(id, 出现位置)` 列表。位置用于周报排序加分。"""
    out: list[tuple[str, str]] = []

    headline = report.get("headline")
    if isinstance(headline, Mapping) and headline.get("id"):
        out.append((str(headline["id"]), "lead"))
    for ref in report.get("highlights") or []:
        if isinstance(ref, Mapping) and ref.get("id"):
            out.append((str(ref["id"]), "highlight"))
    for section in report.get("sections") or []:
        if not isinstance(section, Mapping):
            continue
        for ref in section.get("items") or []:
            if isinstance(ref, Mapping) and ref.get("id"):
                out.append((str(ref["id"]), "main"))
    for ref in report.get("briefs") or []:
        if isinstance(ref, Mapping) and ref.get("id"):
            out.append((str(ref["id"]), "flash"))
    return out


def _refs_by_id(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """一份日报里 id → ItemRef（用于取标题/摘要/分数/分类）。"""
    found: dict[str, Mapping[str, Any]] = {}
    headline = report.get("headline")
    if isinstance(headline, Mapping) and headline.get("id"):
        found[str(headline["id"])] = headline
    for group in ("highlights", "briefs"):
        for ref in report.get(group) or []:
            if isinstance(ref, Mapping) and ref.get("id"):
                found.setdefault(str(ref["id"]), ref)
    for section in report.get("sections") or []:
        if not isinstance(section, Mapping):
            continue
        for ref in section.get("items") or []:
            if isinstance(ref, Mapping) and ref.get("id"):
                found.setdefault(str(ref["id"]), ref)
    return found


class _UnionFind:
    """同事件归并用的并查集：日报 ItemRef 的 `relatedIds` 就是现成的边。"""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, node: str) -> str:
        self._parent.setdefault(node, node)
        root = node
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[node] != root:  # 路径压缩
            self._parent[node], node = root, self._parent[node]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)  # 取小 id 当根，结果稳定


def _score_of(ref: Mapping[str, Any], item: Item | None) -> float:
    """条目分数：日报 ItemRef 优先，缺失时回落到 `Item.avgScore`。"""
    raw = ref.get("avgScore")
    if isinstance(raw, (int, float)):
        return float(raw)
    if item is not None and item.avgScore is not None:
        return float(item.avgScore)
    return 0.0


def _importance_of(ref: Mapping[str, Any], item: Item | None) -> float:
    """条目重要性：日报已经算好的 importance 优先，否则退回分数。"""
    raw = ref.get("importance")
    if isinstance(raw, (int, float)):
        return float(raw)
    return _score_of(ref, item)


def _events_from_dailies(
    dailies: Sequence[Mapping[str, Any]],
    items_by_id: Mapping[str, Item],
) -> list[dict[str, Any]]:
    """把一周日报里出现过的条目按**事件**归并，并记录每次出现的位置与日期。

    为什么要归并：同一件事可能今天进正文、明天以 `followup` 进快讯，周报里只应算一件。
    跨天归并靠两样东西：日报 ItemRef 的 `relatedIds`，以及 `Item.dupOf`。
    """
    union = _UnionFind()
    for item_id, item in items_by_id.items():
        if item.dupOf:
            union.union(item_id, item.dupOf)

    seen: dict[str, dict[str, Any]] = {}
    for report in dailies:
        day = _report_date(report)
        refs = _refs_by_id(report)
        for item_id, position in _positions(report):
            ref = dict(refs.get(item_id, {}))
            for related in ref.get("relatedIds") or []:
                union.union(item_id, str(related))
            bucket = seen.setdefault(item_id, {"ref": ref, "occurrences": []})
            if not bucket["ref"]:
                bucket["ref"] = ref
            bucket["occurrences"].append(
                {"date": day, "position": position, "id": item_id, "ref": ref}
            )

    events: dict[str, dict[str, Any]] = {}
    for item_id, bucket in seen.items():
        root = union.find(item_id)
        target = events.setdefault(root, {"occurrences": []})
        target["occurrences"].extend(bucket["occurrences"])
    return list(events.values())


def _build_weekly_ref(
    event: Mapping[str, Any],
    cfg: ConfigBundle,
    items_by_id: Mapping[str, Item],
) -> dict[str, Any]:
    """把一个事件摊成周报的 ItemRef + 排序信息（rank 只内部用，不进 JSON）。

    正文写法取「最显眼的一次出现」（头条 > 看点 > 正文 > 快讯，其次日期早），
    因为周报是**汇编**日报，不该重写条目的措辞。
    """
    occurrences: list[dict[str, Any]] = list(event["occurrences"])
    occurrences.sort(
        key=lambda o: (-POSITION_BONUS.get(o["position"], 0), o["date"], o["id"])
    )
    best = occurrences[0]
    base_id = str(best["id"])
    daily_ref: Mapping[str, Any] = best["ref"]
    item = items_by_id.get(base_id)

    related_ids = sorted(
        {
            str(other)
            for occurrence in occurrences
            for other in (occurrence["ref"].get("relatedIds") or [])
            if str(other) != base_id
        }
        | {str(o["id"]) for o in occurrences if str(o["id"]) != base_id}
    )
    importance = max(
        _importance_of(o["ref"], item) for o in occurrences
    )
    score = max(_score_of(o["ref"], item) for o in occurrences)

    if item is not None:
        ref = item_ref(item, cfg, importance=importance, related_ids=related_ids)
        # 日报条目里已经有更贴正文的写法时优先用它
        for field in ("titleZh", "summaryZh", "reason", "category", "tier", "url"):
            value = daily_ref.get(field)
            if value:
                ref[field] = value
        ref["categoryLabel"] = category_label(cfg, ref.get("category"))
        ref["sourceName"] = daily_ref.get("sourceName") or ref["sourceName"]
    else:
        # 没有对应 Item 时也能出报（周报只汇编已发布的日报，不依赖重新读全量条目）
        source_id = str(daily_ref.get("sourceId") or "")
        ref = {
            "id": base_id,
            "titleZh": daily_ref.get("titleZh") or "",
            "summaryZh": daily_ref.get("summaryZh") or "",
            "reason": daily_ref.get("reason") or "",
            "category": daily_ref.get("category"),
            "categoryLabel": daily_ref.get("categoryLabel")
            or category_label(cfg, daily_ref.get("category")),
            "sourceId": source_id,
            "sourceName": daily_ref.get("sourceName") or source_name(cfg, source_id),
            "tier": daily_ref.get("tier"),
            "url": daily_ref.get("url") or "",
            "publishedAt": daily_ref.get("publishedAt"),
            "avgScore": daily_ref.get("avgScore"),
            "importance": importance,
            "tags": list(daily_ref.get("tags") or []),
            "relatedIds": related_ids,
        }

    return {
        "ref": ref,
        "rank": score + POSITION_BONUS.get(best["position"], 0),
        "days": sorted({o["date"] for o in occurrences if o["date"]}),
        "id": base_id,
    }


# ══ 总述：模板句 + 可选模型 ══════════════════════════════════════════════


def template_overview(
    sections: Sequence[Mapping[str, Any]],
    stats: Mapping[str, Any],
    period_start: str,
    period_end: str,
) -> str:
    """按模板生成的一句总述（模型不可用或校验不过时的兜底）。

    只用我们自己的数据（期数、件数、栏目名），所以天然不会编造。
    """
    if not sections:
        return f"本期（{period_start} 至 {period_end}）没有可汇编的日报条目。"
    labels = "、".join(str(s.get("label", "")) for s in sections)
    return (
        f"本期（{period_start} 至 {period_end}）汇编 {stats.get('dailyCount', 0)} 期日报、"
        f"共 {stats.get('itemCount', 0)} 件条目，覆盖{labels}。"
    )


def fitted(text: str, max_chars: int = OVERVIEW_CHARS) -> str | None:
    """只保留能装进 `max_chars` 的**整句**；连第一句都装不下就返回 None。

    为什么按句截断：总述是给人读的，砍半个句子比短一点更糟。
    """
    out = ""
    for sentence in re.findall(r"[^。！？]+[。！？]*", text.strip()):
        if len(out) + len(sentence) > max_chars:
            break
        out += sentence
    return out.strip() or None


def overview_grounded(text: str, corpus: str, cfg: ConfigBundle) -> bool:
    """总述是否只说了条目里有的名字和数字（计划 §5.5 的校验）。

    规则：总述里出现的**公司名**、**三位以上数字**、**带百分号的数字**，必须在该周条目
    里出现过；豁免 `taxonomy.plainTerms` 里的词与站名（site.name / alias / subject）。
    公司名中英两种写法都查（`益普索` 与 `Ipsos` 都算同一实体的名字）。
    """
    known = corpus.lower()
    plain = {t.lower() for t in cfg.taxonomy.plainTerms}
    plain |= {cfg.site.name.lower(), cfg.site.alias.lower(), cfg.site.subject.lower()}

    # ① 拉丁词：含大写或数字的（公司名、产品名、型号），必须在条目里出现过
    for token in re.findall(r"[A-Za-z][A-Za-z0-9.+\-]*", text):
        word = token.rstrip(".+-")
        if not word or not re.search(r"[A-Z0-9]", word):
            continue  # 纯小写词（如 and）不查，避免把中文句里的普通词当名字
        if word.lower() in plain or word.lower() in known:
            continue
        return False

    # ② 数字：三位以上，或带小数/百分号
    for figure in re.findall(r"\d+(?:\.\d+)?%?", text):
        if len(figure) >= 3 or "%" in figure or "." in figure:
            if figure not in known:
                return False

    # ③ 中文公司名：条目里没出现过的实体名不能说
    lowered = text.lower()
    for entity in cfg.taxonomy.entities:
        names = [entity.name, *entity.aliases]
        chinese = [n.lower() for n in names if re.search(r"[\u4e00-\u9fff]", n)]
        if not chinese:
            continue
        if any(name in lowered for name in chinese) and not any(
            name in known for name in chinese
        ):
            return False

    return True


def overview_corpus(
    entries: Sequence[Mapping[str, Any]],
    period_start: str,
    period_end: str,
    week_str: str,
) -> str:
    """校验用的语料：本期全部条目的标题/摘要/推荐理由 + 期号与周区间。"""
    parts = [week_str, period_start, period_end]
    for entry in entries:
        parts.append(
            " ".join(
                str(entry.get(field) or "")
                for field in ("titleZh", "summaryZh", "reason", "sourceName", "categoryLabel")
            )
        )
    return "\n".join(parts)


def period_prompt(
    cfg: ConfigBundle,
    sections: Sequence[Mapping[str, Any]],
    period_start: str,
    period_end: str,
) -> str:
    """渲染 `prompts/report-period.md`：本期条目按栏目分好，模型只写总述。

    `{{sections}}` 置空、`{{sectionsExample}}` 给 `{}`：模板要求输出
    `{"overview": ..., "sections": ...}`，周报只用 overview（栏目导读留空）。
    """
    body = render(
        "report-period",
        {**base_variables(cfg), **BRIEF, "sections": "", "sectionsExample": "{}"},
        strict=True,
    )
    lines: list[str] = []
    for section in sections:
        lines.append(f"【{section['label']}】")
        for ref in section["items"]:
            lines.append(f"- {ref.get('titleZh', '')}｜{str(ref.get('summaryZh') or '')[:140]}")
    listing = "\n".join(lines)
    return f"{body}\n\n本期：{period_start} 至 {period_end}\n{listing}"


def write_overview(
    cfg: ConfigBundle,
    sections: Sequence[Mapping[str, Any]],
    stats: Mapping[str, Any],
    corpus: str,
    period_start: str,
    period_end: str,
    *,
    llm: Any | None = None,
    budget: Budget | None = None,
) -> dict[str, Any]:
    """写总述：模型可选，失败/校验不过一律退回模板句（返回诊断便于脚本记日志）。

    返回 `{"overview", "overviewSource", "model", "error"}`；`overviewSource` 只可能是
    `"model"`（模型写的且校验通过）或 `"template"`（模板句），与契约一致。
    """
    template = template_overview(sections, stats, period_start, period_end)
    result: dict[str, Any] = {
        "overview": template,
        "overviewSource": "template",
        "model": None,
        "error": None,
    }

    ready = llm is not None and bool(getattr(llm, "allow_calls", False))
    if not ready or not sections:
        return result

    if budget is not None:
        try:
            budget.charge(1)
        except BudgetExceeded as exc:
            result["error"] = f"预算熔断，未调模型：{exc}"
            return result

    result["model"] = getattr(getattr(llm, "config", None), "model", None)
    try:
        data = llm.complete_json(
            period_prompt(cfg, sections, period_start, period_end), step="report"
        )
        text = str((data or {}).get("overview") or "")
    except LLMError as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    except Exception as exc:  # noqa: BLE001 - 模型侧任何异常都不该阻断出刊
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    candidate = fitted(text, OVERVIEW_CHARS)
    if candidate and overview_grounded(candidate, corpus, cfg):
        result["overview"] = candidate
        result["overviewSource"] = "model"
    elif text:
        # 校验不过：换成模板句，不报错（计划 §5.5）
        result["error"] = "总述里的名字或数字不在本期条目里，已换成模板句"
    return result


# ══ 主流程 ═══════════════════════════════════════════════════════════════


def build_weekly(
    items: Sequence[Item],
    cfg: ConfigBundle,
    week_str: str,
    *,
    previous_dailies: Iterable[Mapping[str, Any]] | None = None,
    llm: Any | None = None,
    budget: Budget | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """生成一期周报，返回 `docs/report-schema.md` 的周报 JSON。

    参数：
    - `items`：全部条目，用于补齐日报 ItemRef 里没有的字段（分数、链接、分类、tags）；
    - `week_str`：ISO 周号（如 `2026-W43`），汇编这一周的日报；
    - `previous_dailies`：这一周的日报内容（`build_daily` 的返回值即可）；
    - `llm`：可选的 `uxhot.llm.LLMClient`。只有 `allow_calls=True` 才会真的调模型；
      其余情况（None、未就绪、抛错、预算用尽、校验不过）一律退回模板句，不报错；
    - `budget`：可选预算；给了就先 `charge(1)`，超限即退回模板句；
    - `now`：`generatedAt` 的取值（默认当前 UTC 时间），测试可注入固定值。

    「模型只写总述」：`sections[].lead` 恒为空串（契约允许为空）。
    """
    period_start, period_end = week_range(week_str)
    window_start, window_end = weekly_window(week_str)
    items_by_id = {i.id: i for i in items}

    dailies = [
        report
        for report in (previous_dailies or [])
        if not _report_date(report) or period_start <= _report_date(report) <= period_end
    ]

    events = [
        _build_weekly_ref(event, cfg, items_by_id)
        for event in _events_from_dailies(dailies, items_by_id)
    ]
    # 「按出现位置与分数」：排名 = 分数 + 最显眼位置的加分；同分先出现（日期早）的在前
    events.sort(key=lambda e: (-e["rank"], e["days"][0] if e["days"] else "", e["id"]))
    top = events[:WEEKLY_LIMIT]

    sections: list[dict[str, Any]] = []
    for category in cfg.taxonomy.category_keys:
        in_section = [e for e in top if e["ref"].get("category") == category]
        if in_section:
            sections.append(
                {
                    "key": category,
                    "label": category_label(cfg, category),
                    "lead": "",  # 模型只写总述（计划 §5.5），栏目导读留空
                    "items": [e["ref"] for e in in_section],
                }
            )

    stats = {"itemCount": len(top), "dailyCount": len(dailies)}
    corpus = overview_corpus(
        [e["ref"] for e in events], period_start, period_end, week_str
    )
    written = write_overview(
        cfg,
        sections,
        stats,
        corpus,
        period_start,
        period_end,
        llm=llm,
        budget=budget,
    )

    if now is None:
        stamp = datetime.now(timezone.utc)
    else:
        if now.tzinfo is None:
            raise ValueError("now 必须带时区（tz-aware）")
        stamp = now.astimezone(timezone.utc)

    return {
        "kind": "weekly",
        "week": week_str,
        "siteName": cfg.site.name,
        "generatedAt": stamp.isoformat(),
        "window": {"start": window_start, "end": window_end},
        "overview": written["overview"],
        "overviewSource": written["overviewSource"],
        "stats": stats,
        "sections": sections,
    }
