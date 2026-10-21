"""阶段 5 验收：日报/周报规则（计划 §5.4 / §5.5）。

全部用**假 Item** 构造数据：不抓真实信源、不调真实模型。模型路径用鸭子类型的
`FakeLLM`（以及真实 `LLMClient` 的安全阀）验证，绝不发网络请求。

断言分成三层：
1. 规则本身（重要性公式、同信源 ≤2、7 期不重复、正文 12 / 快讯 10、空刊、N 款新工具）；
2. 时间窗与边界（北京 08:00 日界，比较前转 UTC）；
3. `docs/report-schema.md` 的 JSON 契约（顶层字段名、ItemRef 字段集、不含 body）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from uxhot.budget import Budget
from uxhot.config import load_config
from uxhot.llm import LLMClient, LLMConfig, LLMError
from uxhot.models import Item, Status
from uxhot.report import (
    BRIEF_FIELDS,
    ITEM_REF_FIELDS,
    build_daily,
    build_weekly,
    daily_window,
    week_range,
    weekly_window,
    write_overview,
)

BJ = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc
FIXED_NOW = datetime(2026, 10, 22, 0, 5, tzinfo=UTC)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def bj(y: int, m: int, d: int, hour: int = 9, minute: int = 0) -> datetime:
    """北京时间（tz-aware）。测试里所有时间都显式带时区，不依赖运行机器时区。"""
    return datetime(y, m, d, hour, minute, tzinfo=BJ)


def make_item(
    item_id: str,
    *,
    published: datetime | None = None,
    source: str = "src-a",
    category: str | None = "tools",
    item_type: str | None = "tool_launch",
    score: float | None = 80.0,
    relation: str | None = None,
    dup_of: str | None = None,
    status: Status = Status.SELECTED,
    tier: str = "T1",
    title: str | None = None,
    summary: str | None = None,
    reason: str = "为什么值得看",
    tags: tuple[str, ...] = (),
    entities: tuple[str, ...] = (),
) -> Item:
    """造一条假资料。默认落在 `2026-10-21 09:00`（北京），即 2026-10-22 那期的窗口内。"""
    when = published or bj(2026, 10, 21, 9, 0)
    return Item(
        id=item_id,
        sourceId=source,
        tier=tier,
        url=f"https://example.com/{item_id}",
        title=title or f"英文标题 {item_id}",
        publishedAt=when,
        discoveredAt=when,
        status=status,
        avgScore=score,
        itemType=item_type,
        category=category,
        titleZh=title or f"中文标题 {item_id}",
        summaryZh=summary if summary is not None else f"摘要 {item_id}",
        reason=reason,
        tags=list(tags),
        entities=list(entities),
        dupOf=dup_of,
        relation=relation,
        hasNewInfo=True,
    )


def main_refs(report: dict) -> list[dict]:
    """正文条目 = headline + highlights + sections 里的条目（三部分互不重复）。"""
    refs: list[dict] = []
    if report["headline"]:
        refs.append(report["headline"])
    refs.extend(report["highlights"])
    for section in report["sections"]:
        refs.extend(section["items"])
    return refs


def main_ids(report: dict) -> list[str]:
    return [ref["id"] for ref in main_refs(report)]


def brief_ids(report: dict) -> list[str]:
    return [ref["id"] for ref in report["briefs"]]


# ══ 时间窗与边界 ═════════════════════════════════════════════════════════


def test_daily_window_is_previous_08_to_edition_08(cfg) -> None:
    """日报 date 08:00 出刊，覆盖前一天 08:00 → 当天 08:00（北京），输出成 UTC。"""
    start, end = daily_window("2026-10-22")
    assert start == datetime(2026, 10, 21, 0, 0, tzinfo=UTC)  # 北京 10-21 08:00
    assert end == datetime(2026, 10, 22, 0, 0, tzinfo=UTC)    # 北京 10-22 08:00

    report = build_daily([make_item("a")], cfg, "2026-10-22", now=FIXED_NOW)
    assert report["window"] == {
        "start": "2026-10-21T00:00:00+00:00",
        "end": "2026-10-22T00:00:00+00:00",
    }


def test_daily_window_boundaries_are_half_open(cfg) -> None:
    """正好 08:00 的条目：起点那一刻归**本期**，终点那一刻归**下一期**。"""
    items = [
        make_item("start", published=bj(2026, 10, 21, 8, 0), source="s-start"),
        make_item("before", published=bj(2026, 10, 21, 7, 59), source="s-before"),
        make_item("inside", published=bj(2026, 10, 22, 7, 59), source="s-inside"),
        make_item("end", published=bj(2026, 10, 22, 8, 0), source="s-end"),
    ]

    this_issue = build_daily(items, cfg, "2026-10-22", now=FIXED_NOW)
    assert set(main_ids(this_issue)) == {"start", "inside"}

    next_issue = build_daily(items, cfg, "2026-10-23", now=FIXED_NOW)
    assert set(main_ids(next_issue)) == {"end"}

    previous_issue = build_daily(items, cfg, "2026-10-21", now=FIXED_NOW)
    assert set(main_ids(previous_issue)) == {"before"}


def test_window_comparison_is_utc_not_local(cfg) -> None:
    """同一时刻写成 UTC 或北京时间，归期结果必须一致（不依赖运行机器时区）。"""
    as_bj = make_item("bj", published=bj(2026, 10, 22, 7, 0), source="s1")
    as_utc = make_item(
        "utc",
        published=datetime(2026, 10, 21, 23, 0, tzinfo=UTC),  # = 北京 10-22 07:00
        source="s2",
    )
    report = build_daily([as_bj, as_utc], cfg, "2026-10-22", now=FIXED_NOW)
    assert set(main_ids(report)) == {"bj", "utc"}


# ══ 重要性排序 ═══════════════════════════════════════════════════════════


def test_importance_formula_with_multi_source_bonus(cfg) -> None:
    """`重要性 = avgScore + 5×(同事件独立来源数 − 1)`，多来源能把分数拉上来。"""
    items = [
        make_item("solo", score=80.0, source="s1"),
        # 同一事件：1 条原帖 + 2 条同事件（不同信源）
        make_item("multi-a", score=72.0, source="s2", category="research", item_type="research_paper"),
        make_item(
            "multi-b", score=60.0, source="s3", dup_of="multi-a", relation="same",
            category="research", item_type="research_paper",
        ),
        make_item(
            "multi-c", score=55.0, source="s4", dup_of="multi-a", relation="same",
            category="research", item_type="research_paper",
        ),
    ]
    report = build_daily(items, cfg, "2026-10-22", now=FIXED_NOW)

    # 72 + 5×(3−1) = 82 > 80 → 多来源事件排第一
    assert report["headline"]["id"] == "multi-a"
    assert report["headline"]["importance"] == 82.0
    assert report["headline"]["relatedIds"] == ["multi-b", "multi-c"]
    assert main_ids(report) == ["multi-a", "solo"]
    assert report["sections"] == []  # 正文只有 2 条，没有剩余分节条目


def test_same_event_from_one_source_counts_once(cfg) -> None:
    """同事件的两条来自同一信源：独立来源数仍是 1，没有加成。"""
    items = [
        make_item("x", score=70.0, source="s1"),
        make_item("y", score=60.0, source="s1", dup_of="x", relation="followup"),
    ]
    report = build_daily(items, cfg, "2026-10-22", now=FIXED_NOW)
    assert report["headline"]["id"] == "x"
    assert report["headline"]["importance"] == 70.0
    assert main_ids(report) == ["x"]


# ══ 正文规则：同信源 ≤2、正文 ≤12、快讯 ≤10 ══════════════════════════════


def test_same_source_at_most_two_in_main(cfg) -> None:
    """同一信源 3 条：只有 2 条进正文，第 3 条落到快讯。"""
    items = [
        make_item("a1", score=90.0, source="src-s1"),
        make_item("a2", score=85.0, source="src-s1"),
        make_item("a3", score=80.0, source="src-s1"),
        make_item("b1", score=70.0, source="src-s2"),
        make_item("c1", score=60.0, source="src-s3"),
    ]
    report = build_daily(items, cfg, "2026-10-22", now=FIXED_NOW)

    assert main_ids(report) == ["a1", "a2", "b1", "c1"]
    assert brief_ids(report) == ["a3"]
    assert report["stats"]["briefCount"] == 1
    assert set(report["briefs"][0]) == set(BRIEF_FIELDS)


def test_main_at_most_12_and_briefs_at_most_10(cfg) -> None:
    items = [
        make_item(f"i{n:02d}", score=99.0 - n, source=f"src-{n:02d}")
        for n in range(30)
    ]
    report = build_daily(items, cfg, "2026-10-22", now=FIXED_NOW)

    assert len(main_refs(report)) == 12
    # 头条 + 看点 + 分节条目互不重复，合计就是 12（契约里的算法）
    assert len(main_ids(report)) == len(set(main_ids(report)))
    assert report["headline"]["id"] == "i00"
    assert [r["id"] for r in report["highlights"]] == ["i01", "i02", "i03"]
    assert len(report["briefs"]) == 10
    assert brief_ids(report) == [f"i{n:02d}" for n in range(12, 22)]
    assert report["stats"] == {"selectedCount": 30, "newTools": 30, "briefCount": 10}
    # 正文里每个信源最多 2 条（这里每源 1 条）
    assert len({r["sourceId"] for r in main_refs(report)}) == 12


def test_sections_are_grouped_by_category_and_ordered(cfg) -> None:
    """正文第 5 条起按分类分节，栏目顺序跟 taxonomy 一致。"""
    items = [
        make_item("t1", score=90.0, source="s1", category="tools"),
        make_item("t2", score=85.0, source="s2", category="tools"),
        make_item("r1", score=80.0, source="s3", category="research", item_type="research_paper"),
        make_item("r2", score=75.0, source="s4", category="research", item_type="research_paper"),
        make_item("m1", score=70.0, source="s5", category="methods", item_type="method_or_template"),
        make_item("c1", score=65.0, source="s6", category="cases", item_type="case_study"),
    ]
    report = build_daily(items, cfg, "2026-10-22", now=FIXED_NOW)

    assert report["headline"]["id"] == "t1"
    assert [r["id"] for r in report["highlights"]] == ["t2", "r1", "r2"]
    assert [(s["key"], s["label"]) for s in report["sections"]] == [
        ("methods", "方法"),
        ("cases", "案例"),
    ]
    assert [r["id"] for r in report["sections"][0]["items"]] == ["m1"]
    assert report["sections"][0]["items"][0]["categoryLabel"] == "方法"


def test_daily_ignores_non_selected_and_out_of_window_items(cfg) -> None:
    items = [
        make_item("scored", status=Status.SCORED),
        make_item("listed", status=Status.LISTED),
        make_item("old", published=bj(2026, 10, 20, 9, 0)),      # 不在本期窗口
        make_item("ok"),
    ]
    report = build_daily(items, cfg, "2026-10-22", now=FIXED_NOW)
    assert main_ids(report) == ["ok"]
    assert report["stats"]["selectedCount"] == 1


# ══ 最近 7 期不重复 ═══════════════════════════════════════════════════════


def test_repeat_events_go_to_briefs_unless_followup(cfg) -> None:
    """7 期报过的事件：只有 `followup` 且非 commentary 类才进正文，否则进快讯。"""
    previous = [
        {
            "kind": "daily",
            "date": "2026-10-21",
            "headline": {"id": "old-a"},
            "highlights": [],
            "sections": [{"key": "tools", "label": "工具", "items": [{"id": "old-c"}]}],
            "briefs": [{"id": "old-b"}],
        }
    ]
    items = [
        make_item("rep-same", dup_of="old-a", relation="same", score=90.0, source="s1"),
        make_item(
            "rep-follow", dup_of="old-b", relation="followup", score=88.0, source="s2",
            category="research", item_type="research_paper",
        ),
        make_item(
            "rep-commentary", dup_of="old-c", relation="followup", score=87.0, source="s3",
            category="methods", item_type="method_or_template",
        ),
        make_item("fresh", score=60.0, source="s4"),
    ]
    report = build_daily(items, cfg, "2026-10-22", previous_reports=previous, now=FIXED_NOW)

    assert set(main_ids(report)) == {"rep-follow", "fresh"}
    assert set(brief_ids(report)) == {"rep-same", "rep-commentary"}
    # 头条是分数最高的 rep-follow（followup 但非 commentary）
    assert report["headline"]["id"] == "rep-follow"


def test_repeat_check_only_looks_at_last_seven_issues(cfg) -> None:
    """只回看最近 7 期：第 8 期报过的事件可以重新进正文。"""
    previous = [
        {
            "kind": "daily",
            "date": f"2026-10-{day:02d}",
            "headline": {"id": f"old-{day}"},
            "highlights": [],
            "sections": [],
            "briefs": [],
        }
        for day in range(14, 22)  # 10-14 … 10-21，共 8 期
    ]
    items = [
        make_item("from-oldest", dup_of="old-14", relation="same", score=90.0, source="s1"),
        make_item("from-latest", dup_of="old-21", relation="same", score=85.0, source="s2"),
    ]
    report = build_daily(items, cfg, "2026-10-22", previous_reports=previous, now=FIXED_NOW)

    # old-14 是第 8 期，超出 7 期窗口 → 不算报过 → 进正文
    assert main_ids(report) == ["from-oldest"]
    assert brief_ids(report) == ["from-latest"]


def test_no_previous_reports_is_fine(cfg) -> None:
    report = build_daily([make_item("a")], cfg, "2026-10-22", now=FIXED_NOW)
    assert main_ids(report) == ["a"]
    assert report["empty"] is False


# ══ 空刊与报头统计 ═══════════════════════════════════════════════════════


def test_empty_issue_when_nothing_selected(cfg) -> None:
    """没有入选精选 → 空刊，不抛异常。"""
    empty_report = build_daily([], cfg, "2026-10-22", now=FIXED_NOW)
    assert empty_report["empty"] is True
    assert empty_report["headline"] is None
    assert empty_report["highlights"] == []
    assert empty_report["sections"] == []
    assert empty_report["briefs"] == []
    assert empty_report["stats"] == {"selectedCount": 0, "newTools": 0, "briefCount": 0}

    not_selected = build_daily(
        [make_item("a", status=Status.SCORED), make_item("b", status=Status.DUPLICATE)],
        cfg,
        "2026-10-22",
        now=FIXED_NOW,
    )
    assert not_selected["empty"] is True


def test_empty_issue_when_all_repeats(cfg) -> None:
    """入选的全是最近 7 期报过的 `same` 事件 → 没有新东西，也出空刊。"""
    previous = [
        {
            "kind": "daily",
            "date": "2026-10-21",
            "headline": {"id": "old-a"},
            "highlights": [],
            "sections": [],
            "briefs": [],
        }
    ]
    report = build_daily(
        [make_item("again", dup_of="old-a", relation="same")],
        cfg,
        "2026-10-22",
        previous_reports=previous,
        now=FIXED_NOW,
    )
    assert report["empty"] is True
    assert report["headline"] is None
    assert report["briefs"] == []


def test_new_tools_count(cfg) -> None:
    """`newTools` 只数 category==tools 且 itemType==tool_launch 的条数。"""
    items = [
        make_item("tool-1", source="s1", category="tools", item_type="tool_launch"),
        make_item("tool-2", source="s2", category="tools", item_type="tool_launch"),
        make_item("tool-3", source="s3", category="tools", item_type="tool_launch"),
        # 分类对但类型不对
        make_item("how-to", source="s4", category="tools", item_type="tutorial_explainer"),
        # 类型对但分类不对
        make_item("paper", source="s5", category="research", item_type="tool_launch"),
    ]
    report = build_daily(items, cfg, "2026-10-22", now=FIXED_NOW)
    assert report["stats"]["newTools"] == 3
    assert report["stats"]["selectedCount"] == 5
    assert cfg.taxonomy.release["unit"] == "款新工具"


# ══ JSON 契约（docs/report-schema.md）════════════════════════════════════


def test_daily_matches_contract_fields(cfg) -> None:
    items = [
        make_item("t1", score=90.0, source="s1"),
        make_item("t2", score=85.0, source="s2"),
        make_item("t3", score=80.0, source="s3"),
        make_item("t4", score=75.0, source="s4"),
        make_item("m1", score=70.0, source="s5", category="methods", item_type="method_or_template"),
        make_item("x1", score=10.0, source="s6"),
    ]
    report = build_daily(items, cfg, "2026-10-22", now=FIXED_NOW)

    assert set(report) == {
        "kind", "date", "siteName", "generatedAt", "window", "empty",
        "stats", "headline", "highlights", "sections", "briefs",
    }
    assert report["kind"] == "daily"
    assert report["date"] == "2026-10-22"
    assert report["siteName"] == cfg.site.name
    assert report["generatedAt"] == "2026-10-22T00:05:00+00:00"
    assert set(report["stats"]) == {"selectedCount", "newTools", "briefCount"}

    refs = main_refs(report) + report["briefs"]
    for one in refs:
        assert "body" not in one
    names = {s.id: s.name for s in cfg.sources.sources}
    for one in main_refs(report):
        assert set(one) == set(ITEM_REF_FIELDS)
        if one["sourceId"] in names:
            assert one["sourceName"] == names[one["sourceId"]]
        assert one["publishedAt"] is not None
        assert datetime.fromisoformat(one["publishedAt"]).tzinfo is not None
    for brief in report["briefs"]:
        assert set(brief) == set(BRIEF_FIELDS)

    assert "body" not in json.dumps(report, ensure_ascii=False)


def test_item_ref_uses_config_source_name_and_category_label(cfg) -> None:
    source = cfg.sources.sources[0]
    report = build_daily(
        [make_item("a", source=source.id, category="tools")],
        cfg,
        "2026-10-22",
        now=FIXED_NOW,
    )
    headline = report["headline"]
    assert headline["sourceName"] == source.name
    assert headline["categoryLabel"] == "工具"
    assert headline["titleZh"] == "中文标题 a"
    assert headline["avgScore"] == 80.0


# ══ 周报：区间、排序、去重、模板句 ═══════════════════════════════════════


def ref(
    item_id: str,
    *,
    score: float = 80.0,
    category: str = "tools",
    related: tuple[str, ...] = (),
    summary: str = "",
    source: str = "src-a",
) -> dict:
    """造一个日报 ItemRef（周报测试的输入）。"""
    labels = {
        "tools": "工具",
        "methods": "方法",
        "research": "论文",
        "industry": "行业",
        "cases": "案例",
        "opinion": "观点",
    }
    return {
        "id": item_id,
        "titleZh": f"中文标题 {item_id}",
        "summaryZh": summary or f"摘要 {item_id}",
        "reason": "为什么值得看",
        "category": category,
        "categoryLabel": labels.get(category, category),
        "sourceId": source,
        "sourceName": "示例来源",
        "tier": "T1",
        "url": f"https://example.com/{item_id}",
        "publishedAt": "2026-10-19T01:00:00+00:00",
        "avgScore": score,
        "importance": score,
        "tags": ["工具发布"],
        "relatedIds": list(related),
    }


def fake_daily(
    date_str: str,
    *,
    headline: dict | None = None,
    highlights: tuple[dict, ...] = (),
    main: tuple[dict, ...] = (),
    briefs: tuple[dict, ...] = (),
) -> dict:
    """造一份日报（形状与 `build_daily` 的输出一致）。"""
    return {
        "kind": "daily",
        "date": date_str,
        "siteName": "UXHOT",
        "generatedAt": f"{date_str}T00:05:00+00:00",
        "window": {"start": f"{date_str}T00:00:00+00:00", "end": f"{date_str}T00:00:00+00:00"},
        "empty": headline is None,
        "stats": {"selectedCount": 0, "newTools": 0, "briefCount": len(briefs)},
        "headline": headline,
        "highlights": list(highlights),
        "sections": [{"key": "tools", "label": "工具", "items": list(main)}] if main else [],
        "briefs": list(briefs),
    }


class FakeLLM:
    """鸭子类型的 LLMClient：只实现 `allow_calls` / `config` / `complete_json`。"""

    def __init__(self, payload=None, *, allow_calls: bool = True, error: Exception | None = None):
        self.allow_calls = allow_calls
        self.config = SimpleNamespace(model="fake-model")
        self.calls: list[str] = []
        self._payload = payload
        self._error = error

    def complete_json(self, prompt: str, *, step: str = "score", **kwargs):
        self.calls.append(prompt)
        if self._error is not None:
            raise self._error
        return self._payload


def test_week_range_and_window(cfg) -> None:
    assert week_range("2026-W43") == ("2026-10-19", "2026-10-25")
    assert weekly_window("2026-W43") == (
        "2026-10-19T00:00:00+00:00",
        "2026-10-26T00:00:00+00:00",
    )
    with pytest.raises(ValueError):
        week_range("2026-43")
    with pytest.raises(ValueError):
        week_range("2026-W99")


def test_weekly_ranks_by_position_and_score(cfg) -> None:
    """「按出现位置与分数」：头条加分能让 90 分压过 95 分。"""
    dailies = [
        fake_daily(
            "2026-10-19",
            headline=ref("A", score=90.0),
            briefs=(ref("B", score=95.0),),
            main=(ref("C", score=94.0),),
        )
    ]
    report = build_weekly([], cfg, "2026-W43", previous_dailies=dailies, now=FIXED_NOW)
    ids = [r["id"] for s in report["sections"] for r in s["items"]]
    assert ids[0] == "A"   # 90 + 6 = 96
    assert ids[1] == "B"   # 95 + 0 = 95
    assert ids[2] == "C"   # 94 + 1 = 95，同分按日期/id 稳定排序


def test_weekly_takes_top_20(cfg) -> None:
    dailies = [
        fake_daily(
            "2026-10-19",
            headline=ref("h0", score=99.0),
            briefs=tuple(ref(f"b{n:02d}", score=float(90 - n)) for n in range(25)),
        )
    ]
    report = build_weekly([], cfg, "2026-W43", previous_dailies=dailies, now=FIXED_NOW)
    total = sum(len(s["items"]) for s in report["sections"])
    assert total == 20
    assert report["stats"] == {"itemCount": 20, "dailyCount": 1}


def test_weekly_counts_same_event_across_days_once(cfg) -> None:
    """同一事件跨天只算一件（靠日报 ItemRef 的 relatedIds 归并）。"""
    dailies = [
        fake_daily("2026-10-19", headline=ref("X", score=80.0)),
        fake_daily("2026-10-20", main=(ref("X2", score=70.0, related=("X",)),)),
    ]
    report = build_weekly([], cfg, "2026-W43", previous_dailies=dailies, now=FIXED_NOW)
    items = [r for s in report["sections"] for r in s["items"]]
    assert len(items) == 1
    assert items[0]["id"] == "X"
    assert items[0]["relatedIds"] == ["X2"]


def test_weekly_ignores_dailies_outside_the_week(cfg) -> None:
    dailies = [
        fake_daily("2026-10-12", headline=ref("lastweek")),  # 上一周
        fake_daily("2026-10-20", headline=ref("thisweek")),
    ]
    report = build_weekly([], cfg, "2026-W43", previous_dailies=dailies, now=FIXED_NOW)
    ids = [r["id"] for s in report["sections"] for r in s["items"]]
    assert ids == ["thisweek"]
    assert report["stats"]["dailyCount"] == 1


def test_weekly_matches_contract_fields(cfg) -> None:
    dailies = [
        fake_daily(
            "2026-10-19",
            headline=ref("h", score=90.0),
            highlights=(ref("g1", score=85.0),),
            main=(ref("m1", score=80.0, category="methods"),),
        )
    ]
    report = build_weekly([], cfg, "2026-W43", previous_dailies=dailies, now=FIXED_NOW)

    assert set(report) == {
        "kind", "week", "siteName", "generatedAt", "window",
        "overview", "overviewSource", "stats", "sections",
    }
    assert report["kind"] == "weekly"
    assert report["week"] == "2026-W43"
    assert report["siteName"] == cfg.site.name
    assert report["overviewSource"] in {"model", "template"}
    assert set(report["stats"]) == {"itemCount", "dailyCount"}
    for section in report["sections"]:
        assert set(section) == {"key", "label", "lead", "items"}
        assert section["lead"] == ""  # 模型只写总述
        for item in section["items"]:
            assert set(item) == set(ITEM_REF_FIELDS)
    assert "body" not in json.dumps(report, ensure_ascii=False)


def test_weekly_empty_period_does_not_raise(cfg) -> None:
    report = build_weekly([], cfg, "2026-W43", now=FIXED_NOW)
    assert report["stats"] == {"itemCount": 0, "dailyCount": 0}
    assert report["sections"] == []
    assert report["overviewSource"] == "template"
    assert "没有可汇编" in report["overview"]


# ══ 周报总述：默认模板句、模型可选、校验不过换模板句 ═════════════════════


def test_weekly_uses_template_without_llm(cfg) -> None:
    dailies = [fake_daily("2026-10-19", headline=ref("A", score=90.0))]
    report = build_weekly([], cfg, "2026-W43", previous_dailies=dailies, now=FIXED_NOW)
    assert report["overviewSource"] == "template"
    assert "汇编 1 期日报" in report["overview"]


def test_weekly_does_not_call_llm_when_not_ready(cfg) -> None:
    """`allow_calls=False`（默认 dry-run）时一次模型都不调。"""
    fake = FakeLLM({"overview": "Qualtrics 有新动作。"}, allow_calls=False)
    dailies = [fake_daily("2026-10-19", headline=ref("A", score=90.0))]
    report = build_weekly(
        [], cfg, "2026-W43", previous_dailies=dailies, llm=fake, now=FIXED_NOW
    )
    assert fake.calls == []
    assert report["overviewSource"] == "template"


def test_weekly_falls_back_when_real_client_is_not_ready(cfg) -> None:
    """真实 LLMClient 的安全阀：没开 `MODEL_CALLS_ENABLED` 时抛错 → 退回模板句。"""
    client = LLMClient(LLMConfig(api_key="", calls_enabled=False), allow_calls=True)
    dailies = [fake_daily("2026-10-19", headline=ref("A", score=90.0))]
    report = build_weekly(
        [], cfg, "2026-W43", previous_dailies=dailies, llm=client, now=FIXED_NOW
    )
    assert report["overviewSource"] == "template"
    assert client.call_count == 0  # 一次真实调用都没发生


def test_weekly_falls_back_when_model_errors(cfg) -> None:
    fake = FakeLLM(error=LLMError("模型挂了"))
    dailies = [fake_daily("2026-10-19", headline=ref("A", score=90.0))]
    report = build_weekly(
        [], cfg, "2026-W43", previous_dailies=dailies, llm=fake, now=FIXED_NOW
    )
    assert report["overviewSource"] == "template"
    assert len(fake.calls) == 1


def test_weekly_overview_rejects_fabricated_company(cfg) -> None:
    """总述里编造条目里没有的公司名 → 换成模板句，不报错。"""
    dailies = [fake_daily("2026-10-19", headline=ref("A", score=90.0))]
    fake = FakeLLM({"overview": "FakeCorp 发布了合成用户工具，值得关注。"})
    report = build_weekly(
        [], cfg, "2026-W43", previous_dailies=dailies, llm=fake, now=FIXED_NOW
    )
    assert report["overviewSource"] == "template"
    assert "FakeCorp" not in report["overview"]
    assert "汇编 1 期日报" in report["overview"]


def test_weekly_overview_rejects_fabricated_numbers(cfg) -> None:
    dailies = [fake_daily("2026-10-19", headline=ref("A", score=90.0))]
    for bad in ("本期融资 5000 万美元。", "使用率提升了 95%。"):
        fake = FakeLLM({"overview": bad})
        report = build_weekly(
            [], cfg, "2026-W43", previous_dailies=dailies, llm=fake, now=FIXED_NOW
        )
        assert report["overviewSource"] == "template", bad


def test_weekly_overview_accepts_grounded_text(cfg) -> None:
    """名字和数字都在本期条目里 → 用模型写的总述。"""
    dailies = [
        fake_daily(
            "2026-10-19",
            headline=ref("A", score=90.0, summary="Qualtrics 发布新工具，覆盖三家厂商。"),
        )
    ]
    text = "Qualtrics 发布新工具，本周工具类有新进展。"
    fake = FakeLLM({"overview": text})
    report = build_weekly(
        [], cfg, "2026-W43", previous_dailies=dailies, llm=fake, now=FIXED_NOW
    )
    assert report["overviewSource"] == "model"
    assert report["overview"] == text
    assert len(fake.calls) == 1


def test_write_overview_reports_why_it_fell_back(cfg) -> None:
    """诊断信息不进 JSON（契约严格），但 `write_overview` 要能说清原因。"""
    dailies = [fake_daily("2026-10-19", headline=ref("A", score=90.0))]
    report = build_weekly([], cfg, "2026-W43", previous_dailies=dailies, now=FIXED_NOW)
    sections = report["sections"]
    stats = report["stats"]
    fake = FakeLLM({"overview": "FakeCorp 上线了新工具。"})
    written = write_overview(
        cfg,
        sections,
        stats,
        "中文标题 A 摘要 A",
        "2026-10-19",
        "2026-10-25",
        llm=fake,
    )
    assert written["overviewSource"] == "template"
    assert "模板句" in (written["error"] or "")
    assert written["model"] == "fake-model"


def test_write_overview_respects_budget(tmp_path, cfg) -> None:
    """预算用尽时连模型都不调，直接退回模板句。"""
    budget = Budget(per_run_calls=0, per_day_calls=0, state_dir=tmp_path)
    dailies = [fake_daily("2026-10-19", headline=ref("A", score=90.0))]
    fake = FakeLLM({"overview": "Qualtrics 有新动作。"})
    report = build_weekly(
        [], cfg, "2026-W43", previous_dailies=dailies, llm=fake, budget=budget, now=FIXED_NOW
    )
    assert fake.calls == []
    assert report["overviewSource"] == "template"


# ══ 周报：从真实日报端到端 ═══════════════════════════════════════════════


def test_weekly_from_real_dailies(cfg) -> None:
    """用 `build_daily` 真出的一周日报喂给周报（不调模型）。"""
    items: list[Item] = []
    for index, day in enumerate(range(19, 26)):  # 10-19 … 10-25
        for n in range(2):
            items.append(
                make_item(
                    f"d{day}-{n}",
                    published=bj(2026, 10, day, 7, 0),
                    source=f"src-{day}-{n}",
                    score=70.0 + index + n,
                )
            )
    dailies = [
        build_daily(items, cfg, f"2026-10-{day:02d}", now=FIXED_NOW)
        for day in range(19, 26)
    ]
    assert all(not d["empty"] for d in dailies)

    report = build_weekly(items, cfg, "2026-W43", previous_dailies=dailies, now=FIXED_NOW)
    assert report["stats"]["dailyCount"] == 7
    assert report["stats"]["itemCount"] == 14
    assert report["overviewSource"] == "template"
    ids = [r["id"] for s in report["sections"] for r in s["items"]]
    assert len(ids) == 14
    assert len(set(ids)) == 14
