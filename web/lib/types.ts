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

export interface DataManifest {
  generatedAt: string;
  counts: Record<string, number>;
  months: string[];
  latestDays: string[];
}

// ── 用研校招（数据来自 uxr-campus-2027，见 web/scripts/sync-campus.mjs）──────

export interface CampusJob {
  id: string;
  company: string;
  title: string;
  industry: string;
  /** 战略/策略向、交互/设计向、体验管理向、不确定 */
  type: string;
  location: string | null;
  headcount: string | null;
  degree: string | null;
  url: string;
  flags: string[];
  tagline: string | null;
  business: string | null;
  jd: string;
  analysis: string | null;
  advice: string | null;
  cohortNote: string | null;
  verificationNote: string | null;
  checkedAt: string | null;
  /** 职责或标签里写了 AI / 大模型 / AIGC */
  ai: boolean;
  /** 明确招 2 人及以上 */
  multipleHires: boolean;
}

export interface CampusCompany {
  name: string;
  mark: string;
  industry: string;
  /** open = 27 届正式校招已开；pending = 尚未确认正式批 */
  status: "open" | "pending";
  recruitment: string | null;
  research: string | null;
  url: string | null;
  checkedAt: string | null;
  jobCount: number;
}

export interface CampusDoc {
  source: { repo: string; repoUrl: string; siteUrl: string; updated: string | null };
  jobs: CampusJob[];
  companies: CampusCompany[];
}

// ── 用研社招（web/content/social.json，由 scripts/sync_social.py 生成）────────

export interface SocialJob {
  id: string;
  company: string;
  title: string;
  url: string;
  cities: string[];
  department: string | null;
  experience: string | null;
  /** 官网给的日期是哪一种：publish = 首次发布；update = 最近更新 / 刷新 */
  dateKind: "publish" | "update";
  /** 官网这次给的日期（会随刷新变） */
  postedAt: string;
  /** 窗口起算日：第一次看到时官网给的日期，之后不变 */
  since: string;
  /** 本站第一次看到 */
  firstSeen: string;
  /** 满 90 天后移出的日期 */
  expiresAt: string;
  duty: string;
  requirement: string;
}

export interface SocialCompany {
  key: string;
  name: string;
  careers: string;
  /** 最近一次抓取是否成功 */
  ok: boolean;
  lastOkAt: string | null;
  jobCount: number;
}

export interface SocialDoc {
  updatedAt: string | null;
  window: { admitDays: number; keepDays: number };
  companies: SocialCompany[];
  jobs: SocialJob[];
}
