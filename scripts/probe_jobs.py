#!/usr/bin/env python3
"""社招可行性探测：公司招聘官网能不能直接拿到用研社招岗位。

一次性的探测工具，不进正式流水线。对 `config/job_probe.yaml` 里的每家公司：

1. **首页**：社招官网是否可达、跳到了哪个域名、是不是托管在飞书招聘 / Moka / 北森
   这类招聘系统上（同一系统写一个适配就能覆盖所有用它的公司）。
2. **robots.txt**：对通用爬虫是否整站禁止、是否禁止 /api。
3. **搜索接口**（有策略的公司）：用「用户研究」「体验研究」各搜一次，记录是否返回 JSON、
   结果总数与前几条岗位名。接口地址来自公开网页前端的调用方式，可能已经变了——
   这正是要探测的事；解析不依赖确切字段名，而是在返回的 JSON 里找岗位列表与总数。

礼貌约束：顺序请求、每次间隔 1 秒、超时 15 秒、UA 表明身份，总共约百来个请求。
结果打印成 Markdown 表格，并写进 GitHub Actions 的运行摘要（如果在 Actions 里跑）。

用法：
    python scripts/probe_jobs.py
    python scripts/probe_jobs.py --only 腾讯 --only 字节跳动
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "config" / "job_probe.yaml"

KEYWORDS = ("用户研究", "体验研究")
# 每次搜索取多少条：看发布时间分布要样本，20 条够看出新旧
PAGE_SIZE = 20
# 联系地址指向公开的关于页，不是源码仓库（私有，DECISIONS D22）
USER_AGENT = (
    "Mozilla/5.0 (compatible; URHOTBot-probe/0.1; "
    "+https://huangzhenhao90.github.io/ai-ux-research-hot/about)"
)
PAUSE_SECONDS = 1.0
TIMEOUT = 15.0

# 托管招聘系统的特征（出现在最终域名或页面里）
PLATFORMS = {
    "飞书招聘": ("jobs.feishu.cn", "jobs.f.mioffice.cn", "atsx", "lf-cdn-tos.bytescm.com"),
    "Moka": ("mokahr.com",),
    "北森": ("zhiye.com", "beisen"),
    "大易": ("dayee.com",),
    "智联 hotjob": ("hotjob.cn",),
    "Wintalent": ("wintalent.cn",),
}

TITLE_KEYS = (
    "title", "name", "postName", "positionName", "RecruitPostName", "jobName",
    "recruitPostName", "position_name", "job_name",
)
TOTAL_KEYS = ("count", "total", "totalCount", "Count", "totalNum", "total_count", "totalSize")
RELEVANT = re.compile(r"研究|用研|体验|洞察|调研|UXR|Research", re.I)


@dataclass
class ApiResult:
    status: int | None = None
    json_ok: bool = False
    total: int | None = None
    titles: list[str] = field(default_factory=list)
    jobs: list[dict] = field(default_factory=list)
    note: str = ""


@dataclass
class CompanyReport:
    name: str
    careers: str
    home_status: int | None = None
    final_host: str = ""
    platform: str = ""
    spa: bool = False
    robots: str = ""
    api: str = ""
    results: dict[str, ApiResult] = field(default_factory=dict)
    error: str = ""


# ── 通用小工具 ─────────────────────────────────────────────────────────


def pause() -> None:
    time.sleep(PAUSE_SECONDS)


def find_jobs(doc: Any) -> tuple[int | None, list[str], list[dict]]:
    """在任意形状的 JSON 里找「岗位列表」与「总数」。

    岗位列表 = 第一个「元素是字典、且带岗位名字段」的数组；总数 = 最先遇到的计数字段。
    同时返回岗位对象本身（看里面有没有发布/更新时间）。
    找不到就返回 (None, [], [])，让报告如实写「没解析出来」。
    """
    total: int | None = None
    titles: list[str] = []
    jobs: list[dict] = []

    def walk(node: Any) -> None:
        nonlocal total, titles, jobs
        if isinstance(node, dict):
            for key in TOTAL_KEYS:
                value = node.get(key)
                if total is None and isinstance(value, int) and not isinstance(value, bool):
                    total = value
            for value in node.values():
                walk(value)
        elif isinstance(node, list) and node and not titles:
            if all(isinstance(x, dict) for x in node[:3]):
                for key in TITLE_KEYS:
                    found = [str(x[key]).strip() for x in node if isinstance(x.get(key), str)]
                    if found:
                        titles = found
                        jobs = [x for x in node if isinstance(x.get(key), str)]
                        return
            for value in node:
                walk(value)

    walk(doc)
    if total is None and titles:
        total = len(titles)
    return total, titles, jobs


def json_result(resp: httpx.Response) -> ApiResult:
    out = ApiResult(status=resp.status_code)
    try:
        doc = resp.json()
    except ValueError:
        out.note = f"不是 JSON（{resp.headers.get('content-type', '?')}，{len(resp.content)} 字节）"
        return out
    out.json_ok = True
    out.total, out.titles, out.jobs = find_jobs(doc)
    if not out.titles:
        # 留一点原文方便人工判断接口要什么参数
        out.note = "JSON 里没找到岗位列表：" + json.dumps(doc, ensure_ascii=False)[:160]
    return out


# ── 发布 / 更新时间 ───────────────────────────────────────────────────

# 字段名里带这些词的才当作时间候选（publish_time、LastUpdateTime、refreshDate……）
DATE_KEY = re.compile(r"time|date|publish|update|refresh|create|modif|online|release", re.I)
DATE_TEXT = re.compile(r"(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})")


def to_date(value: Any) -> str | None:
    """把各种时间写法统一成 YYYY-MM-DD；认不出就返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        n = float(value)
        if 1e12 < n < 1e14:      # 毫秒
            n /= 1000
        if 1e9 < n < 1e11:       # 秒（2001 年以后）
            return time.strftime("%Y-%m-%d", time.gmtime(n))
        return None
    if isinstance(value, str):
        m = DATE_TEXT.search(value)
        if m:
            y, mo, d = (int(g) for g in m.groups())
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def date_fields(job: dict, prefix: str = "") -> dict[str, str]:
    """岗位对象里所有能解析成日期的时间字段（往下看一层嵌套）。"""
    out: dict[str, str] = {}
    for key, value in job.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict) and not prefix:
            out.update(date_fields(value, prefix=f"{key}."))
        elif DATE_KEY.search(str(key)):
            parsed = to_date(value)
            if parsed:
                out[name] = parsed
    return out


def age_days(day: str) -> int:
    return int((time.time() - time.mktime(time.strptime(day, "%Y-%m-%d"))) // 86400)


# ── 各家的搜索接口策略（地址取自公开网页前端的调用方式，可能已变）──────


def s_tencent(client: httpx.Client, kw: str, _: str) -> ApiResult:
    resp = client.get(
        "https://careers.tencent.com/tencentcareer/api/post/Query",
        params={
            "timestamp": int(time.time() * 1000), "countryId": "", "cityId": "", "bgIds": "",
            "productId": "", "categoryId": "", "parentCategoryId": "", "attrId": "",
            "keyword": kw, "pageIndex": 1, "pageSize": PAGE_SIZE, "language": "zh-cn", "area": "cn",
        },
    )
    return json_result(resp)


# 字节系招聘系统的门户参数：第一轮探测拿到的是「site not exist」，说明 CSRF 握手通了、
# 但门户标识不对。这里按常见取值逐个试，报告里记下哪一组能用。
ATSX_VARIANTS: tuple[tuple[str, str], ...] = (
    # 第二轮探出来的两组：字节官网用前者，飞书招聘租户（含小米自有域名）用后者
    ("society", "office"),
    ("index", "saas-career"),
    ("experienced", "office"),
    ("experienced", "saas-career"),
    ("society", "saas-career"),
    ("social", "office"),
)


def _atsx(client: httpx.Client, base: str, kw: str, _website_path: str) -> ApiResult:
    """字节系招聘系统（字节跳动官网与飞书招聘租户）：先取 CSRF，再按门户参数逐个试搜索。"""
    token_resp = client.post(f"{base}/api/v1/csrf/token", json={"portal_entrance": 1})
    token = unquote(client.cookies.get("atsx-csrf-token") or "")
    if not token:
        res = json_result(token_resp)
        res.note = f"没拿到 CSRF token（HTTP {token_resp.status_code}）"
        return res
    last = ApiResult(note="没有可试的门户参数")
    for website_path, channel in ATSX_VARIANTS:
        pause()
        resp = client.post(
            f"{base}/api/v1/search/job/posts",
            json={
                "keyword": kw, "limit": PAGE_SIZE, "offset": 0, "job_category_id_list": [],
                "tag_id_list": [], "location_code_list": [], "subject_id_list": [],
                "recruitment_id_list": [], "portal_type": 2, "job_function_id_list": [],
                "storefront_id_list": [], "portal_entrance": 1,
            },
            headers={
                "x-csrf-token": token, "website-path": website_path,
                "portal-channel": channel, "portal-platform": "pc", "accept-language": "zh-CN",
            },
        )
        last = json_result(resp)
        if last.titles or (last.json_ok and last.total == 0):
            last.note = (f"可用参数：website-path={website_path}, portal-channel={channel}；" + last.note).rstrip("；")
            return last
    last.note = "试过的门户参数都不行；" + last.note
    return last


def s_bytedance(client: httpx.Client, kw: str, _: str) -> ApiResult:
    return _atsx(client, "https://jobs.bytedance.com", kw, "experienced")


def s_feishu(client: httpx.Client, kw: str, tenant: str) -> ApiResult:
    return _atsx(client, f"https://{tenant}.jobs.feishu.cn", kw, "experienced")


def s_atsx(client: httpx.Client, kw: str, base: str) -> ApiResult:
    """自有域名的字节系招聘站（如小米的 jobs.f.mioffice.cn），参数是站点根地址。"""
    return _atsx(client, base, kw, "experienced")


def s_alibaba(client: httpx.Client, kw: str, _: str) -> ApiResult:
    client.get("https://talent.alibaba.com/off-campus/position-list")
    token = client.cookies.get("XSRF-TOKEN") or ""
    pause()
    resp = client.post(
        "https://talent.alibaba.com/position/search",
        params={"_csrf": token},
        json={
            "channel": "group_official_site", "language": "zh", "batchId": "",
            "categories": "", "deptCodes": [], "key": kw, "pageIndex": 1, "pageSize": PAGE_SIZE,
            "regions": "", "subCategories": "",
        },
        headers={"x-xsrf-token": token},
    )
    res = json_result(resp)
    if not token:
        res.note = ("没拿到 XSRF-TOKEN；" + res.note).rstrip("；")
    return res


def s_baidu(client: httpx.Client, kw: str, _: str) -> ApiResult:
    resp = client.post(
        "https://talent.baidu.com/httservice/getPostListNew",
        data={"recruitType": "SOCIAL", "pageSize": PAGE_SIZE, "keyWord": kw, "curPage": 1, "projectType": ""},
        headers={"Referer": "https://talent.baidu.com/jobs/social-list"},
    )
    return json_result(resp)


def s_meituan(client: httpx.Client, kw: str, _: str) -> ApiResult:
    resp = client.post(
        "https://zhaopin.meituan.com/api/official/job/getJobList",
        json={
            "page": {"pageNo": 1, "pageSize": PAGE_SIZE}, "jobShareType": "1", "keywords": kw,
            "cityList": [], "department": [], "jfJgList": [],
            "jobType": [{"code": "3", "subCode": []}], "typeCode": [], "specialCode": [],
        },
        headers={"Referer": "https://zhaopin.meituan.com/web/social"},
    )
    return json_result(resp)


def s_netease(client: httpx.Client, kw: str, _: str) -> ApiResult:
    resp = client.post(
        "https://hr.163.com/api/hr163/position/queryPage",
        json={"currentPage": 1, "pageSize": PAGE_SIZE, "keyword": kw},
        headers={"Referer": "https://hr.163.com/job-list.html"},
    )
    return json_result(resp)


def s_jd(client: httpx.Client, kw: str, _: str) -> ApiResult:
    resp = client.post(
        "https://zhaopin.jd.com/web/job/job_list",
        data={"pageIndex": 1, "pageSize": PAGE_SIZE, "workCityJson": "[]", "jobTypeJson": "[]", "jobSearch": kw},
        headers={"Referer": "https://zhaopin.jd.com/web/job/job_info_list/3"},
    )
    return json_result(resp)


def s_kuaishou(client: httpx.Client, kw: str, _: str) -> ApiResult:
    resp = client.get(
        "https://zhaopin.kuaishou.cn/recruit/e/api/v1/open/positions/simple",
        params={"pageNum": 1, "pageSize": PAGE_SIZE, "keyword": kw},
        headers={"Referer": "https://zhaopin.kuaishou.cn/"},
    )
    return json_result(resp)


STRATEGIES: dict[str, Callable[[httpx.Client, str, str], ApiResult]] = {
    "tencent": s_tencent,
    "bytedance": s_bytedance,
    "feishu": s_feishu,
    "atsx": s_atsx,
    "alibaba": s_alibaba,
    "baidu": s_baidu,
    "meituan": s_meituan,
    "netease": s_netease,
    "jd": s_jd,
    "kuaishou": s_kuaishou,
}


# ── 首页与 robots ──────────────────────────────────────────────────────


def probe_home(client: httpx.Client, report: CompanyReport) -> None:
    resp = client.get(report.careers)
    report.home_status = resp.status_code
    report.final_host = urlsplit(str(resp.url)).hostname or ""
    haystack = f"{resp.url} {resp.text[:200_000]}"
    report.platform = next(
        (name for name, marks in PLATFORMS.items() if any(m in haystack for m in marks)), ""
    )
    # 正文几乎为空、只有挂载点：前端渲染，岗位数据走接口
    body = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", "", resp.text, flags=re.S)
    report.spa = len(body.strip()) < 400


def probe_robots(client: httpx.Client, report: CompanyReport) -> None:
    parts = urlsplit(report.careers)
    resp = client.get(f"{parts.scheme}://{parts.hostname}/robots.txt")
    if resp.status_code != 200 or "disallow" not in resp.text.lower():
        report.robots = f"无限制（HTTP {resp.status_code}）"
        return
    disallows: list[str] = []
    applies = False
    for raw in resp.text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.lower().startswith("user-agent:"):
            applies = line.split(":", 1)[1].strip() == "*"
        elif applies and line.lower().startswith("disallow:"):
            disallows.append(line.split(":", 1)[1].strip())
    if "/" in disallows:
        report.robots = "整站禁止通用爬虫"
    elif any(d.startswith("/api") for d in disallows):
        report.robots = "禁止 /api"
    elif disallows:
        report.robots = f"部分禁止（{len(disallows)} 条）"
    else:
        report.robots = "无限制"


# ── 主流程 ─────────────────────────────────────────────────────────────


def probe_company(
    entry: dict, keywords: tuple[str, ...] = KEYWORDS, *, api_only: bool = False
) -> CompanyReport:
    report = CompanyReport(name=entry["name"], careers=entry["careers"], api=entry.get("api") or "")
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"}
    with httpx.Client(headers=headers, timeout=TIMEOUT, follow_redirects=True) as client:
        for step in () if api_only else (probe_home, probe_robots):
            try:
                step(client, report)
            except httpx.HTTPError as exc:
                report.error += f"{step.__name__}: {type(exc).__name__} "
            pause()
        if report.api:
            name, _, arg = report.api.partition(":")
            strategy = STRATEGIES[name]
            for kw in keywords:
                try:
                    report.results[kw] = strategy(client, kw, arg)
                except (httpx.HTTPError, KeyError, ValueError) as exc:
                    report.results[kw] = ApiResult(note=f"{type(exc).__name__}: {exc}"[:160])
                pause()
    return report


def cell_for(result: ApiResult | None) -> str:
    if result is None:
        return "—"
    if result.titles:
        hits = sum(1 for t in result.titles if RELEVANT.search(t))
        return f"✅ {result.total}（前 {len(result.titles)} 条里 {hits} 条相关）"
    if result.json_ok:
        return f"⚠️ JSON 无岗位（HTTP {result.status}）"
    return f"❌ HTTP {result.status}" if result.status else "❌ 请求失败"


def render(reports: list[CompanyReport], keywords: tuple[str, ...] = KEYWORDS) -> str:
    lines = [
        "# 社招可行性探测报告",
        "",
        f"关键词：{' / '.join(keywords)}；每次取 {PAGE_SIZE} 条；UA：`{USER_AGENT}`",
        "",
        "| 公司 | 首页 | 托管平台 | 前端渲染 | robots.txt | 接口策略 | " + " | ".join(keywords) + " |",
        "|---|---|---|---|---|---|" + "---|" * len(keywords),
    ]
    for r in reports:
        home = f"{r.home_status}" if r.home_status else "失败"
        if r.final_host and r.final_host not in r.careers:
            home += f" → {r.final_host}"
        lines.append(
            f"| {r.name} | {home} | {r.platform or '—'} | {'是' if r.spa else '否'} | "
            f"{r.robots or '—'} | {r.api or '—'} | "
            + " | ".join(cell_for(r.results.get(kw)) for kw in keywords)
            + " |"
        )
    lines += ["", "## 明细", ""]
    for r in reports:
        if not r.results and not r.error:
            continue
        lines.append(f"### {r.name}")
        if r.error:
            lines.append(f"- 错误：{r.error.strip()}")
        for kw, res in r.results.items():
            sample = "、".join(res.titles[:5]) or "—"
            lines.append(f"- 「{kw}」HTTP {res.status} · 总数 {res.total} · 样例：{sample}")
            if res.note:
                lines.append(f"  - 备注：{res.note}")
        lines.append("")
    lines += render_dates(reports)
    return "\n".join(lines)


def render_dates(reports: list[CompanyReport]) -> list[str]:
    """每家接口返回的岗位里有没有发布 / 更新时间，以及这些岗位有多旧。"""
    lines = ["## 发布 / 更新时间", ""]
    for r in reports:
        # 两个关键词常搜到同一批岗位，去重后再统计
        unique: dict[str, dict] = {}
        for res in r.results.values():
            for job in res.jobs:
                unique.setdefault(json.dumps(job, ensure_ascii=False, sort_keys=True), job)
        jobs = list(unique.values())
        if not jobs:
            continue
        lines.append(f"### {r.name}（{len(jobs)} 条岗位）")
        lines.append("- 岗位对象的字段：" + "、".join(list(jobs[0].keys())[:50]))
        fields = [date_fields(job) for job in jobs]
        coverage: dict[str, int] = {}
        for found in fields:
            for key in found:
                coverage[key] = coverage.get(key, 0) + 1
        if not coverage:
            lines.append("- 列表接口里**没有**能解析的时间字段")
            lines.append("")
            continue
        for key, count in sorted(coverage.items(), key=lambda kv: -kv[1]):
            days = sorted(f[key] for f in fields if key in f)
            ages = [age_days(d) for d in days]
            fresh30 = sum(1 for a in ages if a <= 30)
            fresh90 = sum(1 for a in ages if a <= 90)
            lines.append(
                f"- `{key}`：{count}/{len(jobs)} 条有；最早 {days[0]}，最新 {days[-1]}；"
                f"30 天内 {fresh30} 条、90 天内 {fresh90} 条、更早 {len(ages) - fresh90} 条"
            )
        # 字段名像时间、但值认不出来的（空值、别的写法），原样列几条供人工判断
        raw: dict[str, list[str]] = {}
        for job, found in zip(jobs, fields):
            for key, value in job.items():
                if DATE_KEY.search(str(key)) and key not in found and len(raw.setdefault(key, [])) < 3:
                    raw[key].append(json.dumps(value, ensure_ascii=False)[:40])
        for key, values in raw.items():
            lines.append(f"- `{key}` 未解析，原值：{' / '.join(values)}")
        for job, found in list(zip(jobs, fields))[:4]:
            title = next((str(job[k]) for k in TITLE_KEYS if isinstance(job.get(k), str)), "?")
            stamps = "，".join(f"{k}={v}" for k, v in found.items()) or "无"
            lines.append(f"  - 样例：{title[:30]} → {stamps}")
        lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="社招可行性探测")
    parser.add_argument("--only", action="append", default=[], help="只测指定公司（可重复）")
    parser.add_argument("--keyword", action="append", default=[], help="搜索关键词（可重复，默认两个）")
    parser.add_argument("--api-only", action="store_true", help="只测有接口策略的公司，跳过首页与 robots")
    args = parser.parse_args()

    entries = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["companies"]
    if args.only:
        entries = [e for e in entries if e["name"] in args.only]
    if args.api_only:
        entries = [e for e in entries if e.get("api")]
    keywords = tuple(args.keyword) or KEYWORDS

    reports = []
    for entry in entries:
        print(f"… {entry['name']}", file=sys.stderr, flush=True)
        reports.append(probe_company(entry, keywords, api_only=args.api_only))

    text = render(reports, keywords)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
