"""社招岗位的滑动窗口：收 30 天内的、留到满 90 天、下线就拿掉。

规则（DECISIONS D17）：

- **起算日** `since`：第一次看到这个岗位时，官网给的发布日期（字节系、百度、阿里）或
  更新日期（腾讯、网易、美团只有这个）。之后官网再刷新也**不重新计时**——
  否则 HR 点一下刷新，常年挂着的岗位就永远「新」。
- **收录**：第一次看到时 `today - since` ≤ `admitDays`（30）才收。
- **保留**：`today - since` > `keepDays`（90）就移出，记进 `retired`，以后刷新了也不再收。
  不满 30 天就拒收的岗位同样记进 `retired`。
- **下线**：公司这次抓取成功、但连续 `missLimit` 次都没搜到这个岗位，就当官网下线，移出。
  抓取失败的公司不算「没搜到」，它的岗位原样保留（只照常判断是否满 90 天）。

窗口按天算，`today` 用北京时间的日期。
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field


class Job(BaseModel):
    """一条社招岗位（已经过相关性筛选）。"""

    id: str                         # "<公司键>-<官网岗位 id>"
    company: str
    title: str
    url: str
    cities: list[str] = Field(default_factory=list)
    department: str | None = None
    experience: str | None = None
    # 官网给的日期是哪一种：publish = 首次发布；update = 最近更新 / 刷新
    dateKind: str = "publish"
    postedAt: str                   # 官网这次给的日期 YYYY-MM-DD（会随刷新变）
    duty: str = ""
    requirement: str = ""

    # ── 窗口状态（由 apply_window 维护）─────────────────────────────
    since: str = ""                 # 起算日，第一次看到时定下，之后不变
    firstSeen: str = ""
    lastSeen: str = ""
    misses: int = 0                 # 公司抓取成功但没搜到它的连续次数


class Window(BaseModel):
    admitDays: int = 30
    keepDays: int = 90
    missLimit: int = 3
    # retired 名单保留多久（防止它无限增长；一年后官网早就换了一批岗位）
    retireMemoryDays: int = 365


class WindowResult(BaseModel):
    added: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    expired: list[str] = Field(default_factory=list)
    offline: list[str] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)   # 第一次看到就已超过 30 天


def age(day: str, today: date) -> int:
    return (today - date.fromisoformat(day)).days


def expires_on(job: Job, window: Window) -> str:
    """满 keepDays 后的第一天移出；页面上显示「预计下架」。"""
    return (date.fromisoformat(job.since) + timedelta(days=window.keepDays + 1)).isoformat()


def apply_window(
    jobs: list[Job],
    retired: dict[str, str],
    fetched: dict[str, list[Job]],
    today: date,
    window: Window,
) -> tuple[list[Job], dict[str, str], WindowResult]:
    """把这次抓到的岗位并进已有岗位，返回（新岗位表，新 retired 名单，变化明细）。

    `fetched` 只放**抓取成功**的公司：公司名 → 这次搜到的相关岗位（可以是空列表，
    表示这家确实一个都没了）。不在 `fetched` 里的公司视为这次没抓成，岗位不动。
    `retired` 是 岗位 id → 移出日期，不会被原地修改。
    """
    result = WindowResult()
    iso = today.isoformat()
    retired = {
        jid: day for jid, day in retired.items() if age(day, today) <= window.retireMemoryDays
    }
    current = {job.id: job for job in jobs}
    out: dict[str, Job] = {}

    for company, found in fetched.items():
        seen_ids = set()
        for job in found:
            if job.id in seen_ids:
                continue
            seen_ids.add(job.id)
            old = current.get(job.id)
            if old is not None:
                # 内容以官网最新为准；窗口状态沿用
                out[job.id] = job.model_copy(
                    update={"since": old.since, "firstSeen": old.firstSeen, "lastSeen": iso, "misses": 0}
                )
                result.updated.append(job.id)
            elif job.id in retired:
                continue
            elif age(job.postedAt, today) <= window.admitDays:
                out[job.id] = job.model_copy(
                    update={"since": job.postedAt, "firstSeen": iso, "lastSeen": iso, "misses": 0}
                )
                result.added.append(job.id)
            else:
                retired[job.id] = iso
                result.rejected.append(job.id)
        # 这家抓成功了、但这次没搜到的老岗位：攒够次数才算下线
        for old in current.values():
            if old.company != company or old.id in seen_ids:
                continue
            if old.misses + 1 >= window.missLimit:
                result.offline.append(old.id)
            else:
                out[old.id] = old.model_copy(update={"misses": old.misses + 1})

    # 这次没抓成的公司：原样保留
    for old in current.values():
        if old.company not in fetched:
            out[old.id] = old

    kept: list[Job] = []
    for job in out.values():
        if age(job.since, today) > window.keepDays:
            retired[job.id] = iso
            result.expired.append(job.id)
        else:
            kept.append(job)
    # 起算日新的在前；同一天按公司、岗位名排，输出稳定、diff 好看
    kept.sort(key=lambda j: (j.company, j.title, j.id))
    kept.sort(key=lambda j: j.since, reverse=True)
    return kept, retired, result
