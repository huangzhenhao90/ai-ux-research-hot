"use client";

import { useEffect, useMemo, useState } from "react";

import { groupByDay, monthDay, weekdayLong } from "@/lib/format";
import { track } from "@/lib/track";
import type { PublicItem } from "@/lib/types";

import { IconSearch } from "./icons";
import { ItemCard } from "./ItemCard";
import { TimelineDay, TimelineSlot } from "./Timeline";

/** 日期头的锚点 id，跳转与 `?date=` 都靠它。 */
function dayAnchor(day: string): string {
  return `day-${day || "unknown"}`;
}

/**
 * 精选与全部动态共用的信息流：分类胶囊 + 跳到日期 + 搜索框 + 按天分组的时间线。
 *
 * 静态导出没有后端，条目在构建期一次性传进来，筛选、分批展开、跳转都在浏览器内存里做。
 * 当前分类写进 `?category=`、跳到的日期写进 `?date=`，刷新和分享链接都能保留。
 *
 * ⚠️ 数据文件里的条目按分数排，不按时间；必须先按天排好再截取「前 N 条」，
 * 否则先显示的是高分条目，日期分组会缺条，「加载更多」会往已显示的日子里插。
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
  const [jumpDay, setJumpDay] = useState("");
  // 跳转要等目标日期渲染出来才能滚过去
  const [pendingJump, setPendingJump] = useState<string | null>(null);

  const filtered = useMemo(
    () => (active === null ? items : items.filter((item) => item.category === active)),
    [items, active],
  );
  // 整个筛选结果按天分好组（组内、组间都从新到旧）
  const allDays = useMemo(() => groupByDay(filtered), [filtered]);

  // 按天顺序取前 `visible` 条；跨过的那一天只显示已取到的部分
  const shownDays = useMemo(() => {
    const out: typeof allDays = [];
    let left = visible;
    for (const group of allDays) {
      if (left <= 0) break;
      out.push({ day: group.day, items: group.items.slice(0, left) });
      left -= group.items.length;
    }
    return out;
  }, [allDays, visible]);
  const rest = filtered.length - Math.min(visible, filtered.length);
  const refYear = allDays.find((group) => group.day)?.day.slice(0, 4);

  function writeQuery(key: string, value: string | null) {
    const url = new URL(window.location.href);
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
    window.history.replaceState(null, "", url);
  }

  function select(key: string | null) {
    track("filter", { tab: "feed", by: "category" });
    setActive(key);
    setVisible(pageSize);
    setJumpDay("");
    writeQuery("category", key);
    writeQuery("date", null);
  }

  /** 跳到某一天：没加载到的先展开到那一天（再多一批），再滚过去。 */
  function jumpTo(day: string, days = allDays) {
    setJumpDay(day);
    writeQuery("date", day || null);
    if (!day) return;
    let needed = 0;
    for (const group of days) {
      needed += group.items.length;
      if (group.day === day) break;
    }
    // 多展开一批：目标日期下面要有内容，它才能滚到屏幕顶端
    setVisible((value) => Math.max(value, needed + pageSize));
    setPendingJump(day);
  }

  // 打开页面时恢复链接里的分类与日期
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const key = params.get("category");
    const category = key && categories.some((c) => c.key === key) ? key : null;
    if (category) setActive(category);
    const day = params.get("date");
    if (day) {
      const pool = category ? items.filter((item) => item.category === category) : items;
      const days = groupByDay(pool);
      if (days.some((group) => group.day === day)) jumpTo(day, days);
    }
    // 只在首次挂载时读一次链接，之后由用户操作改写
  }, []);

  useEffect(() => {
    if (!pendingJump) return;
    const target = document.getElementById(dayAnchor(pendingJump));
    if (!target) return;
    if (target instanceof HTMLDetailsElement) target.open = true;
    target.scrollIntoView({ block: "start" });
    setPendingJump(null);
  }, [pendingJump, shownDays]);

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
        <div className="feed-bar__tools">
          {allDays.length > 1 ? (
            <select
              className="day-select"
              aria-label="跳到日期"
              value={jumpDay}
              onChange={(event) => {
                if (event.target.value) track("filter", { tab: "feed", by: "date" });
                jumpTo(event.target.value);
              }}
            >
              <option value="">跳到日期</option>
              {allDays
                .filter((group) => group.day)
                .map((group) => (
                  <option key={group.day} value={group.day}>
                    {`${monthDay(group.day, refYear)} ${weekdayLong(group.day)} · ${group.items.length} 条`}
                  </option>
                ))}
            </select>
          ) : null}
          <form
            action={searchAction}
            method="get"
            role="search"
            className="search-box"
            onSubmit={() => track("search", { scope: "feed_bar" })}
          >
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
      </div>

      {shownDays.length === 0 ? (
        <p className="empty">{active === null ? emptyText : "这个分类下还没有内容。"}</p>
      ) : (
        <div className="days">
          {shownDays.map((group) => (
            <TimelineDay
              key={group.day}
              id={dayAnchor(group.day)}
              day={group.day}
              refYear={refYear}
              count={allDays.find((g) => g.day === group.day)?.items.length ?? group.items.length}
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
            onClick={() => {
              track("load_more", { tab: "feed" });
              setVisible((value) => value + pageSize);
            }}
          >
            加载更多（还有 {rest} 条）
          </button>
        </div>
      ) : null}
    </>
  );
}
