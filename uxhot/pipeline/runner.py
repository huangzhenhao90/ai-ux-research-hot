"""流水线编排：采集 → 预筛 → 评分 → 结构化 → 写作 → 去重 → 进精选。

默认 **dry-run**：抓取与机械步骤照做，模型步骤只统计「将会调用多少次」，不发请求
（计划 §2.3）。只有显式 `--execute`、环境里有 `LLM_API_KEY`、且 `MODEL_CALLS_ENABLED=true`
时才真调模型。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from uxhot.budget import Budget
from uxhot.collect import external_json, rss, web_list
from uxhot.collect.dates import now_utc
from uxhot.collect.fetch import SourceState, build_client, fetch
from uxhot.config import ConfigBundle
from uxhot.llm import LLMClient
from uxhot.models import Item, Status, items_path, load_items, upsert_items
from uxhot.pipeline import dedupe, prefilter, score, select, structure, write
from uxhot.pipeline.common import StepContext

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
STATE_FILE = DATA_DIR / "state" / "sources_state.json"
RUNS_DIR = DATA_DIR / "runs"

# 去重比较时「最近精选」的回看窗口
RECENT_SELECTED_DAYS = 7


@dataclass
class SourceOutcome:
    source_id: str
    ok: bool
    fetched: int = 0
    added: int = 0
    updated: int = 0
    error: str | None = None
    skipped_reason: str | None = None


@dataclass
class RunResult:
    dry_run: bool
    startedAt: datetime
    finishedAt: datetime | None = None
    sources: list[SourceOutcome] = field(default_factory=list)
    steps: dict = field(default_factory=dict)
    budget: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)
    plannedCalls: int = 0
    itemCount: int = 0

    @property
    def failed_sources(self) -> list[str]:
        return [s.source_id for s in self.sources if not s.ok]


# ── 信源状态 ────────────────────────────────────────────────────────────


def load_state(path: Path | None = None) -> dict[str, SourceState]:
    state_path = path or STATE_FILE
    if not state_path.is_file():
        return {}
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, SourceState] = {}
    for source_id, payload in raw.items():
        state = SourceState()
        for key, value in payload.items():
            if hasattr(state, key):
                setattr(state, key, value)
        out[source_id] = state
    return out


def save_state(state: dict[str, SourceState], path: Path | None = None) -> None:
    state_path = path or STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {sid: vars(st) for sid, st in state.items()}
    state_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


# ── 采集 ────────────────────────────────────────────────────────────────


def collect_source(
    source,
    cfg: ConfigBundle,
    client,
    state: SourceState,
    *,
    now: datetime,
    limit: int | None = None,
) -> tuple[list[Item], SourceOutcome]:
    """抓一个信源并转成 Item。失败不抛异常，只记结果。"""
    outcome = SourceOutcome(source_id=source.id, ok=False)
    first_import = state.firstImportAt is None

    try:
        if source.kind == "rss":
            result = fetch(source.url, client, state=state)
            if result.status == 304:
                outcome.ok = True
                outcome.skipped_reason = "304 未变化"
                return [], outcome
            if not result.ok:
                outcome.error = result.error or f"HTTP {result.status}"
                return [], outcome

            entries = rss.parse_feed(result.text.encode("utf-8"), source.timezone, now=now)
            items = rss.build_items(
                entries,
                source_id=source.id,
                source_name=source.name,
                tier=source.tier,
                mode=source.mode,
                source_tz=source.timezone,
                initial_backfill_limit=source.initialBackfillLimit,
                fresh_hours=cfg.selection.freshHours,
                first_import=first_import,
                now=now,
            )

        elif source.kind == "web_list":
            result = fetch(source.url, client, state=state)
            if result.status == 304:
                outcome.ok = True
                outcome.skipped_reason = "304 未变化"
                return [], outcome
            if not result.ok:
                outcome.error = result.error or f"HTTP {result.status}"
                return [], outcome

            selectors = source.web_list.model_dump()
            entries = web_list.extract_entries(
                result.text,
                selectors=selectors,
                base_url=source.url,
                source_tz=source.timezone,
                now=now,
            )
            # 列表页没日期的，抓正文页补
            for entry in entries:
                if entry.published is None:
                    entry.published = web_list.fetch_entry_date(
                        entry.url, client, source.timezone, now
                    )
            items = web_list.build_items(
                entries,
                source_id=source.id,
                source_name=source.name,
                tier=source.tier,
                mode=source.mode,
                source_tz=source.timezone,
                initial_backfill_limit=source.initialBackfillLimit,
                fresh_hours=cfg.selection.freshHours,
                first_import=first_import,
                now=now,
            )

        elif source.kind == "external_json":
            result = fetch(source.url, client, state=state)
            if result.status == 304:
                outcome.ok = True
                outcome.skipped_reason = "304 未变化"
                return [], outcome
            if not result.ok:
                outcome.error = result.error or f"HTTP {result.status}"
                return [], outcome
            payload = json.loads(result.text)
            if isinstance(payload, dict):
                payload = payload.get("papers") or payload.get("items") or []
            entries = external_json.parse_papers(payload)
            items = external_json.build_items(
                entries,
                source_id=source.id,
                tier=source.tier,
                mode=source.mode,
                initial_backfill_limit=source.initialBackfillLimit,
                first_import=first_import,
                now=now,
            )

        else:
            outcome.error = f"未知 kind：{source.kind}"
            return [], outcome

    except Exception as exc:  # noqa: BLE001 - 单个信源失败不该中断整次运行
        outcome.error = f"{type(exc).__name__}: {exc}"
        state.consecutiveFailures += 1
        state.lastError = outcome.error
        return [], outcome

    if limit is not None:
        items = items[:limit]

    outcome.ok = True
    outcome.fetched = len(items)
    state.lastFetchAt = now.isoformat()
    if first_import:
        state.firstImportAt = now.isoformat()
    return items, outcome


# ── 主流程 ──────────────────────────────────────────────────────────────


def run_pipeline(
    cfg: ConfigBundle,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    now: datetime | None = None,
    llm: LLMClient | None = None,
    source_ids: list[str] | None = None,
    publish: bool = True,
) -> RunResult:
    reference = now or now_utc()
    started = now_utc()
    result = RunResult(dry_run=dry_run, startedAt=started)

    budget = Budget(
        per_run_calls=cfg.selection.budget["perRunCalls"],
        per_day_calls=cfg.selection.budget["perDayCalls"],
        state_dir=RUNS_DIR,
        now=reference,
    )
    ctx = StepContext(cfg=cfg, budget=budget, client=llm, dry_run=dry_run)

    state = load_state()
    sources = [
        s for s in cfg.sources.sources
        if source_ids is None or s.id in source_ids
    ]

    # ── 1. 采集 ────────────────────────────────────────────────────────
    collected: list[Item] = []
    with build_client() as client:
        for source in sources:
            st = state.setdefault(source.id, SourceState())
            items, outcome = collect_source(
                source, cfg, client, st, now=reference, limit=limit
            )
            result.sources.append(outcome)
            collected.extend(items)
            flag = "ok" if outcome.ok else "FAIL"
            detail = outcome.skipped_reason or outcome.error or f"{outcome.fetched} 条"
            print(f"  [{flag:>4}] {source.id:<26} {detail}")

    # ── 2. 落盘（按 id 合并，已判过的不重算）────────────────────────────
    paths_touched: set[Path] = set()
    for item in collected:
        paths_touched.add(items_path(DATA_DIR / "items", item.discoveredAt))

    added = updated = 0
    for path in sorted(paths_touched):
        batch = [i for i in collected if items_path(DATA_DIR / "items", i.discoveredAt) == path]
        a, u = upsert_items(path, batch)
        added += a
        updated += u

    result.steps["collect"] = {
        "sources": len(sources),
        "failed": len(result.failed_sources),
        "new": added,
        "updated": updated,
    }

    # ── 3. 取出本次要处理的条目 ─────────────────────────────────────────
    all_items = _load_all_items(DATA_DIR / "items")
    pending = [i for i in all_items if i.status in (Status.NEW, Status.PREFILTERED, Status.SCORED)]
    if limit is not None:
        pending = pending[:limit]

    # ── 4. 模型步骤 ────────────────────────────────────────────────────
    prefilter.run(pending, ctx)
    result.steps["prefilter"] = prefilter.summary(pending)

    score.run(pending, ctx)
    result.steps["score"] = score.summary(pending)

    structure.run(pending, ctx)
    result.steps["structure"] = structure.summary(pending)

    write.run(pending, ctx)
    result.steps["write"] = write.summary(pending)

    dedupe.run(
        pending,
        threshold=cfg.selection.dedupe["titleSimilarity"],
        window_hours=cfg.selection.dedupe["windowHours"],
    )
    result.steps["dedupe"] = dedupe.summary(pending)

    recent = _recent_selected(all_items, reference)
    select.run(pending, ctx, recent_selected=recent)
    result.steps["select"] = select.summary(pending)

    # ── 5. 回写 ────────────────────────────────────────────────────────
    for path in sorted({items_path(DATA_DIR / "items", i.discoveredAt) for i in all_items}):
        batch = [i for i in all_items if items_path(DATA_DIR / "items", i.discoveredAt) == path]
        from uxhot.models import write_items

        write_items(path, batch)

    save_state(state)
    budget.save()

    # ── 6. 发布（写 web/public）─────────────────────────────────────────
    # 校验不通过会抛 PublishError，web/public 保持上一版不动（计划 §5.3）。
    if publish:
        try:
            from uxhot.publish import PublishError, build_and_validate

            pub = build_and_validate(all_items, cfg, now=reference)
            result.steps["publish"] = {
                "counts": getattr(pub, "counts", None),
                "replaced": getattr(pub, "replaced", None),
            }
        except PublishError as exc:
            result.steps["publish"] = {"error": str(exc)}
            print(f"  ⚠️ 发布校验失败，保留上一版：{exc}")
        except Exception as exc:  # noqa: BLE001 - 发布失败不该丢掉本次处理结果
            result.steps["publish"] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"  ⚠️ 发布失败，保留上一版：{exc}")

    result.finishedAt = now_utc()
    result.plannedCalls = budget.run_calls
    result.budget = budget.snapshot()
    result.usage = llm.usage_summary() if llm is not None else {}
    result.itemCount = len(all_items)
    _write_run_audit(result, cfg)
    return result


def _load_all_items(items_dir: Path) -> list[Item]:
    items: list[Item] = []
    if not items_dir.is_dir():
        return items
    for path in sorted(items_dir.glob("*.jsonl")):
        items.extend(load_items(path))
    return items


def _recent_selected(items: list[Item], now: datetime, days: int = RECENT_SELECTED_DAYS) -> list[Item]:
    cutoff = now - timedelta(days=days)
    return [
        i for i in items
        if i.status is Status.SELECTED and (i.publishedAt or i.discoveredAt) >= cutoff
    ]


def _write_run_audit(result: RunResult, cfg: ConfigBundle) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = result.startedAt.astimezone().strftime("%Y%m%dT%H%M%S")
    payload = {
        "startedAt": result.startedAt.isoformat(),
        "finishedAt": result.finishedAt.isoformat() if result.finishedAt else None,
        "dryRun": result.dry_run,
        "plannedCalls": result.plannedCalls,
        "itemCount": result.itemCount,
        "steps": result.steps,
        "budget": result.budget,
        "usage": result.usage,
        "failedSources": [
            {"id": s.source_id, "error": s.error}
            for s in result.sources if not s.ok
        ],
        "sources": [
            {
                "id": s.source_id, "ok": s.ok, "fetched": s.fetched,
                "added": s.added, "updated": s.updated, "error": s.error,
                "skipped": s.skipped_reason,
            }
            for s in result.sources
        ],
    }
    path = RUNS_DIR / f"run-{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
