// 端到端：埋点。对不同环境变量构建出来的站点各跑一次（见 e2e/README.md）：
//   PROVIDER=none   默认构建：百度统计已写进每个页面（站点 ID 见 web/lib/baidu.ts）
//   PROVIDER=baidu  与默认构建相同（站点 ID 不再由环境变量覆盖）
//   PROVIDER=umami  NEXT_PUBLIC_ANALYTICS_PROVIDER=umami NEXT_PUBLIC_ANALYTICS_ID=test-site-id NEXT_PUBLIC_ANALYTICS_HOST=http://127.0.0.1:4174
// 统计服务用「按文档行为写的替身脚本」拦下来，不会连真实服务；所以验证的是：我们按文档的用法发出了对的调用。
import { loadPlaywright, startServer } from "./serve.mjs";

const { chromium } = await loadPlaywright();
const server = await startServer();
const BASE = server.base;
const PROVIDER = process.env.PROVIDER || "none";
const BAIDU_SRC = "https://hm.baidu.com/hm.js?83c75a4bd0be4caa753d999c2313e715";
let failed = 0;
const ok = (cond, msg) => {
  console.log(`${cond ? "✓" : "✗"} ${msg}`);
  if (!cond) failed += 1;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sameOrigin = (u) => u.startsWith(server.origin);

const FAKE_UMAMI = `
  window.__umami = [];
  window.umami = { track: (a, b) => {
    if (typeof a === "function") window.__umami.push({ pageview: a({ url: "/default", title: "t" }) });
    else window.__umami.push({ event: a, data: b });
  } };
`;

async function newContext(browser, { dnt = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const requests = [];
  ctx.on("request", (r) => requests.push(r.url()));
  // 站点自己以外的请求一律拦掉：统计脚本换成替身，外链只看是否点到
  await ctx.route((url) => !sameOrigin(url.href), async (route) => {
    const url = route.request().url();
    if (url.startsWith("http://127.0.0.1:4174/script.js")) {
      return route.fulfill({ contentType: "text/javascript", body: FAKE_UMAMI });
    }
    if (url.startsWith("https://hm.baidu.com/hm.js")) {
      return route.fulfill({ contentType: "text/javascript", body: "/* fake hm.js */" });
    }
    return route.fulfill({ status: 200, contentType: "text/html", body: "external" });
  });
  if (dnt) await ctx.addInitScript(() => Object.defineProperty(navigator, "doNotTrack", { value: "1" }));
  return { ctx, requests };
}

const browser = await chromium.launch();

const read = (page) =>
  PROVIDER === "umami"
    ? page.evaluate(() => window.__umami)
    : page.evaluate(() => (window._hmt || []).map((x) => x.map((v) => (v === undefined ? null : v))));

const { ctx, requests } = await newContext(browser);
const page = await ctx.newPage();
await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
await sleep(300);

ok(requests.some((u) => u === BAIDU_SRC), "每个页面都从 <head> 加载百度统计");
if (PROVIDER === "umami") {
  ok(requests.some((u) => u.startsWith("http://127.0.0.1:4174/script.js")), "加载了 Umami 脚本（走配置的 host）");
  const tag = await page.evaluate(() => {
    const s = document.querySelector('script[src$="/script.js"]');
    return { id: s?.dataset.websiteId, auto: s?.dataset.autoTrack, dnt: s?.dataset.doNotTrack };
  });
  ok(tag.id === "test-site-id" && tag.auto === "false" && tag.dnt === "true", `脚本参数：website-id、auto-track=false、do-not-track（${JSON.stringify(tag)}）`);
}

const pathname = (p) => new URL(`${BASE}${p}`).pathname;
let ev = await read(page);
if (PROVIDER === "umami") {
  const views = ev.filter((e) => e.pageview);
  ok(views.length === 1 && views[0].pageview.url === pathname("/"), `进站记 1 次页面浏览（url=${views[0]?.pageview.url}）`);
  ok(ev.some((e) => e.event === "feature_view" && e.data.feature === "home"), "feature_view {feature: home}");
} else {
  ok(!ev.some((e) => e[0] === "_trackPageview"), "百度统计：首次进站由 hm.js 自己记，不重复手动记");
  ok(ev.some((e) => e[0] === "_trackEvent" && e[1] === "feature_view" && e[2] === "home"), "feature_view → _trackEvent(feature_view, home)");
}

// 换页：侧栏点到社招
await page.locator('a.side-link[href$="/social/"]').click();
await page.waitForURL(/\/social\/$/);
await sleep(300);
ev = await read(page);
if (PROVIDER === "umami") {
  const views = ev.filter((e) => e.pageview);
  ok(views.length === 2 && views.at(-1).pageview.url === pathname("/social/"), "换页后补记 1 次页面浏览，url 是新页面");
  ok(ev.some((e) => e.event === "feature_view" && e.data.feature === "social"), "feature_view {feature: social}");
} else {
  const views = ev.filter((e) => e[0] === "_trackPageview");
  ok(views.length === 1 && views[0][1] === pathname("/social/"), "百度统计：换页手动补记 1 次 _trackPageview");
}

// 筛选写进链接（replaceState）不能被算成页面浏览
await page.locator(".chip", { hasText: "腾讯" }).click();
await page.locator(".chip", { hasText: "阿里巴巴" }).click();
await sleep(300);
ev = await read(page);
const pv = PROVIDER === "umami" ? ev.filter((e) => e.pageview).length : ev.filter((e) => e[0] === "_trackPageview").length;
ok(pv === (PROVIDER === "umami" ? 2 : 1), `点筛选（URL 被 replaceState 改写）没有多记页面浏览（共 ${pv} 次）`);
const filters = PROVIDER === "umami" ? ev.filter((e) => e.event === "filter") : ev.filter((e) => e[1] === "filter");
ok(filters.length === 2, `每次筛选记 1 次 filter 事件（${filters.length}）`);
if (PROVIDER === "umami") ok(filters[0].data.tab === "social" && filters[0].data.by === "company", `filter 参数：${JSON.stringify(filters[0].data)}`);
else ok(filters[0][2] === "social" && filters[0][3] === "company", "filter → (filter, social, company)");

// 书签
await page.locator("article.card--item button.bookmark").first().click();
await sleep(200);
ev = await read(page);
const bm = PROVIDER === "umami" ? ev.find((e) => e.event === "bookmark") : ev.find((e) => e[1] === "bookmark");
if (PROVIDER === "umami") ok(bm && bm.data.action === "add" && bm.data.kind === "social" && bm.data.where === "card", `bookmark ${JSON.stringify(bm?.data)}`);
else ok(bm && bm[2] === "add" && bm[3] === "social|card", `bookmark → ${JSON.stringify(bm)}`);

// 外链点击（data-track 统一监听）
const popup = ctx.waitForEvent("page");
await page.locator("article.card--item a.card__origin").first().click();
(await popup).close();
await sleep(200);
ev = await read(page);
const out = PROVIDER === "umami" ? ev.find((e) => e.event === "outbound") : ev.find((e) => e[1] === "outbound");
if (PROVIDER === "umami") ok(out && out.data.kind === "job_apply" && out.data.tab === "social", `outbound ${JSON.stringify(out?.data)}`);
else ok(out && out[2] === "job_apply" && out[3] === "social", `outbound → ${JSON.stringify(out)}`);

// 外观切换
await page.locator('button[role="radio"][title="深色"]').first().click();
await sleep(200);
ev = await read(page);
ok(ev.some((e) => (PROVIDER === "umami" ? e.event === "theme" && e.data.theme === "dark" : e[1] === "theme" && e[2] === "dark")), "theme {theme: dark}");

// 搜索：停顿后记一次，不带关键词
await page.locator(".search-box__input").fill("用户研究");
await sleep(1200);
ev = await read(page);
const searches = PROVIDER === "umami" ? ev.filter((e) => e.event === "search") : ev.filter((e) => e[1] === "search");
ok(searches.length === 1, `输入停顿后记 1 次 search（${searches.length}）`);
ok(!JSON.stringify(ev).includes("用户研究"), "事件里不带搜索关键词");

// RSS 链接（服务端渲染的链接也能埋点）
const rssPage = await ctx.newPage();
await rssPage.goto(`${BASE}/about/`, { waitUntil: "networkidle" });
// 只看事件有没有发出：拦掉点击后的跳转（冒泡阶段的 preventDefault 不影响捕获阶段的埋点监听）
await rssPage.evaluate(() => document.addEventListener("click", (e) => e.preventDefault()));
await rssPage.locator('footer a[data-track="rss"]').click();
await sleep(200);
ev = await read(rssPage);
ok(ev.some((e) => (PROVIDER === "umami" ? e.event === "rss" && e.data.where === "footer" : e[1] === "rss" && e[2] === "footer")), "rss {where: footer}");

// 请勿跟踪：百度统计的安装代码仍在页面里；Umami 不加载
const dnt = await newContext(browser, { dnt: true });
const p2 = await dnt.ctx.newPage();
await p2.goto(`${BASE}/`, { waitUntil: "networkidle" });
ok(
  dnt.requests.every((u) => sameOrigin(u) || u === BAIDU_SRC),
  "请勿跟踪：除页面里的百度统计安装代码外，不加载别的统计脚本",
);
if (PROVIDER === "umami") {
  ok(!dnt.requests.some((u) => u.includes("/script.js")), "请勿跟踪：不加载 Umami");
}

// 脚本还没加载好时的事件会排队，加载后补发（Umami）
if (PROVIDER === "umami") {
  const slow = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await slow.route((url) => !sameOrigin(url.href), async (route) => {
    await sleep(800);
    await route.fulfill({ contentType: "text/javascript", body: FAKE_UMAMI });
  });
  const p3 = await slow.newPage();
  await p3.goto(`${BASE}/social/`, { waitUntil: "domcontentloaded" });
  await p3.waitForSelector("article.card--item button.bookmark");
  await p3.locator("article.card--item button.bookmark").first().click();
  await p3.waitForFunction(() => window.__umami && window.__umami.length >= 3, null, { timeout: 5000 });
  const queued = await p3.evaluate(() => window.__umami);
  ok(queued.some((e) => e.pageview) && queued.some((e) => e.event === "bookmark"), "脚本晚到：之前的页面浏览与点击事件排队后补发");
}

await browser.close();
server.close();
console.log(failed ? `\n${failed} 项失败` : "\n全部通过");
process.exit(failed ? 1 : 0);
