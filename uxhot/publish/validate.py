"""发布产物校验与原子替换（计划 §5.3 最后一条）。

「不通过则整次发布失败、保留上一版」在这里落地，方式是**先写临时目录、校验通过才替换**：

    写 stage（web/.publish-stage-xxx） → validate_publish_dir(stage) → 整体搬进 web/public

校验失败时正式目录一个字节都不动，也就无所谓「回滚」——回滚最容易漏文件。
不用「直接写正式目录、失败再删」的写法：静态产物是几十上百个文件，
写到一半失败会让站点直接 404，而且没法保证删干净。

校验项与计划一一对应：JSON 可解析 / schema 结构正确 / 无重复 id / 链接为 http(s) /
精选都有 titleZh 与 summaryZh / 日期带时区。另外加两条本项目的硬要求：
**公开目录里不许出现 body 等内部字段**、**BLOCK 与 UNKNOWN 不许公开**。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit
from xml.etree import ElementTree

from uxhot.config import ConfigBundle
from uxhot.models import Item, Status
from uxhot.publish.build_site_data import (
    DETAIL_EXTRA_FIELDS,
    PUBLIC_DIR,
    PUBLIC_FIELDS,
    build_site_data,
)
from uxhot.publish.llms_txt import write_llms_txt
from uxhot.publish.rss_out import RSS_FILE, write_rss_files

# 公开目录里绝不能出现的字段。body 是原文全文（版权 + 再分发），
# 其余是流水线内部审计信息，放上公网没有收益只有风险。
FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "body",
        "bodyTruncated",
        "prefilter",
        "promptVersions",
        "fact",
        "scores",
        "errors",
    }
)

# 值必须是 http(s) 的字段名
LINK_KEYS: frozenset[str] = frozenset({"url", "link", "siteUrl", "sourceUrl", "homepage"})

# 每次发布都必须存在的文件（少一个前端就可能 404）
REQUIRED_FILES: tuple[str, ...] = (
    "data/index.json",
    "data/site.json",
    "data/latest.json",
    "data/search-index.json",
    "data/all/index.json",
    "data/categories/index.json",
    "data/topics/index.json",
    RSS_FILE,
    "llms.txt",
)

STATUS_VALUES = frozenset(s.value for s in Status)
NON_PUBLIC_STATUSES = frozenset({Status.BLOCKED.value, Status.UNKNOWN.value})

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
ISO_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


class PublishError(RuntimeError):
    """校验不通过。`problems` 是全部问题（不是第一条），方便一次修完。"""

    def __init__(self, problems: Iterable[str]):
        self.problems: list[str] = list(problems)
        head = "；".join(self.problems[:3])
        more = f"（共 {len(self.problems)} 条）" if len(self.problems) > 3 else ""
        super().__init__(f"发布校验不通过：{head}{more}")


@dataclass(frozen=True)
class PublishResult:
    """一次发布的结果。`replaced` 说明这次有没有真的换掉上一版。"""

    out_dir: Path
    counts: dict[str, int] = field(default_factory=dict)
    replaced: bool = False


# ── 遍历小工具 ─────────────────────────────────────────────────────────


def iter_dicts(value: Any) -> Iterable[dict]:
    """深度遍历所有字典节点（列表和嵌套对象都进）。"""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


# ── 主校验 ─────────────────────────────────────────────────────────────


def validate_publish_dir(path: Path | str) -> list[str]:
    """校验一个发布目录，返回问题列表（空列表 = 通过）。

    只读、不改目录：可以先校验再决定要不要替换（`publish_atomic` 就是这么用的）。
    """
    root = Path(path)
    problems: list[str] = []
    if not root.is_dir():
        return [f"发布目录不存在：{root}"]

    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            problems.append(f"缺少必需文件：{rel}")

    docs = _load_json_docs(root, problems)
    _check_forbidden_keys(docs, problems)
    _check_items(docs, problems)
    _check_generated_shapes(docs, problems)
    _check_site(docs.get("data/site.json"), problems)
    _check_rss(root, problems, has_selected=_has_selected(docs))
    _check_llms(root, problems)
    return problems


def _load_json_docs(root: Path, problems: list[str]) -> dict[str, Any]:
    """读入目录下所有 .json。解析失败记问题并跳过，让其余检查照常进行。"""
    docs: dict[str, Any] = {}
    for file in sorted(root.rglob("*.json")):
        rel = file.relative_to(root).as_posix()
        try:
            docs[rel] = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{rel}: JSON 解析失败：{exc}")
    return docs


def _check_forbidden_keys(docs: dict[str, Any], problems: list[str]) -> None:
    """公开目录里不许出现 body 等内部字段。

    这是「白名单之外的东西不许落盘」的最后一道闸：即便将来有人往产物里多塞了字段，
    只要它在禁名单里，整次发布就会失败，而不是悄悄把原文发上公网。
    """
    for rel, doc in docs.items():
        for node in iter_dicts(doc):
            for key in node:
                if key in FORBIDDEN_KEYS:
                    problems.append(f"{rel}: 出现不该公开的字段「{key}」")


def _check_items(docs: dict[str, Any], problems: list[str]) -> None:
    """逐条检查：id 形状与重复、状态、链接、日期、精选必备字段、跨文件一致。"""
    # id -> 字段 -> (首次出现的文件, 值)：同一 id 在不同文件里必须说同一件事
    seen: dict[str, dict[str, tuple[str, Any]]] = {}

    for rel, doc in sorted(docs.items()):
        local_counts: dict[str, int] = {}
        for node in iter_dicts(doc):
            for key, value in node.items():
                if key in LINK_KEYS and isinstance(value, str) and value:
                    if not value.startswith(("http://", "https://")):
                        problems.append(f"{rel}: 字段「{key}」不是 http(s) 链接：{value}")
                if isinstance(value, str) and value:
                    _check_datetime_value(f"{rel}: 字段「{key}」", key, value, problems)
                if key in ("date", "month") and isinstance(value, str) and value:
                    _check_date_key(f"{rel}: 字段「{key}」", key, value, problems)

            item_id = node.get("id")
            if not isinstance(item_id, str) or not item_id:
                continue
            if not ID_PATTERN.match(item_id):
                problems.append(f"{rel}: id 形状不合法（会被当成路径）：{item_id!r}")
            _check_status_and_writing(rel, node, item_id, problems)
            local_counts[item_id] = local_counts.get(item_id, 0) + 1
            for key, value in node.items():
                if key not in PUBLIC_FIELDS:
                    continue
                record = seen.setdefault(item_id, {})
                if key in record:
                    first_rel, first_value = record[key]
                    if first_value != value:
                        problems.append(
                            f"{rel}: 条目 {item_id} 的「{key}」与 {first_rel} 不一致"
                            "（同一 id 在所有文件里必须一致）"
                        )
                else:
                    record[key] = (rel, value)

        duplicates = sorted(k for k, count in local_counts.items() if count > 1)
        if duplicates:
            problems.append(f"{rel}: 同一文件内 id 重复：{duplicates}")


def _check_status_and_writing(
    rel: str, node: dict, item_id: str, problems: list[str]
) -> None:
    status = node.get("status")
    if not isinstance(status, str) or not status:
        return
    if status not in STATUS_VALUES:
        problems.append(f"{rel}: 条目 {item_id} 的 status 不认识：{status!r}")
        return
    if status in NON_PUBLIC_STATUSES:
        problems.append(f"{rel}: 条目 {item_id} 状态为 {status}，不该公开")
        return
    if status == Status.SELECTED.value:
        title_zh = str(node.get("titleZh") or "").strip()
        summary_zh = str(node.get("summaryZh") or "").strip()
        if not title_zh or not summary_zh:
            missing = [
                name
                for name, value in (("titleZh", title_zh), ("summaryZh", summary_zh))
                if not value
            ]
            problems.append(f"{rel}: 精选 {item_id} 缺 {'/'.join(missing)}")


def _check_datetime_value(label: str, key: str, value: str, problems: list[str]) -> None:
    """日期必须 ISO 8601 且带时区。

    只对「像时间的东西」较真：键名以 At 结尾，或者值本身长得像日期时间。
    这样报告里的普通字符串不会被误判，而真的时间字段一个都跑不掉。
    """
    looks_like_time = bool(ISO_DATETIME_PATTERN.match(value))
    if not (key.endswith("At") or looks_like_time):
        return
    if not looks_like_time:
        problems.append(f"{label} 不是 ISO 8601 时间：{value!r}")
        return
    try:
        # Python 3.11 起 fromisoformat 认 Z；这里仍兼容一下老写法
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        problems.append(f"{label} 不是合法 ISO 8601 时间：{value!r}")
        return
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        problems.append(f"{label} 没有时区：{value!r}")


def _check_date_key(label: str, key: str, value: str, problems: list[str]) -> None:
    """纯日期字段的格式（date=YYYY-MM-DD / month=YYYY-MM）。"""
    pattern = {"date": DATE_PATTERN, "month": MONTH_PATTERN}[key]
    if not pattern.match(value):
        problems.append(f"{label} 格式不对：{value!r}")


def _has_selected(docs: dict[str, Any]) -> bool:
    for doc in docs.values():
        for node in iter_dicts(doc):
            if node.get("status") == Status.SELECTED.value:
                return True
    return False


def _check_generated_shapes(docs: dict[str, Any], problems: list[str]) -> None:
    """自家产物的结构检查：文件名与内容要一致、`count` 要与数组长度一致。

    这些是「schema 结构正确」的具体化。文件名对不上内容这类错误，前端只会表现成
    404 或空页面，很难在页面上一眼看出来，所以在发布前拦。
    """
    for rel, doc in sorted(docs.items()):
        if not isinstance(doc, dict):
            continue
        stem = Path(rel).stem
        if rel.startswith("data/items/"):
            _expect_equal(rel, doc, "id", stem, problems)
            _expect_list(rel, doc, "related", problems)
        elif rel.startswith("data/all/"):
            if stem != "index":
                _expect_equal(rel, doc, "month", stem, problems)
                _expect_counted_list(rel, doc, "items", problems)
        elif rel.startswith("data/categories/"):
            if stem != "index":
                _expect_equal(rel, doc, "key", stem, problems)
                _expect_counted_list(rel, doc, "items", problems)
        elif rel.startswith("data/topics/"):
            if stem != "index":
                _expect_equal(rel, doc, "slug", stem, problems)
                _expect_counted_list(rel, doc, "items", problems)
        elif rel == "data/latest.json":
            for key in ("windowDays", "editionHour"):
                if not isinstance(doc.get(key), int):
                    problems.append(f"{rel}: 缺整数字段「{key}」")
            days = doc.get("days")
            if not isinstance(days, list):
                problems.append(f"{rel}: days 必须是数组")
                continue
            for day in days:
                if not isinstance(day, dict):
                    problems.append(f"{rel}: days 里有非对象项")
                    continue
                name = day.get("date")
                if not isinstance(name, str) or not DATE_PATTERN.match(name):
                    problems.append(f"{rel}: days 里的 date 不合法：{name!r}")
                    continue
                _expect_counted_list(f"{rel}（{name}）", day, "items", problems)
        elif rel == "data/search-index.json":
            _expect_counted_list(rel, doc, "items", problems)
        elif rel == "data/index.json":
            if not isinstance(doc.get("counts"), dict):
                problems.append(f"{rel}: 缺 counts 对象")
            for key in ("months", "latestDays"):
                if not isinstance(doc.get(key), list):
                    problems.append(f"{rel}: {key} 必须是数组")
        elif rel == "data/all/index.json":
            months = doc.get("months")
            if not isinstance(months, list):
                problems.append(f"{rel}: months 必须是数组")
            else:
                for row in months:
                    if not isinstance(row, dict) or not MONTH_PATTERN.match(
                        str(row.get("month") or "")
                    ):
                        problems.append(f"{rel}: months 里有不合法的月份项：{row!r}")
                    elif f"data/all/{row['month']}.json" not in docs:
                        problems.append(f"{rel}: months 里的 {row['month']} 没有对应文件")
        elif rel == "data/categories/index.json":
            if not isinstance(doc.get("categories"), list):
                problems.append(f"{rel}: categories 必须是数组")
        elif rel == "data/topics/index.json":
            for key in ("groups", "topics"):
                if not isinstance(doc.get(key), list):
                    problems.append(f"{rel}: {key} 必须是数组")


def _expect_equal(rel: str, doc: dict, key: str, expected: str, problems: list[str]) -> None:
    if doc.get(key) != expected:
        problems.append(f"{rel}: 字段「{key}」是 {doc.get(key)!r}，与文件名「{expected}」不一致")


def _expect_list(rel: str, doc: dict, key: str, problems: list[str]) -> None:
    if not isinstance(doc.get(key), list):
        problems.append(f"{rel}: {key} 必须是数组")


def _expect_counted_list(rel: str, doc: dict, key: str, problems: list[str]) -> None:
    value = doc.get(key)
    if not isinstance(value, list):
        problems.append(f"{rel}: {key} 必须是数组")
        return
    count = doc.get("count")
    if not isinstance(count, int) or isinstance(count, bool):
        problems.append(f"{rel}: count 必须是整数，实际 {count!r}")
    elif count != len(value):
        problems.append(f"{rel}: count={count} 与 {key} 的实际长度 {len(value)} 不一致")


def _check_site(doc: Any, problems: list[str]) -> None:
    if not isinstance(doc, dict):
        problems.append("data/site.json 不是 JSON 对象")
        return
    for key in ("name", "alias", "subject", "siteUrl", "basePath"):
        value = doc.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"data/site.json 缺字段「{key}」")
    url = doc.get("siteUrl")
    base = doc.get("basePath")
    if isinstance(url, str) and url and not url.startswith(("http://", "https://")):
        problems.append(f"data/site.json 的 siteUrl 不是 http(s)：{url}")
    if isinstance(url, str) and isinstance(base, str) and url:
        if urlsplit(url).path.rstrip("/") != base.rstrip("/"):
            problems.append(
                f"data/site.json 的 basePath「{base}」与 siteUrl「{url}」的路径不一致"
            )


def _check_rss(root: Path, problems: list[str], *, has_selected: bool) -> None:
    """RSS 必须能被 XML 解析器读，且 pubDate 是带时区的 RFC 822。"""
    for name in (RSS_FILE,):
        file = root / name
        if not file.is_file():
            continue  # 缺文件已由 REQUIRED_FILES 报过
        try:
            tree = ElementTree.fromstring(file.read_text(encoding="utf-8"))
        except (OSError, ElementTree.ParseError) as exc:
            problems.append(f"{name}: XML 解析失败：{exc}")
            continue
        if tree.tag != "rss":
            problems.append(f"{name}: 根元素不是 <rss>")
        channel = tree.find("channel")
        if channel is None:
            problems.append(f"{name}: 缺少 <channel>")
            continue
        for tag in ("title", "link", "description", "lastBuildDate"):
            if not (channel.findtext(tag) or "").strip():
                problems.append(f"{name}: <channel> 缺 <{tag}>")
        items = channel.findall("item")
        if name == RSS_FILE and has_selected and not items:
            problems.append(f"{name}: 有精选条目，feed 里却一条都没有")
        for item in items:
            for tag in ("title", "link", "pubDate"):
                if not (item.findtext(tag) or "").strip():
                    problems.append(f"{name}: 有 <item> 缺 <{tag}>")
            link = (item.findtext("link") or "").strip()
            if link and not link.startswith(("http://", "https://")):
                problems.append(f"{name}: <item><link> 不是 http(s)：{link}")
            pub = (item.findtext("pubDate") or "").strip()
            if not pub:
                continue
            try:
                parsed = parsedate_to_datetime(pub)
            except (TypeError, ValueError):
                parsed = None
            if parsed is None or parsed.tzinfo is None:
                problems.append(f"{name}: pubDate 不是带时区的 RFC 822：{pub!r}")


def _check_llms(root: Path, problems: list[str]) -> None:
    file = root / "llms.txt"
    if not file.is_file():
        return
    text = file.read_text(encoding="utf-8")
    if not text.strip():
        problems.append("llms.txt 是空的")
        return
    if not text.lstrip().startswith("# "):
        problems.append("llms.txt 应以一级标题（# ...）开头")
    if "](" not in text:
        problems.append("llms.txt 里没有任何 Markdown 链接")


# ── 原子替换 ───────────────────────────────────────────────────────────


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()


def _commit(stage: Path, out_dir: Path) -> bool:
    """把 stage 的内容搬进正式目录，返回「是否替换了已有目录」。

    逐个顶层条目用 `os.replace` 改名落位（同文件系统内是原子的）：
    先给旧的改名成 `.名字.prev`，新的落位，最后删备份；中途出错就把备份换回来。
    目录整体改名而不是逐个文件拷贝，是为了让 `data/` 这种大目录也只是一次 rename。
    """
    if not out_dir.exists():
        os.replace(stage, out_dir)
        return False

    out_dir.mkdir(parents=True, exist_ok=True)
    moved: list[tuple[Path, Path | None]] = []
    try:
        for entry in sorted(stage.iterdir(), key=lambda p: p.name):
            target = out_dir / entry.name
            backup = out_dir / f".{entry.name}.prev"
            _remove(backup)
            if target.exists():
                os.replace(target, backup)
                moved.append((target, backup))
            else:
                moved.append((target, None))
            os.replace(entry, target)
    except OSError:
        for target, backup in reversed(moved):
            _remove(target)
            if backup is not None and backup.exists():
                os.replace(backup, target)
        raise

    for _, backup in moved:
        if backup is not None:
            _remove(backup)
    return True


def publish_atomic(
    out_dir: Path | str,
    build: Callable[[Path], dict[str, int] | None],
    *,
    validate: Callable[[Path], list[str]] = validate_publish_dir,
) -> PublishResult:
    """临时目录写 → 校验 → 通过才替换正式目录。

    `build(stage)` 往 stage 目录里写全部产物并返回数量统计。校验不通过抛
    `PublishError`，正式目录保持上一版原样。
    """
    out = Path(out_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    # stage 必须与正式目录同一个文件系统，否则 os.replace 会退化成拷贝
    stage = Path(tempfile.mkdtemp(prefix=".publish-stage-", dir=out.parent))
    try:
        counts = build(stage) or {}
        problems = validate(stage)
        if problems:
            raise PublishError(problems)
        replaced = _commit(stage, out)
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
    return PublishResult(out_dir=out, counts=dict(counts), replaced=replaced)


def build_and_validate(
    items: Iterable[Item],
    config: ConfigBundle,
    *,
    public_dir: Path | str | None = None,
    now: datetime | None = None,
) -> PublishResult:
    """完整发布：JSON + RSS + llms.txt 一起写、一起校验、一起替换。

    三样东西放在同一次替换里，是为了不出现「JSON 是新的、RSS 是旧的」这种半发布状态。
    """
    out = Path(public_dir) if public_dir is not None else PUBLIC_DIR
    rows = list(items)

    def build(stage: Path) -> dict[str, int]:
        counts = build_site_data(rows, config, stage, now=now)
        write_rss_files(config, rows, stage, now=now)
        write_llms_txt(config, rows, stage, now=now)
        return counts

    return publish_atomic(out, build)


__all__ = [
    "DETAIL_EXTRA_FIELDS",
    "FORBIDDEN_KEYS",
    "PUBLIC_FIELDS",
    "PublishError",
    "PublishResult",
    "build_and_validate",
    "iter_dicts",
    "publish_atomic",
    "validate_publish_dir",
]
