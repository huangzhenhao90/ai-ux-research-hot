/**
 * 埋点（DECISIONS D21）：了解各个功能的 PV（次数）与 UV（人数）。
 *
 * 站点是静态导出、没有后端，统计交给第三方统计服务（Umami 或百度统计），这里只做一层很薄的封装：
 * 页面上到处调 `track(事件名, 参数)`，由这里转成统计服务认识的调用。
 * 没配统计服务（没设 `NEXT_PUBLIC_ANALYTICS_*`，本地开发、PR 预览都是这样）时，
 * 所有函数都是空操作：不加载任何脚本、不发任何请求、不写任何 cookie。
 * 访客开着浏览器的「请勿跟踪」（Do Not Track）时同样什么都不发。
 *
 * ── 埋点清单（参数顺序即百度统计里 action / label 的顺序）────────────────────
 *
 *   feature_view    {feature}                 进入某个功能页（每次换页一次）。feature 见 `featureOf`
 *   bookmark        {action, kind, where}     收藏 / 取消收藏；action = add | remove；kind = item | social | campus；
 *                                             where = card | detail | favorites
 *   favorites       {action}                  收藏夹里的管理操作：export | import | clear
 *   search          {scope, found}            搜索（输入停顿后记一次，不记关键词）；found = 有没有结果；
 *                                             信息流顶部的搜索框是提交时记一次，不带 found
 *   filter          {tab, by}                 筛选；tab = feed | social | campus | favorites；by = category | date | age | origin | ...
 *   outbound        {kind, tab}               点站外链接（原文、官方投递、公司招聘官网……）
 *   load_more       {tab}                     「加载更多」
 *   theme           {theme}                   切换外观
 *   rss             {where}                   点 RSS 订阅；where = sidebar | footer | home | about
 *
 * 页面上不用写 JS 的链接，直接加属性：`data-track="outbound" data-track-kind="item_origin" data-track-tab="feed"`，
 * `components/Analytics.tsx` 里有一个统一的点击监听，把 `data-track-*` 转成参数（顺序按属性出现的顺序）。
 *
 * 不记录：搜索关键词、标题、任何能认出个人的信息。
 */

export type TrackData = Record<string, string | number | boolean>;

type Provider = "umami" | "baidu";

const PROVIDER = process.env.NEXT_PUBLIC_ANALYTICS_PROVIDER;
const SITE_ID = process.env.NEXT_PUBLIC_ANALYTICS_ID ?? "";
const SCRIPT_HOST = (process.env.NEXT_PUBLIC_ANALYTICS_HOST ?? "").replace(/\/+$/, "");

/** 构建时就定下来：配了统计服务才算启用。 */
export const analyticsProvider: Provider | null =
  (PROVIDER === "umami" || PROVIDER === "baidu") && SITE_ID ? PROVIDER : null;

declare global {
  interface Window {
    umami?: {
      track: (
        eventOrPayload?: string | ((props: Record<string, unknown>) => Record<string, unknown>),
        data?: TrackData,
      ) => void;
    };
    _hmt?: unknown[][];
  }
}

/** 路径（不含 basePath）→ 功能名。详情页按类型归并，不按具体条目拆开。 */
export function featureOf(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  switch (parts[0]) {
    case undefined:
      return "home";
    case "all":
    case "topics":
    case "search":
    case "campus":
    case "social":
    case "favorites":
    case "about":
      return parts.length > 1 ? `${parts[0]}_detail` : parts[0];
    case "category":
      return "category";
    case "item":
      return "item_detail";
    default:
      return "other";
  }
}

function doNotTrack(): boolean {
  const nav = navigator as Navigator & { msDoNotTrack?: string };
  const win = window as Window & { doNotTrack?: string };
  return nav.doNotTrack === "1" || win.doNotTrack === "1" || nav.msDoNotTrack === "1";
}

let started = false;
/** Umami 的脚本是异步加载的，加载完之前的调用先排队。 */
let umamiQueue: (() => void)[] | null = null;

/** 加载统计脚本（只会做一次）。返回是否启用。 */
export function startAnalytics(): boolean {
  if (started) return true;
  if (!analyticsProvider || typeof window === "undefined" || doNotTrack()) return false;
  started = true;

  const script = document.createElement("script");
  script.async = true;
  if (analyticsProvider === "umami") {
    umamiQueue = [];
    script.src = `${SCRIPT_HOST || "https://cloud.umami.is"}/script.js`;
    script.dataset.websiteId = SITE_ID;
    // 页面浏览由我们按「换页」手动发：Umami 默认还会盯着 history.replaceState，
    // 而筛选条件会写进链接（replaceState），那样同一页会被记成很多次浏览
    script.dataset.autoTrack = "false";
    script.dataset.doNotTrack = "true";
    script.addEventListener("load", () => {
      const queued = umamiQueue ?? [];
      umamiQueue = null;
      queued.forEach((run) => run());
    });
  } else {
    window._hmt = window._hmt ?? [];
    script.src = `https://hm.baidu.com/hm.js?${SITE_ID}`;
  }
  document.head.appendChild(script);
  return true;
}

function umamiDo(run: () => void): void {
  if (umamiQueue) umamiQueue.push(run);
  else run();
}

/**
 * 记一次页面浏览。
 * 百度统计的脚本自己会记第一次进站，之后的换页才要手动补（`first` 为 true 时跳过）。
 */
export function trackPageview(first: boolean): void {
  if (!started) return;
  const path = window.location.pathname;
  if (analyticsProvider === "umami") {
    umamiDo(() => window.umami?.track((props) => ({ ...props, url: path })));
  } else if (!first) {
    window._hmt?.push(["_trackPageview", path]);
  }
}

/** 记一个事件。没启用时什么都不做。 */
export function track(name: string, data: TrackData = {}): void {
  if (!started) return;
  if (analyticsProvider === "umami") {
    umamiDo(() => window.umami?.track(name, data));
  } else {
    // 百度统计的事件是 (类别, 操作, 标签)：类别 = 事件名，操作 = 第一个参数，标签 = 其余参数
    const values = Object.values(data).map(String);
    window._hmt?.push(["_trackEvent", name, values[0] ?? name, values.slice(1).join("|") || undefined]);
  }
}

/** 把元素上的 `data-track-*` 转成参数（`data-track-kind="x"` → `{ kind: "x" }`），保持属性顺序。 */
export function dataFromElement(el: HTMLElement): TrackData {
  const data: TrackData = {};
  for (const attr of Array.from(el.attributes)) {
    const match = /^data-track-(.+)$/.exec(attr.name);
    if (match) data[match[1]] = attr.value;
  }
  return data;
}
