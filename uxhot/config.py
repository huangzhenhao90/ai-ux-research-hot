"""配置加载与校验。

六份配置（site / taxonomy / topics / sources / selection / overrides）在这里统一读入，
并在加载时做跨文件一致性校验，避免把错误配置带到流水线里。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"

Tier = Literal["T1", "T1_5", "T2", "EXCLUDE"]
Mode = Literal["editorial", "hot_signal", "isolated"]
Kind = Literal["rss", "web_list", "external_json"]

TIERS: tuple[str, ...] = ("T1", "T1_5", "T2", "EXCLUDE")
MODES: tuple[str, ...] = ("editorial", "hot_signal", "isolated")
KINDS: tuple[str, ...] = ("rss", "web_list", "external_json")

# 参与精选评分、因而必须有门槛的分级（EXCLUDE 不评分）
SCORED_TIERS: tuple[str, ...] = ("T1", "T1_5", "T2")


class ConfigError(ValueError):
    """配置校验失败。消息里要能直接看出是哪个文件、哪一项。"""


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        raise ConfigError(f"配置文件不存在：{path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML 解析失败：{path}\n{exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"配置根节点必须是映射：{path}")
    return data


# ── site.yaml ──────────────────────────────────────────────────────────


class SiteConfig(BaseModel):
    name: str
    alias: str
    subject: str
    siteUrl: str
    homeTitle: str
    description: str
    tagline: str
    byline: str
    reasonLabel: str
    showScore: bool
    locale: str
    timezone: str
    editions: dict[str, str]
    crawlerName: str
    credit: str


# ── taxonomy.yaml ──────────────────────────────────────────────────────


class Category(BaseModel):
    key: str
    label: str
    section: str
    guide: str
    commentary: bool = False


class Entity(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)


class Taxonomy(BaseModel):
    categories: list[Category]
    itemTypes: list[str]
    itemTypeCategoryTag: dict[str, str]
    categoryTags: list[str]
    topicTags: list[str]
    entityTags: list[str]
    tagSynonyms: dict[str, list[str]]
    entities: list[Entity]

    @property
    def category_keys(self) -> list[str]:
        return [c.key for c in self.categories]

    @property
    def entity_ids(self) -> set[str]:
        return {e.id for e in self.entities}

    @property
    def taggable(self) -> set[str]:
        """主题页可以匹配的全部标签。

        `field` 组按 topicTags 匹配，`genre` 组按 categoryTags 匹配（如「论文/研究」「方法/实践」），
        所以两者都算合法来源。
        """
        return set(self.topicTags) | set(self.categoryTags)

    def category_guide_text(self) -> str:
        """渲染成 structure.md 的 {{categoryGuide}}：一行一类。"""
        return "\n".join(f"- {c.key}（{c.label}）：{c.guide}" for c in self.categories)


def validate_taxonomy(tax: Taxonomy) -> None:
    keys = tax.category_keys
    if len(keys) != len(set(keys)):
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        raise ConfigError(f"taxonomy.yaml：分类 key 重复：{dupes}")
    if "industry" not in keys:
        raise ConfigError("taxonomy.yaml：分类必须包含兜底类 industry")

    ids = [e.id for e in tax.entities]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ConfigError(f"taxonomy.yaml：实体 id 重复：{dupes}")

    if len(tax.itemTypes) != len(set(tax.itemTypes)):
        raise ConfigError("taxonomy.yaml：itemTypes 有重复")

    # itemType → 分类标签 的对照必须指向真实存在的分类标签
    bad = {k: v for k, v in tax.itemTypeCategoryTag.items() if v not in tax.categoryTags}
    if bad:
        raise ConfigError(f"taxonomy.yaml：itemTypeCategoryTag 指向了未定义的分类标签：{bad}")
    missing = [t for t in tax.itemTypes if t not in tax.itemTypeCategoryTag]
    if missing:
        raise ConfigError(f"taxonomy.yaml：这些 itemType 缺少分类标签对照：{missing}")

    # 同义词归并的目标必须是已知标签
    known = set(tax.categoryTags) | set(tax.topicTags) | set(tax.entityTags)
    for target, variants in tax.tagSynonyms.items():
        if target not in known:
            raise ConfigError(f"taxonomy.yaml：tagSynonyms 的目标「{target}」不在任何标签词表里")
        if not isinstance(variants, list) or not variants:
            raise ConfigError(f"taxonomy.yaml：tagSynonyms「{target}」的同义词必须是非空列表")



# ── topics.yaml ────────────────────────────────────────────────────────


class TopicGroup(BaseModel):
    key: str
    name: str
    blurb: str


class Topic(BaseModel):
    slug: str
    name: str
    group: str
    definition: str
    entityId: str | None = None
    tags: list[str] = Field(default_factory=list)


class Topics(BaseModel):
    groups: list[TopicGroup]
    topics: list[Topic]


def validate_topics(topics: Topics, tax: Taxonomy) -> None:
    group_keys = [g.key for g in topics.groups]
    if len(group_keys) != len(set(group_keys)):
        raise ConfigError("topics.yaml：分组 key 重复")

    slugs = [t.slug for t in topics.topics]
    if len(slugs) != len(set(slugs)):
        dupes = sorted({s for s in slugs if slugs.count(s) > 1})
        raise ConfigError(f"topics.yaml：slug 重复：{dupes}")

    for t in topics.topics:
        if t.group not in group_keys:
            raise ConfigError(f"topics.yaml：「{t.slug}」的 group「{t.group}」不在 groups 里")
        if t.entityId is not None and t.entityId not in tax.entity_ids:
            raise ConfigError(
                f"topics.yaml：「{t.slug}」的 entityId「{t.entityId}」不在 taxonomy.entities 里"
            )
        unknown = [tag for tag in t.tags if tag not in tax.taggable]
        if unknown:
            raise ConfigError(
                f"topics.yaml：「{t.slug}」用了未定义的标签：{unknown}"
                "（必须来自 taxonomy 的 topicTags 或 categoryTags）"
            )
        if not t.entityId and not t.tags:
            raise ConfigError(f"topics.yaml：「{t.slug}」既没有 entityId 也没有 tags，无法归属条目")


# ── sources.yaml ───────────────────────────────────────────────────────


class WebListSelectors(BaseModel):
    itemSelector: str
    linkSelector: str
    titleSelector: str | None = None
    dateSelector: str | None = None


class Source(BaseModel):
    id: str
    name: str
    kind: Kind
    url: str
    tier: Tier
    mode: Mode = "editorial"
    entity: str | None = None
    initialBackfillLimit: int = 8
    timezone: str = "+08:00"
    web_list: WebListSelectors | None = None
    note: str | None = None


class Sources(BaseModel):
    sources: list[Source]


def validate_sources(sources: Sources, tax: Taxonomy, sel: "SelectionConfig") -> None:
    ids = [s.id for s in sources.sources]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ConfigError(f"sources.yaml：信源 id 重复：{dupes}")

    for s in sources.sources:
        if s.kind not in KINDS:
            raise ConfigError(f"sources.yaml：「{s.id}」kind「{s.kind}」不合法")
        if s.tier not in TIERS:
            raise ConfigError(f"sources.yaml：「{s.id}」tier「{s.tier}」不合法")
        if s.mode not in MODES:
            raise ConfigError(f"sources.yaml：「{s.id}」mode「{s.mode}」不合法")
        if not s.url.startswith(("http://", "https://")):
            raise ConfigError(f"sources.yaml：「{s.id}」url 必须是 http(s)：{s.url}")
        if s.kind == "web_list" and s.web_list is None:
            raise ConfigError(f"sources.yaml：「{s.id}」是 web_list，必须给 web_list 选择器")
        if s.kind != "web_list" and s.web_list is not None:
            raise ConfigError(f"sources.yaml：「{s.id}」不是 web_list，不应有 web_list 选择器")
        if s.entity is not None and s.entity not in tax.entity_ids:
            raise ConfigError(
                f"sources.yaml：「{s.id}」的 entity「{s.entity}」不在 taxonomy.entities 里"
            )
        if s.initialBackfillLimit < 1:
            raise ConfigError(f"sources.yaml：「{s.id}」initialBackfillLimit 必须 ≥1")

    # 门槛必须覆盖所有「会参与精选评分」的分级
    used = {s.tier for s in sources.sources if s.mode == "editorial" and s.tier != "EXCLUDE"}
    missing = sorted(t for t in used if t not in sel.thresholds)
    if missing:
        raise ConfigError(f"selection.yaml：thresholds 未覆盖这些被用到的分级：{missing}")


# ── selection.yaml ─────────────────────────────────────────────────────


class SelectionConfig(BaseModel):
    thresholds: dict[str, int]
    understandFloor: int
    freshHours: int
    budget: dict[str, int]
    scoreAttempts: int
    dedupe: dict[str, int]


def validate_selection(sel: SelectionConfig) -> None:
    for tier, value in sel.thresholds.items():
        if tier not in TIERS:
            raise ConfigError(f"selection.yaml：thresholds 里有未知分级「{tier}」")
        if not 0 <= value <= 100:
            raise ConfigError(f"selection.yaml：门槛 {tier}={value} 必须在 0–100")
    for key in ("perRunCalls", "perDayCalls"):
        if key not in sel.budget:
            raise ConfigError(f"selection.yaml：budget 缺少 {key}")
        if sel.budget[key] < 1:
            raise ConfigError(f"selection.yaml：budget.{key} 必须 ≥1")
    if sel.budget["perRunCalls"] > sel.budget["perDayCalls"]:
        raise ConfigError("selection.yaml：perRunCalls 不应大于 perDayCalls")
    if sel.scoreAttempts < 1:
        raise ConfigError("selection.yaml：scoreAttempts 必须 ≥1")
    if not 0 <= sel.understandFloor <= 100:
        raise ConfigError("selection.yaml：understandFloor 必须在 0–100")
    if sel.freshHours < 1:
        raise ConfigError("selection.yaml：freshHours 必须 ≥1")


# ── overrides.yaml ─────────────────────────────────────────────────────


class Overrides(BaseModel):
    select: list[dict] = Field(default_factory=list)
    reject: list[dict] = Field(default_factory=list)
    category: list[dict] = Field(default_factory=list)


def validate_overrides(ov: Overrides, tax: Taxonomy) -> None:
    for item in ov.category:
        if "category" not in item:
            raise ConfigError("overrides.yaml：category 项缺少 category 字段")
        if item["category"] not in tax.category_keys:
            raise ConfigError(
                f"overrides.yaml：category 项指向未知分类「{item['category']}」"
            )
    for name in ("select", "reject", "category"):
        for item in getattr(ov, name):
            if "url" not in item and "urlPrefix" not in item:
                raise ConfigError(f"overrides.yaml：{name} 项必须给 url 或 urlPrefix")


# ── 统一入口 ───────────────────────────────────────────────────────────


class ConfigBundle(BaseModel):
    site: SiteConfig
    taxonomy: Taxonomy
    topics: Topics
    sources: Sources
    selection: SelectionConfig
    overrides: Overrides


def load_config(config_dir: Path | None = None) -> ConfigBundle:
    """读入并校验全部配置。任一环节不合法就抛 ConfigError。"""
    cdir = config_dir or CONFIG_DIR

    def parse(name: str, model):
        try:
            return model.model_validate(_load_yaml(cdir / name))
        except ValidationError as exc:
            raise ConfigError(f"{name} 字段校验失败：\n{exc}") from exc

    site = parse("site.yaml", SiteConfig)
    taxonomy = parse("taxonomy.yaml", Taxonomy)
    topics = parse("topics.yaml", Topics)
    sources = parse("sources.yaml", Sources)
    selection = parse("selection.yaml", SelectionConfig)
    overrides = parse("overrides.yaml", Overrides)

    validate_taxonomy(taxonomy)
    validate_topics(topics, taxonomy)
    validate_selection(selection)
    validate_sources(sources, taxonomy, selection)
    validate_overrides(overrides, taxonomy)

    return ConfigBundle(
        site=site,
        taxonomy=taxonomy,
        topics=topics,
        sources=sources,
        selection=selection,
        overrides=overrides,
    )
