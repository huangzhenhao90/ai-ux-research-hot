import Link from "next/link";

// ⚠️ 只从 lib/format 取辅助函数，不要从 lib/data 取——
// lib/data 会 import node:fs，一旦链进来，这个组件就不能在 "use client" 里用了。
import { categoryLabel, displayTitle, formatClock, groupByDay } from "@/lib/format";
import type { PublicItem } from "@/lib/types";

import { IconExternal } from "./icons";
import { TimelineDay, TimelineSlot } from "./Timeline";

/**
 * 条目卡片。首页、全部动态、分类页、主题页共用。
 *
 * 顶部一行：来源、分类、精选等角标，右侧「原文」；整张卡片点进详情页。
 * 桌面上时刻画在左侧时间线上，手机上没有时间线，时刻跟在来源后面（`at`）。
 */
export function ItemCard({
  item,
  reasonLabel,
  at = null,
  showCategory = true,
  showReason = true,
  showTags = true,
}: {
  item: PublicItem;
  reasonLabel: string;
  at?: string | null;
  showCategory?: boolean;
  showReason?: boolean;
  showTags?: boolean;
}) {
  const title = displayTitle(item);
  const clock = formatClock(at);
  const tags = showTags ? item.tags.slice(0, 4) : [];

  return (
    <article className="card card--item">
      <header className="card__head">
        <span className="card__source">{item.sourceName}</span>
        {clock ? <span className="card__clock">· {clock}</span> : null}
        {showCategory && item.category ? (
          <Link href={`/category/${item.category}/`} className="badge badge--accent card__raise">
            {categoryLabel(item.category)}
          </Link>
        ) : null}
        {item.status === "selected" ? (
          <span className="badge badge--selected">
            <span className="badge__dot" aria-hidden="true" />
            精选
          </span>
        ) : null}
        {item.itemType === "tool_launch" ? <span className="badge">新工具</span> : null}
        {item.status === "archived" ? <span className="badge">往期</span> : null}
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="card__origin card__raise"
          title="打开原文"
        >
          原文
          <IconExternal size={12} />
        </a>
      </header>

      <h3 className="card__title">
        <Link href={`/item/${item.id}/`} className="card__link">
          {title}
        </Link>
      </h3>

      {item.summaryZh ? <p className="card__summary">{item.summaryZh}</p> : null}

      {tags.length > 0 ? (
        <div className="card__tags">
          {tags.map((tag) => (
            <span key={tag}>#{tag}</span>
          ))}
        </div>
      ) : null}

      {showReason && item.reason ? (
        <p className="card__reason">
          {reasonLabel}：{item.reason}
        </p>
      ) : null}
    </article>
  );
}

/**
 * 按天分组的时间线列表。空的时候给一句提示，而不是渲染成一片空白。
 */
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
  const groups = groupByDay(items);
  const refYear = groups.find((group) => group.day)?.day.slice(0, 4);
  return (
    <div className="days">
      {groups.map((group) => (
        <TimelineDay
          key={group.day}
          day={group.day}
          refYear={refYear}
          count={group.items.length}
        >
          {group.items.map(({ item, at }) => (
            <TimelineSlot key={item.id} at={at}>
              <ItemCard
                item={item}
                at={at}
                reasonLabel={reasonLabel}
                showCategory={showCategory}
                showReason={showReason}
              />
            </TimelineSlot>
          ))}
        </TimelineDay>
      ))}
    </div>
  );
}
