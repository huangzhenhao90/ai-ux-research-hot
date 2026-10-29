"""用研社招的岗位来源标注：官网 / Boss 直聘 / 社群。

标注规则（DECISIONS D20）：
- 同一个岗位官网和 Boss 直聘都有时，只标官网；
- 其余情况有几个来源就标几个（官网 + 社群、Boss 直聘 + 社群都会把两个都标出来）。

「是不是同一个岗位」靠公司 + 岗位名 + 城市判断（`same_job`）。**宁可漏判也不要误判**：
漏判只是同一个岗位出现两张卡，误判会让一个真实存在的岗位被并掉、从页面上消失。
所以岗位名只认「完全一致」或「官网名字里带的某一段与它一致」，不做模糊相似度
（「高级用户研究专家（骑手生态 A）」和「…B」差一个字，模糊匹配会把两个不同的岗位并成一个）。
认不出来的同一岗位，在手动收录时用 `officialId` 指过去。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Protocol

OFFICIAL = "official"
BOSS = "boss"
COMMUNITY = "community"

# 显示顺序，同时是「谁更权威」的顺序
ORIGINS: tuple[str, ...] = (OFFICIAL, BOSS, COMMUNITY)
ORIGIN_LABELS: dict[str, str] = {OFFICIAL: "官网", BOSS: "Boss直聘", COMMUNITY: "社群"}


def collapse_origins(origins: Iterable[str]) -> list[str]:
    """去重、按固定顺序排好，并套用标注规则：官网和 Boss 直聘都有时只留官网。"""
    found = set(origins)
    unknown = found - set(ORIGINS)
    if unknown:
        raise ValueError(f"未知的岗位来源：{sorted(unknown)}")
    if OFFICIAL in found:
        found.discard(BOSS)
    return [origin for origin in ORIGINS if origin in found]


# ── 同一个岗位的判断 ────────────────────────────────────────────────────


def normalize_city(city: str) -> str:
    """各处城市写法不一（「北京市」「北京」），统一成不带「市」的；官网抓取与手动收录共用这一个。"""
    return re.sub(r"(?<=..)市$", "", city.strip())


def _norm(text: str) -> str:
    """全角转半角、转小写、去掉所有空白。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).lower())


# 官网岗位名常把事业部和城市用这些符号拼进去：「千问事业部-高级用户体验研究专员-北京/杭州」
_TITLE_SEPARATORS = re.compile(r"[-–—·/|、,，]+")


def same_title(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # 太短的片段（「研究」「专家」）不足以说明是同一个岗位
    if len(nb) >= 4 and nb in _TITLE_SEPARATORS.split(na):
        return True
    return len(na) >= 4 and na in _TITLE_SEPARATORS.split(nb)


def cities_overlap(a: Iterable[str], b: Iterable[str]) -> bool:
    """两边都写了城市就必须有交集；有一边没写就不拿城市排除。"""
    ca = {normalize_city(c) for c in a if c.strip()}
    cb = {normalize_city(c) for c in b if c.strip()}
    return not ca or not cb or bool(ca & cb)


class Identity(Protocol):
    company: str
    title: str
    cities: list[str]


def same_job(a: Identity, b: Identity) -> bool:
    return _norm(a.company) == _norm(b.company) and same_title(a.title, b.title) and cities_overlap(a.cities, b.cities)
