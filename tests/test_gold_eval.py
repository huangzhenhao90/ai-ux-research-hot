"""阶段 8 验收：金标模型与评测口径。

评测的指标口径很容易写错（分母、失败怎么算、either 怎么处理），所以这里
用**手算得出的期望值**逐项断言，而不是只断言「跑通了」。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from uxhot.config import load_config
from uxhot.evalrun import (
    SWEEP_END,
    SWEEP_START,
    SWEEP_STEP,
    CaseResult,
    ResponseCache,
    build_report,
    compute_metrics,
    evaluate_cases,
    gold_select_rate,
    recommend_threshold,
    sweep_by_tier,
)
from uxhot.gold import (
    GoldCase,
    assign_split,
    filter_split,
    load_gold,
    parse_decision,
    save_gold,
    scored_cases,
    summarize,
)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def make_case(case_id: str, tier: str, decision: str, split: str = "development",
              title: str = "Fixture title", body: str = "Fixture body " * 30) -> GoldCase:
    return GoldCase.model_validate(
        {
            "caseId": case_id,
            "material": {
                "title": title,
                "publishedAt": "2026-10-20T09:00:00+00:00",
                "sourceName": "Fixture Source",
                "bodyOriginal": body,
            },
            "sourceFacts": {
                "sourceKind": "rss",
                "sourceTier": tier,
                "firstParty": tier == "T1",
                "language": "en",
            },
            "samplingContext": {"benchmarkSplit": split, "samplingStratum": f"tier:{tier}"},
            "gold": {"decision": decision},
        }
    )


class FakeLLM:
    """假客户端：按提示词内容决定返回什么，不访问网络。"""

    def __init__(self, *, prefilter: dict[str, str] | None = None,
                 scores: dict[str, tuple[int, int]] | None = None,
                 fail_on: set[str] | None = None):
        self.prefilter = prefilter or {}
        self.scores = scores or {}
        self.fail_on = fail_on or set()
        self.calls: list[str] = []
        self.config = type("Cfg", (), {"model": "fake-model"})()

    def _title_of(self, prompt: str) -> str:
        for line in prompt.splitlines():
            if line.startswith("标题："):
                return line[3:].strip()
        return ""

    def complete_json(self, prompt: str, *, step: str = "", **kwargs):
        title = self._title_of(prompt)
        if title in self.fail_on:
            from uxhot.llm import LLMError

            raise LLMError("假失败")
        self.calls.append(step)
        if step == "prefilter":
            label = self.prefilter.get(title, "PASS")
            return {"label": label, "reason": "fake"}
        if step == "score":
            pair = self.scores.get(title, (70, 70))
            # 两次调用交替返回，模拟两次独立评分
            seen = sum(1 for c in self.calls if c == "score")
            return {"attentionScore": pair[(seen - 1) % 2]}
        return {}


# ══ GoldCase / 切分 ════════════════════════════════════════════════════


def test_assign_split_is_stable() -> None:
    a = assign_split("uxhot-0001")
    b = assign_split("uxhot-0001")
    assert a == b, "同一条必须永远是同一份"


def test_assign_split_is_roughly_two_to_one() -> None:
    splits = [assign_split(f"uxhot-{i:04d}") for i in range(600)]
    dev = splits.count("development")
    hold = splits.count("holdout")
    assert hold > 0, "必须真的有留出集"
    assert 1.6 < dev / hold < 2.4, f"2:1 切分偏差过大：dev={dev} hold={hold}"


def test_parse_decision_accepts_chinese_and_english() -> None:
    assert parse_decision("select") == "select"
    assert parse_decision("该选") == "select"
    assert parse_decision("选") == "select"
    assert parse_decision("reject") == "reject"
    assert parse_decision("不该选") == "reject"
    assert parse_decision("either") == "either"
    assert parse_decision("两可") == "either"
    assert parse_decision("") is None
    assert parse_decision(None) is None
    assert parse_decision("乱写的") is None


def test_scored_cases_excludes_either() -> None:
    cases = [
        make_case("c1", "T1", "select"),
        make_case("c2", "T1", "either"),
        make_case("c3", "T1", "reject"),
    ]
    assert [c.caseId for c in scored_cases(cases)] == ["c1", "c3"]


def test_summarize_counts(tmp_path: Path) -> None:
    cases = [
        make_case("c1", "T1", "select"),
        make_case("c2", "T1", "reject"),
        make_case("c3", "T2", "either", split="holdout"),
    ]
    info = summarize(cases)
    assert info["total"] == 3
    assert info["scored"] == 2
    assert info["either"] == 1
    assert info["byTier"] == {"T1": 2, "T2": 1}
    assert info["bySplit"] == {"development": 2, "holdout": 1}
    # either 不进分母：2 条非 either 里 1 条该选
    assert info["selectRate"] == 0.5


def test_save_and_load_gold_roundtrip(tmp_path: Path) -> None:
    cases = [make_case("c1", "T1", "select"), make_case("c2", "T2", "reject", split="holdout")]
    path = tmp_path / "gold.jsonl"
    save_gold(cases, path)
    back = load_gold(path)
    assert [c.caseId for c in back] == ["c1", "c2"]
    assert filter_split(back, "holdout")[0].caseId == "c2"


def test_load_gold_rejects_bad_line(tmp_path: Path) -> None:
    path = tmp_path / "gold.jsonl"
    path.write_text('{"caseId":"c1"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="不合法"):
        load_gold(path)


def test_source_tier_must_be_known() -> None:
    with pytest.raises(Exception):
        make_case("c1", "T9", "select")


# ══ 指标口径（手算对照）════════════════════════════════════════════════


def _r(case_id: str, tier: str, gold: str, *, prefilter="PASS",
       scores=(70, 70), failed=False) -> CaseResult:
    return CaseResult(
        caseId=case_id, tier=tier, sourceName="S", gold=gold,
        prefilter=prefilter, scores=list(scores), failed=failed,
    )


def test_metrics_hand_computed() -> None:
    """TP=2 FP=1 TN=2 FN=1 → 准确率 4/6，查准 2/3，查全 2/3。"""
    results = [
        _r("a", "T1", "select", scores=(80, 80)),   # TP
        _r("b", "T1", "select", scores=(80, 80)),   # TP
        _r("c", "T1", "reject", scores=(80, 80)),   # FP
        _r("d", "T1", "reject", scores=(10, 10)),   # TN
        _r("e", "T1", "reject", scores=(10, 10)),   # TN
        _r("f", "T1", "select", scores=(10, 10)),   # FN
    ]
    m = compute_metrics(results, {"T1": 60})
    assert (m.tp, m.fp, m.tn, m.fn) == (2, 1, 2, 1)
    assert m.denominator == 6
    assert m.valid == 6
    assert m.accuracy_valid == pytest.approx(4 / 6)
    assert m.precision == pytest.approx(2 / 3)
    assert m.recall == pytest.approx(2 / 3)
    assert m.f1 == pytest.approx(2 / 3)
    assert m.coverage == pytest.approx(1.0)


def test_either_excluded_from_every_denominator() -> None:
    results = [
        _r("a", "T1", "select", scores=(80, 80)),
        _r("b", "T1", "either", scores=(80, 80), prefilter="BLOCK"),
        _r("c", "T1", "either", scores=(10, 10)),
    ]
    m = compute_metrics(results, {"T1": 60})
    assert m.total == 3
    assert m.either == 2
    assert m.denominator == 1, "either 不能进分母"
    assert m.valid == 1
    assert m.accuracy_valid == pytest.approx(1.0)


def test_failures_counted_wrong_in_full_accuracy_but_excluded_from_valid() -> None:
    """失败样本：不进「有效输出准确率」的分母，但进「完整准确率」的分母算错。"""
    results = [
        _r("a", "T1", "select", scores=(80, 80)),              # 对
        _r("b", "T1", "reject", scores=(80, 80)),              # 错
        _r("c", "T1", "select", scores=[], failed=True),       # 失败
        _r("d", "T1", "reject", scores=[], failed=True),       # 失败
    ]
    m = compute_metrics(results, {"T1": 60})
    assert m.denominator == 4
    assert m.valid == 2
    assert m.failed == 2
    assert m.accuracy_valid == pytest.approx(0.5), "只看答出来的：1 对 1 错"
    assert m.accuracy_full == pytest.approx(0.25), "完整口径：4 条里只对 1 条"
    assert m.coverage == pytest.approx(0.5)


def test_block_is_treated_as_reject_regardless_of_threshold() -> None:
    blocked = _r("a", "T1", "reject", scores=(99, 99), prefilter="BLOCK")
    m = compute_metrics([blocked], {"T1": 60})
    assert m.tn == 1, "BLOCK 的条目在线上不进精选，评测里也该算不选"

    blocked_should_select = _r("b", "T1", "select", scores=(99, 99), prefilter="BLOCK")
    m2 = compute_metrics([blocked_should_select], {"T1": 60})
    assert m2.fn == 1


def test_threshold_boundary_sum_ge_double() -> None:
    """门槛判定：两次之和 ≥ 2×门槛。"""
    exactly = _r("a", "T1", "select", scores=(60, 60))
    assert exactly.predicts_select(60) is True
    one_below = _r("b", "T1", "select", scores=(59, 60))
    assert one_below.predicts_select(60) is False


def test_single_score_is_not_a_valid_decision() -> None:
    partial = _r("a", "T1", "select", scores=(90,), failed=True)
    assert partial.total is None
    assert partial.predicts_select(60) is None, "只拿到一次评分不能当作有效决定"


def test_gold_select_rate_excludes_either() -> None:
    results = [
        _r("a", "T1", "select"),
        _r("b", "T1", "reject"),
        _r("c", "T1", "either"),
    ]
    assert gold_select_rate(results) == pytest.approx(0.5)


# ══ 门槛扫描 ═══════════════════════════════════════════════════════════


def test_sweep_covers_40_to_90_step_2() -> None:
    results = [_r("a", "T1", "select", scores=(60, 60))]
    curves = sweep_by_tier(results)
    values = [t for t, _ in curves["T1"]]
    assert values[0] == SWEEP_START == 40
    assert values[-1] == SWEEP_END == 90
    assert all(b - a == SWEEP_STEP for a, b in zip(values, values[1:]))
    assert len(values) == (SWEEP_END - SWEEP_START) // SWEEP_STEP + 1


def test_sweep_is_per_tier() -> None:
    results = [
        _r("a", "T1", "select", scores=(60, 60)),
        _r("b", "T2", "select", scores=(80, 80)),
    ]
    curves = sweep_by_tier(results)
    assert set(curves) == {"T1", "T2"}
    # T1 的分母只有 1 条
    assert all(m.denominator == 1 for _, m in curves["T1"])


def test_recommend_threshold_prefers_recall_above_precision_floor() -> None:
    """查准率 ≥0.8 的前提下取查全率最高的那一档。"""
    from uxhot.evalrun import Metrics

    high_p_low_r = Metrics(denominator=10, valid=8, tp=8, fp=0, fn=2)   # P=1.0 R=0.8
    lower_p_high_r = Metrics(denominator=10, valid=10, tp=9, fp=1, fn=1)  # P=0.9 R=0.9
    bad = Metrics(denominator=10, valid=10, tp=6, fp=4, fn=4)          # P=0.6 不合格
    curve = [(70, high_p_low_r), (60, lower_p_high_r), (50, bad)]
    best = recommend_threshold(curve, min_precision=0.8)
    assert best is not None
    assert best[0] == 60, "应选查全率更高且查准率达标的那档"


def test_recommend_threshold_returns_none_when_precision_unreachable() -> None:
    from uxhot.evalrun import Metrics

    curve = [(t, Metrics(denominator=10, valid=10, tp=5, fp=5, fn=5)) for t in (40, 50, 60)]
    assert recommend_threshold(curve, min_precision=0.8) is None, (
        "没有一档达标时必须返回 None，让人工决定，而不是自动放宽标准"
    )


# ══ 端到端（假 LLM，零成本）══════════════════════════════════════════


def test_evaluate_cases_with_fake_llm(cfg) -> None:
    cases = [
        make_case("c1", "T1", "select", title="该选的工具发布"),
        make_case("c2", "T1", "reject", title="不该选的软文"),
        make_case("c3", "T1", "either", title="两可的边界稿"),
    ]
    llm = FakeLLM(scores={"该选的工具发布": (85, 85), "不该选的软文": (20, 20), "两可的边界稿": (60, 60)})
    results, stats = evaluate_cases(cases, cfg, llm, cache=None)

    assert len(results) == 3
    assert all(r.prefilter == "PASS" for r in results)
    assert results[0].scores == [85, 85]
    # 3 条 × (1 预筛 + 2 评分) = 9
    assert stats.calls == 9

    m = compute_metrics(results, {"T1": 60})
    assert m.either == 1
    assert m.denominator == 2
    assert m.tp == 1 and m.tn == 1


def test_evaluate_cases_marks_blocked_as_not_selected(cfg) -> None:
    cases = [make_case("c1", "T1", "reject", title="无关内容")]
    llm = FakeLLM(prefilter={"无关内容": "BLOCK"})
    results, stats = evaluate_cases(cases, cfg, llm, cache=None)

    assert results[0].prefilter == "BLOCK"
    assert results[0].scores == [], "BLOCK 的不该去评分"
    # 只调了预筛
    assert stats.calls == 1
    assert compute_metrics(results, {"T1": 60}).tn == 1


def test_evaluate_cases_records_failure_not_silent_reject(cfg) -> None:
    """调用失败必须记为 failed，不能悄悄当成 reject。"""
    cases = [make_case("c1", "T1", "select", title="会失败的稿子")]
    llm = FakeLLM(fail_on={"会失败的稿子"})
    results, _ = evaluate_cases(cases, cfg, llm, cache=None)

    assert results[0].failed is True
    assert results[0].error
    m = compute_metrics(results, {"T1": 60})
    assert m.failed == 1
    assert m.fn == 0, "失败不能算成 FN，它连有效决定都没有"
    assert m.accuracy_full == 0.0, "失败在完整准确率里算错"


def test_no_client_marks_all_failed(cfg) -> None:
    cases = [make_case("c1", "T1", "select")]
    results, stats = evaluate_cases(cases, cfg, None, cache=None)
    assert all(r.failed for r in results)
    assert stats.calls == 0


def test_response_cache_avoids_second_call(cfg, tmp_path: Path) -> None:
    cases = [make_case("c1", "T1", "select", title="缓存测试")]
    cache = ResponseCache(tmp_path / "cache.json")

    llm1 = FakeLLM(scores={"缓存测试": (80, 80)})
    first, _ = evaluate_cases(cases, cfg, llm1, cache=cache)
    first_calls = len(llm1.calls)
    cache.save()

    # 用新缓存对象重跑（模拟第二次运行）
    cache2 = ResponseCache(tmp_path / "cache.json")
    llm2 = FakeLLM(scores={"缓存测试": (80, 80)})
    second, stats2 = evaluate_cases(cases, cfg, llm2, cache=cache2)

    assert first_calls == 3, "首次要真调：1 预筛 + 2 评分"
    assert llm2.calls == [], "命中缓存就不该再调模型"
    assert stats2.cache_hits == 3
    assert second[0].scores == first[0].scores


def test_cache_keeps_two_score_calls_independent(cfg, tmp_path: Path) -> None:
    """两次评分用的提示词完全相同，缓存不能把它们合并成一次。

    合并的话两次分数会永远相等，评测里「两次独立评分」的方差信号就没了。
    """
    cases = [make_case("c1", "T1", "select", title="两次不同")]
    cache = ResponseCache(tmp_path / "cache.json")

    # 两次评分返回不同分数
    llm1 = FakeLLM(scores={"两次不同": (80, 62)})
    first, _ = evaluate_cases(cases, cfg, llm1, cache=cache)
    assert first[0].scores == [80, 62], "同一提示词的两次调用应拿到两个不同的返回"
    cache.save()

    cache2 = ResponseCache(tmp_path / "cache.json")
    llm2 = FakeLLM()
    second, stats2 = evaluate_cases(cases, cfg, llm2, cache=cache2)

    assert llm2.calls == []
    assert second[0].scores == [80, 62], "重跑要能复现两个不同的分数，而不是都变成第一个"
    assert stats2.cache_hits == 3


# ══ 报告 ═══════════════════════════════════════════════════════════════


def test_report_contains_required_sections(cfg) -> None:
    cases = [make_case("c1", "T1", "select", title="T"), make_case("c2", "T1", "reject", title="R")]
    llm = FakeLLM(scores={"T": (85, 85), "R": (20, 20)})
    results, stats = evaluate_cases(cases, cfg, llm, cache=None)
    curves = sweep_by_tier(results)

    report = build_report(
        label="v1", split="development", model="fake-model",
        results=results, threshold=cfg.selection.thresholds,
        curves=curves, stats=stats,
        generated_at=datetime(2026, 10, 22, tzinfo=timezone.utc),
    )

    assert "精选评测报告 · v1" in report
    assert "goldSelectRate" in report
    assert "有效输出准确率" in report
    assert "完整准确率" in report
    assert "覆盖率" in report
    assert "查准率" in report
    assert "查全率" in report
    assert "门槛曲线" in report
    assert "判错的样本" in report
    assert "未拿到有效决定" in report
    # 逐 tier 曲线要有表
    assert "| 门槛 |" in report


def test_report_lists_wrong_cases(cfg) -> None:
    cases = [make_case("c1", "T1", "select", title="被漏掉的")]
    llm = FakeLLM(scores={"被漏掉的": (10, 10)})
    results, stats = evaluate_cases(cases, cfg, llm, cache=None)
    report = build_report(
        label="v1", split="development", model="m",
        results=results, threshold={"T1": 60},
        curves=sweep_by_tier(results), stats=stats,
    )
    assert "c1" in report
    assert "判错的样本（1 条）" in report
