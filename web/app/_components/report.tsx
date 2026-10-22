import Link from "next/link";

import { categoryLabel, formatTime } from "@/lib/data";
import type { BriefRef, ItemRef } from "@/lib/types";

/**
 * 日报 / 周报专用展示件。
 *
 * 报告里的条目是 `ItemRef`（字段是 `PublicItem` 的子集，没有原标题、没有 status），
 * 所以不能直接复用 `ItemCard`；这里只复用同一套 CSS 类（`card` / `headline` /
 * `brief-list` / `report-head`），保持视觉一致，不发明新类名。
 */

/** 北京时间星期几，如 `周四`。解析不了就返回空串。 */
export function weekdayZh(date: string): string {
  const parsed = new Date(`${date}T00:00:00+08:00`);
  if (Number.isNaN(parsed.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    weekday: "short",
  }).format(parsed);
}

// ── 报头 ────────────────────────────────────────────────────────────────

export function ReportHead({
  title,
  period,
  note,
  stats,
}: {
  title: string;
  period: string;
  note?: string;
  stats: React.ReactNode;
}) {
  return (
    <header className="report-head">
      <h1 className="report-head__title">{title}</h1>
      {period ? (
        <p className="section__count" style={{ marginTop: "0.35rem" }}>
          {period}
        </p>
      ) : null}
      <div className="report-head__stats">{stats}</div>
      {note ? (
        <p className="section__count" style={{ marginTop: "0.5rem" }}>
          {note}
        </p>
      ) : null}
    </header>
  );
}

/** 报头里的一个统计项：`标签 + 粗体数字 + 单位`。 */
export function ReportStat({
  label,
  value,
  unit,
}: {
  label?: string;
  value: number | string;
  unit?: string;
}) {
  return (
    <span className="report-head__stat">
      {label ? `${label} ` : null}
      <strong>{value}</strong>
      {unit ? ` ${unit}` : null}
    </span>
  );
}

// ── 条目 ────────────────────────────────────────────────────────────────

function categoryText(item: ItemRef): string {
  const label = item.categoryLabel?.trim();
  if (label) return label;
  return item.category ? categoryLabel(item.category) : "";
}

/** 报告里的一条正文条目（ItemRef 版卡片）。 */
export function ItemRefCard({
  item,
  reasonLabel,
}: {
  item: ItemRef;
  reasonLabel: string;
}) {
  const category = categoryText(item);
  const related = item.relatedIds?.length ?? 0;
  const time = formatTime(item.publishedAt);
  const title = item.titleZh?.trim() || item.url;

  return (
    <article className="card">
      <div className="card__top">
        {category ? <span className="badge">{category}</span> : null}
        {related > 0 ? (
          <span className="badge badge--plain">同一事件另有 {related} 篇</span>
        ) : null}
      </div>

      <h3 className="card__title">
        <Link href={`/item/${item.id}/`}>{title}</Link>
      </h3>

      {item.summaryZh ? <p className="card__summary">{item.summaryZh}</p> : null}

      {item.reason ? (
        <div className="card__reason">
          <span className="card__reason-label">{reasonLabel}</span>
          {item.reason}
        </div>
      ) : null}

      {(item.tags?.length ?? 0) > 0 ? (
        <div className="tag-row">
          {item.tags.slice(0, 6).map((tag) => (
            <span key={tag} className="badge badge--plain">
              {tag}
            </span>
          ))}
        </div>
      ) : null}

      <div className="card__meta">
        <span>{item.sourceName}</span>
        {time ? (
          <time dateTime={item.publishedAt ?? undefined}>{time}</time>
        ) : null}
        <a href={item.url} target="_blank" rel="noopener noreferrer nofollow">
          原文
        </a>
      </div>
    </article>
  );
}

/** 一组条目。空的时候给一句提示，而不是渲染空的分节标题。 */
export function ItemRefCardList({
  items,
  reasonLabel,
  emptyText = "这一节还没有条目。",
}: {
  items: ItemRef[];
  reasonLabel: string;
  emptyText?: string;
}) {
  if (items.length === 0) {
    return <p className="empty">{emptyText}</p>;
  }
  return (
    <div className="card-list">
      {items.map((item) => (
        <ItemRefCard key={item.id} item={item} reasonLabel={reasonLabel} />
      ))}
    </div>
  );
}

// ── 头条 ────────────────────────────────────────────────────────────────

export function HeadlineBlock({
  item,
  reasonLabel,
  label = "头条",
}: {
  item: ItemRef;
  reasonLabel: string;
  label?: string;
}) {
  const category = categoryText(item);
  const related = item.relatedIds?.length ?? 0;
  const time = formatTime(item.publishedAt);
  const title = item.titleZh?.trim() || item.url;

  return (
    <section className="headline">
      <p className="headline__label">{label}</p>

      <h2 className="headline__title">
        <Link href={`/item/${item.id}/`}>{title}</Link>
      </h2>

      {item.summaryZh ? (
        <p className="headline__summary">{item.summaryZh}</p>
      ) : null}

      {item.reason ? (
        <div className="card__reason" style={{ marginTop: "0.85rem" }}>
          <span className="card__reason-label">{reasonLabel}</span>
          {item.reason}
        </div>
      ) : null}

      <div className="card__meta">
        {category ? <span>{category}</span> : null}
        <span>{item.sourceName}</span>
        {time ? (
          <time dateTime={item.publishedAt ?? undefined}>{time}</time>
        ) : null}
        {related > 0 ? <span>同一事件另有 {related} 篇</span> : null}
        <a href={item.url} target="_blank" rel="noopener noreferrer nofollow">
          原文
        </a>
      </div>
    </section>
  );
}

// ── 快讯 ────────────────────────────────────────────────────────────────

export function BriefList({ briefs }: { briefs: BriefRef[] }) {
  return (
    <ul className="brief-list">
      {briefs.map((brief) => (
        <li key={brief.id}>
          <Link href={`/item/${brief.id}/`}>
            {brief.titleZh?.trim() || brief.url}
          </Link>
          <span className="brief-list__source">{brief.sourceName}</span>
        </li>
      ))}
    </ul>
  );
}

// ── 期别列表（日报列表 / 周报列表共用）─────────────────────────────────

export interface EditionEntry {
  key: string;
  /** 站内路径（`href()` 处理过尾斜杠），如 `/daily/2026-10-22/`。 */
  href: string;
  label: string;
  count: number | null;
  note?: string | null;
}

export function EditionList({
  entries,
  unit = "条",
}: {
  entries: EditionEntry[];
  unit?: string;
}) {
  return (
    <ul className="brief-list">
      {entries.map((entry) => (
        <li key={entry.key}>
          <Link href={entry.href}>{entry.label}</Link>
          {entry.note ? (
            <span className="section__count">{entry.note}</span>
          ) : null}
          <span className="brief-list__source">
            {entry.count === null ? "条数未知" : `${entry.count} ${unit}`}
          </span>
        </li>
      ))}
    </ul>
  );
}
