import type { ReactNode } from "react";

import { formatClock, monthDay, weekdayLong } from "@/lib/format";

import { IconChevronDown } from "./icons";

// ⚠️ 和 ItemCard 一样只依赖 lib/format，服务端页面与 "use client" 组件都能用。

/**
 * 一天：可折叠的日期头 + 竖向时间线。
 *
 * 用原生 `<details>` 折叠，不需要客户端脚本；日期头在滚动时吸顶。
 * `day` 为空串表示没有时间的条目。
 */
export function TimelineDay({
  day,
  count,
  aside,
  children,
}: {
  day: string;
  count: number;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <details className="day" open>
      <summary className="day-head">
        <span className="day-head__date">{day ? monthDay(day) : "日期未知"}</span>
        <span className="day-head__toggle" aria-hidden="true">
          <IconChevronDown size={14} />
        </span>
        <span className="day-head__meta">
          {day ? `${weekdayLong(day)} · ` : ""}
          <span className="num">{count}</span> 条
        </span>
        {aside ? <span className="day-head__aside">{aside}</span> : null}
      </summary>
      <ol className="timeline">{children}</ol>
    </details>
  );
}

/** 时间线上的一格：左边时刻，中间竖线和圆点，右边内容。手机上不画竖线。 */
export function TimelineSlot({
  at,
  children,
}: {
  at: string | null;
  children: ReactNode;
}) {
  const clock = formatClock(at);
  return (
    <li className="slot">
      {clock ? (
        <time className="slot__time" dateTime={at ?? undefined}>
          {clock}
        </time>
      ) : (
        <span className="slot__time" />
      )}
      <span className="slot__rail" aria-hidden="true" />
      <div className="slot__body">{children}</div>
    </li>
  );
}
