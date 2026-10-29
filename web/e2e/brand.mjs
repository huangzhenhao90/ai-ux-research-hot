// 端到端：品牌。URhot 标志、「真知浩见出品」署名里的出品方 logo 在站点子路径下真的能加载（basePath 写错时图会 404）。
// 对默认构建跑。用法见 e2e/README.md。
import { loadPlaywright, startServer } from "./serve.mjs";

const { chromium } = await loadPlaywright();
const server = await startServer();
const BASE = server.base;
let failed = 0;
const ok = (cond, msg) => {
  console.log(`${cond ? "✓" : "✗"} ${msg}`);
  if (!cond) failed += 1;
};

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
const failedRequests = [];
page.on("response", (r) => {
  if (r.status() >= 400) failedRequests.push(`${r.status()} ${r.url()}`);
});

const logoState = (selector) =>
  page.evaluate((sel) => {
    const img = document.querySelector(sel);
    return img ? { loaded: img.complete && img.naturalWidth > 0, w: img.naturalWidth, alt: img.getAttribute("alt"), src: img.getAttribute("src") } : null;
  }, selector);

await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
const side = await logoState(".sidebar .byline__logo");
ok(side?.loaded && side.w === 96 && side.alt === "", `侧栏署名里的出品方 logo 已加载（${side?.src}，装饰图 alt 为空）`);
ok((await page.locator(".sidebar .byline").innerText()).trim() === "真知浩见出品", "侧栏署名文字是「真知浩见出品」");
ok((await page.locator(".site-footer").innerText()).includes("真知浩见出品"), "页脚写了「真知浩见出品」");
ok((await page.locator(".sidebar .logo-mark").count()) === 1, "侧栏有 URhot 标志");

// 侧栏里别名（AI 用研热点）要和上面的字标那一行左右对齐；读屏软件读到的是完整别名
const aligned = await page.evaluate(() => {
  const rect = (el) => el.getBoundingClientRect();
  const words = [...document.querySelectorAll(".sidebar__alias > span:not(.sr-only)")];
  if (!words.length) return null;
  const boxes = words.map(rect);
  return {
    left: Math.min(...boxes.map((b) => b.left)) - rect(document.querySelector(".sidebar .logo-mark")).left,
    right: Math.max(...boxes.map((b) => b.right)) - rect(document.querySelector(".sidebar .wordmark__text")).right,
    visible: words.map((el) => el.textContent).join(""),
    spoken: document.querySelector(".sidebar__alias .sr-only")?.textContent ?? "",
  };
});
ok(aligned && Math.abs(aligned.left) < 0.5 && Math.abs(aligned.right) < 0.5, `侧栏别名与字标左右对齐（左差 ${aligned?.left.toFixed(2)}px，右差 ${aligned?.right.toFixed(2)}px）`);
ok(aligned && aligned.spoken.trim() !== "" && aligned.visible === aligned.spoken.replace(/\s/g, ""), `摊开的字拼起来就是别名「${aligned?.spoken}」，读屏读的也是它`);
const icon = await page.getAttribute('link[rel="icon"]', "href");
ok(!!icon && /icon\.svg/.test(icon) && icon.startsWith(new URL(BASE).pathname), `浏览器标签页图标指向子路径下的 icon.svg（${icon}）`);

await page.goto(`${BASE}/about/`, { waitUntil: "networkidle" });
const about = await logoState(".brand-hero .byline__logo");
ok(about?.loaded && about.w === 192, `关于页大号署名用 192px 的 logo（${about?.src}）`);

// 手机宽度：顶栏里的署名也带 logo
await page.setViewportSize({ width: 390, height: 800 });
await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
const phone = await logoState(".phonebar .byline__logo");
ok(phone?.loaded, "手机顶栏的署名里有 logo 且已加载");

ok(failedRequests.length === 0, `没有 4xx / 5xx 请求${failedRequests.length ? "：" + failedRequests.join(" | ") : ""}`);

await browser.close();
server.close();
console.log(failed ? `\n${failed} 项失败` : "\n全部通过");
process.exit(failed ? 1 : 0);
