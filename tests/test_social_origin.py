"""用研社招的来源标注（官网 / Boss 直聘 / 社群）与手动收录（DECISIONS D20）。"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from uxhot.social.manual import ManualError, ManualJob, load_manual, merge_manual
from uxhot.social.origin import (
    BOSS,
    COMMUNITY,
    OFFICIAL,
    cities_overlap,
    collapse_origins,
    same_job,
    same_title,
)
from uxhot.social.public import PUBLIC_JOB_FIELDS, manual_job, official_job
from uxhot.social.sync import TZ, build_content, load_social_config, sync
from uxhot.social.window import Job, Window

TODAY = date(2026, 11, 1)
W = Window(admitDays=30, keepDays=90, missLimit=3)


# ── 标注规则 ───────────────────────────────────────────────────────────


def test_official_and_boss_collapse_to_official_only():
    assert collapse_origins([OFFICIAL, BOSS]) == [OFFICIAL]
    assert collapse_origins([BOSS, OFFICIAL]) == [OFFICIAL]


def test_other_combinations_keep_every_origin_in_fixed_order():
    assert collapse_origins([COMMUNITY, OFFICIAL]) == [OFFICIAL, COMMUNITY]
    assert collapse_origins([COMMUNITY, BOSS]) == [BOSS, COMMUNITY]
    # 官网 + Boss + 社群：Boss 并进官网，社群仍然标出
    assert collapse_origins([BOSS, COMMUNITY, OFFICIAL]) == [OFFICIAL, COMMUNITY]
    assert collapse_origins([BOSS, BOSS]) == [BOSS]


def test_unknown_origin_is_rejected():
    with pytest.raises(ValueError, match="未知的岗位来源"):
        collapse_origins(["official", "linkedin"])


# ── 同一个岗位怎么认 ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("用户研究专家", "用户研究专家", True),
        ("用户研究专家（骑手生态）", "用户研究专家(骑手生态)", True),               # 全角 / 半角括号
        ("Senior UX Researcher", "senior  ux researcher", True),
        # 官网把事业部和城市拼进岗位名，Boss 上写的是中间那段
        ("千问事业部-高级用户体验研究专员-北京/杭州", "高级用户体验研究专员", True),
        ("高级用户体验研究专员", "千问事业部-高级用户体验研究专员-北京/杭州", True),
        # 资历不同、生态不同、差一个字母：是不同的岗位，宁可不并
        ("用户研究", "用户研究专家", False),
        ("用户研究专家（骑手生态）", "用户研究专家（商家生态）", False),
        ("高级用户研究专家（骑手生态A）", "高级用户研究专家（骑手生态B）", False),
        # 太短的片段不算数
        ("体验-研究", "研究", False),
        ("", "用户研究", False),
    ],
)
def test_same_title(a, b, same):
    assert same_title(a, b) is same


def test_same_job_needs_same_company_and_overlapping_cities():
    def ident(company, title, cities):
        return SimpleNamespace(company=company, title=title, cities=cities)

    base = ident("美团", "用户研究专家", ["北京"])
    assert same_job(base, ident("美团", "用户研究专家", ["北京", "上海"]))
    assert not same_job(base, ident("美团", "用户研究专家", ["上海"]))
    assert not same_job(base, ident("腾讯", "用户研究专家", ["北京"]))
    # 有一边没写城市就不拿城市排除
    assert same_job(base, ident("美团", "用户研究专家", []))
    assert cities_overlap(["北京市"], ["北京"])


# ── manual.yaml ───────────────────────────────────────────────────────


def write_manual(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "manual.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_manual_missing_or_empty_file_is_no_jobs(tmp_path):
    assert load_manual(tmp_path / "nope.yaml") == []
    assert load_manual(write_manual(tmp_path, "")) == []
    assert load_manual(write_manual(tmp_path, "jobs: []\n")) == []


def test_load_manual_parses_and_normalizes(tmp_path):
    path = write_manual(tmp_path, """
jobs:
  - source: boss
    company: " 滴滴 "
    title: 用户体验研究专家
    addedAt: 2026-10-29
    cities: [北京市, 北京, " 上海 "]
    salary: 30-50K·15薪
    url: ""
    internal: 截图 boss-1029-03.png
""")
    (job,) = load_manual(path)
    assert job.company == "滴滴" and job.cities == ["北京", "上海"]
    assert job.url is None and job.salary == "30-50K·15薪"
    assert job.addedAt == date(2026, 10, 29)
    # 没写 id：按 来源 + 公司 + 岗位名 + 收录日 生成，稳定
    assert job.job_id.startswith("boss-") and job.job_id == load_manual(path)[0].job_id


@pytest.mark.parametrize(
    ("body", "needle"),
    [
        ("jobs:\n  - {source: linkedin, company: 滴滴, title: x, addedAt: 2026-10-29}\n", "source"),
        ("jobs:\n  - {source: boss, company: 滴滴, title: x, addedAt: 2026-10-29, postAt: 2026-10-01}\n", "postAt"),
        ("jobs:\n  - {source: boss, company: '', title: x, addedAt: 2026-10-29}\n", "company"),
        ("jobs:\n  - {source: boss, company: 滴滴, title: x}\n", "addedAt"),
        ("jobs:\n  - {source: boss, company: 滴滴, title: x, addedAt: 2026-10-29, url: 'javascript:alert(1)'}\n", "url"),
        ("jobs:\n  - {source: boss, company: 滴滴, title: x, addedAt: 2026-10-29, id: '../x'}\n", "id"),
        ("jobs:\n  - {source: boss, company: 滴滴, title: x, addedAt: 2026-10-01, postedAt: 2026-10-29}\n", "postedAt"),
        ("jobs: 3\n", "列表"),
        ("jobz: []\n", "jobs"),
        ("jobs: [\n", "YAML"),
    ],
)
def test_load_manual_rejects_mistakes_with_a_readable_message(tmp_path, body, needle):
    with pytest.raises(ManualError, match=needle):
        load_manual(write_manual(tmp_path, body))


def test_load_manual_rejects_duplicate_ids(tmp_path):
    path = write_manual(tmp_path, """
jobs:
  - {id: a, source: boss, company: 滴滴, title: x, addedAt: 2026-10-29}
  - {id: a, source: community, company: 滴滴, title: y, addedAt: 2026-10-29}
""")
    with pytest.raises(ManualError, match="id 重复"):
        load_manual(path)


# ── 并入官网岗位 ──────────────────────────────────────────────────────


def official(jid: str, company: str, title: str, cities: list[str], since: date = TODAY) -> dict:
    job = Job(id=jid, company=company, title=title, url=f"https://x/{jid}", cities=cities,
              postedAt=since.isoformat(), since=since.isoformat(), firstSeen=since.isoformat(),
              lastSeen=since.isoformat())
    return official_job(job)


def manual(source: str = "boss", company: str = "美团", title: str = "用户研究专家（骑手生态）",
           added: date = TODAY, **kw) -> ManualJob:
    return ManualJob(source=source, company=company, title=title, addedAt=added, **kw)


def test_boss_job_that_is_also_on_the_official_site_is_labelled_official_only():
    officials = [official("meituan-1", "美团", "用户研究专家（骑手生态）", ["北京"])]
    jobs, report = merge_manual(officials, [manual("boss", cities=["北京"], salary="40-60K")], TODAY, W)
    assert [j["id"] for j in jobs] == ["meituan-1"]               # 不会多出一张 Boss 卡
    assert jobs[0]["origins"] == [OFFICIAL]
    assert jobs[0]["salary"] is None                               # 官网卡片不掺 Boss 的信息
    assert report.merged and not report.shown


def test_community_job_that_is_also_on_the_official_site_keeps_both_labels():
    officials = [official("meituan-1", "美团", "用户研究专家（骑手生态）", ["北京"])]
    jobs, _ = merge_manual(officials, [manual("community", cities=["北京"])], TODAY, W)
    assert jobs[0]["origins"] == [OFFICIAL, COMMUNITY]


def test_job_only_on_boss_stands_alone_with_its_own_label():
    jobs, report = merge_manual([], [manual("boss", company="滴滴", cities=["北京"], salary="30-50K")], TODAY, W)
    (job,) = jobs
    assert job["origins"] == [BOSS] and job["company"] == "滴滴" and job["salary"] == "30-50K"
    assert job["url"] is None and job["dateKind"] == "added" and job["since"] == TODAY.isoformat()
    assert report.shown == [job["id"]]


def test_boss_and_community_copies_of_the_same_job_become_one_card_with_both_labels():
    entries = [manual("boss", company="滴滴", cities=["北京"]), manual("community", company="滴滴", cities=["北京"])]
    jobs, report = merge_manual([], entries, TODAY, W)
    assert len(jobs) == 1 and jobs[0]["origins"] == [BOSS, COMMUNITY] and len(report.merged) == 1


def test_different_jobs_at_the_same_company_stay_separate():
    officials = [official("meituan-1", "美团", "用户研究专家（骑手生态）", ["北京"])]
    jobs, _ = merge_manual(officials, [manual("boss", title="用户研究专家（商家生态）", cities=["北京"])], TODAY, W)
    assert len(jobs) == 2


def test_official_id_forces_the_match_and_dangling_ids_are_reported():
    officials = [official("meituan-1", "美团", "用户研究专家（骑手生态）", ["北京"])]
    forced = manual("boss", title="骑手生态用研", cities=["北京"], officialId="meituan-1")
    jobs, _ = merge_manual(officials, [forced], TODAY, W)
    assert len(jobs) == 1 and jobs[0]["origins"] == [OFFICIAL]

    gone = manual("boss", title="骑手生态用研", cities=["北京"], officialId="meituan-404")
    jobs, report = merge_manual(officials, [gone], TODAY, W)
    assert len(jobs) == 2 and report.dangling == [gone.job_id]     # 指错了：当作没指，单独成卡


def test_manual_jobs_follow_the_same_retention_rules_as_official_ones():
    old_added = TODAY - timedelta(days=91)
    jobs, report = merge_manual([], [manual("boss", added=old_added)], TODAY, W)
    assert jobs == [] and len(report.expired) == 1

    still_in = manual("boss", added=TODAY - timedelta(days=90))
    jobs, _ = merge_manual([], [still_in], TODAY, W)
    assert len(jobs) == 1

    # 写了发布日期且收录时已经超过 30 天：常年挂着的岗位，不收
    stale = manual("community", added=TODAY, postedAt=TODAY - timedelta(days=31))
    jobs, report = merge_manual([], [stale], TODAY, W)
    assert jobs == [] and report.stale == [stale.job_id]

    fresh = manual("community", added=TODAY, postedAt=TODAY - timedelta(days=30))
    jobs, _ = merge_manual([], [fresh], TODAY, W)
    assert jobs[0]["dateKind"] == "publish" and jobs[0]["since"] == (TODAY - timedelta(days=30)).isoformat()


def test_future_added_date_is_an_error_not_a_silent_drop():
    with pytest.raises(ManualError, match="在今天之后"):
        merge_manual([], [manual("boss", added=TODAY + timedelta(days=1))], TODAY, W)


def test_a_manual_id_that_collides_with_an_official_job_is_an_error():
    officials = [official("meituan-1", "美团", "用户研究专家", ["北京"])]
    clash = manual("boss", company="滴滴", title="体验研究", id="meituan-1")
    with pytest.raises(ManualError, match="id 与已有岗位重复"):
        merge_manual(officials, [clash], TODAY, W)


def test_merge_does_not_mutate_its_input_and_sorts_newest_first():
    officials = [official("meituan-1", "美团", "用户研究专家（骑手生态）", ["北京"], since=TODAY - timedelta(days=5))]
    entries = [manual("community", cities=["北京"]), manual("boss", company="滴滴", title="体验研究", added=TODAY)]
    jobs, _ = merge_manual(officials, entries, TODAY, W)
    assert officials[0]["origins"] == [OFFICIAL]
    assert [j["company"] for j in jobs] == ["滴滴", "美团"]


# ── 发布字段白名单 ────────────────────────────────────────────────────


def test_public_jobs_have_exactly_the_whitelisted_fields_and_never_the_internal_note():
    job = Job(id="x-1", company="美团", title="t", url="https://x", postedAt="2026-10-28", since="2026-10-28",
              firstSeen="2026-10-28", lastSeen="2026-10-29", misses=2)
    entry = manual("boss", internal="某某分享的，截图 a.png", officialId="x-9")
    assert tuple(official_job(job)) == PUBLIC_JOB_FIELDS
    assert tuple(manual_job(entry)) == PUBLIC_JOB_FIELDS
    assert "某某" not in json.dumps(manual_job(entry), ensure_ascii=False)


# ── 接入同步流程 ──────────────────────────────────────────────────────


class _NullClient:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_sync_publishes_manual_jobs_and_rebuilds_content_even_when_the_crawl_is_skipped(tmp_path):
    cfg = load_social_config()
    cfg = cfg.model_copy(update={"companies": cfg.companies[:1]})            # 腾讯
    name = cfg.companies[0].name
    now = datetime(2026, 10, 29, 9, 0, tzinfo=TZ)
    state, content = tmp_path / "jobs.json", tmp_path / "social.json"
    manual_file = tmp_path / "manual.yaml"

    def fetch(client, company, cfg):
        return [Job(id="t-1", company=name, title="用户研究专家", url="https://x/t-1", cities=["深圳"],
                    postedAt="2026-10-28")]

    report = sync(cfg, now=now, state_path=state, content_path=content, manual_path=manual_file,
                  fetch=fetch, client_factory=_NullClient)
    doc = json.loads(content.read_text(encoding="utf-8"))
    assert [j["origins"] for j in doc["jobs"]] == [["official"]] and report.total == 1

    # 之后只改了 manual.yaml、官网这次不抓：页面数据照样更新
    manual_file.write_text(f"""
jobs:
  - {{source: boss, company: {name}, title: 用户研究专家, cities: [深圳], addedAt: 2026-10-29}}
  - {{source: community, company: 滴滴, title: 体验研究, addedAt: 2026-10-29, internal: 某某分享}}
""", encoding="utf-8")

    def boom(*_):
        raise AssertionError("不该抓取")

    again = sync(cfg, now=now + timedelta(hours=5), state_path=state, content_path=content,
                 manual_path=manual_file, fetch=boom, client_factory=_NullClient)
    assert again.skipped and again.total == 2
    doc = json.loads(content.read_text(encoding="utf-8"))
    by_id = {j["id"]: j for j in doc["jobs"]}
    assert by_id["t-1"]["origins"] == ["official"]                  # Boss 也有这条：只标官网
    (other,) = [j for j in doc["jobs"] if j["id"] != "t-1"]
    assert other["company"] == "滴滴" and other["origins"] == ["community"]
    assert "某某" not in content.read_text(encoding="utf-8")        # internal 不发布
    # 公司行的 jobCount 只数官网来源的岗位
    assert {c["name"]: c["jobCount"] for c in doc["companies"]} == {name: 1}


def test_a_broken_manual_file_stops_the_sync_before_anything_is_written(tmp_path):
    cfg = load_social_config()
    cfg = cfg.model_copy(update={"companies": cfg.companies[:1]})
    state, content = tmp_path / "jobs.json", tmp_path / "social.json"
    manual_file = tmp_path / "manual.yaml"
    manual_file.write_text("jobs:\n  - {source: boss, company: 滴滴, title: x}\n", encoding="utf-8")   # 缺 addedAt

    def fetch(client, company, cfg):
        return [Job(id="t-1", company=cfg.companies[0].name, title="用户研究专家", url="https://x",
                    postedAt="2026-10-28")]

    with pytest.raises(ManualError, match="addedAt"):
        sync(cfg, now=datetime(2026, 10, 29, 9, 0, tzinfo=TZ), state_path=state, content_path=content,
             manual_path=manual_file, fetch=fetch, client_factory=_NullClient)
    # 页面数据与状态都没动：沿用上一版，等人修 manual.yaml
    assert not state.exists() and not content.exists()


def test_build_content_without_manual_jobs_is_official_only(tmp_path):
    cfg = load_social_config()
    from uxhot.social.sync import State

    state = State(jobs=[Job(id="a", company=cfg.companies[0].name, title="t", url="https://x",
                            postedAt="2026-10-28", since="2026-10-28", firstSeen="2026-10-28")])
    doc = build_content(state, cfg)
    assert doc["jobs"][0]["origins"] == ["official"]


def test_committed_manual_file_is_valid():
    """仓库里那份 data/social/manual.yaml 写错了，要在合并前就报出来，而不是等到定时任务。"""
    from uxhot.social.sync import MANUAL_PATH

    load_manual(MANUAL_PATH)
