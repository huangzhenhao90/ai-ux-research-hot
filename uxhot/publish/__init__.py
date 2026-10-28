"""发布层：把处理好的条目变成前端能读的静态产物（计划 §5.3）。

四个模块各管一件事：

- `build_site_data`：`web/public/data/` 下的全套 JSON（只放公开字段白名单）
- `rss_out`：`web/public/rss.xml`（精选）
- `llms_txt`：`web/public/llms.txt`
- `validate`：产物校验 + 「先写临时目录、校验通过才替换」的原子发布

入口通常是 `build_and_validate(items, config)`：一次写入、一次校验、一次替换；
校验不通过抛 `PublishError`，`web/public` 保持上一版不动。
"""

from __future__ import annotations

from uxhot.publish.build_site_data import (
    DETAIL_EXTRA_FIELDS,
    PUBLIC_DIR,
    PUBLIC_FIELDS,
    base_path_of,
    build_site_data,
    edition_day,
    iso_utc,
    public_item,
    sort_items,
    source_name_map,
)
from uxhot.publish.llms_txt import build_llms_txt, write_llms_txt
from uxhot.publish.rss_out import (
    RSS_FILE,
    build_rss,
    write_rss_files,
)
from uxhot.publish.validate import (
    PublishError,
    PublishResult,
    build_and_validate,
    publish_atomic,
    validate_publish_dir,
)

__all__ = [
    # 构建
    "build_site_data",
    "build_rss",
    "build_llms_txt",
    "write_rss_files",
    "write_llms_txt",
    # 校验与发布
    "validate_publish_dir",
    "publish_atomic",
    "build_and_validate",
    "PublishError",
    "PublishResult",
    # 契约
    "PUBLIC_FIELDS",
    "DETAIL_EXTRA_FIELDS",
    "PUBLIC_DIR",
    "RSS_FILE",
    # 小工具（测试与调用方都用得上）
    "iso_utc",
    "public_item",
    "sort_items",
    "source_name_map",
    "base_path_of",
    "edition_day",
]
