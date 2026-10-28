"use client";

import { useEffect, useMemo, useState } from "react";

import { groupByDay } from "@/lib/format";
import type { PublicItem } from "@/lib/types";

import { IconSearch } from "./icons";
import { ItemCard } from "./ItemCard";
import { TimelineDay, TimelineSlot } from "./Timeline";

/**
 * 精选与全部动态共用的信息流：分类胶囊 + 搜索框 + 按天分组的时间线。
 *
 * 静态导出没有后端，条目在构建期一次性传进来，筛选与分批展开都在浏览器内存里做。
 * 当前分类写进 `?category=`，刷新和分享链接都能保留。
 */
export function FeedClient({
  items,
  categories,
  reasonLabel,
  searchAction,
  pageSize = 100,
  emptyText = "这里还没有内容。",
}: {
  items: PublicItem[];
  categories: { key: string; label: string }[];
  reasonLabel: string;
  /** 搜索页的完整地址（含 basePath），搜索框提交到这里。 */
  searchAction: string;
  pageSize?: number;
  emptyText?: string;
}) {
  // null = 不筛选
  const [active, setActive] = useState<string | null>(null);
  const [visible, setVisible] = useState(pageSize);

  useEffect(() => {
    const key = new URLSearchParams(window.location.search).get("category");
    if (key && categories.some((c) => c.key === key)) setActive(key);
  }, [categories]);

  function select(key: string | null) {
    setActive(key);
    setVisible(pageSize);
    const url = new URL(window.location.href);
    if (key) url.searchParams.set("category", key);
    else url.searchParams.delete("category");
    window.history.replaceState(null, "", url);
  }

  const filtered = useMemo(
    () => (active === null ? items : items.filter((item) => item.category === active)),
    [items, active],
  );
  const shown = filtered.slice(0, visible);
  const rest = filtered.length - shown.length;
  const groups = useMemo(() => groupByDay(shown), [shown]);
  // 日期头上的条数按整个筛选结果算，不受「加载更多」截断影响
  const dayTotals = useMemo(() => {
    const totals = new Map<string, number>();
    for (const group of groupByDay(filtered)) totals.set(group.day, group.items.length);
    return totals;
  }, [filtered]);

  const tabs = [{ key: null as string | null, label: "全部" }, ...categories];

  return (
    <>
      <div className="feed-bar">
        <div className="pill-tabs" role="group" aria-label="按分类筛选">
          {tabs.map((tab) => (
            <button
              key={tab.key ?? "all"}
              type="button"
              className="pill-tabs__tab"
              aria-pressed={active === tab.key}
              onClick={() => select(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <form action={searchAction} method="get" role="search" className="search-box">
          <IconSearch size={15} />
          <input
            type="search"
            name="q"
            placeholder="搜索标题、摘要…"
            aria-label="搜索"
            className="search-box__input"
          />
        </form>
      </div>

      {shown.length === 0 ? (
        <p className="empty">{active === null ? emptyText : "这个分类下还没有内容。"}</p>
      ) : (
        <div className="days">
          {groups.map((group) => (
            <TimelineDay
              key={group.day}
              day={group.day}
              count={dayTotals.get(group.day) ?? group.items.length}
            >
              {group.items.map(({ item, at }) => (
                <TimelineSlot key={item.id} at={at}>
                  <ItemCard item={item} at={at} reasonLabel={reasonLabel} />
                </TimelineSlot>
              ))}
            </TimelineDay>
          ))}
        </div>
      )}

      {rest > 0 ? (
        <div className="load-more">
          <button
            type="button"
            className="pill-button"
            onClick={() => setVisible((value) => value + pageSize)}
          >
            加载更多（还有 {rest} 条）
          </button>
        </div>
      ) : null}
    </>
  );
}
