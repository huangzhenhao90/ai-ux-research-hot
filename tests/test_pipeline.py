"""阶段 5 验收：采集规则、日期与时区、门槛边界、预算熔断、假 LLM 端到端。

端到端用 `tests/fixtures/` 里 3 个本地 RSS XML，**不访问网络**；模型步骤用假 LLM，
**不发起真实调用**。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from uxhot.budget import Budget, BudgetExceeded
from uxhot.collect import external_json, rss
from uxhot.collect.dates import (
    is_future,
    is_stale,
    parse_date,
    resolve_published_at,
)
from uxhot.config import load_config
from uxhot.models import Item, Status, make_id
from uxhot.pipeline import dedupe, prefilter, score, select, structure, write
from uxhot.pipeline.common import StepContext
from uxhot.pipeline.normalize import (
    canonicalize_url,
    is_same_title,
    title_similarity,
)

FIXTURES = Path(__file__).parent / "fixtures"

# 固定「现在」，让所有时间断言与运行机器的当前时间、时区无关
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


# ══ 假 LLM（不发起任何真实调用）════════════════════════════════════════


class FakeLLM:
    """按 step 返回预设结果的假客户端。"""

    def __init__(
        self,
        *,
        prefilter_label: str = "PASS",
        scores: tuple[int, ...] = (80, 80),
        understand: dict | None = None,
        group_relation: str = "different",
        has_new_info: bool = True,
    ) -> None:
        self.prefilter_label = prefilter_label
        self.scores = list(scores)
        self.understand = understand or {
            "itemType": "tool_launch",
            "authorRole": "principal",
            "tags": ["工具发布", "AI 访谈"],
            "editorialJudgment": "原文给出了能力变化与开放档位，研究员可以据此判断它如何改变现有访谈流程。",
            "titleZh": "某平台发布 AI 访谈功能",
            "summaryZh": "某平台发布 AI 访谈功能，给出开放档位与主要能力变化。",
        }
        self.group_relation = group_relation
        self.has_new_info = has_new_info
        self.calls: list[str] = []
        self._score_index = 0

    def complete_json(self, prompt, *, step="score", **kwargs):
        self.calls.append(step)
        if step == "prefilter":
            return {"label": self.prefilter_label, "reason": "测试"}
        if step == "score":
            value = self.scores[self._score_index % len(self.scores)]
            self._score_index += 1
            return {"attentionScore": value}
        if step == "structure":
            return {"category": "tools", "tags": ["工具发布"], "subjects": [], "scope": "single", "fact": None}
        if step == "write":
            return dict(self.understand)
        if step == "group":
            return {"relation": self.group_relation, "hasNewInfo": self.has_new_info, "reason": "测试"}
        return {}

    def complete_text(self, prompt, *, step="write", **kwargs):
        self.calls.append(step)
        return "title_zh: 测试标题\nsummary_zh: 测试摘要，包含核心事实。"

    @property
    def step_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for step in self.calls:
            out[step] = out.get(step, 0) + 1
        return out


def make_ctx(cfg, llm=None, *, dry_run=False, state_dir: Path | None = None, now=NOW) -> StepContext:
    budget = Budget(
        per_run_calls=cfg.selection.budget["perRunCalls"],
        per_day_calls=cfg.selection.budget["perDayCalls"],
        state_dir=state_dir or Path("/tmp/uxhot-test-budget"),
        now=now,
    )
    return StepContext(cfg=cfg, budget=budget, client=llm, dry_run=dry_run)


def load_fixture(name: str, **kwargs) -> list[Item]:
    raw = (FIXTURES / name).read_bytes()
    entries = rss.parse_feed(raw, "+00:00", now=NOW)
    return rss.build_items(entries, **kwargs, now=NOW)


# ══ URL 规范化 ═════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "raw,expected",
    [
        # 去追踪参数
        ("https://a.com/post?utm_source=x&utm_medium=y", "https://a.com/post"),
        ("https://a.com/post?id=1&utm_campaign=z", "https://a.com/post?id=1"),
        # 去 fragment
        ("https://a.com/post#section", "https://a.com/post"),
        # 去尾斜杠（根路径除外）
        ("https://a.com/post/", "https://a.com/post"),
        ("https://a.com/", "https://a.com/"),
        # 去 www
        ("https://www.a.com/post", "https://a.com/post"),
        # query 排序
        ("https://a.com/p?b=2&a=1", "https://a.com/p?a=1&b=2"),
        # 默认端口
        ("https://a.com:443/post", "https://a.com/post"),
        # fbclid 等
        ("https://a.com/p?fbclid=abc", "https://a.com/p"),
        # 大写 scheme/host
        ("HTTPS://A.COM/Post", "https://a.com/Post"),
    ],
)
def test_canonicalize_url(raw: str, expected: str) -> None:
    assert canonicalize_url(raw) == expected


def test_canonicalize_keeps_query_for_id_in_query_hosts() -> None:
    """ACM / SAGE 这类站点的文章 id 在 query 里，不能整段丢掉。"""
    url = "https://dl.acm.org/action/showFeed?type=etoc&feed=rss&jc=JTOCI"
    assert "jc=JTOCI" in canonicalize_url(url)


def test_same_article_different_tracking_gets_same_id() -> None:
    a = make_id(canonicalize_url("https://a.com/post?utm_source=rss"))
    b = make_id(canonicalize_url("https://www.a.com/post/"))
    assert a == b


# ══ 标题相似度与机械去重 ═══════════════════════════════════════════════


def test_title_similarity_detects_near_duplicates() -> None:
    assert is_same_title(
        "Acme launches AI-moderated interview feature",
        "Acme launches AI moderated interview feature!",
    )
    assert not is_same_title(
        "Acme launches AI-moderated interview feature",
        "Dovetail adds synthetic respondent validation checks",
    )


def _item(title: str, url: str, *, published=NOW, tier="T1", status=Status.NEW) -> Item:
    return Item(
        id=make_id(canonicalize_url(url)),
        sourceId="s",
        tier=tier,
        url=url,
        canonicalUrl=canonicalize_url(url),
        title=title,
        publishedAt=published,
        discoveredAt=NOW,
        status=status,
    )


def test_dedupe_marks_near_duplicate_and_keeps_better_tier() -> None:
    t2 = _item("Acme launches AI-moderated interview feature", "https://t2.com/a", tier="T2")
    t1 = _item("Acme launches AI moderated interview feature", "https://t1.com/a", tier="T1")
    items = dedupe.run([t2, t1], threshold=92, window_hours=72)

    # T1 优先保留，T2 被判重复
    assert t1.dupOf is None
    assert t2.dupOf == t1.id
    assert t2.status is Status.DUPLICATE


def test_dedupe_ignores_items_outside_window() -> None:
    old = _item("Same title here", "https://a.com/1", published=NOW - timedelta(days=10))
    new = _item("Same title here", "https://b.com/2", published=NOW)
    items = dedupe.run([old, new], threshold=92, window_hours=72)
    assert all(i.dupOf is None for i in items)


# ══ 日期与时区 ═════════════════════════════════════════════════════════


def test_naive_date_uses_source_timezone() -> None:
    """无时区的日期按信源时区解析。"""
    dt = parse_date("2026-10-21 09:00:00", "+08:00")
    assert dt is not None
    assert dt.utcoffset() == timedelta(hours=8)
    # 09:00 +08:00 == 01:00 UTC
    assert dt.astimezone(timezone.utc).hour == 1


def test_explicit_offset_is_respected() -> None:
    dt = parse_date("2026-10-21T09:00:00+00:00", "+08:00")
    assert dt.astimezone(timezone.utc).hour == 9


def test_year_month_only_date() -> None:
    dt = parse_date("2026-10", "+08:00")
    assert dt is not None and dt.year == 2026 and dt.month == 10 and dt.day == 1


def test_future_date_is_rejected() -> None:
    """期刊提前标的未来期号不能当可信日期（ur-ai-papers 的 2027-01）。"""
    dt, issue = resolve_published_at("2027-01", "+08:00", now=NOW)
    assert dt is None
    assert issue == "future_date"


def test_near_future_within_tolerance_is_accepted() -> None:
    """轻微时钟偏差不应被判成未来。"""
    dt, issue = resolve_published_at("2026-10-21T18:00:00+00:00", "+00:00", now=NOW)
    assert dt is not None and issue is None


def test_is_stale_uses_fresh_hours() -> None:
    fresh = NOW - timedelta(hours=10)
    stale = NOW - timedelta(hours=72)
    assert not is_stale(fresh, 48, NOW)
    assert is_stale(stale, 48, NOW)
    # 无可信日期 → 当作不新鲜
    assert is_stale(None, 48, NOW)


def test_timezone_result_independent_of_machine_tz() -> None:
    """同一输入在不同机器时区下必须得到同一 UTC 时刻。"""
    dt = parse_date("2026-10-21 09:00:00", "+08:00")
    assert dt.astimezone(timezone.utc) == datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc)


# ══ 旧文不刷屏 ═════════════════════════════════════════════════════════


def test_first_import_archives_everything_and_limits_count() -> None:
    items = load_fixture(
        "feed_t1_recent.xml",
        source_id="t1", source_name="T1", tier="T1",
        initial_backfill_limit=2, fresh_hours=48, first_import=True,
    )
    assert len(items) == 2, "首次导入只取前 initialBackfillLimit 条"
    assert all(i.status is Status.ARCHIVED for i in items)


def test_stale_items_archived_on_normal_import() -> None:
    items = load_fixture(
        "feed_t1_recent.xml",
        source_id="t1", source_name="T1", tier="T1",
        initial_backfill_limit=8, fresh_hours=48, first_import=False,
    )
    by_title = {i.title: i for i in items}
    assert by_title["Acme launches AI-moderated interview feature"].status is Status.NEW
    assert by_title["Old post from two weeks ago"].status is Status.ARCHIVED


def test_items_without_date_are_not_public() -> None:
    """无可信日期 → 不公开，下次再试。"""
    items = load_fixture(
        "feed_no_dates.xml",
        source_id="nd", source_name="ND", tier="T1",
        initial_backfill_limit=8, fresh_hours=48, first_import=False,
    )
    assert items, "应当解析出条目"
    for item in items:
        assert item.status is Status.UNKNOWN
        assert not item.is_public


def test_future_dated_feed_item_not_treated_as_fresh() -> None:
    items = load_fixture(
        "feed_no_dates.xml",
        source_id="nd", source_name="ND", tier="T1",
        initial_backfill_limit=8, fresh_hours=48, first_import=False,
    )
    future = [i for i in items if "future" in i.url]
    assert future, "fixture 里应有未来日期的条目"
    assert future[0].publishedAt is None
    assert future[0].status is Status.UNKNOWN


def test_tracking_params_stripped_when_collecting() -> None:
    items = load_fixture(
        "feed_t1_recent.xml",
        source_id="t1", source_name="T1", tier="T1",
        initial_backfill_limit=8, fresh_hours=48, first_import=False,
    )
    acme = next(i for i in items if "Acme" in i.title)
    assert "utm_source" not in acme.canonicalUrl
    assert acme.canonicalUrl == "https://fixture-t1.example.com/blog/ai-interview"


# ══ 门槛判定 ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "scores,threshold,expected",
    [
        ((60, 60), 60, True),    # 和 == 2×门槛，边界值应通过
        ((59, 60), 60, False),   # 和 119 < 120
        ((61, 59), 60, True),
        ((76, 75), 76, False),   # 和 151 < 152，差一分就不过
        ((76, 76), 76, True),    # 正好 2×门槛
    ],
)
def test_threshold_boundary(cfg, scores, threshold, expected) -> None:
    item = _item("t", "https://x.com/1")
    item.scores = list(scores)
    item.avgScore = sum(scores) / len(scores)
    item.tier = "T1"
    ctx = make_ctx(cfg)
    # 还原成改之前的值，而不是写死某个数字——否则门槛一改，这里会把配置留成脏的
    original = ctx.cfg.selection.thresholds["T1"]
    ctx.cfg.selection.thresholds["T1"] = threshold
    try:
        assert score.passes_threshold(item, ctx) is expected
    finally:
        ctx.cfg.selection.thresholds["T1"] = original


def test_exactly_double_threshold_passes(cfg) -> None:
    """和正好等于 2×门槛 → 通过。门槛从配置读，不写死数字。"""
    ctx = make_ctx(cfg)
    limit = ctx.cfg.selection.thresholds["T2"]
    item = _item("t", "https://x.com/1")
    item.scores = [limit, limit]
    item.tier = "T2"
    assert sum(item.scores) == 2 * limit
    assert score.passes_threshold(item, ctx)


def test_one_below_double_threshold_fails(cfg) -> None:
    """和比 2×门槛少 1 分 → 不通过。"""
    ctx = make_ctx(cfg)
    limit = ctx.cfg.selection.thresholds["T2"]
    item = _item("t", "https://x.com/1")
    item.scores = [limit, limit - 1]
    item.tier = "T2"
    assert not score.passes_threshold(item, ctx)


# ══ 预算熔断 ═══════════════════════════════════════════════════════════


def test_budget_blocks_after_per_run_limit(tmp_path: Path) -> None:
    budget = Budget(per_run_calls=3, per_day_calls=100, state_dir=tmp_path, now=NOW)
    for _ in range(3):
        budget.charge(1)
    assert budget.remaining == 0
    with pytest.raises(BudgetExceeded, match="额度用尽"):
        budget.charge(1)


def test_budget_per_day_limit_across_runs(tmp_path: Path) -> None:
    first = Budget(per_run_calls=100, per_day_calls=5, state_dir=tmp_path, now=NOW)
    first.charge(5)
    first.save()

    # 模拟同一天的下一次运行
    second = Budget(per_run_calls=100, per_day_calls=5, state_dir=tmp_path, now=NOW)
    assert second.day_calls == 5
    assert second.remaining == 0
    with pytest.raises(BudgetExceeded):
        second.charge(1)


def test_budget_resets_on_new_day(tmp_path: Path) -> None:
    first = Budget(per_run_calls=100, per_day_calls=5, state_dir=tmp_path, now=NOW)
    first.charge(5)
    first.save()

    tomorrow = Budget(
        per_run_calls=100, per_day_calls=5, state_dir=tmp_path,
        now=NOW + timedelta(days=1),
    )
    assert tomorrow.day_calls == 0, "新的一天日计数归零"
    # remaining 取「本次剩余」与「当日剩余」里更紧的：min(100, 5) = 5
    assert tomorrow.day_remaining == 5
    assert tomorrow.remaining == 5


def test_budget_charge_does_not_count_when_exceeding(tmp_path: Path) -> None:
    budget = Budget(per_run_calls=2, per_day_calls=100, state_dir=tmp_path, now=NOW)
    budget.charge(2)
    with pytest.raises(BudgetExceeded):
        budget.charge(1)
    assert budget.run_calls == 2, "超限的那次不应被记账"


def test_step_context_stops_calling_when_budget_exhausted(cfg, tmp_path: Path) -> None:
    """预算用尽后不再调用，但已完成的保留。"""
    llm = FakeLLM()
    ctx = make_ctx(cfg, llm, state_dir=tmp_path)
    ctx.budget.per_run_calls = 2

    items = [
        _item(f"t{i}", f"https://x.com/{i}", status=Status.PREFILTERED)
        for i in range(5)
    ]
    score.run(items, ctx)

    assert len(llm.calls) <= 2, f"超出预算仍调用了 {len(llm.calls)} 次"
    # 至少有一条拿到完整两次评分
    assert any(len(i.scores) == 2 for i in items)


# ══ 模型步骤行为 ═══════════════════════════════════════════════════════


def test_dry_run_makes_no_calls(cfg, tmp_path: Path) -> None:
    llm = FakeLLM()
    ctx = make_ctx(cfg, llm, dry_run=True, state_dir=tmp_path)
    items = [_item(f"t{i}", f"https://x.com/{i}", status=Status.NEW) for i in range(4)]

    prefilter.run(items, ctx)
    score.run(items, ctx)

    assert llm.calls == [], "dry-run 不能真的调用"
    # 4 条 × (1 预筛 + 2 评分) = 12
    assert ctx.budget.run_calls == 12


def test_prefilter_block_makes_item_not_public(cfg, tmp_path: Path) -> None:
    llm = FakeLLM(prefilter_label="BLOCK")
    ctx = make_ctx(cfg, llm, state_dir=tmp_path)
    items = [_item("t", "https://x.com/1")]
    prefilter.run(items, ctx)
    assert items[0].status is Status.BLOCKED
    assert not items[0].is_public


def test_prefilter_unknown_not_public(cfg, tmp_path: Path) -> None:
    llm = FakeLLM(prefilter_label="UNKNOWN")
    ctx = make_ctx(cfg, llm, state_dir=tmp_path)
    items = [_item("t", "https://x.com/1")]
    prefilter.run(items, ctx)
    assert items[0].status is Status.UNKNOWN
    assert not items[0].is_public


def test_exclude_tier_is_not_scored(cfg, tmp_path: Path) -> None:
    """EXCLUDE 分级（hot_signal）不评分。"""
    llm = FakeLLM()
    ctx = make_ctx(cfg, llm, state_dir=tmp_path)
    item = _item("t", "https://x.com/1", tier="EXCLUDE")
    prefilter.run([item], ctx)
    score.run([item], ctx)
    assert llm.calls == []
    assert item.scores == []


def test_hot_signal_mode_is_not_scored(cfg, tmp_path: Path) -> None:
    llm = FakeLLM()
    ctx = make_ctx(cfg, llm, state_dir=tmp_path)
    item = _item("t", "https://x.com/1")
    item.mode = "hot_signal"
    prefilter.run([item], ctx)
    score.run([item], ctx)
    assert llm.calls == []


def test_structure_drops_tags_outside_whitelist(cfg, tmp_path: Path) -> None:
    class BadTagsLLM(FakeLLM):
        def complete_json(self, prompt, *, step="score", **kwargs):
            if step == "structure":
                self.calls.append(step)
                return {
                    "category": "tools",
                    "tags": ["工具发布", "编造出来的标签"],
                    "subjects": ["不存在的公司"],
                    "scope": "single",
                    "fact": None,
                }
            return super().complete_json(prompt, step=step, **kwargs)

    llm = BadTagsLLM()
    ctx = make_ctx(cfg, llm, state_dir=tmp_path)
    item = _item("t", "https://x.com/1", status=Status.PREFILTERED)
    structure.run([item], ctx)

    assert "工具发布" in item.tags
    assert "编造出来的标签" not in item.tags
    assert item.entities == []
    assert any("白名单外" in e for e in item.errors)


def test_structure_rejects_unknown_category(cfg, tmp_path: Path) -> None:
    class BadCatLLM(FakeLLM):
        def complete_json(self, prompt, *, step="score", **kwargs):
            if step == "structure":
                self.calls.append(step)
                return {"category": "不存在的分类", "tags": [], "subjects": [], "scope": "single", "fact": None}
            return super().complete_json(prompt, step=step, **kwargs)

    ctx = make_ctx(cfg, BadCatLLM(), state_dir=tmp_path)
    item = _item("t", "https://x.com/1", status=Status.PREFILTERED)
    structure.run([item], ctx)
    assert item.category is None
    assert any("未知分类" in e for e in item.errors)


def test_write_uses_deep_prompt_for_high_scores(cfg, tmp_path: Path) -> None:
    llm = FakeLLM(scores=(90, 90))
    ctx = make_ctx(cfg, llm, state_dir=tmp_path)
    item = _item("t", "https://x.com/1")
    item.scores = [90, 90]
    item.avgScore = 90.0
    item.status = Status.SCORED

    write.run([item], ctx)
    assert "write" in llm.calls
    assert item.titleZh == "某平台发布 AI 访谈功能"
    assert item.reason


def test_write_falls_back_to_short_prompt_for_low_scores(cfg, tmp_path: Path) -> None:
    llm = FakeLLM(scores=(30, 30))
    ctx = make_ctx(cfg, llm, state_dir=tmp_path)
    item = _item("t", "https://x.com/1")
    item.body = "Some article body about a research tool."
    item.scores = [30, 30]
    item.avgScore = 30.0
    item.status = Status.SCORED

    write.run([item], ctx)
    assert item.titleZh == "测试标题", "低于 understandFloor 应用 summarize-* 的短写法"
    assert item.reason is None, "短写法不应产出推荐理由"


def test_write_drops_fabricated_entity(cfg, tmp_path: Path) -> None:
    """标题里出现的实体名若原文没有，重写后仍不过就删名（防张冠李戴）。"""
    body = "Acme released a new research tool today."

    class FabricatingLLM(FakeLLM):
        def complete_json(self, prompt, *, step="score", **kwargs):
            if step == "write":
                self.calls.append(step)
                return {
                    "itemType": "tool_launch",
                    "authorRole": "principal",
                    "tags": ["工具发布"],
                    "editorialJudgment": "工具更新值得关注。",
                    "titleZh": "Dovetail 发布新研究工具",
                    "summaryZh": "Dovetail 发布了新的研究工具。",
                }
            return super().complete_json(prompt, step=step, **kwargs)

    ctx = make_ctx(cfg, FabricatingLLM(), state_dir=tmp_path)
    item = _item("Acme released a new research tool", "https://x.com/1")
    item.body = body
    item.entities = ["dovetail"]
    item.scores = [90, 90]
    item.avgScore = 90.0
    item.status = Status.SCORED

    write.run([item], ctx)

    assert "Dovetail" not in (item.titleZh or "")
    assert any("原文没有的实体" in e for e in item.errors)


def test_select_marks_duplicate_when_same_and_no_new_info(cfg, tmp_path: Path) -> None:
    llm = FakeLLM(group_relation="same", has_new_info=False)
    ctx = make_ctx(cfg, llm, state_dir=tmp_path)

    recent = _item("Original story", "https://a.com/1", status=Status.SELECTED)
    item = _item("Follow-up coverage", "https://b.com/2")
    item.scores = [90, 90]
    item.avgScore = 90.0
    item.status = Status.SCORED

    select.run([item], ctx, recent_selected=[recent])
    assert item.status is Status.DUPLICATE
    assert item.dupOf == recent.id


def test_select_marks_selected_when_followup(cfg, tmp_path: Path) -> None:
    llm = FakeLLM(group_relation="followup", has_new_info=True)
    ctx = make_ctx(cfg, llm, state_dir=tmp_path)

    recent = _item("Original story", "https://a.com/1", status=Status.SELECTED)
    item = _item("Later development", "https://b.com/2")
    item.scores = [90, 90]
    item.avgScore = 90.0
    item.status = Status.SCORED

    select.run([item], ctx, recent_selected=[recent])
    assert item.status is Status.SELECTED


def test_select_below_threshold_goes_to_listed(cfg, tmp_path: Path) -> None:
    ctx = make_ctx(cfg, FakeLLM(), state_dir=tmp_path)
    item = _item("t", "https://x.com/1")
    item.scores = [10, 10]
    item.avgScore = 10.0
    item.status = Status.SCORED

    select.run([item], ctx, recent_selected=[])
    assert item.status is Status.LISTED


# ══ 人工覆盖 ═══════════════════════════════════════════════════════════


def test_override_force_select_and_reject(cfg, tmp_path: Path) -> None:
    ctx = make_ctx(cfg, FakeLLM(), state_dir=tmp_path)

    forced = _item("t1", "https://x.com/forced")
    forced.scores = [10, 10]
    forced.avgScore = 10.0
    forced.status = Status.SCORED

    killed = _item("t2", "https://x.com/killed")
    killed.scores = [99, 99]
    killed.avgScore = 99.0
    killed.status = Status.SCORED

    ctx.cfg.overrides.select = [{"url": "https://x.com/forced", "note": "测试"}]
    ctx.cfg.overrides.reject = [{"url": "https://x.com/killed", "note": "测试"}]
    try:
        select.run([forced, killed], ctx, recent_selected=[])
        assert forced.status is Status.SELECTED
        assert killed.status is Status.LISTED
    finally:
        ctx.cfg.overrides.select = []
        ctx.cfg.overrides.reject = []


# ══ 端到端（本地 fixtures + 假 LLM，不访问网络）═════════════════════════


def test_end_to_end_with_local_fixtures(cfg, tmp_path: Path) -> None:
    """采集 → 预筛 → 评分 → 结构化 → 写作 → 去重 → 进精选，全流程跑通。"""
    llm = FakeLLM(scores=(85, 85))
    ctx = make_ctx(cfg, llm, state_dir=tmp_path)

    items: list[Item] = []
    items += load_fixture(
        "feed_t1_recent.xml", source_id="t1", source_name="T1", tier="T1",
        initial_backfill_limit=8, fresh_hours=48, first_import=False,
    )
    items += load_fixture(
        "feed_t2_mixed.xml", source_id="t2", source_name="T2", tier="T2",
        initial_backfill_limit=8, fresh_hours=48, first_import=False,
    )
    items += load_fixture(
        "feed_no_dates.xml", source_id="nd", source_name="ND", tier="T1",
        initial_backfill_limit=8, fresh_hours=48, first_import=False,
    )

    assert len(items) == 7

    prefilter.run(items, ctx)
    score.run(items, ctx)
    structure.run(items, ctx)
    write.run(items, ctx)
    dedupe.run(items, threshold=cfg.selection.dedupe["titleSimilarity"],
                window_hours=cfg.selection.dedupe["windowHours"])
    select.run(items, ctx, recent_selected=[])

    # 新鲜条目应当走完全程并被选中
    fresh = [i for i in items if i.status is Status.SELECTED]
    assert fresh, "应有条目进精选"
    for item in fresh:
        assert item.titleZh, "精选必须有中文标题"
        assert item.avgScore is not None
        assert item.prefilter is not None
        assert "prefilter" in item.promptVersions
        assert "score" in item.promptVersions

    # 无日期的条目始终不公开
    for item in items:
        if item.sourceId == "nd":
            assert not item.is_public


def test_end_to_end_all_blocked_produces_no_selection(cfg, tmp_path: Path) -> None:
    llm = FakeLLM(prefilter_label="BLOCK")
    ctx = make_ctx(cfg, llm, state_dir=tmp_path)
    items = load_fixture(
        "feed_t1_recent.xml", source_id="t1", source_name="T1", tier="T1",
        initial_backfill_limit=8, fresh_hours=48, first_import=False,
    )
    prefilter.run(items, ctx)
    score.run(items, ctx)
    select.run(items, ctx, recent_selected=[])

    # 新鲜条目被 BLOCK；已归档的旧条目本来就不参与预筛，保持 archived
    blocked = [i for i in items if i.status is Status.BLOCKED]
    assert blocked, "新鲜条目应被 BLOCK"
    assert all(i.prefilter and i.prefilter.label == "BLOCK" for i in blocked)
    # BLOCK 的条目不公开；archived 的旧条目仍可进「全部动态」，所以只断言 BLOCK 的
    assert all(not i.is_public for i in blocked), "BLOCK 的条目不得公开"
    assert not any(i.status is Status.SELECTED for i in items)


# ══ ur-ai-papers 适配器 ════════════════════════════════════════════════


def test_external_json_future_date_becomes_unknown() -> None:
    payload = [
        {
            "id": 1, "title": "Future issue paper", "date": "2027-01",
            "url": "https://doi.org/10.1/aaa", "ai_score": 5.0,
            "domain_score": 4.0, "tldr": "摘要", "ai_reason": "理由",
        }
    ]
    entries = external_json.parse_papers(payload)
    items = external_json.build_items(entries, source_id="ur", tier="T2", now=NOW)

    assert len(items) == 1
    assert items[0].publishedAt is None
    assert items[0].status is Status.UNKNOWN
    assert not items[0].is_public


def test_external_json_skips_low_score_and_old_papers() -> None:
    payload = [
        {"id": 1, "title": "Low score", "date": "2026-10-20", "url": "https://doi.org/10.1/low",
         "ai_score": 2.0, "tldr": "x", "ai_reason": "y"},
        {"id": 2, "title": "Too old", "date": "2026-01-01", "url": "https://doi.org/10.1/old",
         "ai_score": 5.0, "tldr": "x", "ai_reason": "y"},
        {"id": 3, "title": "Good", "date": "2026-10-20", "url": "https://doi.org/10.1/good",
         "ai_score": 5.0, "tldr": "摘要", "ai_reason": "理由"},
    ]
    entries = external_json.parse_papers(payload)
    items = external_json.build_items(
        entries, source_id="ur", tier="T2", min_ai_score=4.0,
        max_age_days=30, now=NOW, first_import=False,
    )

    titles = [i.title for i in items]
    assert "Good" in titles
    assert "Low score" not in titles
    assert "Too old" not in titles, "超过 max_age_days 的论文应硬跳过，不入库"


def test_external_json_respects_backfill_limit() -> None:
    payload = [
        {"id": i, "title": f"P{i}", "date": "2026-10-20",
         "url": f"https://doi.org/10.1/{i}", "ai_score": 5.0, "tldr": "x", "ai_reason": "y"}
        for i in range(20)
    ]
    entries = external_json.parse_papers(payload)
    items = external_json.build_items(
        entries, source_id="ur", tier="T2", initial_backfill_limit=3,
        first_import=True, now=NOW,
    )
    assert len(items) == 3
    assert all(i.status is Status.ARCHIVED for i in items)


# ══ 数据模型 ═══════════════════════════════════════════════════════════


def test_item_rejects_naive_datetime() -> None:
    """计划验收要求日期带时区。"""
    with pytest.raises(Exception):
        Item(
            id="x", sourceId="s", tier="T1", url="https://a.com",
            discoveredAt=datetime(2026, 10, 21),  # naive
        )


def test_item_rejects_out_of_range_score() -> None:
    with pytest.raises(Exception):
        Item(
            id="x", sourceId="s", tier="T1", url="https://a.com",
            discoveredAt=NOW, scores=[120],
        )


def test_body_is_truncated_to_8000() -> None:
    item = _item("t", "https://x.com/1")
    item.set_body("字" * 9000)
    assert len(item.body) == 8000
    assert item.bodyTruncated is True


def test_public_flag_excludes_blocked_and_unknown() -> None:
    blocked = _item("t", "https://x.com/1", status=Status.BLOCKED)
    unknown = _item("t", "https://x.com/2", status=Status.UNKNOWN)
    selected = _item("t", "https://x.com/3", status=Status.SELECTED)
    assert not blocked.is_public
    assert not unknown.is_public
    assert selected.is_public


# ══ 出刊日归属：跨层一致性回归测试 ═══════════════════════════════════════
#
# 背景：发布层曾把 `edition_day` 算成 `date(dt - hour)`，比正确值早一天，
# 会让 latest.json 的分期与采集层的出刊窗口对不上。
# 这里用「窗口是否真的包含该时刻」这个独立事实来验证，而不是断言某个具体日期。


def _true_edition_date(dt: datetime) -> str:
    """独立求法：找出哪个出刊日的窗口真正包含 dt。"""
    from uxhot.collect.dates import day_bounds_bj, parse_tz

    tz = parse_tz("Asia/Shanghai")
    for offset in range(-2, 3):
        candidate = (dt.astimezone(tz) + timedelta(days=offset)).strftime("%Y-%m-%d")
        prev = (datetime.strptime(candidate, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        start, end = day_bounds_bj(prev)
        if start <= dt < end:
            return candidate
    raise AssertionError(f"没有窗口包含 {dt}")


@pytest.mark.parametrize("hour", [0, 6, 7, 8, 9, 12, 23])
def test_edition_day_matches_window_containment(hour: int) -> None:
    """发布层的 edition_day 必须与「窗口包含」这一事实一致。"""
    from uxhot.collect.dates import parse_tz
    from uxhot.publish.build_site_data import edition_day

    tz = parse_tz("Asia/Shanghai")
    dt = datetime(2026, 10, 21, hour, 0, tzinfo=tz)
    assert str(edition_day(dt, tz, 8)) == _true_edition_date(dt)


def test_edition_day_boundary_is_exclusive_at_start() -> None:
    """窗口起点闭、终点开：正好 08:00 归下一期，07:59 归本期。"""
    from uxhot.collect.dates import parse_tz
    from uxhot.publish.build_site_data import edition_day

    tz = parse_tz("Asia/Shanghai")
    before = datetime(2026, 10, 21, 7, 59, tzinfo=tz)
    at = datetime(2026, 10, 21, 8, 0, tzinfo=tz)
    assert str(edition_day(before, tz, 8)) == "2026-10-21"
    assert str(edition_day(at, tz, 8)) == "2026-10-22"


# ══ 正文剥离（data/items 要能提交进 public 仓库）═══════════════════════


def test_strip_bodies_clears_processed_items_only() -> None:
    """已处理完的条目丢正文；还需处理的保留正文，否则下一步做不了。"""
    from uxhot.models import strip_bodies

    done = _item("done", "https://x.com/1", status=Status.SELECTED)
    done.set_body("x" * 5000)
    listed = _item("listed", "https://x.com/2", status=Status.LISTED)
    listed.set_body("y" * 3000)
    blocked = _item("blocked", "https://x.com/3", status=Status.BLOCKED)
    blocked.set_body("z" * 1000)

    pending = _item("pending", "https://x.com/4", status=Status.PREFILTERED)
    pending.set_body("need this body")
    scored = _item("scored", "https://x.com/5", status=Status.SCORED)
    scored.set_body("need this too")
    fresh = _item("fresh", "https://x.com/6", status=Status.NEW)
    fresh.set_body("need this as well")

    items = [done, listed, blocked, pending, scored, fresh]
    stripped = strip_bodies(items)

    assert stripped == 3
    for item in (done, listed, blocked):
        assert item.body == ""
        assert item.bodyChars > 0, "长度要留着做审计"
    for item in (pending, scored, fresh):
        assert item.body, f"{item.status} 的正文不能被清掉"


def test_needs_write_retry_only_for_scored_items_missing_chinese() -> None:
    """评过分、已定状态却没写出中文的（当次额度用尽）才补写；别的情况都不碰。"""
    stuck = _item("stuck", "https://x.com/r1", status=Status.LISTED)
    stuck.scores = [30, 32]
    stuck.set_body("原文")
    assert stuck.needs_write_retry

    stripped = _item("stripped", "https://x.com/r0", status=Status.LISTED)
    stripped.scores = [30, 32]
    assert not stripped.needs_write_retry, "正文已清掉的补写不出东西，不补"

    written = _item("written", "https://x.com/r2", status=Status.LISTED)
    written.scores = [30, 32]
    written.set_body("原文")
    written.titleZh, written.summaryZh = "中文标题", "中文摘要"
    assert not written.needs_write_retry

    archived = _item("archived", "https://x.com/r3", status=Status.ARCHIVED)
    assert not archived.needs_write_retry, "归档旧文本来就不进模型"

    unscored = _item("unscored", "https://x.com/r4", status=Status.LISTED)
    unscored.set_body("原文")
    assert not unscored.needs_write_retry, "没评过分的不补写"

    signal = _item("signal", "https://x.com/r5", status=Status.LISTED)
    signal.scores = [30, 32]
    signal.set_body("原文")
    signal.mode = "hot_signal"
    assert not signal.needs_write_retry, "热度信号源不进模型"


def test_strip_bodies_keeps_items_needing_write_retry() -> None:
    """还要补写中文的条目留着正文，否则补写时没有原文可读。"""
    from uxhot.models import strip_bodies

    stuck = _item("stuck", "https://x.com/k1", status=Status.LISTED)
    stuck.scores = [30, 32]
    stuck.set_body("原文还要用")
    done = _item("done", "https://x.com/k2", status=Status.LISTED)
    done.scores = [30, 32]
    done.titleZh, done.summaryZh = "中文标题", "中文摘要"
    done.set_body("写完了")

    assert strip_bodies([stuck, done]) == 1
    assert stuck.body == "原文还要用"
    assert done.body == ""


def test_publishable_requires_chinese_except_selected() -> None:
    """D16：非精选没中文不上页面；精选缺中文仍算可发布，交给发布校验报错。"""
    listed = _item("listed", "https://x.com/p1", status=Status.LISTED)
    assert listed.is_public and not listed.is_publishable
    listed.titleZh, listed.summaryZh = "中文标题", "中文摘要"
    assert listed.is_publishable

    selected = _item("selected", "https://x.com/p2", status=Status.SELECTED)
    assert selected.is_publishable

    blocked = _item("blocked", "https://x.com/p3", status=Status.BLOCKED)
    blocked.titleZh, blocked.summaryZh = "中文标题", "中文摘要"
    assert not blocked.is_publishable


def test_strip_bodies_clears_unknown_and_never_processed() -> None:
    """UNKNOWN 与 hot_signal / EXCLUDE 永远不会进模型步骤，正文该清掉。

    不清的话，public 仓库里会留着一批永远读不到的第三方正文
    （实测过一次：30 条共 6,483 字，其中 9 条是 hot_signal 的 Reddit 帖子）。
    """
    from uxhot.models import strip_bodies

    unknown = _item("u", "https://x.com/u", status=Status.UNKNOWN)
    unknown.set_body("永远读不到的正文")

    hot = _item("h", "https://x.com/h", status=Status.NEW)
    hot.mode = "hot_signal"
    hot.set_body("热度信号，不展示")

    excluded = _item("e", "https://x.com/e", status=Status.NEW, tier="EXCLUDE")
    excluded.set_body("不参与精选")

    assert strip_bodies([unknown, hot, excluded]) == 3
    assert unknown.body == "" and hot.body == "" and excluded.body == ""


def test_strip_bodies_keeps_editorial_new_body() -> None:
    """但 editorial 的 NEW 必须保留 —— 它下一步就要被评分。"""
    from uxhot.models import strip_bodies

    item = _item("n", "https://x.com/n", status=Status.NEW)
    item.set_body("马上要送去评分")
    assert strip_bodies([item]) == 0
    assert item.body == "马上要送去评分"


def test_strip_bodies_keeps_body_chars_for_audit() -> None:
    from uxhot.models import strip_bodies

    item = _item("t", "https://x.com/1", status=Status.SELECTED)
    item.set_body("a" * 1234)
    strip_bodies([item])
    assert item.body == ""
    assert item.bodyChars == 1234


def test_archived_items_are_stripped() -> None:
    """归档条目永远不进模型步骤，正文留着没有意义。"""
    from uxhot.models import strip_bodies

    item = _item("t", "https://x.com/1", status=Status.ARCHIVED)
    item.set_body("old content")
    assert strip_bodies([item]) == 1
    assert item.body == ""


# ══ 回填时间下界：非首次导入不能重灌整个 feed ═════════════════════════
#
# 背景：`initial_backfill_limit` 只约束**首次导入**。之后的运行若不给时间下界，
# 就会把整个 feed 重新灌一遍 —— 实测某个「最新 8 条」的信源在第二次运行后
# 变成 98 条，把 2017 年的旧文也拉进了「全部动态」。


def test_second_run_without_since_reingests_whole_feed() -> None:
    """复现 bug：不给 since 时，第二次运行会把整个 feed 都收进来。"""
    entries = rss.parse_feed((FIXTURES / "feed_t1_recent.xml").read_bytes(), "+00:00", now=NOW)
    assert len(entries) == 3

    # 第二次运行（first_import=False）且不给 since → 3 条全收，包括两周前那条
    items = rss.build_items(
        entries, source_id="t1", source_name="T1", tier="T1",
        initial_backfill_limit=2, fresh_hours=48, first_import=False,
        known_ids=set(), since=None, now=NOW,
    )
    assert len(items) == 3, "这正是 bug 的表现：超出 backfill 上限的旧文也被收了"
    assert any(i.title == "Old post from two weeks ago" for i in items)


def test_second_run_with_since_skips_old_entries() -> None:
    """给了 since 之后，早于它的旧文不该再被收进来。"""
    entries = rss.parse_feed((FIXTURES / "feed_t1_recent.xml").read_bytes(), "+00:00", now=NOW)

    # 首次导入时间设为 10-21 10:00，减 48h 得到下界
    since = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)
    items = rss.build_items(
        entries, source_id="t1", source_name="T1", tier="T1",
        initial_backfill_limit=2, fresh_hours=48, first_import=False,
        known_ids=set(), since=since, now=NOW,
    )

    titles = [i.title for i in items]
    assert "Old post from two weeks ago" not in titles, "两周前的旧文应被 since 挡住"
    assert len(items) == 2


def test_known_ids_skips_already_stored_items() -> None:
    """已存在的条目 id 要跳过，避免重复进后续步骤。"""
    entries = rss.parse_feed((FIXTURES / "feed_t1_recent.xml").read_bytes(), "+00:00", now=NOW)
    first = rss.build_items(
        entries, source_id="t1", source_name="T1", tier="T1",
        initial_backfill_limit=8, fresh_hours=48, first_import=False, now=NOW,
    )
    known = {i.id for i in first}

    again = rss.build_items(
        entries, source_id="t1", source_name="T1", tier="T1",
        initial_backfill_limit=8, fresh_hours=48, first_import=False,
        known_ids=known, now=NOW,
    )
    assert again == [], "全都认识，不该再产出条目"


def test_web_list_respects_since() -> None:
    """网页列表采集同样要受 since 约束。"""
    from uxhot.collect import web_list

    entries = [
        web_list.WebListEntry("新", "https://x.com/new", None, NOW - timedelta(hours=2)),
        web_list.WebListEntry("旧", "https://x.com/old", None, NOW - timedelta(days=30)),
    ]
    items = web_list.build_items(
        entries, source_id="wl", source_name="WL", tier="T1",
        first_import=False, since=NOW - timedelta(days=7), now=NOW,
    )
    titles = [i.title for i in items]
    assert "新" in titles
    assert "旧" not in titles


def test_external_json_respects_since() -> None:
    """外部 JSON 采集同样要受 since 约束。"""
    payload = [
        {"id": 1, "title": "新", "date": "2026-10-20", "url": "https://doi.org/10.1/new",
         "ai_score": 5.0, "tldr": "x", "ai_reason": "y"},
        {"id": 2, "title": "旧", "date": "2026-08-01", "url": "https://doi.org/10.1/old",
         "ai_score": 5.0, "tldr": "x", "ai_reason": "y"},
    ]
    entries = external_json.parse_papers(payload)
    items = external_json.build_items(
        entries, source_id="ur", tier="T2", max_age_days=365,
        first_import=False, since=datetime(2026, 10, 1, tzinfo=timezone.utc), now=NOW,
    )
    titles = [i.title for i in items]
    assert "新" in titles
    assert "旧" not in titles


# ══ 原始出处（venue）：聚合源不能顶替真出处 ═══════════════════════════
#
# 背景：卡片上显示的是「ur-ai-papers（用户与交互 AI 论文库）」——
# 那是二手聚合库，不是出处。读者要看到「Computers in Human Behavior」或「arXiv」。


def test_resolve_venue_prefers_arxiv_from_url() -> None:
    """URL 比 journal 字段可信：arXiv 的 journal 常常是空的或不准。"""
    assert external_json.resolve_venue(None, "https://arxiv.org/abs/2610.1", {}) == "arXiv"
    assert external_json.resolve_venue("CHB", "https://arxiv.org/abs/2610.1", {}) == "arXiv"


def test_resolve_venue_maps_abbreviation_to_full_name() -> None:
    mapping = {"CHB": "Computers in Human Behavior", "IJHCS": "International Journal of Human-Computer Studies"}
    assert external_json.resolve_venue("CHB", "https://doi.org/10.1/x", mapping) == "Computers in Human Behavior"
    assert external_json.resolve_venue("IJHCS", "https://doi.org/10.1/y", mapping) == "International Journal of Human-Computer Studies"


def test_resolve_venue_falls_back_to_abbreviation() -> None:
    """映射里没有就显示缩写，**不能留空**（留空等于又退回聚合库名）。"""
    assert external_json.resolve_venue("ZZZ", "https://doi.org/10.1/x", {}) == "ZZZ"


def test_resolve_venue_handles_missing_journal() -> None:
    assert external_json.resolve_venue(None, "https://doi.org/10.1/x", {}) == ""
    assert external_json.resolve_venue("", "https://doi.org/10.1/x", {}) == ""


def test_load_journal_names_survives_fetch_failure() -> None:
    """映射拉不到不能中断采集 —— 退回缩写即可。"""
    class Boom:
        def get(self, url):
            raise RuntimeError("网络炸了")

    assert external_json.load_journal_names(Boom()) == {}

    class BadStatus:
        def get(self, url):
            return type("R", (), {"status_code": 500, "text": ""})()

    assert external_json.load_journal_names(BadStatus()) == {}


def test_papers_get_venue_from_journal() -> None:
    payload = [
        {"id": 1, "title": "T", "date": "2026-10-20", "url": "https://doi.org/10.1/a",
         "journal": "CHB", "ai_score": 5.0, "tldr": "x", "ai_reason": "y"},
        {"id": 2, "title": "A", "date": "2026-10-20", "url": "https://arxiv.org/abs/2610.9",
         "journal": None, "ai_score": 5.0, "tldr": "x", "ai_reason": "y"},
    ]
    entries = external_json.parse_papers(payload)
    items = external_json.build_items(
        entries, source_id="ur", tier="T2", first_import=False,
        journal_names={"CHB": "Computers in Human Behavior"}, now=NOW,
    )
    by_title = {i.title: i for i in items}
    assert by_title["T"].venue == "Computers in Human Behavior"
    assert by_title["A"].venue == "arXiv"


# ══ 分类与内容类型必须自洽 ═════════════════════════════════════════════
#
# 背景：分类（structure.md）和内容类型（content-understanding.md）是两次独立调用，
# 可能互相矛盾。实测过一次：NN/g 的《The 3 Roles of Context for AI Agents》
# 被归成 research（论文），而它给的类型是 tutorial_explainer —— 一篇教程挂在「论文」下。


def test_align_fixes_tutorial_misclassified_as_research() -> None:
    from uxhot.pipeline.write import align_category_with_item_type

    item = _item("t", "https://x.com/1")
    item.itemType = "tutorial_explainer"
    item.category = "research"

    assert align_category_with_item_type(item) is True
    assert item.category == "methods"
    assert any("consistency" in e for e in item.errors)


@pytest.mark.parametrize(
    "item_type,expected",
    [
        ("tool_launch", "tools"),
        ("method_or_template", "methods"),
        ("research_paper", "research"),
        ("industry_event", "industry"),
        ("case_study", "cases"),
        ("opinion_analysis", "opinion"),
        ("tutorial_explainer", "methods"),
    ],
)
def test_align_maps_every_item_type(item_type: str, expected: str) -> None:
    from uxhot.pipeline.write import align_category_with_item_type

    item = _item("t", "https://x.com/1")
    item.itemType = item_type
    item.category = "industry" if expected != "industry" else "research"
    align_category_with_item_type(item)
    assert item.category == expected


def test_align_leaves_consistent_item_alone() -> None:
    from uxhot.pipeline.write import align_category_with_item_type

    item = _item("t", "https://x.com/1")
    item.itemType = "research_paper"
    item.category = "research"
    assert align_category_with_item_type(item) is False
    assert item.errors == []


def test_align_does_not_guess_when_value_missing() -> None:
    """缺一个就不猜 —— 没有 itemType 时不能凭 category 反推。"""
    from uxhot.pipeline.write import align_category_with_item_type

    no_type = _item("a", "https://x.com/1")
    no_type.category = "research"
    assert align_category_with_item_type(no_type) is False

    no_cat = _item("b", "https://x.com/2")
    no_cat.itemType = "research_paper"
    assert align_category_with_item_type(no_cat) is False
