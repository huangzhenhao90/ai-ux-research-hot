"""阶段 8 验收：金标分层抽样、标注表导出、`--convert` 转 gold.jsonl。

全部用**假 Item** 与临时目录，不真实抓取、不真实调模型、不依赖仓库里现有数据条数
（现有数据会被其他阶段改动，测试不能跟着漂）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from openpyxl import load_workbook

from uxhot.config import load_config
from uxhot.gold import assign_split, load_gold, parse_decision
from uxhot.models import Item, Status, write_items

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "sample_gold.py"

# 测试用门槛：故意选好算的数字，让「门槛附近 ±10」的边界一眼可验
TEST_THRESHOLDS = {"T1": 60, "T1_5": 65, "T2": 80}
CATEGORIES = ["tools", "methods", "research", "industry", "cases", "opinion"]


def _load_module():
    """按路径加载 `scripts/sample_gold.py`。

    scripts/ 不是包（没有 `__init__.py`），所以不能直接 import；
    用 importlib 并**先塞进 sys.modules**，否则 dataclass 解析注解时会炸。
    """
    spec = importlib.util.spec_from_file_location("sample_gold_under_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sg = _load_module()

NOW = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)


def make_item(
    item_id: str,
    *,
    tier: str = "T1",
    category: str | None = "tools",
    avg_score: float | None = 55.0,
    source_id: str = "dovetail-blog",
    title: str = "",
    url: str = "",
    body: str = "",
    lang: str | None = None,
    published_at: datetime | None = None,
    status: Status = Status.SCORED,
) -> Item:
    """构造一条假 Item。默认已评分，够 `sample_cases` 用。"""
    return Item(
        id=item_id,
        sourceId=source_id,
        tier=tier,
        url=url or f"https://example.com/{item_id}",
        title=title or f"标题 {item_id}",
        lang=lang,
        body=body,
        publishedAt=published_at or NOW,
        discoveredAt=NOW,
        status=status,
        avgScore=avg_score,
        category=category,
        # 故意塞上模型产出，用来验证它们**不会**漏进标注表（D11）
        summaryZh=f"模型摘要 {item_id}",
        titleZh=f"模型标题 {item_id}",
        scores=[int(avg_score or 0)],
    )


def plan_for(
    items: list[Item],
    *,
    target: int,
    min_per_category: int = 1,
    min_near_threshold: int = 1,
    near_window: int = 10,
    thresholds: dict[str, int] | None = None,
):
    """按测试口径抽样（门槛用 TEST_THRESHOLDS，避免依赖仓库配置）。"""
    return sg.sample_cases(
        items,
        thresholds=dict(thresholds or TEST_THRESHOLDS),
        categories=CATEGORIES,
        target=target,
        min_per_category=min_per_category,
        min_near_threshold=min_near_threshold,
        near_window=near_window,
    )


# ══ 1. 分层抽样确实按分类 / tier / 门槛附近分配 ═════════════════════════


def test_sample_stratifies_by_category_tier_and_threshold() -> None:
    items: list[Item] = []
    # 每个分类两条：一条贴着门槛（T1 门槛 60 → 52/60 都在 ±10 内），一条离得远
    for index, category in enumerate(CATEGORIES):
        items.append(make_item(f"near-{category}", category=category, avg_score=52.0))
        items.append(make_item(f"far-{category}", category=category, avg_score=5.0))
    # T2 也要有：T2 门槛 80 → 75 贴着门槛
    items.append(make_item("t2-near", tier="T2", category="tools", avg_score=75.0))
    items.append(make_item("t2-far", tier="T2", category="cases", avg_score=10.0))

    plan = plan_for(items, target=14, min_per_category=2, min_near_threshold=7)

    # 分类：每类至少 2 条
    for category in CATEGORIES:
        assert plan.report["byCategory"].get(category, 0) >= 2, category
    # tier：T1 与 T2 都要有
    assert plan.report["tierCovered"].get("T1", 0) >= 1
    assert plan.report["tierCovered"].get("T2", 0) >= 1
    # 门槛附近：7 条候选都在 ±10 内，应全部抽中
    assert plan.report["nearThresholdSelected"] >= 7
    near_cases = [c for c in plan.cases if c.near_threshold]
    assert len(near_cases) >= 7
    # 分层名带前缀，报告里能一眼看出是什么分层
    stratums = {c.stratum for c in plan.cases}
    assert any(s.startswith("near-threshold:") for s in stratums)
    assert any(s.startswith("category:") for s in stratums)
    assert all(
        s.startswith(("near-threshold:", "category:", "tier:", "other:")) for s in stratums
    )
    # 难例优先：贴门槛的排在离得远的前面
    assert plan.cases[0].near_threshold is True
    assert plan.cases[-1].near_threshold is False
    # 每条只归属一层：分层计数之和 == 抽样条数（没有重复计数）
    assert sum(plan.report["byStratum"].values()) == len(plan.cases)
    # 未评分的条目一律不参与
    unscored = make_item("unscored", avg_score=None)
    assert all(c.item.id != unscored.id for c in plan_for(items + [unscored], target=14).cases)


def test_near_threshold_window_is_configurable() -> None:
    """窗口调小 → 门槛附近候选变少，这是「难例多少」的旋钮。"""
    items = [
        make_item("d2", avg_score=58.0),    # |58-60| = 2
        make_item("d8", avg_score=68.0),    # |68-60| = 8
        make_item("d20", avg_score=40.0),   # |40-60| = 20
        make_item("d21", avg_score=39.0),
        make_item("d22", avg_score=38.0),
        make_item("d23", avg_score=37.0),
    ]
    narrow = plan_for(items, target=6, min_near_threshold=1, near_window=3)
    wide = plan_for(items, target=6, min_near_threshold=1, near_window=10)
    assert narrow.report["nearThresholdAvailable"] == 1
    assert wide.report["nearThresholdAvailable"] == 2


# ══ 2. 目标达不到时如实报告缺口 ═════════════════════════════════════════


def test_reports_gaps_instead_of_padding_silently() -> None:
    """候选池远小于目标时：不报错、不重复凑数，但缺口必须被列出来。"""
    items = [
        make_item("t1", tier="T1", category="tools", avg_score=95.0),      # 离门槛远
        make_item("t2", tier="T2", category="methods", avg_score=78.0),    # T2 门槛 80 → 贴门槛
        make_item("t3", tier="T1", category="opinion", avg_score=41.0),    # 离门槛远
        make_item("t4", tier="T1", category="opinion", avg_score=None),    # 没评分，应被排除
    ]
    plan = plan_for(items, target=6, min_per_category=1, min_near_threshold=30)

    # 只有 3 条可抽，就抽 3 条——不重复、不造数
    assert len(plan.cases) == 3
    assert len({c.item.id for c in plan.cases}) == 3
    assert plan.report["scoredPool"] == 3
    assert plan.report["selected"] == 3

    gaps = {gap["key"]: gap for gap in plan.report["gaps"]}
    assert "near-threshold:all" in gaps
    assert gaps["near-threshold:all"]["target"] == 30
    assert gaps["near-threshold:all"]["actual"] == 1
    assert gaps["near-threshold:all"]["gap"] == 29
    for category in ("research", "industry", "cases"):
        key = f"category:{category}"
        assert key in gaps, key
        assert gaps[key]["actual"] == 0
        assert gaps[key]["target"] == 1

    notes = "\n".join(plan.report["notes"])
    assert "抽不满 target=6" in notes
    assert "全库只有 1 条" in notes
    assert "不足 1 条" in notes

    # 缺口要能打印出来，不是只躺在数据结构里
    text = sg.render_gap_report(plan.report)
    assert "缺口" in text
    assert "near-threshold:all" in text
    assert "category:research" in text

    # 参数本身矛盾时直接报错，而不是静默少抽
    with pytest.raises(ValueError, match="无法同时满足"):
        plan_for(items, target=3, min_per_category=15)


def test_unfilled_quota_does_not_exceed_target() -> None:
    """约束填不满时也只能抽到 target 条，不能靠「剩余填充」超发。"""
    items = [make_item(f"i{n}", avg_score=float(n)) for n in range(40)]
    plan = plan_for(items, target=7, min_per_category=1, min_near_threshold=1)
    assert len(plan.cases) == 7


# ══ 3. 导出 xlsx ═══════════════════════════════════════════════════════


def test_write_candidates_xlsx_columns_and_rows(tmp_path: Path) -> None:
    items = [
        make_item(
            f"i{n}",
            category=CATEGORIES[n % len(CATEGORIES)],
            avg_score=52.0 + n,
            # 正文刻意长于 500 字，用来验证摘录截断（原文截断，不翻译）
            body="Original English body sentence. " * 40,
        )
        for n in range(6)
    ]
    plan = sg.build_sample_cases(
        items,
        thresholds=TEST_THRESHOLDS,
        categories=CATEGORIES,
        source_names={"dovetail-blog": "Dovetail Blog"},
        target=6,
        min_per_category=1,
        min_near_threshold=1,
    )
    out = tmp_path / "gold_candidates.xlsx"
    sg.write_candidates_xlsx(plan.cases, out)

    assert out.is_file()
    workbook = load_workbook(out)
    assert sg.SHEET_MAIN in workbook.sheetnames
    assert sg.SHEET_GUIDE in workbook.sheetnames

    sheet = workbook[sg.SHEET_MAIN]
    assert sheet.max_column == 10
    assert [cell.value for cell in sheet[1]] == list(sg.COLUMNS)
    assert sheet.max_row == len(plan.cases) + 1
    assert sheet.freeze_panes == "A2"
    assert sheet["A1"].font.bold is True
    # 正文摘录列自动换行
    assert sheet.cell(row=2, column=sg.COLUMNS.index("正文摘录") + 1).alignment.wrap_text is True
    # caseId 稳定编号 + 序号 1..N
    assert [sheet.cell(row=r, column=2).value for r in range(2, sheet.max_row + 1)] == [
        f"uxhot-{n:04d}" for n in range(1, len(plan.cases) + 1)
    ]
    assert [sheet.cell(row=r, column=1).value for r in range(2, sheet.max_row + 1)] == list(
        range(1, len(plan.cases) + 1)
    )
    # 来源列是信源名，不是 sourceId
    assert sheet.cell(row=2, column=4).value == "Dovetail Blog"
    # 正文摘录是原文前 500 字（英文保持英文）
    excerpt_col = sg.COLUMNS.index("正文摘录") + 1
    excerpt = sheet.cell(row=2, column=excerpt_col).value
    assert excerpt and excerpt.startswith("Original English body sentence.")
    assert len(excerpt) == 500

    guide_text = "\n".join(
        str(cell.value) for row in workbook[sg.SHEET_GUIDE].iter_rows() for cell in row
        if cell.value is not None
    )
    for expected in ("select", "reject", "either", "--convert", "gold.jsonl", "留空"):
        assert expected in guide_text, expected


def test_xlsx_contains_no_model_output_anchor_fields(tmp_path: Path) -> None:
    """D11：标注表里不得出现均分 / 建议 / 模型写的中文摘要等锚定内容。"""
    items = [
        make_item(f"i{n}", category=CATEGORIES[n % len(CATEGORIES)], avg_score=58.0 + n)
        for n in range(6)
    ]
    plan = sg.build_sample_cases(
        items,
        thresholds=TEST_THRESHOLDS,
        categories=CATEGORIES,
        source_names={"dovetail-blog": "Dovetail Blog"},
        target=6,
        min_per_category=1,
        min_near_threshold=1,
    )
    out = tmp_path / "gold_candidates.xlsx"
    sg.write_candidates_xlsx(plan.cases, out)
    workbook = load_workbook(out)
    sheet = workbook[sg.SHEET_MAIN]

    header = [str(cell.value or "") for cell in sheet[1]]
    for forbidden in ("均分", "建议", "summaryZh", "titleZh", "摘要"):
        assert all(forbidden not in name for name in header), forbidden

    # 主表每一个单元格都要干净：既不能出现禁词，也不能出现模型写的摘要文本
    model_texts = {f"模型摘要 {n}" for n in range(6)} | {f"模型标题 {n}" for n in range(6)}
    for row in sheet.iter_rows(values_only=True):
        for value in row:
            text = "" if value is None else str(value)
            for forbidden in sg.FORBIDDEN_MARKERS:
                assert forbidden not in text, f"标注表出现锚定字段 {forbidden!r}：{text!r}"
            for model_text in model_texts:
                assert model_text not in text, f"标注表出现模型产出：{text!r}"


def test_export_fills_excerpt_from_body_cache(tmp_path: Path) -> None:
    """回归：`data/items` 里正文被 strip_bodies 清空了，摘录必须来自补抓缓存。

    这是真实跑出来的 bug——一开始摘录列整列是空的，因为正文没从缓存传到写表那一步。
    """
    items = [
        make_item(f"cached-{n}", category=CATEGORIES[n % len(CATEGORIES)], avg_score=float(55 + n),
                  body="")   # 已处理条目：正文已被清空
        for n in range(6)
    ]
    items_path = tmp_path / "items" / "2026-10.jsonl"
    write_items(items_path, items)

    # 预先放好正文缓存（模拟上一次补抓的结果），--no-fetch 时直接复用
    cache_path = tmp_path / "bodies.jsonl"
    cache_path.write_text(
        "\n".join(
            json.dumps({"id": item.id, "body": f"补抓到的正文 {item.id} " * 50}, ensure_ascii=False)
            for item in items
        ) + "\n",
        encoding="utf-8",
    )

    out = tmp_path / "cand.xlsx"
    plan = sg.export_candidates(
        items_path=items_path,
        out_path=out,
        body_cache_path=cache_path,
        cfg=load_config(),
        target=6,
        min_per_category=1,
        min_near_threshold=1,
        no_fetch=True,
    )
    assert len(plan.cases) == 6
    assert all(c.body for c in plan.cases)          # 正文确实挂到了 case 上

    sheet = load_workbook(out)[sg.SHEET_MAIN]
    excerpt_col = sg.COLUMNS.index("正文摘录") + 1
    excerpts = [sheet.cell(row=r, column=excerpt_col).value for r in range(2, sheet.max_row + 1)]
    assert all(excerpts), "正文摘录不能整列为空"
    assert all(text.startswith("补抓到的正文") for text in excerpts)
    assert all(len(text) <= sg.DEFAULT_EXCERPT_CHARS for text in excerpts)
    # 抓到了正文就不该再写「未抓到原文正文」
    note_col = sg.COLUMNS.index("备注") + 1
    notes = [sheet.cell(row=r, column=note_col).value for r in range(2, sheet.max_row + 1)]
    assert all("未抓到原文正文" not in (note or "") for note in notes)


def test_export_marks_missing_body_in_notes(tmp_path: Path) -> None:
    """没缓存又 --no-fetch 时：不假装抓到，备注列如实说明。"""
    items = [
        make_item(f"nobody-{n}", category=CATEGORIES[n % len(CATEGORIES)], avg_score=float(55 + n))
        for n in range(6)
    ]
    items_path = tmp_path / "items" / "2026-10.jsonl"
    write_items(items_path, items)

    out = tmp_path / "cand.xlsx"
    plan = sg.export_candidates(
        items_path=items_path,
        out_path=out,
        body_cache_path=tmp_path / "empty.jsonl",
        cfg=load_config(),
        target=6,
        min_per_category=1,
        min_near_threshold=1,
        no_fetch=True,
    )
    assert plan.report["bodyMissing"] == [c.case_id for c in plan.cases]
    sheet = load_workbook(out)[sg.SHEET_MAIN]
    note_col = sg.COLUMNS.index("备注") + 1
    for row in range(2, sheet.max_row + 1):
        assert "未抓到原文正文" in (sheet.cell(row=row, column=note_col).value or "")


def test_decision_column_is_empty_and_has_real_dropdown(tmp_path: Path) -> None:
    items = [
        make_item(f"i{n}", category=CATEGORIES[n % len(CATEGORIES)], avg_score=58.0 + n)
        for n in range(6)
    ]
    plan = sg.build_sample_cases(
        items,
        thresholds=TEST_THRESHOLDS,
        categories=CATEGORIES,
        source_names={"dovetail-blog": "Dovetail Blog"},
        target=6,
        min_per_category=1,
        min_near_threshold=1,
    )
    out = tmp_path / "gold_candidates.xlsx"
    sg.write_candidates_xlsx(plan.cases, out)
    sheet = load_workbook(out)[sg.SHEET_MAIN]

    decision_col = sg.COLUMNS.index(sg.DECISION_COLUMN) + 1
    # 全部留空：预填 either 会让用户以为已经标完了
    for row in range(2, sheet.max_row + 1):
        assert sheet.cell(row=row, column=decision_col).value in (None, "")

    # 真实下拉：openpyxl 的 DataValidation（写进 xlsx 的 dataValidation 节点）
    validations = sheet.data_validations.dataValidation
    assert len(validations) == 1
    validation = validations[0]
    assert validation.type == "list"
    assert validation.formula1 == '"select,reject,either"'
    assert str(validation.sqref) == f"I2:I{sheet.max_row}"
    # allow_blank 必须为真：留空表示「还没标」
    assert validation.allowBlank is True


# ══ 4. --convert ═══════════════════════════════════════════════════════


def _export_then_fill(tmp_path: Path, decisions: dict[int, str], count: int = 12):
    """导出一份候选表，按行号填入 `该选吗`，返回 (xlsx 路径, 抽样 plan)。"""
    items = [
        make_item(
            f"item-{n}",
            category=CATEGORIES[n % len(CATEGORIES)],
            avg_score=float(55 + n),
            tier="T2" if n % 4 == 0 else "T1",
        )
        for n in range(count)
    ]
    plan = sg.build_sample_cases(
        items,
        thresholds=TEST_THRESHOLDS,
        categories=CATEGORIES,
        source_names={"dovetail-blog": "Dovetail Blog"},
        target=count,
        min_per_category=1,
        min_near_threshold=1,
    )
    xlsx = tmp_path / "gold_candidates.xlsx"
    sg.write_candidates_xlsx(plan.cases, xlsx)

    workbook = load_workbook(xlsx)
    sheet = workbook[sg.SHEET_MAIN]
    decision_col = sg.COLUMNS.index(sg.DECISION_COLUMN) + 1
    for row_index, value in decisions.items():
        sheet.cell(row=row_index + 1, column=decision_col, value=value)
    workbook.save(xlsx)
    return xlsx, plan


def test_convert_skips_blanks_and_keeps_either(tmp_path: Path) -> None:
    # 行 1..6：2 空、1 个无法识别；其余 3 条有效（含中文写法与 either）
    decisions = {
        1: "select",
        2: "",           # 留空 → 跳过
        3: "该选",
        4: "reject",
        5: "maybe",      # 无法识别 → 按未标注跳过
        6: "两可",
    }
    xlsx, plan = _export_then_fill(tmp_path, decisions, count=6)
    assert len(plan.cases) == 6
    gold_path = tmp_path / "gold.jsonl"
    case_ids = {case.case_id: case.item.id for case in plan.cases}
    cases, report = sg.convert_xlsx_to_gold(xlsx, gold_path, case_ids=case_ids)

    assert report["rows"] == 6
    assert report["skipped"] == 2
    assert set(report["skippedCaseIds"]) == {"uxhot-0002", "uxhot-0005"}
    assert report["converted"] == 4

    # 留空的**不是** either
    assert sum(1 for c in cases if c.gold.decision == "either") == 1
    assert sum(1 for c in cases if c.gold.decision == "select") == 2
    assert sum(1 for c in cases if c.gold.decision == "reject") == 1
    assert report["summary"]["either"] == 1
    assert report["summary"]["scored"] == 3
    assert report["summary"]["selectRate"] == round(2 / 3, 4)
    # 无法识别的值要单独报告，不能悄悄当成「已标注」
    assert [entry["value"] for entry in report["unknownValues"]] == ["maybe"]
    # 分层从说明 sheet 的机器可读区带回来
    assert all(c.samplingContext.samplingStratum for c in cases)


def test_convert_split_is_two_to_one_and_stable(tmp_path: Path) -> None:
    decisions = {index: "select" for index in range(1, 11)}
    xlsx, plan = _export_then_fill(tmp_path, decisions, count=10)
    gold_path = tmp_path / "gold.jsonl"
    case_ids = {case.case_id: case.item.id for case in plan.cases}
    cases, _ = sg.convert_xlsx_to_gold(xlsx, gold_path, case_ids=case_ids)

    # 每条都按 assign_split(caseId) 切分，且稳定
    assert all(c.samplingContext.benchmarkSplit == assign_split(c.caseId) for c in cases)

    # 2:1 比例在大量 caseId 上成立（少量样本允许波动）
    splits = [assign_split(f"uxhot-{n:04d}") for n in range(1, 151)]
    development = splits.count("development")
    assert 0.60 <= development / len(splits) <= 0.73


def test_convert_source_facts_and_readback(tmp_path: Path) -> None:
    items = [
        make_item("t1-item", tier="T1", category="tools", avg_score=58.0,
                  body="这是一段中文正文。" * 30, lang="zh"),
        make_item("t2-item", tier="T2", category="methods", avg_score=75.0,
                  body="English body. " * 40, lang="en"),
    ] + [
        make_item(f"fill-{n}", category=CATEGORIES[n % len(CATEGORIES)], avg_score=20.0 + n)
        for n in range(4)
    ]
    items_path = tmp_path / "items" / "2026-10.jsonl"
    write_items(items_path, items)
    plan = sg.build_sample_cases(
        items,
        thresholds=TEST_THRESHOLDS,
        categories=CATEGORIES,
        source_names={"dovetail-blog": "Dovetail Blog"},
        target=6,
        min_per_category=1,
        min_near_threshold=1,
    )
    xlsx = tmp_path / "gold_candidates.xlsx"
    sg.write_candidates_xlsx(plan.cases, xlsx)

    # 找出目标两条在表里的行号，别假设顺序
    id_by_case = {case.case_id: case.item.id for case in plan.cases}
    row_of = {item_id: case_id for case_id, item_id in id_by_case.items()}
    workbook = load_workbook(xlsx)
    sheet = workbook[sg.SHEET_MAIN]
    decision_col = sg.COLUMNS.index(sg.DECISION_COLUMN) + 1
    for row in range(2, sheet.max_row + 1):
        case_id = sheet.cell(row=row, column=2).value
        item_id = id_by_case[case_id]
        if item_id == "t1-item":
            sheet.cell(row=row, column=decision_col, value="select")
        elif item_id == "t2-item":
            sheet.cell(row=row, column=decision_col, value="reject")
    workbook.save(xlsx)

    bodies = {item.id: item.body for item in items}
    gold_path = tmp_path / "gold.jsonl"
    cases, report = sg.convert_xlsx_to_gold(
        xlsx, gold_path, bodies=bodies, case_ids=id_by_case,
        source_kinds={"dovetail-blog": "web_list"},
        name_to_source_id={"Dovetail Blog": "dovetail-blog"},
    )
    # 只有 2 条被标注，且都有正文 → 没有 bodyMissing；
    # 没标的 4 条不算（它们不进金标，缺不缺正文无所谓）
    assert report["bodyMissing"] == []
    assert report["skipped"] == 4
    assert row_of["t1-item"] not in report["bodyMissing"]
    assert row_of["t2-item"] not in report["bodyMissing"]

    by_item = {c.material.title: c for c in cases}
    assert by_item, "标题应能作为键索引到金标条目"
    first = next(c for c in cases if c.gold.decision == "select")
    assert first.sourceFacts.sourceTier == "T1"
    assert first.sourceFacts.firstParty is True          # T1 → 一手
    assert first.sourceFacts.language == "zh"            # 正文是中文
    assert first.sourceFacts.sourceKind == "web_list"    # 从配置回填的真值
    assert first.material.bodyOriginal and "中文正文" in first.material.bodyOriginal
    assert first.material.sourceName == "Dovetail Blog"
    assert first.material.publishedAt is not None

    second = next(c for c in cases if c.gold.decision == "reject")
    assert second.sourceFacts.sourceTier == "T2"
    assert second.sourceFacts.firstParty is False        # 非 T1 → 不是一手
    assert second.sourceFacts.language == "en"

    # 写出来的 gold.jsonl 必须能被 load_gold 读回，且内容一致
    loaded = load_gold(gold_path)
    assert len(loaded) == len(cases)
    assert [c.caseId for c in loaded] == [c.caseId for c in cases]
    assert loaded[0].samplingContext.benchmarkSplit == cases[0].samplingContext.benchmarkSplit
    assert {c.gold.decision for c in loaded} == {"select", "reject"}


def test_convert_all_blank_raises(tmp_path: Path) -> None:
    """一行都没标就明确报错，不写一个空金标文件。"""
    xlsx, _ = _export_then_fill(tmp_path, {})
    with pytest.raises(ValueError, match="没有任何一行填了"):
        sg.convert_xlsx_to_gold(xlsx, tmp_path / "gold.jsonl")


def test_parse_decision_recognizes_chinese_and_numbers() -> None:
    """转换依赖 gold.parse_decision 归一，这里把契约钉住（中文写法必须认）。"""
    for raw in ("select", "选", "该选", "SELECT", " 该选 "):
        assert parse_decision(raw) == "select", raw
    for raw in ("reject", "不选", "不该选", "Reject"):
        assert parse_decision(raw) == "reject", raw
    for raw in ("either", "两可", "都可以", "不确定"):
        assert parse_decision(raw) == "either", raw
    for raw in ("", "   ", None, "maybe", "也许"):
        assert parse_decision(raw) is None, raw


# ══ 5. CLI 端到端（--no-fetch，不访问网络）═════════════════════════════


def test_cli_export_and_convert_roundtrip(tmp_path: Path) -> None:
    items = [
        make_item(f"cli-{n}", category=CATEGORIES[n % len(CATEGORIES)], avg_score=float(50 + n))
        for n in range(6)
    ]
    items_path = tmp_path / "items" / "2026-10.jsonl"
    write_items(items_path, items)

    out = tmp_path / "cand.xlsx"
    code = sg.main([
        "--items", str(items_path),
        "--out", str(out),
        "--body-cache", str(tmp_path / "bodies.jsonl"),
        "--report", str(tmp_path / "report.json"),
        "--no-fetch",
        "--target", "6",
        "--min-per-category", "1",
        "--min-near-threshold", "1",
    ])
    assert code == 0
    assert out.is_file()

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["selected"] == 6
    assert report["gaps"] == []          # 这个小池子够满足测试口径

    sheet = load_workbook(out)[sg.SHEET_MAIN]
    assert [cell.value for cell in sheet[1]] == list(sg.COLUMNS)

    # 标 3 条，其中 1 条 either；转换后应写出 3 条
    workbook = load_workbook(out)
    sheet = workbook[sg.SHEET_MAIN]
    decision_col = sg.COLUMNS.index(sg.DECISION_COLUMN) + 1
    for row, value in ((2, "select"), (3, "reject"), (4, "either")):
        sheet.cell(row=row, column=decision_col, value=value)
    workbook.save(out)

    gold_path = tmp_path / "gold.jsonl"
    code = sg.main([
        "--convert",
        "--items", str(items_path),
        "--out", str(out),
        "--gold", str(gold_path),
        "--body-cache", str(tmp_path / "bodies.jsonl"),
    ])
    assert code == 0
    cases = load_gold(gold_path)
    assert len(cases) == 3
    assert {c.gold.decision for c in cases} == {"select", "reject", "either"}


# ══ 分层不得泄漏进标注表（D11 的延伸）══════════════════════════════════
#
# 分层值是从模型均分推出来的：`near-threshold:all` 等于告诉标注的人
# 「这条贴着门槛」。即使只写在「说明」sheet 里，也是把模型判断泄漏给了
# 正在标注的人，所以它必须活在旁路文件里，标注表里一个字符都不能有。


def _plan_for_leak_check(tmp_path: Path):
    items = [
        make_item(f"leak{n}", category=CATEGORIES[n % len(CATEGORIES)], avg_score=52.0 + n)
        for n in range(6)
    ]
    plan = sg.build_sample_cases(
        items,
        thresholds=TEST_THRESHOLDS,
        categories=CATEGORIES,
        source_names={"dovetail-blog": "Dovetail Blog"},
        target=6,
        min_per_category=1,
        min_near_threshold=3,
    )
    return plan


def test_xlsx_never_mentions_stratum_or_near_threshold(tmp_path: Path) -> None:
    """整个工作簿（含所有 sheet）都不能出现分层值或 near-threshold 字样。"""
    plan = _plan_for_leak_check(tmp_path)
    out = tmp_path / "gold_candidates.xlsx"
    sg.write_candidates_xlsx(plan.cases, out)

    workbook = load_workbook(out)
    needles = ("near-threshold", "category:tools", "tier:T1", "samplingStratum", "分层：")
    for sheet_name in workbook.sheetnames:
        for row in workbook[sheet_name].iter_rows(values_only=True):
            for cell in row:
                text = "" if cell is None else str(cell)
                for needle in needles:
                    assert needle not in text, (
                        f"{sheet_name} 里出现了分层线索「{needle}」：{text[:80]}"
                    )


def test_strata_written_to_sidecar_next_to_xlsx(tmp_path: Path) -> None:
    plan = _plan_for_leak_check(tmp_path)
    out = tmp_path / "gold_candidates.xlsx"
    sg.write_candidates_xlsx(plan.cases, out)

    sidecar = sg.stratum_sidecar(out)
    assert sidecar.is_file(), "分层应写进 sidecar 文件"
    mapping = json.loads(sidecar.read_text(encoding="utf-8"))
    assert len(mapping) == len(plan.cases)
    assert all(case.case_id in mapping for case in plan.cases)


def test_read_back_gets_strata_from_sidecar(tmp_path: Path) -> None:
    plan = _plan_for_leak_check(tmp_path)
    out = tmp_path / "gold_candidates.xlsx"
    sg.write_candidates_xlsx(plan.cases, out)

    _, strata = sg.read_candidates_xlsx(out)
    assert strata, "应能从 sidecar 读回分层"
    assert set(strata) == {case.case_id for case in plan.cases}


def test_missing_sidecar_degrades_gracefully(tmp_path: Path) -> None:
    """sidecar 丢了不该让 --convert 失败，只是分层为空。"""
    plan = _plan_for_leak_check(tmp_path)
    out = tmp_path / "gold_candidates.xlsx"
    sg.write_candidates_xlsx(plan.cases, out)
    sg.stratum_sidecar(out).unlink()

    _, strata = sg.read_candidates_xlsx(out)
    assert strata == {}
