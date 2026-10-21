"""日报与周报编排（计划 §5.4 / §5.5，输出契约见 `docs/report-schema.md`）。

- `daily.build_daily`：日报，纯规则、不调模型；
- `weekly.build_weekly`：周报，模板句为默认，模型只写总述且可选。

两个入口都返回可直接落盘的 JSON 字典（`data/reports/daily/YYYY-MM-DD.json`、
`data/reports/weekly/YYYY-Www.json`），不含 `body`。
"""

from __future__ import annotations

from uxhot.report.daily import (
    BRIEF_FIELDS,
    FLASH_LIMIT,
    HIGHLIGHT_LIMIT,
    ITEM_REF_FIELDS,
    MAIN_LIMIT,
    PER_SOURCE_LIMIT,
    QUIET_TITLE,
    REPEAT_WINDOW,
    brief_ref,
    build_daily,
    category_label,
    commentary_categories,
    daily_window,
    item_ref,
    memory_keys,
    report_item_refs,
    source_name,
)
from uxhot.report.weekly import (
    WEEKLY_LIMIT,
    build_weekly,
    fitted,
    overview_corpus,
    overview_grounded,
    template_overview,
    week_range,
    weekly_window,
    write_overview,
)

__all__ = [
    # 日报
    "build_daily",
    "daily_window",
    "item_ref",
    "brief_ref",
    "memory_keys",
    "report_item_refs",
    "category_label",
    "commentary_categories",
    "source_name",
    "MAIN_LIMIT",
    "HIGHLIGHT_LIMIT",
    "FLASH_LIMIT",
    "PER_SOURCE_LIMIT",
    "REPEAT_WINDOW",
    "QUIET_TITLE",
    "ITEM_REF_FIELDS",
    "BRIEF_FIELDS",
    # 周报
    "build_weekly",
    "week_range",
    "weekly_window",
    "template_overview",
    "overview_grounded",
    "overview_corpus",
    "write_overview",
    "fitted",
    "WEEKLY_LIMIT",
]
