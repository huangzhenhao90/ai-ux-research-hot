/**
 * 收藏的数据结构、校验，以及「卡片 → 收藏快照」（DECISIONS D19）。
 *
 * 收藏存在读者自己浏览器的 localStorage 里：站点是静态导出，没有账号也没有后端，
 * 所以收藏只属于「这个浏览器」，不上传、不同步，清除浏览器数据会丢；换设备靠收藏夹页面的「导出 / 导入」。
 * 存的是一份够画出卡片的快照（标题、来源、链接），不是 id 引用——社招岗位会按窗口下架，
 * 下架后详情页没了，收藏夹仍要能显示它、并告诉读者「已下架」。
 *
 * ⚠️ 这个文件只放纯函数：服务端渲染的卡片（ItemCard）要用它生成快照，所以**不能 import react**
 * （服务端组件拿不到 `useSyncExternalStore`），也不能 import `node:fs`。
 * 读写 localStorage 与 hooks 在 `favorites-store.ts`，只给客户端组件用。
 */

import { categoryLabel, displayTitle, ORIGIN_LABELS } from "./format";
import type { CampusJob, PublicItem, SocialJob } from "./types";

export type FavKind = "item" | "social" | "campus";

export const FAV_KINDS: { kind: FavKind; label: string }[] = [
  { kind: "item", label: "资讯" },
  { kind: "social", label: "社招" },
  { kind: "campus", label: "校招" },
];

export interface FavEntry {
  /** `${kind}:${id}`，收藏夹里的唯一键 */
  key: string;
  kind: FavKind;
  id: string;
  title: string;
  /** 来源 / 公司，卡片第二行 */
  subtitle: string;
  /** 几个小标签：分类、城市、来源…… */
  tags: string[];
  /** 站外链接：原文 / 官方岗位页；没有就是 null */
  url: string | null;
  /** 收藏时间（ISO） */
  savedAt: string;
}

/** 收藏时由卡片提供；`savedAt` 由存储层补。 */
export type FavInput = Omit<FavEntry, "key" | "savedAt">;

// ── 校验 ─────────────────────────────────────────────────────────────────
//
// 读出来的、导入进来的数据一律当不可信的：重新算 key 与站内路径，只放行 http(s) 外链，
// 文本截断。免得被改过的存储或导入文件把 `javascript:` 之类塞进页面链接里。

const MAX_TITLE = 300;
const MAX_TEXT = 120;
const MAX_TAGS = 6;
export const MAX_ENTRIES = 2000;
const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;

export function favKey(kind: FavKind, id: string): string {
  return `${kind}:${id}`;
}

/** 站内详情页路径（不含 basePath，`<Link>` 会自己加）。 */
export function favHref(kind: FavKind, id: string): string {
  return `/${kind}/${id}/`;
}

function text(value: unknown, max: number): string {
  return typeof value === "string" ? value.trim().slice(0, max) : "";
}

function safeUrl(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 2000) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

/** 不合格返回 null。 */
export function sanitizeEntry(raw: unknown, now: () => string = () => new Date().toISOString()): FavEntry | null {
  if (typeof raw !== "object" || raw === null) return null;
  const row = raw as Record<string, unknown>;
  const kind = row.kind;
  if (kind !== "item" && kind !== "social" && kind !== "campus") return null;
  const id = typeof row.id === "string" ? row.id : "";
  if (!ID_PATTERN.test(id)) return null;
  const title = text(row.title, MAX_TITLE);
  if (!title) return null;
  const savedAt =
    typeof row.savedAt === "string" && !Number.isNaN(Date.parse(row.savedAt)) ? row.savedAt : now();
  return {
    key: favKey(kind, id),
    kind,
    id,
    title,
    subtitle: text(row.subtitle, MAX_TEXT),
    tags: Array.isArray(row.tags)
      ? row.tags.map((tag) => text(tag, 40)).filter(Boolean).slice(0, MAX_TAGS)
      : [],
    url: safeUrl(row.url),
    savedAt,
  };
}

/** 解析存储或导入的 JSON：数组，或 `{ entries: [...] }`；去重、丢弃不合格的、最新收藏在前。 */
export function parseEntries(json: string): FavEntry[] {
  let doc: unknown;
  try {
    doc = JSON.parse(json);
  } catch {
    return [];
  }
  const rows = Array.isArray(doc)
    ? doc
    : typeof doc === "object" && doc !== null && Array.isArray((doc as { entries?: unknown }).entries)
      ? (doc as { entries: unknown[] }).entries
      : [];
  const seen = new Set<string>();
  const out: FavEntry[] = [];
  for (const row of rows.slice(0, MAX_ENTRIES)) {
    const entry = sanitizeEntry(row);
    if (!entry || seen.has(entry.key)) continue;
    seen.add(entry.key);
    out.push(entry);
  }
  return out.sort((a, b) => Date.parse(b.savedAt) - Date.parse(a.savedAt));
}

// ── 各类卡片 → 收藏快照 ───────────────────────────────────────────────────

export function itemFav(item: PublicItem): FavInput {
  return {
    kind: "item",
    id: item.id,
    title: displayTitle(item),
    subtitle: item.sourceName,
    tags: item.category ? [categoryLabel(item.category)] : [],
    url: item.url,
  };
}

export function socialFav(
  job: Pick<SocialJob, "id" | "title" | "company" | "cities" | "origins" | "url">,
): FavInput {
  return {
    kind: "social",
    id: job.id,
    title: job.title,
    subtitle: job.company,
    tags: [...job.cities.slice(0, 2), ...job.origins.map((origin) => ORIGIN_LABELS[origin])],
    url: job.url,
  };
}

export function campusFav(job: Pick<CampusJob, "id" | "title" | "company" | "location" | "type" | "url">): FavInput {
  return {
    kind: "campus",
    id: job.id,
    title: job.title,
    subtitle: job.company,
    tags: [job.location, job.type].filter((tag): tag is string => !!tag),
    url: job.url,
  };
}
