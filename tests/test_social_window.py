"""用研社招滑动窗口（D17）：收 30 天、留 90 天、刷新不重新计时、下线才拿掉。"""

from __future__ import annotations

from datetime import date, timedelta

from uxhot.social.window import Job, Window, apply_window

TODAY = date(2026, 11, 1)
W = Window(admitDays=30, keepDays=90, missLimit=3)


def ago(days: int, today: date = TODAY) -> str:
    return (today - timedelta(days=days)).isoformat()


def job(jid: str, posted_days_ago: int, company: str = "腾讯", today: date = TODAY, **kw) -> Job:
    return Job(id=jid, company=company, title=kw.pop("title", jid), url=f"https://x/{jid}",
               postedAt=ago(posted_days_ago, today), **kw)


def test_cold_start_admits_only_last_30_days():
    fetched = {"腾讯": [job("a", 0), job("b", 30), job("c", 31), job("d", 200)]}
    kept, retired, res = apply_window([], {}, fetched, TODAY, W)
    assert [j.id for j in kept] == ["a", "b"]
    assert sorted(res.rejected) == ["c", "d"]
    assert set(retired) == {"c", "d"}
    a = kept[0]
    assert a.since == a.postedAt == TODAY.isoformat()
    assert a.firstSeen == a.lastSeen == TODAY.isoformat()


def test_window_grows_to_90_days_then_slides():
    """上线时收 30 天内的；之后同一批岗位留到满 90 天，第 91 天移出。"""
    kept, retired, _ = apply_window([], {}, {"腾讯": [job("a", 30)]}, TODAY, W)
    for days_later in (30, 60):
        day = TODAY + timedelta(days=days_later)
        kept, retired, _ = apply_window(kept, retired, {"腾讯": [job("a", 30)]}, day, W)
        assert [j.id for j in kept] == ["a"], days_later
    assert kept[0].since == ago(30)

    day = TODAY + timedelta(days=61)          # 起算日之后第 91 天
    kept, retired, res = apply_window(kept, retired, {"腾讯": [job("a", 30)]}, day, W)
    assert kept == [] and res.expired == ["a"] and "a" in retired


def test_refresh_does_not_restart_the_clock():
    """腾讯 / 网易 / 美团只给更新日期：HR 刷新后日期变新，但起算日不动。"""
    kept, retired, _ = apply_window([], {}, {"腾讯": [job("a", 10, dateKind="update")]}, TODAY, W)
    later = TODAY + timedelta(days=70)
    refreshed = job("a", 0, today=later, dateKind="update", title="改了名")
    kept, retired, _ = apply_window(kept, retired, {"腾讯": [refreshed]}, later, W)
    assert kept[0].title == "改了名"              # 内容跟官网走
    assert kept[0].postedAt == later.isoformat()
    assert kept[0].since == ago(10)               # 起算日不变
    kept, retired, res = apply_window(kept, retired, {"腾讯": [refreshed]}, TODAY + timedelta(days=81), W)
    assert kept == [] and res.expired == ["a"]


def test_retired_jobs_are_not_readmitted_after_refresh():
    _, retired, _ = apply_window([], {}, {"腾讯": [job("old", 120, dateKind="update")]}, TODAY, W)
    later = TODAY + timedelta(days=7)
    kept, retired, res = apply_window([], retired, {"腾讯": [job("old", 0, today=later, dateKind="update")]}, later, W)
    assert kept == [] and res.added == []


def test_offline_after_consecutive_misses():
    kept, retired, _ = apply_window([], {}, {"腾讯": [job("a", 1), job("b", 1)]}, TODAY, W)
    for n in (1, 2):
        kept, retired, res = apply_window(kept, retired, {"腾讯": [job("a", 1)]}, TODAY + timedelta(days=n), W)
        assert {j.id for j in kept} == {"a", "b"}
    assert next(j for j in kept if j.id == "b").misses == 2
    kept, retired, res = apply_window(kept, retired, {"腾讯": [job("a", 1)]}, TODAY + timedelta(days=3), W)
    assert [j.id for j in kept] == ["a"] and res.offline == ["b"]
    # 下线不进 retired：重新上架且仍在 30 天内的话可以再收
    assert "b" not in retired


def test_seen_again_resets_misses():
    kept, retired, _ = apply_window([], {}, {"腾讯": [job("a", 1)]}, TODAY, W)
    kept, retired, _ = apply_window(kept, retired, {"腾讯": []}, TODAY + timedelta(days=1), W)
    assert kept[0].misses == 1
    kept, retired, _ = apply_window(kept, retired, {"腾讯": [job("a", 1)]}, TODAY + timedelta(days=2), W)
    assert kept[0].misses == 0


def test_failed_company_keeps_its_jobs():
    """这次没抓成的公司（不在 fetched 里）不算没搜到，岗位原样保留，只照常过期。"""
    kept, retired, _ = apply_window(
        [], {}, {"腾讯": [job("t", 1)], "百度": [job("b", 1, company="百度")]}, TODAY, W
    )
    for n in range(1, 5):
        kept, retired, res = apply_window(kept, retired, {"腾讯": [job("t", 1)]}, TODAY + timedelta(days=n), W)
    assert {j.id for j in kept} == {"t", "b"}
    assert next(j for j in kept if j.id == "b").misses == 0
    kept, retired, res = apply_window(kept, retired, {}, TODAY + timedelta(days=91), W)
    assert kept == [] and sorted(res.expired) == ["b", "t"]


def test_retired_memory_is_pruned():
    old = {"x": (TODAY - timedelta(days=400)).isoformat(), "y": ago(10)}
    _, retired, _ = apply_window([], old, {}, TODAY, W)
    assert retired == {"y": ago(10)}


def test_sorted_newest_first_and_input_not_mutated():
    jobs_in = [job("a", 5), job("b", 1), job("c", 3)]
    kept, retired, _ = apply_window([], {}, {"腾讯": jobs_in}, TODAY, W)
    assert [j.id for j in kept] == ["b", "c", "a"]
    assert all(j.since == "" for j in jobs_in)
    _, _, _ = apply_window(kept, retired, {"腾讯": []}, TODAY + timedelta(days=1), W)
    assert all(j.misses == 0 for j in kept)
