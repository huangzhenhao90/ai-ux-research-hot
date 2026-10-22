import Link from "next/link";

// ⚠️ 只从 lib/format 取辅助函数，不要从 lib/data 取——
// lib/data 会 import node:fs，一旦链进来，这个组件就不能在 "use client" 里用了。
import { categoryLabel, displayTitle, formatTime } from "@/lib/format";
import type { PublicItem } from "@/lib/types";

/**
 * 条目卡片。首页、全部动态、分类页、主题页共用。
 *
 * 视觉上没有用 AIHOT 的配色或 Logo（计划成功标准 6），只有文字角标。
 */
export function ItemCard({
  item,
  reasonLabel,
  showCategory = true,
  showReason = true,
}: {
  item: PublicItem;
  reasonLabel: string;
  showCategory?: boolean;
  showReason?: boolean;
}) {
  const title = displayTitle(item);
  const time = formatTime(item.publishedAt);

  return (
    <article className="card">
      <div className="card__top">
        {showCategory && item.category ? (
          <Link href={`/category/${item.category}/`} className="badge">
            {categoryLabel(item.category)}
          </Link>
        ) : null}
        {item.itemType === "tool_launch" ? (
          <span className="badge badge--plain">新工具</span>
        ) : null}
        {item.status === "archived" ? (
          <span className="badge badge--plain">往期</span>
        ) : null}
      </div>

      <h3 className="card__title">
        <Link href={`/item/${item.id}/`}>{title}</Link>
      </h3>

      {item.summaryZh ? <p className="card__summary">{item.summaryZh}</p> : null}

      {showReason && item.reason ? (
        <div className="card__reason">
          <span className="card__reason-label">{reasonLabel}</span>
          {item.reason}
        </div>
      ) : null}

      {item.tags.length > 0 ? (
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
        {time ? <time dateTime={item.publishedAt ?? undefined}>{time}</time> : null}
        <a href={item.url} target="_blank" rel="noopener noreferrer nofollow">
          原文
        </a>
      </div>
    </article>
  );
}

/** 卡片列表。空的时候给一句提示，而不是渲染成一片空白。 */
export function ItemCardList({
  items,
  reasonLabel,
  emptyText = "这里还没有内容。",
  showCategory = true,
  showReason = true,
}: {
  items: PublicItem[];
  reasonLabel: string;
  emptyText?: string;
  showCategory?: boolean;
  showReason?: boolean;
}) {
  if (items.length === 0) {
    return <p className="empty">{emptyText}</p>;
  }
  return (
    <div className="card-list">
      {items.map((item) => (
        <ItemCard
          key={item.id}
          item={item}
          reasonLabel={reasonLabel}
          showCategory={showCategory}
          showReason={showReason}
        />
      ))}
    </div>
  );
}
