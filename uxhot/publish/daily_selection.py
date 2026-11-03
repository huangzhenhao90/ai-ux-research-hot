"""按首页展示的北京时间自然日决定公开精选。保留原始候选，后续抓取可重新计算。"""

from collections import defaultdict
from datetime import date
from typing import Iterable

from uxhot.collect.dates import parse_tz
from uxhot.config import ConfigBundle
from uxhot.models import Item, Status
from uxhot.publish.build_site_data import (
    dedupe_by_id, display_source, item_time, sort_items, source_name_map,
)


def daily_selection(items: Iterable[Item], config: ConfigBundle) -> list[Item]:
    rows = dedupe_by_id(items)
    names = source_name_map(config)
    tz = parse_tz(config.site.timezone)
    days: dict[date, dict[str, list[Item]]] = defaultdict(lambda: defaultdict(list))
    for item in rows:
        if item.is_selected:
            day = item_time(item).astimezone(tz).date()
            source = display_source(item, names).strip().casefold()
            if source.split()[:1] == ["arxiv"]:
                source = "arxiv"
            days[day][source].append(item)

    excluded = set()
    for sources in days.values():
        total = sum(len(group) for group in sources.values())
        for group in sources.values():
            # 严格少于一半：本来源最多保留「其他来源合计 - 1」。
            # 只有两个来源时，两者不可能同时达标，当天不出精选。
            limit = max(0, total - len(group) - 1) if len(sources) >= 3 else 0
            if len(group) > limit:
                excluded.update(item.id for item in sort_items(group)[limit:])

    return [
        item.model_copy(update={"status": Status.LISTED, "selectedAt": None})
        if item.id in excluded else item
        for item in rows
    ]
