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
