/**
 * 数据读取层。
 *
 * 所有页面在**构建时**读 `public/data/*.json`（`output: "export"` 静态导出），
 * 页面打开后不访问任何后端、不调模型（计划 §阶段 6）。
 *
 * 读文件用 `node:fs`：这些调用只发生在构建期的 server component 里。
 */

import { readFileSync, existsSync, readdirSync } from "node:fs";
import { join } from "node:path";

import type {
  AllIndex,
  AllMonth,
  CategoriesIndex,
  CategoryDoc,
  DataManifest,
  ItemDetail,
  SearchIndexDoc,
  SiteConfig,
  TopicDoc,
  TopicsIndex,
} from "./types";

const DATA_DIR = join(process.cwd(), "public", "data");

/** 读一个 JSON。读不到就抛，避免页面静默渲染成空。 */
function readJson<T>(relativePath: string): T {
  const full = join(DATA_DIR, relativePath);
  if (!existsSync(full)) {
    throw new Error(
      `缺少数据文件：public/data/${relativePath}\n` +
        `先在仓库根目录跑 \`python scripts/run_pipeline.py --dry-run\` 生成。`,
    );
  }
  return JSON.parse(readFileSync(full, "utf8")) as T;
}

/** 读一个可能不存在的 JSON（条目详情、分类、主题按 id 取，取不到就 404）。 */
function readJsonOptional<T>(relativePath: string): T | null {
  const full = join(DATA_DIR, relativePath);
  if (!existsSync(full)) return null;
  try {
    return JSON.parse(readFileSync(full, "utf8")) as T;
  } catch {
    return null;
  }
}

// ── 站点 ────────────────────────────────────────────────────────────────

export function getSite(): SiteConfig {
  return readJson<SiteConfig>("site.json");
}

export function getManifest(): DataManifest {
  return readJson<DataManifest>("index.json");
}

// ── 精选与全部动态 ──────────────────────────────────────────────────────

export function getAllIndex(): AllIndex {
  return readJson<AllIndex>("all/index.json");
}

export function getMonth(month: string): AllMonth {
  return readJson<AllMonth>(`all/${month}.json`);
}

/** 全部动态（按月份合并，最新在前）。 */
export function getAllItems() {
  const index = getAllIndex();
  return index.months.flatMap((entry) => getMonth(entry.month).items);
}

export function getItem(id: string): ItemDetail | null {
  return readJsonOptional<ItemDetail>(`items/${id}.json`);
}

export function listItemIds(): string[] {
  const dir = join(DATA_DIR, "items");
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((name) => name.endsWith(".json"))
    .map((name) => name.replace(/\.json$/, ""));
}

// ── 分类与主题 ──────────────────────────────────────────────────────────

export function getCategories(): CategoriesIndex {
  return readJson<CategoriesIndex>("categories/index.json");
}

export function getCategory(key: string): CategoryDoc | null {
  return readJsonOptional<CategoryDoc>(`categories/${key}.json`);
}

export function getTopics(): TopicsIndex {
  return readJson<TopicsIndex>("topics/index.json");
}

export function getTopic(slug: string): TopicDoc | null {
  return readJsonOptional<TopicDoc>(`topics/${slug}.json`);
}

// ── 搜索 ────────────────────────────────────────────────────────────────

export function getSearchIndex(): SearchIndexDoc {
  return readJson<SearchIndexDoc>("search-index.json");
}

// ── 展示工具 ────────────────────────────────────────────────────────────
//
// 实现在 `lib/format.ts`（不 import node:fs，客户端组件也能用）。
// 这里重新导出，让服务端代码可以只 import 一个模块。

export {
  categoryLabel,
  displayTitle,
  formatDate,
  formatTime,
  href,
} from "./format";
