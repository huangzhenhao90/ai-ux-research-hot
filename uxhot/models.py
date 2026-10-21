"""数据模型。

一条资料的全部处理结果存成 `data/items/YYYY-MM.jsonl` 的一行（计划 §5.1）。
按 id 更新时重写整个文件（v1 数据量小，够用且简单）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

BODY_LIMIT = 8000


class Status(str, Enum):
    """一条资料的生命周期。"""

    NEW = "new"                    # 刚抓进来，还没预筛
    ARCHIVED = "archived"          # 旧文（首次导入或发布超过 freshHours）→ 进全部动态，不进今天/日报
    PREFILTERED = "prefiltered"    # 预筛通过，等评分
    BLOCKED = "blocked"            # 预筛 BLOCK → 不公开
    UNKNOWN = "unknown"            # 预筛拿不准，等补材料
    SCORED = "scored"              # 评过分，但没过门槛
    SELECTED = "selected"          # 进了精选
    LISTED = "listed"              # 只进全部动态
    DUPLICATE = "duplicate"        # 与已有精选同事件且无新信息


class PrefilterResult(BaseModel):
    label: str                     # PASS | BLOCK | UNKNOWN
    reason: str = ""


class Item(BaseModel):
    """一条资料。字段名与计划 §5.1 一一对应。"""

    # ── 身份 ────────────────────────────────────────────────────────
    id: str                        # sha1(规范化 URL)
    sourceId: str
    tier: str
    mode: str = "editorial"
    url: str
    canonicalUrl: str = ""

    # ── 来源信息 ────────────────────────────────────────────────────
    title: str = ""
    author: str | None = None
    lang: str | None = None

    # ── 时间（一律 tz-aware）─────────────────────────────────────────
    publishedAt: datetime | None = None
    discoveredAt: datetime

    # ── 正文 ────────────────────────────────────────────────────────
    body: str = ""
    bodyTruncated: bool = False

    # ── 处理状态 ────────────────────────────────────────────────────
    status: Status = Status.NEW
    prefilter: PrefilterResult | None = None
    scores: list[int] = Field(default_factory=list)
    avgScore: float | None = None

    # 入选时刻。日报窗口是「前一天 08:00 → 当天 08:00 **入选**的精选」，
    # 用 publishedAt/discoveredAt 近似会让补跑与延迟确认的条目落错期。
    selectedAt: datetime | None = None

    # ── 结构化与写作 ────────────────────────────────────────────────
    itemType: str | None = None
    authorRole: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    scope: str | None = None
    fact: dict[str, Any] | None = None

    titleZh: str | None = None
    summaryZh: str | None = None
    reason: str | None = None

    # ── 去重 ────────────────────────────────────────────────────────
    dupOf: str | None = None
    relation: str | None = None
    hasNewInfo: bool | None = None

    # ── 审计 ────────────────────────────────────────────────────────
    promptVersions: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ── 校验 ────────────────────────────────────────────────────────

    @field_validator("publishedAt", "discoveredAt", "updatedAt", "selectedAt")
    @classmethod
    def _require_tz(cls, v: datetime | None) -> datetime | None:
        """计划验收要求「日期带时区」，且结果不随运行机器时区变化。"""
        if v is None:
            return None
        if v.tzinfo is None:
            raise ValueError("时间必须带时区（tz-aware）")
        return v

    @field_validator("scores")
    @classmethod
    def _scores_in_range(cls, v: list[int]) -> list[int]:
        for s in v:
            if not 0 <= s <= 100:
                raise ValueError(f"评分必须在 0–100：{s}")
        return v

    # ── 派生 ────────────────────────────────────────────────────────

    @property
    def is_public(self) -> bool:
        """能不能出现在公开页面上。BLOCK 与 UNKNOWN 不公开。"""
        return self.status not in (Status.BLOCKED, Status.UNKNOWN)

    @property
    def is_selected(self) -> bool:
        return self.status is Status.SELECTED

    @property
    def display_title(self) -> str:
        return self.titleZh or self.title

    @property
    def published_utc(self) -> datetime | None:
        return self.publishedAt.astimezone(timezone.utc) if self.publishedAt else None

    def set_body(self, text: str) -> None:
        """正文截断到 8000 字（计划 §5.1）。"""
        if len(text) > BODY_LIMIT:
            self.body = text[:BODY_LIMIT]
            self.bodyTruncated = True
        else:
            self.body = text
            self.bodyTruncated = False


def make_id(canonical_url: str) -> str:
    """id = sha1(规范化 URL) 前 16 位。

    用规范化 URL 而不是原始 URL，保证带 utm 参数的同一篇文章只有一个 id。
    """
    return hashlib.sha1(canonical_url.encode("utf-8")).hexdigest()[:16]


# ── JSONL 存取 ─────────────────────────────────────────────────────────


def month_key(dt: datetime) -> str:
    """按 UTC 归月，避免跨时区运行时归到不同文件。"""
    utc = dt.astimezone(timezone.utc)
    return f"{utc.year:04d}-{utc.month:02d}"


def items_path(items_dir: Path, dt: datetime) -> Path:
    return items_dir / f"{month_key(dt)}.jsonl"


def load_items(path: Path) -> list[Item]:
    """读一个 JSONL 文件。坏行跳过并记录，不让一行毁掉整个文件。"""
    if not path.is_file():
        return []
    items: list[Item] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            items.append(Item.model_validate(json.loads(line)))
        except Exception:  # noqa: BLE001 - 坏行不应中断整次运行
            continue
    return items


def write_items(path: Path, items: list[Item]) -> None:
    """整文件重写。调用方负责保证顺序稳定。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [item.model_dump_json() for item in items]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def upsert_items(path: Path, new_items: list[Item]) -> tuple[int, int]:
    """按 id 合并写入。返回 (新增数, 更新数)。

    已有条目保留其处理结果：只覆盖本次真的重新算过的字段由调用方决定——
    这里采取「新条目优先」但保留旧的 status 若新的是 NEW 而旧的已处理过。
    """
    existing = {item.id: item for item in load_items(path)}
    added = updated = 0
    for item in new_items:
        old = existing.get(item.id)
        if old is None:
            existing[item.id] = item
            added += 1
        else:
            merged = _merge(old, item)
            existing[item.id] = merged
            updated += 1
    ordered = sorted(existing.values(), key=lambda i: (i.discoveredAt, i.id))
    write_items(path, ordered)
    return added, updated


def _merge(old: Item, new: Item) -> Item:
    """合并同 id 的两条。

    关键规则（与 AIHOT 一致）：已经判过的资料不重算。
    新的抓取只补充正文与元数据，不把 status/scores/写作结果打回未处理。
    """
    data = old.model_dump()
    # 元数据以新抓的为准（正文可能补全了）
    for field in ("title", "author", "lang", "body", "bodyTruncated", "url", "canonicalUrl"):
        value = getattr(new, field)
        if value:
            data[field] = value
    if new.publishedAt is not None:
        data["publishedAt"] = new.publishedAt
    # 处理结果保留旧的（已判过的不重算）
    data["updatedAt"] = new.updatedAt
    data["errors"] = list(dict.fromkeys([*old.errors, *new.errors]))
    return Item.model_validate(data)
