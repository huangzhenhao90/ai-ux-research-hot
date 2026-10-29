"""用研社招同步：抓各家官网 → 相关性筛选 → 滑动窗口 → 并入手动收录的岗位 → 写状态与站点数据。

- 状态：`data/social/jobs.json`（窗口里的官网岗位、retired 名单、各家最近一次抓取结果），提交进仓库；
- 手动收录：`data/social/manual.yaml`（Boss 直聘截图、社群信息；见 `manual.py`），人工维护；
- 站点数据：`web/content/social.json`（页面构建时读），由状态与手动收录整理出来，
  字段白名单见 `public.py`。

一家抓失败不影响别家：它的岗位原样保留，页面上标「上次更新于 …」。
全部失败时不写任何文件，退出码 1，让定时任务出黄色警告、沿用上一版。
"""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import httpx
import yaml
from pydantic import BaseModel, Field

from uxhot.config import CONFIG_DIR, REPO_ROOT
from uxhot.social.manual import ManualReport, load_manual, merge_manual
from uxhot.social.origin import OFFICIAL
from uxhot.social.public import official_job
from uxhot.social.sources import ADAPTERS, AdapterError, Company
from uxhot.social.window import Job, Window, WindowResult, apply_window

TZ = ZoneInfo("Asia/Shanghai")
STATE_PATH = REPO_ROOT / "data" / "social" / "jobs.json"
MANUAL_PATH = REPO_ROOT / "data" / "social" / "manual.yaml"
CONTENT_PATH = REPO_ROOT / "web" / "content" / "social.json"

PAUSE_SECONDS = 1.0
TIMEOUT = 15.0


class SocialConfig(BaseModel):
    minIntervalHours: float = 20
    window: Window = Field(default_factory=Window)
    maxPages: int = 5
    pageSize: int = 20
    keywords: list[str]
    include: str
    exclude: str = ""
    companies: list[Company]


def load_social_config(path: Path | None = None) -> SocialConfig:
    raw = yaml.safe_load((path or CONFIG_DIR / "social.yaml").read_text(encoding="utf-8"))
    cfg = SocialConfig.model_validate(raw)
    keys = [c.key for c in cfg.companies]
    if len(set(keys)) != len(keys):
        raise ValueError("config/social.yaml：公司 key 重复")
    unknown = sorted({c.adapter for c in cfg.companies} - set(ADAPTERS))
    if unknown:
        raise ValueError(f"config/social.yaml：没有这些 adapter：{unknown}")
    re.compile(cfg.include)
    re.compile(cfg.exclude)
    return cfg


class CompanyStatus(BaseModel):
    ok: bool = False
    lastOkAt: str | None = None     # 最近一次抓成功的时间（ISO，北京时间）
    lastError: str | None = None
    found: int = 0                  # 最近一次抓成功时搜到几条相关岗位


class State(BaseModel):
    fetchedAt: str | None = None
    companies: dict[str, CompanyStatus] = Field(default_factory=dict)
    jobs: list[Job] = Field(default_factory=list)
    retired: dict[str, str] = Field(default_factory=dict)


def load_state(path: Path = STATE_PATH) -> State:
    if not path.exists():
        return State()
    return State.model_validate_json(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


# ── 抓取 ───────────────────────────────────────────────────────────────


def is_relevant(title: str, cfg: SocialConfig) -> bool:
    if not re.search(cfg.include, title, re.I):
        return False
    return not (cfg.exclude and re.search(cfg.exclude, title, re.I))


def fetch_company(client: httpx.Client, company: Company, cfg: SocialConfig) -> list[Job]:
    """按每个关键词翻页搜，留下相关岗位（按 id 去重）。

    任何一次请求失败都让整家算「这次没抓成」——只拿到一半结果的话，
    没搜到的岗位会被误判成下线。
    """
    adapter = ADAPTERS[company.adapter]
    found: dict[str, Job] = {}
    for keyword in cfg.keywords:
        for page in range(1, cfg.maxPages + 1):
            total, raws = adapter.search(client, company, keyword, page, cfg.pageSize)
            time.sleep(PAUSE_SECONDS)
            hits = 0
            for raw in raws:
                job = adapter.normalize(company, raw)
                if job is None or not is_relevant(job.title, cfg):
                    continue
                hits += 1
                found.setdefault(job.id, job)
            # 搜索按相关度排：这一页一条相关的都没有，后面的页也不会有
            if len(raws) < cfg.pageSize or hits == 0 or page * cfg.pageSize >= (total or 0):
                break
    return list(found.values())


def user_agent(site_yaml: Path | None = None) -> str:
    """采集器的 User-Agent：`Mozilla/5.0 (compatible; URHOTBot/0.1; +关于页地址)`。

    名字与联系地址取自 config/site.yaml 的 `crawlerName`（「URHOTBot (+关于页地址)」）：联系地址要指向
    公开的关于页——源码仓库是私有的，被抓的站点点进去会是 404（DECISIONS D22）。
    """
    site = yaml.safe_load((site_yaml or CONFIG_DIR / "site.yaml").read_text(encoding="utf-8"))
    crawler = str(site["crawlerName"]).strip()
    m = re.match(r"^(\S+)\s*\((\+[^)]*)\)$", crawler)
    return f"Mozilla/5.0 (compatible; {m.group(1)}/0.1; {m.group(2)})" if m else f"Mozilla/5.0 (compatible; {crawler})"


def build_client() -> httpx.Client:
    from uxhot.collect.fetch import build_client as base_client

    return base_client(
        timeout=TIMEOUT,
        headers={"User-Agent": user_agent(), "Accept-Language": "zh-CN,zh;q=0.9"},
    )


# ── 主流程 ─────────────────────────────────────────────────────────────


class SyncReport(BaseModel):
    skipped: bool = False
    ok: list[str] = Field(default_factory=list)
    failed: dict[str, str] = Field(default_factory=dict)
    window: WindowResult = Field(default_factory=WindowResult)
    manual: ManualReport = Field(default_factory=ManualReport)
    total: int = 0


def assemble_jobs(
    state: State, cfg: SocialConfig, manual_path: Path | None, today: date
) -> tuple[list[dict], ManualReport]:
    """页面上的全部岗位 = 官网岗位 + 手动收录的岗位（按来源标注规则并在一起）。"""
    manual = load_manual(manual_path) if manual_path else []
    return merge_manual([official_job(job) for job in state.jobs], manual, today, cfg.window)


def sync(
    cfg: SocialConfig,
    *,
    now: datetime | None = None,
    force: bool = False,
    state_path: Path = STATE_PATH,
    content_path: Path = CONTENT_PATH,
    manual_path: Path | None = MANUAL_PATH,
    fetch: Callable[[httpx.Client, Company, SocialConfig], list[Job]] = fetch_company,
    client_factory: Callable[[], httpx.Client] = build_client,
) -> SyncReport:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    state = load_state(state_path)
    report = SyncReport()

    if not force and state.fetchedAt:
        last = datetime.fromisoformat(state.fetchedAt)
        if now - last < timedelta(hours=cfg.minIntervalHours):
            report.skipped = True
            # 不抓取，但手动收录的岗位随时可能改过、也每天在过期：页面数据照常重建（没变化就不会产生提交）
            jobs, report.manual = assemble_jobs(state, cfg, manual_path, now.date())
            report.total = len(jobs)
            write_json(content_path, build_content(state, cfg, jobs))
            return report

    fetched: dict[str, list[Job]] = {}
    with client_factory() as client:
        for company in cfg.companies:
            status = state.companies.get(company.name, CompanyStatus())
            try:
                jobs = fetch(client, company, cfg)
            except (httpx.HTTPError, AdapterError, ValueError, KeyError, TypeError, AttributeError) as exc:
                status.ok = False
                status.lastError = f"{type(exc).__name__}: {exc}"[:200]
                report.failed[company.name] = status.lastError
            else:
                fetched[company.name] = jobs
                status.ok, status.lastError = True, None
                status.lastOkAt, status.found = now.isoformat(timespec="seconds"), len(jobs)
                report.ok.append(company.name)
            state.companies[company.name] = status

    if not fetched:
        return report

    state.jobs, state.retired, report.window = apply_window(
        state.jobs, state.retired, fetched, now.date(), cfg.window
    )
    state.fetchedAt = now.isoformat(timespec="seconds")
    # 配置里删掉的公司：状态与岗位一起清掉
    names = {c.name for c in cfg.companies}
    state.companies = {k: v for k, v in state.companies.items() if k in names}
    state.jobs = [j for j in state.jobs if j.company in names]

    jobs, report.manual = assemble_jobs(state, cfg, manual_path, now.date())
    report.total = len(jobs)

    write_json(state_path, state.model_dump())
    write_json(content_path, build_content(state, cfg, jobs))
    return report


def build_content(state: State, cfg: SocialConfig, jobs: list[dict] | None = None) -> dict:
    """页面读的数据：岗位按起算日新→旧（官网 + 手动收录，每条带 origins 来源）；公司带官网抓取状态。

    `jobs` 是 `assemble_jobs` 的结果；不传就只有官网岗位。
    """
    if jobs is None:
        jobs = [official_job(job) for job in state.jobs]
    counts: dict[str, int] = {}
    for doc in jobs:
        if OFFICIAL in doc["origins"]:
            counts[doc["company"]] = counts.get(doc["company"], 0) + 1
    companies = []
    for c in cfg.companies:
        status = state.companies.get(c.name, CompanyStatus())
        companies.append({
            "key": c.key,
            "name": c.name,
            "careers": c.careers,
            "ok": status.ok,
            "lastOkAt": status.lastOkAt,
            # 来自这家公司官网的岗位数（Boss 直聘、社群来源的不算）
            "jobCount": counts.get(c.name, 0),
        })
    return {
        "updatedAt": state.fetchedAt,
        "window": {"admitDays": cfg.window.admitDays, "keepDays": cfg.window.keepDays},
        "companies": companies,
        "jobs": jobs,
    }
