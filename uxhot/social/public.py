"""社招岗位里「会发布到页面」的字段。

页面数据 `web/content/social.json` 最终会进公开站点，所以每个字段都在这里逐个列出（白名单）：
以后给 `Job` / `ManualJob` 加了内部字段，默认不会漏出去。窗口状态（misses、lastSeen）、
手动收录里的 `internal` 备注都不在其中。

只用属性访问、不 import 模型类，避免与 manual.py 循环引用。
"""

from __future__ import annotations

from typing import Any

from uxhot.social.origin import OFFICIAL

PUBLIC_JOB_FIELDS: tuple[str, ...] = (
    "id", "company", "title", "url", "cities", "department", "experience", "salary",
    "origins", "dateKind", "postedAt", "since", "firstSeen", "duty", "requirement",
)


def official_job(job: Any) -> dict:
    """官网抓到的岗位（`window.Job`）→ 页面数据。"""
    return {
        "id": job.id,
        "company": job.company,
        "title": job.title,
        "url": job.url,
        "cities": list(job.cities),
        "department": job.department,
        "experience": job.experience,
        "salary": None,
        "origins": [OFFICIAL],
        "dateKind": job.dateKind,
        "postedAt": job.postedAt,
        "since": job.since,
        "firstSeen": job.firstSeen,
        "duty": job.duty,
        "requirement": job.requirement,
    }


def manual_job(entry: Any) -> dict:
    """手动收录的岗位（`manual.ManualJob`）→ 页面数据。

    没写发布日期时，起算日用收录日，页面上显示「N 天前收录」（`dateKind` 为 added）。
    """
    since = (entry.postedAt or entry.addedAt).isoformat()
    return {
        "id": entry.job_id,
        "company": entry.company,
        "title": entry.title,
        "url": entry.url,
        "cities": list(entry.cities),
        "department": entry.department,
        "experience": entry.experience,
        "salary": entry.salary,
        "origins": [entry.source],
        "dateKind": "publish" if entry.postedAt else "added",
        "postedAt": since,
        "since": since,
        "firstSeen": entry.addedAt.isoformat(),
        "duty": entry.duty,
        "requirement": entry.requirement,
    }
