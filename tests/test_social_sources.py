"""用研社招：各家岗位整理、相关性筛选、同步流程（不联网）。

样例来自 2026-10-28 的探测（scripts/probe_job_samples.py），长文本截断过。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from uxhot.social.sources import ADAPTERS, AdapterError, Company, clean, cookie, parse, to_date
from uxhot.social.sync import TZ, SocialConfig, fetch_company, is_relevant, load_social_config, sync
from uxhot.social.window import Job

SAMPLES = json.loads((Path(__file__).parent / "fixtures" / "social_samples.json").read_text(encoding="utf-8"))
CFG = load_social_config()
COMPANIES = {c.key: c for c in CFG.companies}


def norm(key: str, index: int = 0) -> Job | None:
    company = COMPANIES[key]
    return ADAPTERS[company.adapter].normalize(company, SAMPLES[key][index])


def test_config_loads_and_every_company_has_an_adapter():
    assert len(CFG.companies) == 11
    assert all(c.adapter in ADAPTERS for c in CFG.companies)
    assert CFG.window.admitDays == 30 and CFG.window.keepDays == 90


@pytest.mark.parametrize(
    ("key", "jid", "title", "url", "kind", "posted", "cities"),
    [
        ("tencent", "tencent-2112095379343454208", "魔方市场用户研究经理",
         "https://careers.tencent.com/jobdesc.html?postId=2112095379343454208", "update", "2026-10-19", ["深圳"]),
        ("bytedance", "bytedance-7637726737113975045", "用户研究AI Agent产品-抖音",
         "https://jobs.bytedance.com/experienced/position/7637726737113975045/detail", "publish", "2026-05-09", ["深圳"]),
        ("xiaomi", None, None, "https://xiaomi.jobs.f.mioffice.cn/index/position/", "publish", None, None),
        ("alibaba", "alibaba-100020840001", "千问事业部-高级用户体验研究专员-北京/杭州",
         "https://talent.alibaba.com/off-campus/position-detail?positionId=100020840001", "publish", "2026-10-28",
         ["北京", "杭州"]),
        ("baidu", "baidu-f7ae2310-4637-4ed1-be76-50fc744df6bd", "用户研究",
         "https://talent.baidu.com/jobs/detail/SOCIAL/f7ae2310-4637-4ed1-be76-50fc744df6bd", "publish",
         "2024-07-08", ["北京市"]),
        ("meituan", "meituan-4663364114", "用户研究专家（骑手生态）",
         "https://zhaopin.meituan.com/web/position/detail?jobUnionId=4663364114&highlightType=social",
         "update", "2026-10-28", ["北京市"]),
        ("netease", "netease-78151", "用户研究实习生",
         "https://hr.163.com/job-detail.html?id=78151", "update", None, ["北京市"]),
    ],
)
def test_normalize_samples(key, jid, title, url, kind, posted, cities):
    job = norm(key)
    assert job is not None
    assert job.id == (jid or job.id) and job.id.startswith(f"{key}-")
    assert job.title == (title or job.title)
    assert job.url.startswith(url)
    assert job.dateKind == kind
    if posted:
        assert job.postedAt == posted
    if cities:
        assert job.cities == cities
    assert job.company == COMPANIES[key].name
    assert job.duty  # 每家都有职责文本


def test_details_per_company():
    tencent = norm("tencent")
    assert tencent.department == "IEG · UC-手游APP" and tencent.experience == "一年以上工作经验"
    assert "\r" not in tencent.duty
    alibaba = norm("alibaba")
    assert alibaba.experience == "3 年以上" and alibaba.requirement
    meituan = norm("meituan")
    assert meituan.department == "核心本地商业-到家履约平台" and meituan.requirement
    assert norm("baidu").department == "技术中台群组"
    assert norm("netease").department == "传媒事业群 · 网易传媒"


def test_atsx_keeps_only_experienced_hires():
    raw = json.loads(json.dumps(SAMPLES["poizon"][0]))
    company = COMPANIES["poizon"]
    assert ADAPTERS["atsx"].normalize(company, raw) is not None
    raw["recruit_type"]["parent"]["name"] = "校招"
    assert ADAPTERS["atsx"].normalize(company, raw) is None


def test_job_without_date_is_skipped():
    raw = dict(SAMPLES["tencent"][0], LastUpdateTime="")
    assert ADAPTERS["tencent"].normalize(COMPANIES["tencent"], raw) is None


def test_to_date_and_clean():
    assert to_date(1793153243000) == "2026-10-28"       # 毫秒，北京时间
    assert to_date(1793153243) == "2026-10-28"
    assert to_date("2026年10月19日") == "2026-10-19"
    assert to_date("2026-7-1 10:00") == "2026-07-01"
    assert to_date("2026-02-30") is None
    assert to_date(None) is None and to_date(0) is None and to_date(True) is None
    assert clean("1.a\r\n\r\n\r\n2.b  \n") == "1.a\n\n2.b"


def _resp(doc, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=doc)


def test_parse_finds_list_and_rejects_surprises():
    total, jobs = parse(_resp({"Code": 200, "Data": {"Count": 2, "Posts": [
        {"RecruitPostName": "a", "PostId": "1"}, {"RecruitPostName": "b", "PostId": "2"}]}}),
        "RecruitPostName", "PostId")
    assert total == 2 and [j["PostId"] for j in jobs] == ["1", "2"]
    assert parse(_resp({"Code": 200, "Data": {"Count": 0, "Posts": None}}), "RecruitPostName", "PostId") == (0, [])
    with pytest.raises(AdapterError):
        parse(_resp([]), "name", "id")                                # 京东那种「什么都没有」
    with pytest.raises(AdapterError):
        parse(_resp({"code": -1, "message": "系统错误"}), "name", "id")
    with pytest.raises(AdapterError):
        parse(_resp({}, status=403), "name", "id")


@pytest.mark.parametrize(
    ("title", "ok"),
    [
        ("用户研究专家（骑手生态）", True), ("用户分析研究专家", True), ("游戏用户体验研究专家", True),
        ("用户体验洞察与研究", True), ("市场与用户研究经理-数据分析方向", True), ("Senior UX Researcher", True),
        ("用户研究实习生", False), ("政策研究专家", False), ("安全研究员", False), ("用户增长运营", False),
        ("商业洞察经理/主管", False), ("资深交互设计师", False),
    ],
)
def test_relevance(title, ok):
    assert is_relevant(title, CFG) is ok


def _job(jid: str, title: str = "用户研究员", company: str = "腾讯", posted: str = "2026-10-27") -> Job:
    return Job(id=jid, company=company, title=title, url="https://x", postedAt=posted)


def test_fetch_company_pages_until_nothing_relevant(monkeypatch):
    calls: list[tuple[str, int]] = []
    pages = {
        1: [{"t": "用户研究员", "i": 1}, {"t": "政策研究专家", "i": 2}],
        2: [{"t": "用户研究专家", "i": 3}, {"t": "用户研究专家", "i": 3}],
        3: [{"t": "安全研究员", "i": 4}, {"t": "战略研究", "i": 5}],
        4: [{"t": "用户研究员", "i": 6}, {"t": "用户研究员", "i": 7}],
    }

    def search(client, company, keyword, page, size):
        calls.append((keyword, page))
        return 100, pages[page]

    def normalize(company, raw):
        return _job(f"t-{raw['i']}", raw["t"])

    monkeypatch.setitem(ADAPTERS, "fake", ADAPTERS["tencent"]._replace(search=search, normalize=normalize))
    monkeypatch.setattr("uxhot.social.sync.PAUSE_SECONDS", 0)
    cfg = CFG.model_copy(update={"keywords": ["用户研究"], "pageSize": 2})
    found = fetch_company(None, Company(key="t", name="腾讯", careers="https://x", adapter="fake"), cfg)
    assert calls == [("用户研究", 1), ("用户研究", 2), ("用户研究", 3)]   # 第 3 页没有相关的就停
    assert sorted(j.id for j in found) == ["t-1", "t-3"]


class _NullClient:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _cfg(*names: str) -> SocialConfig:
    companies = [Company(key=f"c{i}", name=n, careers="https://x", adapter="tencent") for i, n in enumerate(names)]
    return CFG.model_copy(update={"companies": companies})


def test_sync_writes_state_and_content(tmp_path):
    now = datetime(2026, 10, 28, 9, 0, tzinfo=TZ)
    state, content = tmp_path / "jobs.json", tmp_path / "social.json"

    def fetch(client, company, cfg):
        if company.name == "百度":
            raise AdapterError("没找到岗位列表")
        return [_job("t-1"), _job("t-2", posted="2026-08-01")]

    report = sync(_cfg("腾讯", "百度"), now=now, state_path=state, content_path=content,
                  fetch=fetch, client_factory=_NullClient)
    assert report.ok == ["腾讯"] and list(report.failed) == ["百度"]
    assert report.window.added == ["t-1"] and report.window.rejected == ["t-2"]
    doc = json.loads(content.read_text(encoding="utf-8"))
    assert doc["window"] == {"admitDays": 30, "keepDays": 90}
    assert [j["id"] for j in doc["jobs"]] == ["t-1"]
    assert doc["jobs"][0]["expiresAt"] == "2027-01-26"
    assert "misses" not in doc["jobs"][0]
    by_name = {c["name"]: c for c in doc["companies"]}
    assert by_name["腾讯"]["ok"] and by_name["腾讯"]["jobCount"] == 1
    assert not by_name["百度"]["ok"] and by_name["百度"]["lastOkAt"] is None

    # 20 小时内再跑：跳过，不抓
    def boom(*_):
        raise AssertionError("不该抓取")

    again = sync(_cfg("腾讯", "百度"), now=now + timedelta(hours=5), state_path=state, content_path=content,
                 fetch=boom, client_factory=_NullClient)
    assert again.skipped and again.total == 1


def test_sync_all_failed_writes_nothing(tmp_path):
    state, content = tmp_path / "jobs.json", tmp_path / "social.json"

    def fetch(client, company, cfg):
        raise httpx.ConnectError("断网")

    report = sync(_cfg("腾讯"), now=datetime(2026, 10, 28, tzinfo=TZ), state_path=state,
                  content_path=content, fetch=fetch, client_factory=_NullClient)
    assert list(report.failed) == ["腾讯"] and not state.exists() and not content.exists()


def test_cookie_picks_the_right_site():
    """同一个客户端里有好几家的同名 cookie，且常设在带点的上级域名上。"""
    client = httpx.Client()
    client.cookies.set("atsx-csrf-token", "byte%3D1", domain=".jobs.bytedance.com")
    client.cookies.set("atsx-csrf-token", "nio", domain="nio.jobs.feishu.cn")
    client.cookies.set("XSRF-TOKEN", "ali", domain="talent.alibaba.com")
    assert cookie(client, "atsx-csrf-token", "jobs.bytedance.com") == "byte=1"
    assert cookie(client, "atsx-csrf-token", "nio.jobs.feishu.cn") == "nio"
    assert cookie(client, "atsx-csrf-token", "li.jobs.feishu.cn") == ""
    assert cookie(client, "XSRF-TOKEN", "talent.alibaba.com") == "ali"
    client.close()
