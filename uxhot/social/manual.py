"""手动收录的社招岗位：Boss 直聘截图、社群里看到的信息。

这两类岗位没有官网接口可抓，由人（或 Claude 看过截图后）整理进 `data/social/manual.yaml`
（格式见该文件开头的注释）。这里负责：校验、套用和官网岗位一样的保留规则、
按来源标注规则并进官网岗位（`origin.py`）。

⚠️ manual.yaml 里可能有社群成员信息、截图来源这类不该公开的内容，只放在私有仓库（DECISIONS D22）。
发布到页面的字段由 `public.manual_job` 逐个列出，`internal` 备注永远不会进页面数据。
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from uxhot.social.origin import collapse_origins, normalize_city, same_job
from uxhot.social.public import manual_job
from uxhot.social.window import Window

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class ManualError(ValueError):
    """manual.yaml 写错了：消息里会说是第几条、哪个字段。"""


def _blank_to_none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


class ManualJob(BaseModel):
    # 写错字段名（比如把 postedAt 拼成 postAt）直接报错，不要悄悄丢掉
    model_config = ConfigDict(extra="forbid")

    source: Literal["boss", "community"]
    company: str
    title: str
    addedAt: date                           # 收录日：把这条信息整理进来的那天
    # 省略时按「来源 + 公司 + 岗位名 + 收录日」生成；之后改了其中任何一项 id 都会变（收藏会失效），
    # 想固定就自己写
    id: str | None = None
    postedAt: date | None = None            # 截图 / 消息里能看出发布日期时才写
    cities: list[str] = Field(default_factory=list)
    department: str | None = None
    experience: str | None = None
    salary: str | None = None               # Boss 截图里都有；官网通常不给
    url: str | None = None                  # 能打开的岗位页；Boss 截图通常没有
    duty: str = ""
    requirement: str = ""
    # 手动指定它就是官网的哪个岗位（岗位名对不上、自动认不出来时用）
    officialId: str | None = None
    # 私有备注（谁分享的、截图文件名……）：只留在这个文件里，不会发布
    internal: str | None = None

    @field_validator("company", "title")
    @classmethod
    def _required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("department", "experience", "salary", "internal", "officialId")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @field_validator("duty", "requirement")
    @classmethod
    def _body(cls, value: str) -> str:
        return value.strip()

    @field_validator("cities")
    @classmethod
    def _cities(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(normalize_city(c) for c in value if c.strip()))

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        value = _blank_to_none(value)
        if value and not re.match(r"^https?://", value):
            raise ValueError("只接受 http(s) 链接")
        return value

    @field_validator("id")
    @classmethod
    def _id(cls, value: str | None) -> str | None:
        value = _blank_to_none(value)
        if value and not ID_PATTERN.match(value):
            raise ValueError("id 只能用字母、数字、下划线和连字符（它会进页面路径）")
        return value

    @model_validator(mode="after")
    def _dates(self) -> "ManualJob":
        if self.postedAt and self.postedAt > self.addedAt:
            raise ValueError("postedAt（发布日期）不能晚于 addedAt（收录日）")
        return self

    @property
    def job_id(self) -> str:
        if self.id:
            return self.id
        key = f"{self.source}|{self.company}|{self.title}|{self.addedAt.isoformat()}"
        return f"{self.source}-{hashlib.sha1(key.encode()).hexdigest()[:10]}"


def load_manual(path: Path) -> list[ManualJob]:
    """读 manual.yaml。文件不存在或是空的就是没有手动收录的岗位。"""
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ManualError(f"{path.name} 不是合法的 YAML：{exc}") from exc
    if not isinstance(raw, dict) or set(raw) - {"jobs"}:
        raise ManualError(f"{path.name} 顶层只能有一个 jobs 列表")
    rows = raw.get("jobs") or []
    if not isinstance(rows, list):
        raise ManualError(f"{path.name} 的 jobs 必须是列表")

    jobs: list[ManualJob] = []
    for index, row in enumerate(rows, 1):
        try:
            jobs.append(ManualJob.model_validate(row))
        except ValidationError as exc:
            what = " / ".join(
                f"{'.'.join(str(p) for p in err['loc']) or '整条'}：{err['msg']}" for err in exc.errors()
            )
            label = f"{row.get('company', '?')} {row.get('title', '?')}" if isinstance(row, dict) else "?"
            raise ManualError(f"{path.name} 第 {index} 条（{label}）有问题：{what}") from exc

    seen: set[str] = set()
    for job in jobs:
        if job.job_id in seen:
            raise ManualError(f"{path.name}：id 重复：{job.job_id}")
        seen.add(job.job_id)
    return jobs


def _identity(company: str, title: str, cities: list[str]) -> SimpleNamespace:
    return SimpleNamespace(company=company, title=title, cities=cities)


class ManualReport(BaseModel):
    shown: list[str] = Field(default_factory=list)      # 单独成卡的
    merged: list[str] = Field(default_factory=list)     # 并进了官网岗位或另一条手动岗位的
    expired: list[str] = Field(default_factory=list)    # 满 keepDays 天移出的
    stale: list[str] = Field(default_factory=list)      # 发布日期比收录日早了 admitDays 天以上，不收
    dangling: list[str] = Field(default_factory=list)   # officialId 指向的官网岗位不存在


def merge_manual(
    officials: list[dict],
    manual: list[ManualJob],
    today: date,
    window: Window,
) -> tuple[list[dict], ManualReport]:
    """把手动收录的岗位并进官网岗位，返回（页面上的全部岗位，变化明细）。

    `officials` 已经是页面数据的形状（`public.official_job`），不会被原地修改。

    保留规则与官网岗位一致（DECISIONS D17）：起算日是发布日期（没写就是收录日），
    满 `keepDays` 天移出；写了发布日期且比收录日早了 `admitDays` 天以上的不收
    （「常年挂着不招的岗位不出现在这里」这条对手动收录同样成立）。
    """
    out = [{**doc, "origins": list(doc["origins"])} for doc in officials]
    by_id = {doc["id"]: doc for doc in out}
    report = ManualReport()

    for entry in manual:
        jid = entry.job_id
        if entry.addedAt > today:
            raise ManualError(f"{jid}：addedAt（收录日）{entry.addedAt} 在今天之后")
        if entry.postedAt and (entry.addedAt - entry.postedAt).days > window.admitDays:
            report.stale.append(jid)
            continue
        if (today - (entry.postedAt or entry.addedAt)).days > window.keepDays:
            report.expired.append(jid)
            continue

        target = None
        if entry.officialId:
            target = by_id.get(entry.officialId)
            if target is None:
                report.dangling.append(jid)
        if target is None:
            probe = _identity(entry.company, entry.title, entry.cities)
            target = next(
                (doc for doc in out if same_job(_identity(doc["company"], doc["title"], doc["cities"]), probe)),
                None,
            )

        if target is not None:
            target["origins"] = collapse_origins([*target["origins"], entry.source])
            report.merged.append(jid)
            continue
        doc = manual_job(entry)
        if doc["id"] in by_id:
            # 页面路径、收藏、React 的 key 都靠 id，撞了会让两个岗位互相顶掉
            raise ManualError(f"{jid}：id 与已有岗位重复（官网岗位的 id 形如 腾讯-123，请换一个）")
        out.append(doc)
        by_id[doc["id"]] = doc
        report.shown.append(jid)

    # 起算日新的在前；同一天按公司、岗位名排，输出稳定、diff 好看（与 apply_window 一致）
    out.sort(key=lambda doc: (doc["company"], doc["title"], doc["id"]))
    out.sort(key=lambda doc: doc["since"], reverse=True)
    return out, report
