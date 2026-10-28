"""各家招聘官网的岗位搜索接口（adapter）：搜索一页 + 把岗位整理成 `Job`。

接口地址与参数取自公开网页前端的调用方式，字段形状以 2026-10 的探测样例为准
（scripts/probe_job_samples.py）。官网改版时这里最容易坏：解析不到岗位列表就抛
`AdapterError`，这家这次算没抓成、岗位原样保留，不会误删。

每家只做两件事：
- `search(client, company, keyword, page, size)` → (总数, 原始岗位列表)
- `normalize(company, raw)` → `Job`；不是社招正式岗（如字节系的校招 / 实习）返回 None
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Callable, NamedTuple
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel

from uxhot.social.window import Job

TZ = ZoneInfo("Asia/Shanghai")
TOTAL_KEYS = ("count", "total", "totalCount", "Count", "totalNum", "total_count", "totalSize")
DATE_TEXT = re.compile(r"(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})")


class Company(BaseModel):
    key: str
    name: str
    careers: str
    adapter: str
    base: str | None = None     # 字节系自有域名 / 飞书招聘租户的站点根地址


class AdapterError(RuntimeError):
    """接口返回的不是预期的岗位列表（参数变了、被拦了、改版了）。"""


class Adapter(NamedTuple):
    search: Callable[[httpx.Client, Company, str, int, int], tuple[int | None, list[dict]]]
    normalize: Callable[[Company, dict], Job | None]


# ── 通用小工具 ─────────────────────────────────────────────────────────


def to_date(value: Any) -> str | None:
    """毫秒 / 秒时间戳、「2026年10月19日」「2026-07-21」→ YYYY-MM-DD（北京时间）。"""
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        n = float(value)
        if n > 1e12:
            n /= 1000
        if n < 1e9:
            return None
        return datetime.fromtimestamp(n, TZ).date().isoformat()
    m = DATE_TEXT.search(str(value))
    if not m:
        return None
    y, mo, d = (int(g) for g in m.groups())
    try:
        return datetime(y, mo, d).date().isoformat()
    except ValueError:
        return None


def clean(text: Any) -> str:
    """官网的职责 / 要求文本：统一换行、去掉首尾空白和多余空行。"""
    if not isinstance(text, str):
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("　", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def names(items: Any, key: str = "name") -> list[str]:
    if not isinstance(items, list):
        return []
    out = [str(x.get(key)).strip() for x in items if isinstance(x, dict) and x.get(key)]
    return list(dict.fromkeys(out))


def joined(*parts: Any) -> str | None:
    text = " · ".join(str(p).strip() for p in parts if isinstance(p, str) and p.strip())
    return text or None


def find_list(doc: Any, title_key: str, id_key: str) -> tuple[int | None, list[dict] | None]:
    """在返回的 JSON 里找岗位列表（元素同时带岗位名与 id 字段）和最先出现的总数。"""
    total: int | None = None
    found: list[dict] | None = None

    def walk(node: Any) -> None:
        nonlocal total, found
        if found is not None:
            return
        if isinstance(node, dict):
            for key in TOTAL_KEYS:
                value = node.get(key)
                if total is None and isinstance(value, int) and not isinstance(value, bool):
                    total = value
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            if node and all(isinstance(x, dict) and title_key in x and id_key in x for x in node):
                found = node
                return
            for value in node:
                walk(value)

    walk(doc)
    return total, found


def parse(resp: httpx.Response, title_key: str, id_key: str) -> tuple[int | None, list[dict]]:
    if resp.status_code != 200:
        raise AdapterError(f"HTTP {resp.status_code}")
    try:
        doc = resp.json()
    except ValueError as exc:
        raise AdapterError(f"不是 JSON（{resp.headers.get('content-type', '?')}）") from exc
    total, jobs = find_list(doc, title_key, id_key)
    if jobs is not None:
        return total, jobs
    if total == 0:
        return 0, []
    raise AdapterError("没找到岗位列表：" + resp.text[:160])


def job_id(company: Company, raw_id: Any) -> str:
    if raw_id in (None, ""):
        raise AdapterError("岗位没有 id")
    return f"{company.key}-{raw_id}"


def build(company: Company, *, raw_id: Any, title: Any, url: str, posted: Any, kind: str, **fields: Any) -> Job | None:
    """统一组装；标题或日期缺失的岗位直接跳过（没有日期就没法进窗口）。"""
    title = str(title or "").strip()
    posted_at = to_date(posted)
    if not title or not posted_at:
        return None
    return Job(
        id=job_id(company, raw_id), company=company.name, title=title, url=url,
        dateKind=kind, postedAt=posted_at, **fields,
    )


# ── 腾讯 ───────────────────────────────────────────────────────────────


def tencent_search(client: httpx.Client, _: Company, keyword: str, page: int, size: int):
    resp = client.get(
        "https://careers.tencent.com/tencentcareer/api/post/Query",
        params={
            "timestamp": int(time.time() * 1000), "countryId": "", "cityId": "", "bgIds": "",
            "productId": "", "categoryId": "", "parentCategoryId": "", "attrId": "",
            "keyword": keyword, "pageIndex": page, "pageSize": size, "language": "zh-cn", "area": "cn",
        },
    )
    return parse(resp, "RecruitPostName", "PostId")


def tencent_job(company: Company, raw: dict) -> Job | None:
    pid = raw.get("PostId")
    return build(
        company, raw_id=pid, title=raw.get("RecruitPostName"),
        # 接口给的 PostURL 是 http:// 的，会卡在跳转上；用 https 的同一页
        url=f"https://careers.tencent.com/jobdesc.html?postId={pid}",
        posted=raw.get("LastUpdateTime"), kind="update",
        cities=[c for c in [str(raw.get("LocationName") or "").strip()] if c],
        department=joined(raw.get("BGName"), raw.get("ProductName")),
        experience=raw.get("RequireWorkYearsName") or None,
        duty=clean(raw.get("Responsibility")),
    )


# ── 字节系（字节跳动官网、飞书招聘租户、小米自有域名）────────────────


BYTEDANCE_BASE = "https://jobs.bytedance.com"


def _atsx_search(client: httpx.Client, base: str, portal: tuple[str, str], keyword: str, page: int, size: int):
    host = urlsplit(base).hostname or ""
    token = unquote(client.cookies.get("atsx-csrf-token", domain=host) or "")
    if not token:
        client.post(f"{base}/api/v1/csrf/token", json={"portal_entrance": 1})
        token = unquote(client.cookies.get("atsx-csrf-token", domain=host) or "")
        if not token:
            raise AdapterError("没拿到 CSRF token")
    website_path, channel = portal
    resp = client.post(
        f"{base}/api/v1/search/job/posts",
        json={
            "keyword": keyword, "limit": size, "offset": (page - 1) * size, "job_category_id_list": [],
            "tag_id_list": [], "location_code_list": [], "subject_id_list": [],
            "recruitment_id_list": [], "portal_type": 2, "job_function_id_list": [],
            "storefront_id_list": [], "portal_entrance": 1,
        },
        headers={
            "x-csrf-token": token, "website-path": website_path, "portal-channel": channel,
            "portal-platform": "pc", "accept-language": "zh-CN",
        },
    )
    return parse(resp, "title", "id")


def _atsx_job(company: Company, raw: dict, url: str) -> Job | None:
    # 飞书招聘租户的搜索会混进校招 / 实习，只留「社招」下的岗位
    recruit = raw.get("recruit_type") or {}
    parent = (recruit.get("parent") or {}).get("name") if isinstance(recruit, dict) else None
    if parent and parent != "社招":
        return None
    cities = names(raw.get("city_list")) or names([raw.get("city_info")])
    return build(
        company, raw_id=raw.get("id"), title=raw.get("title"), url=url,
        posted=raw.get("publish_time"), kind="publish", cities=cities,
        duty=clean(raw.get("description")), requirement=clean(raw.get("requirement")),
    )


def bytedance_search(client: httpx.Client, _: Company, keyword: str, page: int, size: int):
    return _atsx_search(client, BYTEDANCE_BASE, ("society", "office"), keyword, page, size)


def bytedance_job(company: Company, raw: dict) -> Job | None:
    return _atsx_job(company, raw, f"{BYTEDANCE_BASE}/experienced/position/{raw.get('id')}/detail")


def atsx_search(client: httpx.Client, company: Company, keyword: str, page: int, size: int):
    if not company.base:
        raise AdapterError("atsx 需要在 config/social.yaml 里写 base")
    return _atsx_search(client, company.base.rstrip("/"), ("index", "saas-career"), keyword, page, size)


def atsx_job(company: Company, raw: dict) -> Job | None:
    base = (company.base or "").rstrip("/")
    return _atsx_job(company, raw, f"{base}/index/position/{raw.get('id')}/detail")


# ── 阿里巴巴 ───────────────────────────────────────────────────────────


def alibaba_search(client: httpx.Client, _: Company, keyword: str, page: int, size: int):
    token = client.cookies.get("XSRF-TOKEN", domain="talent.alibaba.com")
    if not token:
        client.get("https://talent.alibaba.com/off-campus/position-list")
        token = client.cookies.get("XSRF-TOKEN", domain="talent.alibaba.com")
        if not token:
            raise AdapterError("没拿到 XSRF-TOKEN")
    resp = client.post(
        "https://talent.alibaba.com/position/search",
        params={"_csrf": token},
        json={
            "channel": "group_official_site", "language": "zh", "batchId": "", "categories": "",
            "deptCodes": [], "key": keyword, "pageIndex": page, "pageSize": size, "regions": "",
            "subCategories": "",
        },
        headers={"x-xsrf-token": token},
    )
    return parse(resp, "name", "id")


def _years(exp: Any) -> str | None:
    if not isinstance(exp, dict) or not isinstance(exp.get("from"), int):
        return None
    lo, hi = exp["from"], exp.get("to")
    return f"{lo}-{hi} 年" if isinstance(hi, int) else f"{lo} 年以上"


def alibaba_job(company: Company, raw: dict) -> Job | None:
    pid = raw.get("id")
    return build(
        company, raw_id=pid, title=raw.get("name"),
        # 与接口给的 positionUrl 同一路由（去掉一次性的 track_id）；前端脚本里也是这个路由
        url=f"https://talent.alibaba.com/off-campus/position-detail?positionId={pid}",
        posted=raw.get("publishTime"), kind="publish",
        cities=[str(c) for c in raw.get("workLocations") or [] if c],
        experience=_years(raw.get("experience")),
        duty=clean(raw.get("description")), requirement=clean(raw.get("requirement")),
    )


# ── 百度 ───────────────────────────────────────────────────────────────


def baidu_search(client: httpx.Client, _: Company, keyword: str, page: int, size: int):
    resp = client.post(
        "https://talent.baidu.com/httservice/getPostListNew",
        data={"recruitType": "SOCIAL", "pageSize": size, "keyWord": keyword, "curPage": page, "projectType": ""},
        headers={"Referer": "https://talent.baidu.com/jobs/social-list"},
    )
    return parse(resp, "name", "postId")


def baidu_job(company: Company, raw: dict) -> Job | None:
    pid = raw.get("postId")
    # 岗位名后面挂着内部编号「（J72632）」，对读者没用
    title = re.sub(r"\s*[（(]J\d+[)）]\s*$", "", str(raw.get("name") or ""))
    return build(
        company, raw_id=pid, title=title,
        # 前端路由是 /jobs/detail/:type/:id（type 即 recruitType）
        url=f"https://talent.baidu.com/jobs/detail/SOCIAL/{pid}",
        posted=raw.get("publishDate"), kind="publish",
        cities=[c.strip() for c in re.split(r"[,，、]", str(raw.get("workPlace") or "")) if c.strip()],
        department=raw.get("bgShortName") or None,
        experience=raw.get("workYears") or None,
        duty=clean(raw.get("workContent")), requirement=clean(raw.get("serviceCondition")),
    )


# ── 美团 ───────────────────────────────────────────────────────────────


def meituan_search(client: httpx.Client, _: Company, keyword: str, page: int, size: int):
    resp = client.post(
        "https://zhaopin.meituan.com/api/official/job/getJobList",
        json={
            "page": {"pageNo": page, "pageSize": size}, "jobShareType": "1", "keywords": keyword,
            "cityList": [], "department": [], "jfJgList": [],
            "jobType": [{"code": "3", "subCode": []}], "typeCode": [], "specialCode": [],
        },
        headers={"Referer": "https://zhaopin.meituan.com/web/social"},
    )
    return parse(resp, "name", "jobUnionId")


def meituan_job(company: Company, raw: dict) -> Job | None:
    uid = raw.get("jobUnionId")
    departments = names(raw.get("department"))
    return build(
        company, raw_id=uid, title=raw.get("name"),
        url=f"https://zhaopin.meituan.com/web/position/detail?jobUnionId={uid}&highlightType=social",
        # firstPostTime / expiredTime 在样例里全是空的，只有刷新时间可用
        posted=raw.get("refreshTime"), kind="update",
        cities=names(raw.get("cityList")),
        department=departments[0] if departments else None,
        experience=raw.get("workYear") or None,
        duty=clean(raw.get("jobDuty")), requirement=clean(raw.get("jobRequirement")),
    )


# ── 网易 ───────────────────────────────────────────────────────────────


def netease_search(client: httpx.Client, _: Company, keyword: str, page: int, size: int):
    resp = client.post(
        "https://hr.163.com/api/hr163/position/queryPage",
        json={"currentPage": page, "pageSize": size, "keyword": keyword},
        headers={"Referer": "https://hr.163.com/job-list.html"},
    )
    return parse(resp, "name", "id")


def netease_job(company: Company, raw: dict) -> Job | None:
    pid = raw.get("id")
    return build(
        company, raw_id=pid, title=raw.get("name"),
        url=f"https://hr.163.com/job-detail.html?id={pid}",
        posted=raw.get("updateTime"), kind="update",
        cities=[str(c) for c in raw.get("workPlaceNameList") or [] if c],
        department=joined(raw.get("firstDepName"), raw.get("productName")),
        experience=raw.get("reqWorkYearsName") or None,
        duty=clean(raw.get("description")), requirement=clean(raw.get("requirement")),
    )


ADAPTERS: dict[str, Adapter] = {
    "tencent": Adapter(tencent_search, tencent_job),
    "bytedance": Adapter(bytedance_search, bytedance_job),
    "atsx": Adapter(atsx_search, atsx_job),
    "alibaba": Adapter(alibaba_search, alibaba_job),
    "baidu": Adapter(baidu_search, baidu_job),
    "meituan": Adapter(meituan_search, meituan_job),
    "netease": Adapter(netease_search, netease_job),
}
