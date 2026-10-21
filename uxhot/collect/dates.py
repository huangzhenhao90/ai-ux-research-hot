"""日期解析与时区处理。

三条硬要求（计划 §5 验收）：

1. **无时区的日期按信源时区解析**（默认 `+08:00`）。
2. **结果不随运行机器时区变化** —— 内部一律先转 UTC 再比较。
3. **未来日期要当心**：`ur-ai-papers` 的论文 `date` 会到 2027-01（期刊提前标期号），
   若按「刚发布」处理会全部涌上首页。这类日期视为不可信，按「无可信日期」处理。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import parser as dateutil_parser

DEFAULT_TZ = "+08:00"

# 允许的「未来」容差：跨时区或轻微时钟偏差可能让今天发布的文章看起来在未来
DEFAULT_MAX_FUTURE_DAYS = 1


class DateIssue(str):
    """解析结果里的异常说明（用于 errors 与日志）。"""


def parse_tz(value: str | None):
    """把 `+08:00` 或 `Asia/Shanghai` 解析成 tzinfo。"""
    if not value:
        return timezone(timedelta(hours=8))
    value = value.strip()
    m = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", value)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        delta = timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
        return timezone(sign * delta)
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return timezone(timedelta(hours=8))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_date(raw: str | None, source_tz: str | None = DEFAULT_TZ) -> datetime | None:
    """解析单个日期字符串成 tz-aware datetime（UTC 之外不转换，只补时区）。

    支持：ISO 8601（带或不带时区）、RFC 2822、`2026-10`（只有年月，补 1 号）。
    解析不出来返回 None。
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    tz = parse_tz(source_tz)

    # 只有年月：2026-10 / 2026-10-01 之外的简写
    m = re.fullmatch(r"(\d{4})-(\d{2})", text)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), 1, tzinfo=tz)

    # 只有年
    if re.fullmatch(r"\d{4}", text):
        return datetime(int(text), 1, 1, tzinfo=tz)

    try:
        dt = dateutil_parser.parse(text, fuzzy=False)
    except (ValueError, OverflowError, TypeError):
        try:
            dt = dateutil_parser.parse(text, fuzzy=True)
        except (ValueError, OverflowError, TypeError):
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


def parse_feed_time(entry_struct, source_tz: str | None = DEFAULT_TZ) -> datetime | None:
    """把 feedparser 的 `*_parsed`（UTC struct_time）转成 tz-aware datetime。

    feedparser 已经把 `published_parsed` 归一到 UTC，所以这里直接标 UTC。
    """
    if not entry_struct:
        return None
    try:
        return datetime(*entry_struct[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def is_future(dt: datetime | None, now: datetime | None = None,
              max_future_days: int = DEFAULT_MAX_FUTURE_DAYS) -> bool:
    """是否明显在未来（超过容差）。比较前一律转 UTC。"""
    if dt is None:
        return False
    reference = (now or now_utc()).astimezone(timezone.utc)
    return dt.astimezone(timezone.utc) > reference + timedelta(days=max_future_days)


def resolve_published_at(
    raw: str | None,
    source_tz: str | None = DEFAULT_TZ,
    *,
    now: datetime | None = None,
    max_future_days: int = DEFAULT_MAX_FUTURE_DAYS,
) -> tuple[datetime | None, str | None]:
    """解析发布时间，并挡掉不可信的未来日期。

    返回 `(发布时间, 问题说明)`：
    - 解析成功且日期可信 → `(dt, None)`
    - 没有日期 / 解析失败 → `(None, "no_date")`
    - 日期明显在未来（如期刊提前标的 2027-01）→ `(None, "future_date")`

    返回 None 的条目按计划「无可信日期的不公开，下次再试」处理。
    """
    dt = parse_date(raw, source_tz)
    if dt is None:
        return None, "no_date" if raw else "no_date"
    if is_future(dt, now, max_future_days):
        return None, "future_date"
    return dt, None


def to_utc(dt: datetime) -> datetime:
    """统一转 UTC，保证跨机器时区结果一致。"""
    if dt.tzinfo is None:
        raise ValueError("naive datetime 不能直接转 UTC，先补时区")
    return dt.astimezone(timezone.utc)


def age_hours(published: datetime | None, now: datetime | None = None) -> float | None:
    """已发布多少小时。用于 freshHours 判断。"""
    if published is None:
        return None
    reference = now or now_utc()
    delta = reference.astimezone(timezone.utc) - published.astimezone(timezone.utc)
    return delta.total_seconds() / 3600.0


def is_stale(published: datetime | None, fresh_hours: int,
             now: datetime | None = None) -> bool:
    """首次发现时已发布超过 fresh_hours → 归档（进全部动态，不进今天/日报）。"""
    hours = age_hours(published, now)
    if hours is None:
        return True  # 无可信日期 → 不当作新鲜
    return hours > fresh_hours


def day_bounds_bj(date_str: str) -> tuple[datetime, datetime]:
    """给一个北京日期 `YYYY-MM-DD`，返回该日 08:00 到次日 08:00 的 UTC 区间。

    日报覆盖「前一天 08:00 到当天 08:00」（北京时间，计划 §5.4）。
    """
    tz = parse_tz("Asia/Shanghai")
    y, m, d = (int(x) for x in date_str.split("-"))
    start_local = datetime(y, m, d, 8, 0, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return to_utc(start_local), to_utc(end_local)
