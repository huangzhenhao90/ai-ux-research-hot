/**
 * 纯展示辅助函数。
 *
 * ⚠️ **这个文件不能 import `node:fs`。**
 * 它同时被服务端组件和 `"use client"` 组件使用；一旦这里链到 `lib/data.ts`
 * （那个文件要读文件系统），客户端组件打包会直接失败：
 * `UnhandledSchemeError: Reading from "node:fs" is not handled`。
 *
 * 需要读数据的函数放 `lib/data.ts`。
 */

const CATEGORY_LABELS: Record<string, string> = {
  tools: "工具",
  methods: "方法",
  research: "论文",
  industry: "行业",
  cases: "案例",
  opinion: "观点",
};

export function categoryLabel(key: string | null | undefined): string {
  if (!key) return "未分类";
  return CATEGORY_LABELS[key] ?? key;
}

/** 条目显示标题：优先中文标题，退回原标题。 */
export function displayTitle(item: {
  titleZh?: string | null;
  title: string;
}): string {
  return item.titleZh?.trim() || item.title;
}

/** 把 ISO 时间格式化成北京时间 `YYYY-MM-DD HH:mm`。 */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}`;
}

/** 只要日期部分（北京时间）。 */
export function formatDate(iso: string | null | undefined): string {
  const full = formatTime(iso);
  return full ? full.slice(0, 10) : "";
}

/**
 * 拼站内链接路径。
 *
 * `output: "export"` + `trailingSlash: true` 下站内链接要带尾斜杠，
 * 否则 GitHub Pages 会 404。用 `<Link>` 时 Next 会自己加 basePath，
 * 所以这里只拼路径部分。
 */
export function href(path: string): string {
  const clean = path.startsWith("/") ? path : `/${path}`;
  return clean.endsWith("/") ? clean : `${clean}/`;
}

/** 供客户端组件用的「展示就绪」条目：时间与分类标签已格式化。 */
export interface DisplayItem<T> {
  item: T;
  title: string;
  time: string;
  categoryLabel: string;
}

// ── 时间线用的北京时间拆分 ─────────────────────────────────────────────

function beijingParts(iso: string | null | undefined) {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    weekday: "long",
    hour12: false,
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return {
    day: `${get("year")}-${get("month")}-${get("day")}`,
    // 部分运行时把零点写成 24
    clock: `${get("hour") === "24" ? "00" : get("hour")}:${get("minute")}`,
    weekday: get("weekday"),
  };
}

/** 条目在时间线上用的时刻：发布时间优先，没有就用发现时间。 */
export function itemMoment(item: {
  publishedAt: string | null;
  discoveredAt?: string | null;
}): string | null {
  return item.publishedAt ?? item.discoveredAt ?? null;
}

/** 北京时间 `HH:mm`。 */
export function formatClock(iso: string | null | undefined): string {
  return beijingParts(iso)?.clock ?? "";
}

/**
 * `YYYY-MM-DD` → `10月28日`；年份与 `refYear`（通常是列表里最新那天的年份）
 * 不同时带上年份，如 `2020年7月2日`，免得跨年的旧条目看不出是哪一年。
 */
export function monthDay(day: string, refYear?: string): string {
  const [year, month, date] = day.split("-");
  if (!month || !date) return day;
  const head = refYear && year !== refYear ? `${year}年` : "";
  return `${head}${Number(month)}月${Number(date)}日`;
}

/** `YYYY-MM-DD` → `星期三`（按北京时间）。 */
export function weekdayLong(day: string): string {
  return beijingParts(`${day}T12:00:00+08:00`)?.weekday ?? "";
}

/**
 * 按北京时间的自然日分组，组内与组间都按时间从新到旧。
 * 没有任何时间的条目归到最后一组「日期未知」（key 为空串）。
 */
export function groupByDay<
  T extends { publishedAt: string | null; discoveredAt?: string | null },
>(items: T[]): { day: string; items: { item: T; at: string | null }[] }[] {
  const rows = items.map((item) => {
    const at = itemMoment(item);
    return { item, at, day: beijingParts(at)?.day ?? "", ts: at ? Date.parse(at) : 0 };
  });
  rows.sort((a, b) => b.ts - a.ts);
  const groups: { day: string; items: { item: T; at: string | null }[] }[] = [];
  for (const row of rows) {
    let group = groups.at(-1);
    if (!group || group.day !== row.day) {
      group = { day: row.day, items: [] };
      groups.push(group);
    }
    group.items.push({ item: row.item, at: row.at });
  }
  return groups;
}

// ── 用研社招的日期 ─────────────────────────────────────────────────────

/** 北京时间的今天 `YYYY-MM-DD`。页面在构建时算，定时更新每次都会重新构建。 */
export function beijingToday(now: Date = new Date()): string {
  return beijingParts(now.toISOString())?.day ?? now.toISOString().slice(0, 10);
}

/** 两个 `YYYY-MM-DD` 相差几天（`to - from`）。 */
export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}

/** `今天` / `昨天` / `12 天前` */
export function daysAgoLabel(day: string, today: string): string {
  const n = daysBetween(day, today);
  if (n <= 0) return "今天";
  if (n === 1) return "昨天";
  return `${n} 天前`;
}
