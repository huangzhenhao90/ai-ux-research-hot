/**
 * 发布层产出的公开数据结构。
 *
 * ⚠️ 这些类型必须与 `uxhot/publish/build_site_data.py` 的字段白名单一致。
 * 改发布层字段时这里要跟着改，否则 typecheck 会先报错。
 *
 * 注意：公开产物**不含原文全文**（`body`），也不含评分（`showScore: false`）。
 */

/** 一条公开条目（列表/卡片用）。 */
export interface PublicItem {
  id: string;
  sourceId: string;
  sourceName: string;
  tier: string;
  url: string;
  title: string;
  titleZh: string | null;
  summaryZh: string | null;
  reason: string | null;
  category: string | null;
  tags: string[];
  entities: string[];
  itemType: string | null;
  publishedAt: string | null;
  discoveredAt: string | null;
  status: string;
  dupOf: string | null;
  relation: string | null;
}

/** 详情页：比列表多一个「同一事件的其他报道」。 */
export interface ItemDetail extends PublicItem {
  related: RelatedRef[];
}

export interface RelatedRef {
  id: string;
  titleZh: string | null;
  title: string;
  url: string;
  sourceName: string;
  relation: string | null;
}

export interface SiteConfig {
  name: string;
  alias: string;
  subject: string;
  siteUrl: string;
  basePath: string;
  homeTitle: string;
  description: string;
  tagline: string;
  reasonLabel: string;
  showScore: boolean;
  locale: string;
  timezone: string;
  editions: Record<string, string>;
  credit: string;
}

export interface LatestDoc {
  generatedAt: string;
  windowDays: number;
  editionHour: number;
  days: LatestDay[];
}

export interface LatestDay {
  date: string;
  count: number;
  items: PublicItem[];
}

export interface AllIndex {
  generatedAt: string;
  total: number;
  months: { month: string; count: number; path: string }[];
}

export interface AllMonth {
  month: string;
  count: number;
  items: PublicItem[];
}

export interface CategoryMeta {
  key: string;
  label: string;
  section: string;
  commentary: boolean;
  count: number;
}

export interface CategoriesIndex {
  generatedAt: string;
  categories: CategoryMeta[];
}

export interface CategoryDoc extends CategoryMeta {
  items: PublicItem[];
}

export interface TopicGroup {
  key: string;
  name: string;
  blurb: string;
}

export interface TopicMeta {
  slug: string;
  name: string;
  group: string;
  definition: string;
  count: number;
  entityId?: string;
  tags?: string[];
}

export interface TopicsIndex {
  generatedAt: string;
  groups: TopicGroup[];
  topics: TopicMeta[];
}

export interface TopicDoc extends TopicMeta {
  items: PublicItem[];
}

export interface SearchIndexItem {
  id: string;
  title: string;
  titleZh: string | null;
  summaryZh: string | null;
  tags: string[];
  entities: string[];
  category: string | null;
  sourceName: string;
  url: string;
  publishedAt: string | null;
}

export interface SearchIndexDoc {
  count: number;
  items: SearchIndexItem[];
}

/** 日报里引用一条精选的最小字段集（见 docs/report-schema.md）。 */
export interface ItemRef {
  id: string;
  titleZh: string;
  summaryZh: string;
  reason: string | null;
  category: string | null;
  categoryLabel: string | null;
  sourceId: string;
  sourceName: string;
  tier: string;
  url: string;
  publishedAt: string | null;
  avgScore: number | null;
  importance: number | null;
  tags: string[];
  relatedIds: string[];
}

export interface BriefRef {
  id: string;
  titleZh: string;
  url: string;
  sourceId: string;
  sourceName: string;
}

export interface DailyReport {
  kind: "daily";
  date: string;
  siteName: string;
  generatedAt: string;
  window: { start: string; end: string };
  empty: boolean;
  stats: { selectedCount: number; newTools: number; briefCount: number };
  headline: ItemRef | null;
  highlights: ItemRef[];
  sections: { key: string; label: string; items: ItemRef[] }[];
  briefs: BriefRef[];
}

export interface WeeklyReport {
  kind: "weekly";
  week: string;
  siteName: string;
  generatedAt: string;
  window: { start: string; end: string };
  overview: string;
  overviewSource: "model" | "template";
  stats: { itemCount: number; dailyCount: number };
  sections: { key: string; label: string; lead: string; items: ItemRef[] }[];
}

export interface ReportIndexEntry {
  date?: string;
  week?: string;
  url: string;
  count: number | null;
  title: string | null;
}

export interface ReportIndex {
  generatedAt: string;
  kind: "daily" | "weekly";
  count: number;
  entries: ReportIndexEntry[];
}

export interface DataManifest {
  generatedAt: string;
  counts: Record<string, number>;
  months: string[];
  latestDays: string[];
}
