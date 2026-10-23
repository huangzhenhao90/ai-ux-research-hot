"""阶段 5.3 验收：发布层产物正确、公开边界守得住、校验失败时保留上一版。

测试全部用 `tests/fixtures/publish_items.py` 的假条目，不抓网络、不调模型。
重点不在「函数能跑」，而在几条**必须为真**的规则：

- 产物里不许出现 `body`（含报告透传进来的文件）
- BLOCK / UNKNOWN 不公开
- 无重复 id、同一 id 在各文件里内容一致
- 精选缺 titleZh / summaryZh、链接不是 http(s)、日期没时区 → 整次发布失败
- **校验失败时正式目录一字节不动**（这才是「保留上一版」）
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import feedparser
import pytest

from tests.fixtures.publish_items import (
    NOW,
    SECRET_BODY,
    daily_report,
    id_of,
    make_item,
    sample_items,
    url_of,
    weekly_report,
    write_reports,
)
from uxhot.config import load_config
from uxhot.models import Status
from uxhot.publish import (
    DETAIL_EXTRA_FIELDS,
    PUBLIC_FIELDS,
    PublishError,
    build_and_validate,
    publish_atomic,
    validate_publish_dir,
)

SITE_URL = "https://huangzhenhao90.github.io/ai-ux-research-hot"


# ── 夹具 ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture()
def public_dir(tmp_path: Path) -> Path:
    """发布根目录（对应仓库里的 web/public）。"""
    return tmp_path / "web" / "public"


@pytest.fixture()
def reports_dir(tmp_path: Path) -> Path:
    return write_reports(tmp_path / "data" / "reports")


@pytest.fixture()
def empty_reports(tmp_path: Path) -> Path:
    """还没有报告时的样子（只有空目录）。"""
    target = tmp_path / "data" / "reports"
    (target / "daily").mkdir(parents=True, exist_ok=True)
    (target / "weekly").mkdir(parents=True, exist_ok=True)
    return target


@pytest.fixture()
def published(cfg, public_dir: Path, reports_dir: Path) -> Path:
    build_and_validate(
        sample_items(), cfg, public_dir=public_dir, reports_dir=reports_dir, now=NOW
    )
    return public_dir


# ── 小工具 ─────────────────────────────────────────────────────────────


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def iter_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def snapshot(root: Path) -> dict[str, str]:
    """目录快照（相对路径 → 内容），用来证明「一字节没动」。"""
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8", errors="ignore")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def all_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    for path in sorted(root.rglob("*.json")):
        for node in iter_dicts(load_json(path)):
            value = node.get("id")
            if isinstance(value, str):
                ids.add(value)
    return ids


# ── 公开边界：body / BLOCK / UNKNOWN ───────────────────────────────────


def test_output_contains_no_body_field(published: Path) -> None:
    """硬要求：`web/public/` 里任何文件都不许出现 body（含报告透传文件）。"""
    for path in sorted(published.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert SECRET_BODY not in text, f"{path} 里出现了原文全文"
        if path.suffix != ".json":
            continue
        for node in iter_dicts(load_json(path)):
            for key in ("body", "bodyTruncated", "fact", "promptVersions", "scores", "errors"):
                assert key not in node, f"{path} 里出现了不该公开的字段「{key}」"


def test_blocked_and_unknown_are_not_published(published: Path) -> None:
    banned = {id_of(5), id_of(6)}
    assert not (banned & all_ids(published))
    for path in sorted(published.rglob("*")):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for item_id in banned:
                assert item_id not in text, f"{path} 里出现了不该公开的条目 {item_id}"
    for path in sorted(published.rglob("*.json")):
        for node in iter_dicts(load_json(path)):
            assert node.get("status") not in {"blocked", "unknown"}


def test_item_fields_stay_inside_whitelist(published: Path) -> None:
    """条目对象的字段必须是白名单的子集（正向白名单，不是「排除 body」）。"""
    allowed = set(PUBLIC_FIELDS)
    detail_allowed = allowed | set(DETAIL_EXTRA_FIELDS)
    checked = 0
    for path in sorted(published.rglob("*.json")):
        rel = path.relative_to(published).as_posix()
        if rel.startswith("data/reports/"):
            continue  # 报告 schema 归 report/ 模块
        for node in iter_dicts(load_json(path)):
            if "status" not in node:
                continue  # 只有条目对象带 status
            limit = detail_allowed if rel.startswith("data/items/") else allowed
            extra = set(node) - limit
            assert not extra, f"{rel}: 条目多出白名单外的字段 {sorted(extra)}"
            checked += 1
    assert checked > 0, "没检查到任何条目，测试本身失效了"


def test_avg_score_only_when_show_score(cfg, public_dir: Path, empty_reports: Path) -> None:
    """真实配置 showScore=false → 产物里没有 avgScore；打开后才有。"""
    build_and_validate(
        sample_items(), cfg, public_dir=public_dir, reports_dir=empty_reports, now=NOW
    )
    assert cfg.site.showScore is False
    doc = load_json(public_dir / "data" / "all" / "2026-10.json")
    assert all("avgScore" not in item for item in doc["items"])

    loud = cfg.model_copy(update={"site": cfg.site.model_copy(update={"showScore": True})})
    other = public_dir.parent / "public-with-score"
    build_and_validate(sample_items(), loud, public_dir=other, reports_dir=empty_reports, now=NOW)
    scored = load_json(other / "data" / "all" / "2026-10.json")["items"]
    assert any(item["avgScore"] is not None for item in scored)


# ── 结构：latest / all / items / categories / topics / search ───────────


def test_latest_covers_three_edition_days(published: Path) -> None:
    """首页三天窗口按出刊日（北京 08:00 边界）切，不是自然日。"""
    doc = load_json(published / "data" / "latest.json")
    assert doc["windowDays"] == 3
    assert doc["editionHour"] == 8
    # 出刊日 = 包含该条目的窗口右端点：10-21 09:00 北京落在 [10-21 08:00, 10-22 08:00)
    assert [day["date"] for day in doc["days"]] == [
        "2026-10-22",
        "2026-10-21",
        "2026-10-20",
    ]
    ids = [item["id"] for day in doc["days"] for item in day["items"]]
    assert ids == [id_of(1), id_of(2), id_of(3)]
    assert all(item["status"] == "selected" for day in doc["days"] for item in day["items"])
    assert id_of(4) not in ids, "四天前的条目不该进首页"
    # 北京时间 10-21 07:00 发布的那条属于 10-20 那一期
    assert id_of(2) in [item["id"] for item in doc["days"][1]["items"]]


def test_all_month_keeps_non_selected(published: Path) -> None:
    doc = load_json(published / "data" / "all" / "2026-10.json")
    ids = {item["id"] for item in doc["items"]}
    assert ids == {id_of(1), id_of(2), id_of(3), id_of(4), id_of(7), id_of(8)}
    assert doc["count"] == 6
    index = load_json(published / "data" / "all" / "index.json")
    assert index["total"] == 6
    assert index["months"] == [
        {"month": "2026-10", "count": 6, "path": "data/all/2026-10.json"}
    ]


def test_item_detail_matches_filename_and_lists_related(published: Path) -> None:
    detail = load_json(published / "data" / "items" / f"{id_of(1)}.json")
    assert detail["id"] == id_of(1)
    assert [ref["id"] for ref in detail["related"]] == [id_of(7)]
    assert detail["related"][0]["url"].startswith("https://")
    other = load_json(published / "data" / "items" / f"{id_of(7)}.json")
    assert [ref["id"] for ref in other["related"]] == [id_of(1)]
    # 没有同事件伙伴的条目给空数组，不是缺字段
    solo = load_json(published / "data" / "items" / f"{id_of(3)}.json")
    assert solo["related"] == []


def test_categories_cover_all_keys_even_empty(cfg, published: Path) -> None:
    index = load_json(published / "data" / "categories" / "index.json")
    assert {row["key"] for row in index["categories"]} == set(cfg.taxonomy.category_keys)
    tools = load_json(published / "data" / "categories" / "tools.json")
    # 条目 1（精选）与条目 7（同事件的其他报道）都在 tools 分类，按分数降序
    assert [item["id"] for item in tools["items"]] == [id_of(1), id_of(7)]
    assert tools["label"] == "工具"
    empty = load_json(published / "data" / "categories" / "cases.json")
    assert empty["count"] == 0 and empty["items"] == []


def test_topics_match_entity_id_and_tags(cfg, published: Path) -> None:
    index = load_json(published / "data" / "topics" / "index.json")
    assert len(index["topics"]) == len(cfg.topics.topics)
    assert {group["key"] for group in index["groups"]} == {
        group.key for group in cfg.topics.groups
    }
    # qualtrics 主题页按 entityId 命中（条目 1、7 的 entities 里都有 qualtrics）
    qualtrics = load_json(published / "data" / "topics" / "qualtrics.json")
    assert [item["id"] for item in qualtrics["items"]] == [id_of(1), id_of(7)]
    # synthetic-users 主题页按标签命中
    synth = load_json(published / "data" / "topics" / "synthetic-users.json")
    assert [item["id"] for item in synth["items"]] == [id_of(2)]
    # ai-interview 主题页按标签命中
    interview = load_json(published / "data" / "topics" / "ai-interview.json")
    assert [item["id"] for item in interview["items"]] == [id_of(1), id_of(7)]
    # 没有命中条目的主题页也要有文件（前端 generateStaticParams 用）
    assert (published / "data" / "topics" / "ethics.json").is_file()


def test_search_index_has_title_summary_tags(published: Path) -> None:
    doc = load_json(published / "data" / "search-index.json")
    assert doc["count"] == len(doc["items"]) == 6
    allowed = set(PUBLIC_FIELDS)
    for entry in doc["items"]:
        assert set(entry) <= allowed
        assert entry["id"] and entry["title"]
        assert isinstance(entry["tags"], list)
    assert doc["items"][0]["id"] == id_of(1), "搜索索引应与首页同序（分数高的在前）"


def test_site_json_carries_base_path(published: Path) -> None:
    doc = load_json(published / "data" / "site.json")
    assert doc["siteUrl"] == SITE_URL
    assert doc["basePath"] == "/ai-ux-research-hot"
    assert doc["name"] == "UXHOT"
    assert doc["alias"] == "AI 用研热点"
    assert doc["subject"] == "AI 用研"


def test_data_manifest_counts(published: Path) -> None:
    doc = load_json(published / "data" / "index.json")
    assert doc["counts"] == {
        "public": 6,
        "selected": 3,
        "months": 1,
        "categories": 6,
        "topics": 24,
        "searchIndex": 6,
        "dailyReports": 2,
        "weeklyReports": 1,
    }
    assert doc["months"] == ["2026-10"]
    assert doc["latestDays"] == ["2026-10-22", "2026-10-21", "2026-10-20"]


# ── 日期 ───────────────────────────────────────────────────────────────


def test_all_dates_are_tz_aware_utc(published: Path) -> None:
    checked = 0
    for path in sorted(published.rglob("*.json")):
        for node in iter_dicts(load_json(path)):
            for key, value in node.items():
                if not key.endswith("At") or not isinstance(value, str) or not value:
                    continue
                parsed = datetime.fromisoformat(value)
                assert parsed.tzinfo is not None, f"{path}: {key}={value} 没有时区"
                assert parsed.utcoffset() == timedelta(0), f"{path}: {key}={value} 不是 UTC"
                checked += 1
    assert checked > 0


def test_published_at_is_normalized_to_utc(published: Path) -> None:
    """输入带 +08:00，产物必须是同一个瞬间的 UTC 表示。"""
    doc = load_json(published / "data" / "latest.json")
    item = doc["days"][0]["items"][0]
    assert item["id"] == id_of(1)
    assert item["publishedAt"] == "2026-10-21T01:00:00+00:00"


def test_naive_datetime_in_product_is_rejected(published: Path) -> None:
    """手改产物成没有时区的时间 → 校验必须报出来（挡住「日期不带时区」）。"""
    path = published / "data" / "latest.json"
    doc = load_json(path)
    doc["days"][0]["items"][0]["publishedAt"] = "2026-10-21T01:00:00"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    problems = validate_publish_dir(published)
    assert any("没有时区" in p and "publishedAt" in p for p in problems), problems


# ── 无重复 id ──────────────────────────────────────────────────────────


def test_publish_has_no_duplicate_ids(published: Path) -> None:
    assert validate_publish_dir(published) == []
    for path in sorted(published.rglob("*.json")):
        rel = path.relative_to(published).as_posix()
        if rel.startswith("data/reports/"):
            continue
        seen: list[str] = []
        for node in iter_dicts(load_json(path)):
            value = node.get("id")
            if isinstance(value, str):
                seen.append(value)
        assert len(seen) == len(set(seen)), f"{rel} 里有重复 id"


def test_duplicate_id_in_one_file_is_detected(published: Path) -> None:
    path = published / "data" / "all" / "2026-10.json"
    doc = load_json(path)
    doc["items"].append(dict(doc["items"][0]))
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    problems = validate_publish_dir(published)
    assert any("id 重复" in p for p in problems), problems


def test_inconsistent_values_for_same_id_are_detected(published: Path) -> None:
    """同一 id 在 latest 与 all 里说法不一致 → 必须报出来。"""
    path = published / "data" / "all" / "2026-10.json"
    doc = load_json(path)
    doc["items"][0]["titleZh"] = "被改过的标题"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    problems = validate_publish_dir(published)
    assert any("不一致" in p for p in problems), problems


def test_body_field_in_product_is_detected(published: Path) -> None:
    path = published / "data" / "items" / f"{id_of(3)}.json"
    doc = load_json(path)
    doc["body"] = "原文全文"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    problems = validate_publish_dir(published)
    assert any("body" in p for p in problems), problems


def test_count_mismatch_is_detected(published: Path) -> None:
    path = published / "data" / "categories" / "tools.json"
    doc = load_json(path)
    doc["count"] = 99
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    problems = validate_publish_dir(published)
    assert any("count=99" in p for p in problems), problems


def test_filename_content_mismatch_is_detected(published: Path) -> None:
    path = published / "data" / "topics" / "qualtrics.json"
    doc = load_json(path)
    doc["slug"] = "dovetail"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    problems = validate_publish_dir(published)
    assert any("slug" in p and "文件名" in p for p in problems), problems


def test_item_detail_filename_must_equal_id(published: Path) -> None:
    source = published / "data" / "items" / f"{id_of(3)}.json"
    stray = published / "data" / "items" / "wrong-name.json"
    stray.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    problems = validate_publish_dir(published)
    assert any("wrong-name" in p for p in problems), problems


def test_missing_required_file_is_detected(published: Path) -> None:
    (published / "llms.txt").unlink()
    problems = validate_publish_dir(published)
    assert any("llms.txt" in p for p in problems), problems


# ── 校验拦截：发布必须整体失败 ──────────────────────────────────────────


def test_selected_without_title_zh_fails_publish(cfg, public_dir: Path, empty_reports: Path) -> None:
    items = [make_item(1, titleZh=None), make_item(2)]
    with pytest.raises(PublishError) as excinfo:
        build_and_validate(items, cfg, public_dir=public_dir, reports_dir=empty_reports, now=NOW)
    assert any("titleZh" in p for p in excinfo.value.problems)


def test_selected_without_summary_zh_fails_publish(
    cfg, public_dir: Path, empty_reports: Path
) -> None:
    items = [make_item(1, summaryZh="   ")]
    with pytest.raises(PublishError) as excinfo:
        build_and_validate(items, cfg, public_dir=public_dir, reports_dir=empty_reports, now=NOW)
    assert any("summaryZh" in p for p in excinfo.value.problems)


def test_non_http_link_fails_publish(cfg, public_dir: Path, empty_reports: Path) -> None:
    items = [make_item(1, url="ftp://example.com/post-1")]
    with pytest.raises(PublishError) as excinfo:
        build_and_validate(items, cfg, public_dir=public_dir, reports_dir=empty_reports, now=NOW)
    assert any("http(s)" in p for p in excinfo.value.problems)


def test_javascript_url_fails_publish(cfg, public_dir: Path, empty_reports: Path) -> None:
    items = [make_item(1, url="javascript:alert(1)")]
    with pytest.raises(PublishError) as excinfo:
        build_and_validate(items, cfg, public_dir=public_dir, reports_dir=empty_reports, now=NOW)
    assert any("http(s)" in p for p in excinfo.value.problems)


def test_validation_failure_keeps_previous_version(
    cfg, public_dir: Path, reports_dir: Path
) -> None:
    """核心要求：跑一次会失败的发布，旧数据必须原样还在。"""
    build_and_validate(
        sample_items(), cfg, public_dir=public_dir, reports_dir=reports_dir, now=NOW
    )
    (public_dir / "KEEP-ME.txt").write_text("上一版留下的文件", encoding="utf-8")
    before = snapshot(public_dir)
    assert before, "第一版没写出来，后面的断言没意义"

    broken = [
        make_item(1, url="ftp://example.com/post-1"),  # 链接不合规
        make_item(2, titleZh=None),                    # 精选缺中文标题
    ]
    with pytest.raises(PublishError) as excinfo:
        build_and_validate(
            broken, cfg, public_dir=public_dir, reports_dir=reports_dir, now=NOW
        )
    assert any("http(s)" in p for p in excinfo.value.problems)
    assert any("titleZh" in p for p in excinfo.value.problems)

    assert snapshot(public_dir) == before, "校验失败却动了正式目录"
    assert (public_dir / "KEEP-ME.txt").read_text(encoding="utf-8") == "上一版留下的文件"
    assert not list(public_dir.parent.glob(".publish-stage-*")), "临时目录没清干净"


def test_first_publish_into_missing_dir_works(cfg, tmp_path: Path, empty_reports: Path) -> None:
    """第一次发布时正式目录还不存在，也要能落位。"""
    target = tmp_path / "web" / "public"
    result = build_and_validate(
        sample_items(), cfg, public_dir=target, reports_dir=empty_reports, now=NOW
    )
    assert result.replaced is False
    assert (target / "data" / "latest.json").is_file()
    assert not list(target.parent.glob(".publish-stage-*"))


def test_successful_publish_replaces_previous_and_drops_stale_files(
    cfg, public_dir: Path, empty_reports: Path
) -> None:
    build_and_validate(
        sample_items(), cfg, public_dir=public_dir, reports_dir=empty_reports, now=NOW
    )
    stale = public_dir / "data" / "obsolete.json"
    stale.write_text("{}", encoding="utf-8")
    result = build_and_validate(
        sample_items(), cfg, public_dir=public_dir, reports_dir=empty_reports, now=NOW
    )
    assert result.replaced is True
    assert not stale.exists(), "整体替换后不该留下上一版的孤儿文件"


def test_validate_reports_missing_dir(tmp_path: Path) -> None:
    problems = validate_publish_dir(tmp_path / "nope")
    assert problems and "不存在" in problems[0]


def test_publish_is_deterministic(cfg, tmp_path: Path, empty_reports: Path) -> None:
    """同样的输入与 now 必须产出逐字节相同的结果（顺序抖动会让 CI 反复提交）。"""
    first = tmp_path / "a"
    second = tmp_path / "b"
    build_and_validate(sample_items(), cfg, public_dir=first, reports_dir=empty_reports, now=NOW)
    build_and_validate(sample_items(), cfg, public_dir=second, reports_dir=empty_reports, now=NOW)
    assert snapshot(first) == snapshot(second)


def test_publish_atomic_passes_through_build_counts(tmp_path: Path) -> None:
    calls: list[str] = []

    def build(stage: Path) -> dict[str, int]:
        calls.append(str(stage))
        (stage / "hello.txt").write_text("hi", encoding="utf-8")
        return {"n": 7}

    result = publish_atomic(tmp_path / "out", build, validate=lambda _: [])
    assert result.counts == {"n": 7}
    assert result.replaced is False
    assert (tmp_path / "out" / "hello.txt").read_text(encoding="utf-8") == "hi"
    assert len(calls) == 1


# ── 报告透传与契约校验 ─────────────────────────────────────────────────


def test_reports_are_passed_through_unchanged(published: Path, reports_dir: Path) -> None:
    source = load_json(reports_dir / "daily" / "2026-10-21.json")
    copied = load_json(published / "data" / "reports" / "daily" / "2026-10-21.json")
    assert copied == source
    assert load_json(published / "data" / "reports" / "weekly" / "2026-W43.json") == weekly_report()


def test_report_index_is_sorted_with_urls_and_counts(published: Path) -> None:
    daily = load_json(published / "data" / "reports" / "daily" / "index.json")
    assert daily["kind"] == "daily"
    assert daily["count"] == 2
    assert [entry["date"] for entry in daily["entries"]] == ["2026-10-21", "2026-10-20"]
    first = daily["entries"][0]
    assert first["url"] == f"{SITE_URL}/daily/2026-10-21/"
    assert first["count"] == 3  # 取 stats.selectedCount
    assert first["title"] is None
    assert daily["entries"][1]["count"] == 0  # 空刊

    weekly = load_json(published / "data" / "reports" / "weekly" / "index.json")
    assert [entry["week"] for entry in weekly["entries"]] == ["2026-W43"]
    assert weekly["entries"][0]["url"] == f"{SITE_URL}/weekly/2026-W43/"
    assert weekly["entries"][0]["count"] == 12  # 取 stats.itemCount


def test_empty_reports_dir_still_publishes(cfg, public_dir: Path, empty_reports: Path) -> None:
    result = build_and_validate(
        sample_items(), cfg, public_dir=public_dir, reports_dir=empty_reports, now=NOW
    )
    assert result.counts["dailyReports"] == 0
    index = load_json(public_dir / "data" / "reports" / "daily" / "index.json")
    assert index["entries"] == []


def test_report_with_body_is_rejected(cfg, public_dir: Path, reports_dir: Path) -> None:
    """报告透传文件里夹带 body 也要挡住（Lead 明确要求）。"""
    path = reports_dir / "daily" / "2026-10-21.json"
    doc = load_json(path)
    doc["headline"]["body"] = "原文全文"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PublishError) as excinfo:
        build_and_validate(
            sample_items(), cfg, public_dir=public_dir, reports_dir=reports_dir, now=NOW
        )
    assert any("body" in p for p in excinfo.value.problems)


def test_daily_report_without_headline_when_not_empty_is_rejected(
    cfg, public_dir: Path, reports_dir: Path
) -> None:
    path = reports_dir / "daily" / "2026-10-21.json"
    doc = load_json(path)
    doc["empty"] = False
    doc["headline"] = None
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PublishError) as excinfo:
        build_and_validate(
            sample_items(), cfg, public_dir=public_dir, reports_dir=reports_dir, now=NOW
        )
    assert any("headline" in p for p in excinfo.value.problems)


def test_report_with_wrong_kind_is_rejected(cfg, public_dir: Path, reports_dir: Path) -> None:
    path = reports_dir / "daily" / "2026-10-21.json"
    doc = load_json(path)
    doc["kind"] = "weekly"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PublishError) as excinfo:
        build_and_validate(
            sample_items(), cfg, public_dir=public_dir, reports_dir=reports_dir, now=NOW
        )
    assert any("kind" in p for p in excinfo.value.problems)


def test_weekly_overview_source_must_be_known(cfg, public_dir: Path, reports_dir: Path) -> None:
    path = reports_dir / "weekly" / "2026-W43.json"
    doc = load_json(path)
    doc["overviewSource"] = "llm"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PublishError) as excinfo:
        build_and_validate(
            sample_items(), cfg, public_dir=public_dir, reports_dir=reports_dir, now=NOW
        )
    assert any("overviewSource" in p for p in excinfo.value.problems)


def test_report_index_entry_without_file_is_rejected(published: Path) -> None:
    path = published / "data" / "reports" / "daily" / "index.json"
    doc = load_json(path)
    doc["entries"].append({"date": "2026-10-19", "url": f"{SITE_URL}/daily/2026-10-19/", "count": 1, "title": None})
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    problems = validate_publish_dir(published)
    assert any("2026-10-19" in p for p in problems), problems


def test_report_file_missing_from_index_is_rejected(published: Path) -> None:
    stray = published / "data" / "reports" / "daily" / "2026-10-18.json"
    stray.write_text(json.dumps(daily_report("2026-10-18"), ensure_ascii=False), encoding="utf-8")
    problems = validate_publish_dir(published)
    assert any("2026-10-18" in p for p in problems), problems


# ── RSS ────────────────────────────────────────────────────────────────


def test_rss_parses_and_has_one_entry_per_selected(published: Path) -> None:
    text = (published / "rss.xml").read_text(encoding="utf-8")
    feed = feedparser.parse(text)
    assert not feed.bozo, getattr(feed, "bozo_exception", None)
    assert len(feed.entries) == 3  # 三条精选（1 / 2 / 3）
    assert [entry.link for entry in feed.entries] == [url_of(1), url_of(2), url_of(3)]
    assert feed.entries[0].title == "中文标题 1"
    assert feed.entries[0].summary == "中文摘要 1：一句话说清这条讲了什么。"
    for entry in feed.entries:
        assert entry.published_parsed is not None
        assert entry.link.startswith("https://")
    assert feed.feed.title == "UXHOT · AI 用研热点"
    assert feed.feed.link == SITE_URL


def test_rss_daily_only_links_to_reports_that_exist(published: Path) -> None:
    """日报 feed 里每个链接都必须有对应页面 —— 不能指向没出过的期。

    曾经的实现是「从 Item 推」，于是有入选条目但没出过日报的日子也会发出去。
    实测过一次：37 条 item 里 32 条指向不存在的 `/daily/<date>/`，
    RSS 阅读器点进去全是死链。现在只发真的写进产物里的那几期。
    """
    feed = feedparser.parse((published / "rss-daily.xml").read_text(encoding="utf-8"))
    assert not feed.bozo, getattr(feed, "bozo_exception", None)

    # 夹具里只写了 10-21 与 10-20 两期日报
    report_dates = {
        path.stem
        for path in (published / "data" / "reports" / "daily").glob("*.json")
        if path.name != "index.json"
    }
    assert report_dates == {"2026-10-20", "2026-10-21"}

    linked = {entry.link.rstrip("/").split("/")[-1] for entry in feed.entries}
    assert linked == report_dates, "feed 里只能有真的出过的那几期"
    assert "2026-10-22" not in linked, "10-22 有入选条目但没出日报，不该出现在 feed 里"

    # 每条链接都要能对上产物里的日报文件
    for entry in feed.entries:
        date = entry.link.rstrip("/").split("/")[-1]
        assert (published / "data" / "reports" / "daily" / f"{date}.json").is_file(), (
            f"{entry.link} 指向的日报不存在"
        )


def test_rss_is_well_formed_and_escaped(cfg, public_dir: Path, empty_reports: Path) -> None:
    """标题里的 & < > 必须转义，否则阅读器直接解析失败。"""
    items = [
        make_item(
            1,
            title="A & B <script>alert(1)</script>",
            titleZh='中文 & "引号" <标签>',
            summaryZh="摘要里有 <b>HTML</b> 与 & 符号",
        )
    ]
    build_and_validate(items, cfg, public_dir=public_dir, reports_dir=empty_reports, now=NOW)
    text = (public_dir / "rss.xml").read_text(encoding="utf-8")
    assert "&amp;" in text
    assert "<script>" not in text  # 原始尖括号绝不能进 XML
    feed = feedparser.parse(text)
    assert not feed.bozo, getattr(feed, "bozo_exception", None)
    assert len(feed.entries) == 1
    assert "&" in feed.entries[0].title
    assert feed.entries[0].title == '中文 & "引号" <标签>'


def test_rss_without_selected_items_is_empty_not_broken(cfg, public_dir: Path, empty_reports: Path) -> None:
    """没有精选（空刊）时 feed 仍然合法，只是没有条目。"""
    build_and_validate(
        [make_item(1, status=Status.LISTED)],
        cfg,
        public_dir=public_dir,
        reports_dir=empty_reports,
        now=NOW,
    )
    feed = feedparser.parse((public_dir / "rss.xml").read_text(encoding="utf-8"))
    assert not feed.bozo, getattr(feed, "bozo_exception", None)
    assert feed.entries == []


def test_rss_pubdate_is_rfc822_with_offset(published: Path) -> None:
    text = (published / "rss.xml").read_text(encoding="utf-8")
    assert "GMT" in text
    problems = validate_publish_dir(published)
    assert not any("pubDate" in p for p in problems)


# ── llms.txt ───────────────────────────────────────────────────────────


def test_llms_txt_has_intro_and_selected_links(published: Path) -> None:
    text = (published / "llms.txt").read_text(encoding="utf-8")
    assert text.startswith("# UXHOT · AI 用研热点")
    assert "> AI 用研的每日精选" in text
    assert "## 最新精选" in text
    assert f"]({url_of(1)})" in text
    assert "中文标题 1" in text
    assert "中文摘要 1" in text
    assert f"- [RSS（精选）]({SITE_URL}/rss.xml)" in text
    # 精选列表（## 最新精选 之后）每条精选一行
    picks = text.split("## 最新精选", 1)[1]
    assert len([line for line in picks.splitlines() if line.startswith("- [")]) == 3


def test_llms_txt_escapes_brackets_in_titles(cfg, public_dir: Path, empty_reports: Path) -> None:
    items = [make_item(1, titleZh="标题里有 [方括号] 和换行\n第二行")]
    build_and_validate(items, cfg, public_dir=public_dir, reports_dir=empty_reports, now=NOW)
    text = (public_dir / "llms.txt").read_text(encoding="utf-8")
    picks = text.split("## 最新精选", 1)[1]
    entry_lines = [line for line in picks.splitlines() if line.startswith("- [")]
    assert len(entry_lines) == 1, "换行没压平会把一个条目拆成两个"
    assert "\\[方括号\\]" in entry_lines[0]
    assert "第二行" in entry_lines[0]


def test_llms_txt_without_selected_items(cfg, public_dir: Path, empty_reports: Path) -> None:
    """没有精选时列表位置要有明确说明，不能留下空标题，也不能因此发不出去。"""
    build_and_validate(
        [make_item(1, status=Status.LISTED)],
        cfg,
        public_dir=public_dir,
        reports_dir=empty_reports,
        now=NOW,
    )
    text = (public_dir / "llms.txt").read_text(encoding="utf-8")
    assert "## 最新精选" in text
    picks = text.split("## 最新精选", 1)[1]
    assert "- 暂无精选。" in picks
    assert "](http" in text  # 入口链接仍在，校验要求的链接不是空的


def test_source_name_is_identical_across_all_output_files(published: Path) -> None:
    """同一个 id 的 sourceName 在所有产物文件里必须一致。

    踩过的坑：`public_item` / `_ref`（同事件的其他报道）/ `search-index`
    三处各算各的来源名。我改了 `public_item` 用 `venue` 之后另外两处没跟上，
    产物里同一条 id 的 sourceName 不一致，被发布校验拦下 —— 校验器是对的。
    现在三处都走 `display_source()`，这条测试守住它。
    """
    by_id: dict[str, set[str]] = {}
    for path in sorted((published / "data").rglob("*.json")):
        doc = load_json(path)
        for row in iter_dicts(doc):
            if isinstance(row, dict) and "id" in row and "sourceName" in row:
                by_id.setdefault(row["id"], set()).add(row["sourceName"])

    inconsistent = {k: v for k, v in by_id.items() if len(v) > 1}
    assert not inconsistent, f"这些 id 的来源名不一致：{list(inconsistent.items())[:3]}"


def test_venue_replaces_aggregator_name_in_output(published: Path) -> None:
    """有 venue 的条目，产物里的 sourceName 必须是 venue，不能是聚合源名。"""
    doc = load_json(published / "data" / "search-index.json")
    for row in doc["items"]:
        venue = row.get("venue")
        if venue:
            assert row["sourceName"] == venue, (
                f"有 venue 就该显示它，实际显示 {row['sourceName']!r}"
            )
