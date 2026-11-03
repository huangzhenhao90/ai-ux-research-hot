import json
from datetime import datetime, timedelta, timezone

import feedparser

from tests.fixtures.publish_items import make_item
from uxhot.config import load_config
from uxhot.models import Status
from uxhot.publish import publish_candidates
from uxhot.publish.daily_selection import daily_selection


def test_quota_uses_beijing_midnight_and_reconsiders_candidates():
    before = datetime(2026, 11, 2, 15, 59, tzinfo=timezone.utc)
    after = before + timedelta(minutes=1)
    rows = [make_item(i, sourceId=s, published=t, avgScore=i)
            for i, (s, t) in enumerate([("A", before), ("B", before), ("C", before),
                                        ("A", after), ("A", after), ("B", after)])]
    cfg = load_config()
    assert [r.is_selected for r in daily_selection(rows, cfg)] == [True] * 3 + [False] * 3
    rows.append(make_item(6, sourceId="C", published=after))
    # 当天有了第三个来源，A 的两条中只保留得分更高的那条。
    assert [r.is_selected for r in daily_selection(rows, cfg)] == [True] * 3 + [False, True, True, True]
    assert all(r.is_selected for r in rows)


def test_overflow_is_listed_in_public_data_and_absent_from_rss(tmp_path):
    rows = [make_item(i, sourceId=s, avgScore=i) for i, s in enumerate(["listen-labs"] * 4 + ["b", "c"])]
    rows += [make_item(6, sourceId="other", status=Status.LISTED)]
    result = publish_candidates(rows, load_config(), public_dir=tmp_path)
    assert result.counts["selected"] == 3
    all_items = json.loads((tmp_path / "data/all/2026-10.json").read_text())["items"]
    assert len(all_items) == len(rows)
    assert {r["id"] for r in all_items if r["status"] == "selected"} == {r.id for r in rows[3:6]}
    assert {r.link for r in feedparser.parse(str(tmp_path / "rss.xml")).entries} == {r.url for r in rows[3:6]}
    for item in rows[:3]:
        assert json.loads((tmp_path / f"data/items/{item.id}.json").read_text())["status"] == "listed"


def test_arxiv_aliases_share_one_quota():
    rows = [make_item(i, avgScore=i) for i in range(4)]
    for row, venue in zip(rows, ["arXiv", "arXiv cs.HC", "CHI", "UIST"]):
        row.venue = venue
    assert [r.is_selected for r in daily_selection(rows, load_config())] == [False, True, True, True]
