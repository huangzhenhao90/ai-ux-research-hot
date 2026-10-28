"""阶段 4 验收：提示词能渲染、无残留占位符、无未知引用、内容符合已确认决策。

正例测真实提示词；负例用临时目录证明渲染器真的会拦循环引用、缺失文件、未知占位符。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from uxhot.config import load_config
from uxhot.prompts import (
    INCLUDE_RE,
    KNOWN_PLACEHOLDERS,
    VAR_RE,
    CircularIncludeError,
    MissingPromptError,
    PROMPTS_DIR,
    UnknownPlaceholderError,
    UnfilledPlaceholderError,
    base_variables,
    includes_of,
    list_prompts,
    load_raw,
    prompt_version,
    render,
)

# 计划 §4 要求的提示词清单（不用的不复制）
REQUIRED_PROMPTS = [
    "prefilter.md",
    "selection-score.md",
    "content-understanding.md",
    "understand.md",
    "structure.md",
    "summarize-article.md",
    "summarize-article-empty.md",
    "summarize-short-post.md",
    "rules-domain.md",
    "rules-anti-hallucination.md",
    "rules-self-contained-title.md",
    "rules-answer-first-summary.md",
    "safety.md",
    "group-pair.md",
    "group-definitions.md",
    "group-method.md",
    "translate-body.md",
]


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def variables(cfg) -> dict[str, str]:
    """全部已知占位符都有值，用于 strict 渲染。"""
    return {
        **base_variables(cfg),
        "publishedDate": "2026-10-20",
        "today": "2026-10-21",
        "sourceName": "Example Source",
        "title": "Example title",
        "body": "Example body",
        "identity": "",
        "post": "Example post",
        "kindName": "周报",
        "span": "一周",
        "sentences": "3",
        "chars": "300",
        "sections": "",
        "sectionsExample": '{"papers": "本节导读"}',
    }


# ══ 提示词清单与渲染 ════════════════════════════════════════════════════


def test_all_required_prompts_exist() -> None:
    present = set(list_prompts())
    missing = [p for p in REQUIRED_PROMPTS if p not in present]
    assert not missing, f"缺少提示词：{missing}"


def test_every_prompt_renders_without_leftovers(variables) -> None:
    """每份提示词都能渲染，且不残留未展开的占位符。"""
    for name in list_prompts():
        rendered = render(name, variables, strict=True)
        assert rendered.strip(), f"{name} 渲染后为空"
        assert "{{" not in rendered, f"{name} 仍有未展开的占位符"
        assert not VAR_RE.findall(rendered), f"{name} 仍有未替换的变量"


def test_no_unknown_placeholders_anywhere(variables) -> None:
    """所有用到的占位符都必须在 KNOWN_PLACEHOLDERS 里。"""
    for name in list_prompts():
        raw = load_raw(name)
        used = set(VAR_RE.findall(raw))
        unknown = used - KNOWN_PLACEHOLDERS
        assert not unknown, f"{name} 用了未知占位符：{sorted(unknown)}"


def test_all_includes_resolve() -> None:
    for name in list_prompts():
        includes_of(name)  # 文件缺失会抛 MissingPromptError


def test_understand_pulls_in_all_rule_files() -> None:
    included = includes_of("understand.md")
    for expected in (
        "content-understanding",
        "rules-domain",
        "rules-anti-hallucination",
        "rules-self-contained-title",
        "rules-answer-first-summary",
    ):
        assert expected in included, f"understand.md 应包含 {expected}"


# ══ 渲染器负例：证明真的会拦 ═══════════════════════════════════════════


def test_circular_include_detected(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("A {{> b}}", encoding="utf-8")
    (tmp_path / "b.md").write_text("B {{> a}}", encoding="utf-8")
    with pytest.raises(CircularIncludeError, match="循环引用"):
        render("a", {}, prompts_dir=tmp_path)


def test_self_include_detected(tmp_path: Path) -> None:
    (tmp_path / "self.md").write_text("{{> self}}", encoding="utf-8")
    with pytest.raises(CircularIncludeError):
        render("self", {}, prompts_dir=tmp_path)


def test_missing_include_detected(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("{{> nope}}", encoding="utf-8")
    with pytest.raises(MissingPromptError, match="不存在"):
        render("a", {}, prompts_dir=tmp_path)


def test_unknown_placeholder_detected(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("hello {{notARealPlaceholder}}", encoding="utf-8")
    with pytest.raises(UnknownPlaceholderError, match="未知占位符"):
        render("a", {}, prompts_dir=tmp_path)


def test_strict_mode_rejects_unfilled(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("hello {{siteName}}", encoding="utf-8")
    with pytest.raises(UnfilledPlaceholderError, match="没有被赋值"):
        render("a", {}, prompts_dir=tmp_path, strict=True)


def test_include_without_extension_resolves(variables) -> None:
    """{{> group-method}} 与 {{> group-method.md}} 等价。"""
    assert render("group-pair", variables, strict=True)


# ══ 计划 §4 要求的 grep 检查 ════════════════════════════════════════════


def test_no_aihot_branding_in_prompts() -> None:
    """许可要求：提示词正文里不出现 AIHOT 的名字和 Logo。

    注意范围是「提示词」，不含 prompts/README.md —— 那个文件按计划 §2.9 必须逐文件
    注明改编来源，因此必然会提到 AIHOT。
    """
    for name in list_prompts():
        text = load_raw(name).lower()
        assert "aihot" not in text, f"{name} 里出现了 AIHOT 的名字"


def test_no_html_comments_in_prompts() -> None:
    """提示词会原样发给模型，不能夹带注释。"""
    for name in list_prompts():
        assert "<!--" not in load_raw(name), f"{name} 里有 HTML 注释"


def test_readme_documents_provenance() -> None:
    """计划 §2.9：prompts/README.md 里逐文件写「改编自 AIHOT industry/prompts/xxx.md」。"""
    readme = (PROMPTS_DIR / "README.md").read_text(encoding="utf-8")
    assert "industry/prompts/" in readme
    for name in list_prompts():
        assert name in readme, f"README.md 没有记录 {name} 的来源"


def test_grep_forbidden_terms_only_in_boundary_rules() -> None:
    """计划 §4 的 grep：OpenAI / Anthropic / model_release / 模型发布 只应出现在
    「泛 AI 模型发布属噪声/边界外」这类故意保留的规则里。"""
    allowed_files = {"prefilter.md", "selection-score.md"}
    pattern = re.compile(r"OpenAI|Anthropic|model_release|模型发布")
    for name in list_prompts():
        for line in load_raw(name).splitlines():
            if pattern.search(line):
                assert name in allowed_files, f"{name} 出现了禁止词：{line.strip()}"
                assert "发布" in line, f"{name} 的匹配不是边界规则：{line.strip()}"


# ══ 内容契约：与已确认决策一致 ═════════════════════════════════════════


def test_selection_score_weights_match_confirmed_rubric() -> None:
    """评分权重必须与用户确认的表一致（每行和为 10）。"""
    expected = {
        "tool_launch": (2, 2, 1, 2, 3),
        "method_or_template": (1, 2, 1, 2, 4),
        "research_paper": (3, 3, 2, 1, 1),
        "industry_event": (3, 1, 2, 4, 0),
        "case_study": (2, 2, 2, 2, 2),
        "opinion_analysis": (1, 3, 1, 4, 1),
        "tutorial_explainer": (1, 1, 1, 3, 4),
    }
    text = load_raw("selection-score.md")
    row = re.compile(
        r"^\|\s*([a-z_]+)\s*\|\s*(\d)\s*\|\s*(\d)\s*\|\s*(\d)\s*\|\s*(\d)\s*\|\s*(\d)\s*\|\s*$"
    )
    found = {}
    for line in text.splitlines():
        m = row.match(line.strip())
        if m and m.group(1) in expected:
            found[m.group(1)] = tuple(int(m.group(i)) for i in range(2, 7))

    assert found, "没能在 selection-score.md 里解析出权重表"
    for item_type, weights in expected.items():
        assert item_type in found, f"权重表缺少 {item_type}"
        assert found[item_type] == weights, (
            f"{item_type} 权重与确认值不符：{found[item_type]} != {weights}"
        )
        assert sum(weights) == 10, f"{item_type} 权重和应为 10"


def test_selection_score_has_only_score_field() -> None:
    text = load_raw("selection-score.md")
    assert '"attentionScore"' in text
    assert "顶层必须且只能包含" in text


def test_selection_score_keeps_event_calibration_section() -> None:
    """计划要求保留「事件口径校正」结构。"""
    text = load_raw("selection-score.md")
    assert "事件口径校正" in text


def test_prefilter_has_three_labels_and_boundary() -> None:
    """D3 收录边界必须写进预筛。"""
    text = load_raw("prefilter.md")
    for label in ("PASS", "BLOCK", "UNKNOWN"):
        assert label in text
    assert "BLOCK" in text and "宽召回" in text
    # D3：泛 AI 模型发布不收
    assert "通用大模型发布" in text or "泛 AI 模型发布" in text


def test_structure_outputs_five_fields() -> None:
    text = load_raw("structure.md")
    assert "category, tags, subjects, scope, fact" in text


def test_group_pair_outputs_relation_and_newinfo() -> None:
    text = load_raw("group-pair.md")
    assert "hasNewInfo" in text
    assert "same" in text and "followup" in text and "different" in text


def test_content_understanding_outputs_six_fields() -> None:
    text = load_raw("content-understanding.md")
    for field in ("itemType", "authorRole", "tags", "editorialJudgment", "titleZh", "summaryZh"):
        assert field in text, f"content-understanding.md 缺少字段 {field}"


def test_domain_rules_contain_required_ux_translations() -> None:
    """计划 §4.4 要求的用研术语固定译法必须齐全。"""
    text = load_raw("rules-domain.md")
    required = [
        "可用性测试",
        "合成用户",
        "合成受访者",
        "AI 主持访谈",
        "主题分析",
        "亲和图",
        "卡片分类",
        "树测试",
        "甄别问卷",
        "洞察库",
        "样本库",
        "编码者一致性",
        "日记研究",
    ]
    missing = [term for term in required if term not in text]
    assert not missing, f"rules-domain.md 缺少固定译法：{missing}"


def test_domain_rules_keep_generic_ai_terms() -> None:
    text = load_raw("rules-domain.md")
    for term in ("LLM", "Agent", "Token", "Prompt", "Hallucination"):
        assert term in text, f"rules-domain.md 丢失了通用 AI 术语 {term}"


def test_editorial_judgment_banned_words_extended() -> None:
    """计划 §4.3：禁用词表补「赋能」「黑科技」。"""
    text = load_raw("content-understanding.md")
    assert "赋能" in text and "黑科技" in text


# ══ 版本哈希（阶段 5 要用）════════════════════════════════════════════


def test_prompt_version_is_stable(variables) -> None:
    a = prompt_version("prefilter", variables)
    b = prompt_version("prefilter", variables)
    assert a == b
    assert len(a) == 8 and re.fullmatch(r"[0-9a-f]{8}", a)


def test_prompt_version_changes_with_content(tmp_path: Path, variables) -> None:
    (tmp_path / "p.md").write_text("版本一 {{siteName}}", encoding="utf-8")
    v1 = prompt_version("p", variables, prompts_dir=tmp_path)
    (tmp_path / "p.md").write_text("版本二 {{siteName}}", encoding="utf-8")
    v2 = prompt_version("p", variables, prompts_dir=tmp_path)
    assert v1 != v2, "提示词内容变了，版本哈希必须变"


def test_prompt_version_changes_with_site_name() -> None:
    """{{siteName}} 变了，版本也要变（同一份提示词在不同站是不同的提示词）。"""
    v1 = prompt_version("prefilter", {"siteName": "URHOT"})
    v2 = prompt_version("prefilter", {"siteName": "OTHER"})
    assert v1 != v2


# ══ 渲染快照（供人工抽看，计划 §4 验收）═══════════════════════════════


def test_render_snapshot_written(tmp_path: Path, variables) -> None:
    for name in list_prompts():
        out = tmp_path / name
        out.write_text(render(name, variables, strict=True), encoding="utf-8")
        assert out.stat().st_size > 0

    # 抽看三份关键提示词的关键结构
    score = (tmp_path / "selection-score.md").read_text(encoding="utf-8")
    assert "URHOT" in score
    assert "attentionScore" in score

    pre = (tmp_path / "prefilter.md").read_text(encoding="utf-8")
    assert "URHOT" in pre

    struct = (tmp_path / "structure.md").read_text(encoding="utf-8")
    assert "6选一" in struct, "categoryCount 应渲染成 6"


def test_taxonomy_variables_render_into_structure(variables) -> None:
    """structure.md 的 {{categoryGuide}} 等必须来自 taxonomy.yaml，而不是写死。"""
    rendered = render("structure.md", variables, strict=True)
    for key in ("tools", "methods", "research", "industry", "cases", "opinion"):
        assert key in rendered, f"categoryGuide 里缺分类 {key}"
    assert "AI 访谈" in rendered, "topicTags 未注入"
    assert "qualtrics" in rendered, "entities 未注入"
