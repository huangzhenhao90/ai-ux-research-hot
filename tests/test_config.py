"""阶段 3 验收：六份配置可解析、字段齐全、跨文件引用一致。

正例测真实配置；负例用构造的非法配置证明校验真的会拦下来（否则「测试通过」没有意义）。
"""

from __future__ import annotations

import pytest

from uxhot.config import (
    Category,
    ConfigError,
    Entity,
    SelectionConfig,
    Source,
    Sources,
    Taxonomy,
    Topic,
    TopicGroup,
    Topics,
    WebListSelectors,
    load_config,
    validate_selection,
    validate_sources,
    validate_taxonomy,
    validate_topics,
)

# ══ 正例：真实配置 ══════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_all_configs_parse(cfg) -> None:
    assert cfg.site.name == "UXHOT"
    assert cfg.taxonomy.categories
    assert cfg.topics.topics
    assert cfg.sources.sources
    assert cfg.selection.thresholds


def test_site_url_matches_confirmed_repo_name(cfg) -> None:
    """D7：仓库名是 ai-ux-research-hot，不是计划里预填的 uxhot。"""
    assert cfg.site.siteUrl.endswith("/ai-ux-research-hot")
    assert not cfg.site.siteUrl.endswith("/uxhot")


def test_site_uses_confirmed_identity(cfg) -> None:
    """D1/D2：站名与行业词。"""
    assert cfg.site.name == "UXHOT"
    assert cfg.site.alias == "AI 用研热点"
    assert cfg.site.subject == "AI 用研"


def test_site_editions_match_d10(cfg) -> None:
    """D10：日报 08:00、周报周一 10:00。"""
    assert cfg.site.editions["daily"] == "08:00"
    assert cfg.site.editions["weekly"].startswith("MON")


def test_budget_matches_d9(cfg) -> None:
    """D9：每次 ≤300、每天 ≤1000。"""
    assert cfg.selection.budget["perRunCalls"] == 300
    assert cfg.selection.budget["perDayCalls"] == 1000


def test_categories_unique_and_include_industry(cfg) -> None:
    keys = cfg.taxonomy.category_keys
    assert len(keys) == len(set(keys)), "分类 key 必须唯一"
    assert "industry" in keys, "必须有兜底分类 industry"
    assert keys == ["tools", "methods", "research", "industry", "cases", "opinion"], (
        "D4 确认的 6 类，且顺序稳定"
    )


def test_item_types_map_to_known_category_tags(cfg) -> None:
    tax = cfg.taxonomy
    assert set(tax.itemTypes) == {
        "tool_launch",
        "method_or_template",
        "research_paper",
        "industry_event",
        "case_study",
        "opinion_analysis",
        "tutorial_explainer",
    }
    for item_type in tax.itemTypes:
        assert item_type in tax.itemTypeCategoryTag
        assert tax.itemTypeCategoryTag[item_type] in tax.categoryTags


def test_topics_reference_valid_entities_and_tags(cfg) -> None:
    tax = cfg.taxonomy
    for topic in cfg.topics.topics:
        if topic.entityId is not None:
            assert topic.entityId in tax.entity_ids, f"{topic.slug} 的 entityId 未定义"
        for tag in topic.tags:
            assert tag in tax.taggable, f"{topic.slug} 的标签「{tag}」未定义"


def test_genre_topics_use_category_tags(cfg) -> None:
    """genre 组按内容体裁匹配，用的是 categoryTags（如「论文/研究」「方法/实践」）。"""
    genre = [t for t in cfg.topics.topics if t.group == "genre"]
    assert genre, "应有 genre 组主题页"
    for topic in genre:
        assert topic.tags, f"{topic.slug} 没有匹配标签"
        for tag in topic.tags:
            assert tag in cfg.taxonomy.categoryTags, f"{topic.slug} 的标签「{tag}」不是分类标签"


def test_topics_groups_and_slugs_valid(cfg) -> None:
    group_keys = {g.key for g in cfg.topics.groups}
    slugs = [t.slug for t in cfg.topics.topics]
    assert len(slugs) == len(set(slugs)), "slug 必须唯一"
    for topic in cfg.topics.topics:
        assert topic.group in group_keys


def test_sources_enums_and_required_fields(cfg) -> None:
    for s in cfg.sources.sources:
        assert s.id and s.name, f"信源缺少 id/name：{s}"
        assert s.kind in ("rss", "web_list", "external_json")
        assert s.tier in ("T1", "T1_5", "T2", "EXCLUDE")
        assert s.mode in ("editorial", "hot_signal", "isolated")
        assert s.url.startswith(("http://", "https://")), f"{s.id} url 不是 http(s)"
        assert s.initialBackfillLimit >= 1
        if s.entity is not None:
            assert s.entity in cfg.taxonomy.entity_ids, f"{s.id} 的 entity 未定义"


def test_web_list_sources_have_selectors(cfg) -> None:
    for s in cfg.sources.sources:
        if s.kind == "web_list":
            assert s.web_list is not None, f"{s.id} 是 web_list 但没有选择器"
            assert s.web_list.itemSelector, f"{s.id} 缺少 itemSelector"
            assert s.web_list.linkSelector, f"{s.id} 缺少 linkSelector"
        else:
            assert s.web_list is None, f"{s.id} 不是 web_list 却带了选择器"


def test_sources_without_date_are_documented(cfg) -> None:
    """取不到日期的 web_list 源必须在 note 里写明，避免以后被当成漏抓。"""
    for s in cfg.sources.sources:
        if s.kind == "web_list" and s.web_list and s.web_list.dateSelector is None:
            assert s.note and "日期" in s.note, f"{s.id} 无 dateSelector 却没在 note 说明"


def test_thresholds_cover_all_scored_tiers(cfg) -> None:
    used = {
        s.tier
        for s in cfg.sources.sources
        if s.mode == "editorial" and s.tier != "EXCLUDE"
    }
    for tier in used:
        assert tier in cfg.selection.thresholds, f"门槛未覆盖分级 {tier}"


def test_source_goal_met(cfg) -> None:
    """计划成功标准 2：≥30 个信源抓取成功；T1 ≥10。"""
    editorial = [s for s in cfg.sources.sources if s.mode == "editorial"]
    t1 = [s for s in editorial if s.tier == "T1"]
    assert len(editorial) >= 30, f"参与精选的信源只有 {len(editorial)} 个"
    assert len(t1) >= 10, f"T1 信源只有 {len(t1)} 个"


def test_overrides_empty_by_default(cfg) -> None:
    """初始状态不应有任何人工覆盖，否则会掩盖评分问题。"""
    assert cfg.overrides.select == []
    assert cfg.overrides.reject == []
    assert cfg.overrides.category == []
    assert cfg.overrides.pin == []


# ══ 负例：证明校验真的会拦 ═══════════════════════════════════════════════


def _tax(**overrides) -> Taxonomy:
    base = dict(
        categories=[
            Category(key="tools", label="工具", section="工具", guide="g"),
            Category(key="industry", label="行业", section="行业", guide="g"),
        ],
        itemTypes=["tool_launch"],
        itemTypeCategoryTag={"tool_launch": "工具发布"},
        release={"category": "tools", "tag": "工具发布", "unit": "款新工具"},
        categoryTags=["工具发布"],
        topicTags=["AI 访谈"],
        entityTags=["Qualtrics"],
        tagSynonyms={"AI 访谈": ["AI moderated"]},
        entities=[Entity(id="qualtrics", name="Qualtrics")],
        plainTerms=["ai"],
    )
    base.update(overrides)
    return Taxonomy(**base)


def test_duplicate_category_key_rejected() -> None:
    tax = _tax(
        categories=[
            Category(key="tools", label="工具", section="s", guide="g"),
            Category(key="tools", label="工具2", section="s", guide="g"),
            Category(key="industry", label="行业", section="s", guide="g"),
        ]
    )
    with pytest.raises(ConfigError, match="重复"):
        validate_taxonomy(tax)


def test_missing_industry_category_rejected() -> None:
    tax = _tax(categories=[Category(key="tools", label="工具", section="s", guide="g")])
    with pytest.raises(ConfigError, match="industry"):
        validate_taxonomy(tax)


def test_item_type_without_category_tag_rejected() -> None:
    tax = _tax(itemTypeCategoryTag={"tool_launch": "不存在的标签"})
    with pytest.raises(ConfigError, match="未定义的分类标签"):
        validate_taxonomy(tax)


def test_tag_synonym_target_must_exist() -> None:
    tax = _tax(tagSynonyms={"不存在的目标": ["x"]})
    with pytest.raises(ConfigError, match="不在任何标签词表"):
        validate_taxonomy(tax)


def test_topic_with_unknown_entity_rejected() -> None:
    tax = _tax()
    topics = Topics(
        groups=[TopicGroup(key="company", name="公司", blurb="b")],
        topics=[Topic(slug="s", name="n", group="company", definition="d", entityId="ghost")],
    )
    with pytest.raises(ConfigError, match="不在 taxonomy.entities"):
        validate_topics(topics, tax)


def test_topic_with_unknown_tag_rejected() -> None:
    tax = _tax()
    topics = Topics(
        groups=[TopicGroup(key="field", name="方向", blurb="b")],
        topics=[Topic(slug="s", name="n", group="field", definition="d", tags=["未定义标签"])],
    )
    with pytest.raises(ConfigError, match="未定义的标签"):
        validate_topics(topics, tax)


def test_topic_without_entity_or_tags_rejected() -> None:
    tax = _tax()
    topics = Topics(
        groups=[TopicGroup(key="field", name="方向", blurb="b")],
        topics=[Topic(slug="s", name="n", group="field", definition="d")],
    )
    with pytest.raises(ConfigError, match="无法归属条目"):
        validate_topics(topics, tax)


def _sel(**overrides) -> SelectionConfig:
    base = dict(
        thresholds={"T1": 60, "T1_5": 65, "T2": 76},
        understandFloor=50,
        freshHours=48,
        budget={"perRunCalls": 300, "perDayCalls": 1000},
        scoreAttempts=2,
        dedupe={"titleSimilarity": 92, "windowHours": 72},
    )
    base.update(overrides)
    return SelectionConfig(**base)


def _src(**overrides) -> Source:
    base = dict(id="s1", name="S", kind="rss", url="https://example.com/f", tier="T1")
    base.update(overrides)
    return Source(**base)


def test_web_list_without_selectors_rejected() -> None:
    sources = Sources(sources=[_src(kind="web_list")])
    with pytest.raises(ConfigError, match="必须给 web_list 选择器"):
        validate_sources(sources, _tax(), _sel())


def test_rss_with_selectors_rejected() -> None:
    sources = Sources(
        sources=[_src(web_list=WebListSelectors(itemSelector="a", linkSelector=":scope"))]
    )
    with pytest.raises(ConfigError, match="不应有 web_list 选择器"):
        validate_sources(sources, _tax(), _sel())


def test_invalid_tier_rejected() -> None:
    # pydantic 的 Literal 会先拦住非法 tier
    with pytest.raises(Exception):
        _src(tier="T9")


def test_source_with_unknown_entity_rejected() -> None:
    sources = Sources(sources=[_src(entity="ghost")])
    with pytest.raises(ConfigError, match="不在 taxonomy.entities"):
        validate_sources(sources, _tax(), _sel())


def test_duplicate_source_id_rejected() -> None:
    sources = Sources(sources=[_src(), _src()])
    with pytest.raises(ConfigError, match="信源 id 重复"):
        validate_sources(sources, _tax(), _sel())


def test_thresholds_missing_used_tier_rejected() -> None:
    sources = Sources(sources=[_src(tier="T1_5")])
    sel = _sel(thresholds={"T1": 60})
    with pytest.raises(ConfigError, match="未覆盖"):
        validate_sources(sources, _tax(), sel)


def test_budget_run_exceeding_day_rejected() -> None:
    with pytest.raises(ConfigError, match="perRunCalls 不应大于 perDayCalls"):
        validate_selection(_sel(budget={"perRunCalls": 2000, "perDayCalls": 1000}))


def test_threshold_out_of_range_rejected() -> None:
    with pytest.raises(ConfigError, match="0–100"):
        validate_selection(_sel(thresholds={"T1": 120}))


def test_missing_config_file_raises_config_error(tmp_path) -> None:
    with pytest.raises(ConfigError, match="不存在"):
        load_config(tmp_path)
