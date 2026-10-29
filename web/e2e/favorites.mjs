// 端到端：卡片书签 → 收藏夹（本地存储、刷新保留、跨标签同步、导出导入、下架标记、恶意数据）。
// 对默认构建（不带统计环境变量）跑。用法见 e2e/README.md。
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

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
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
const page = await ctx.newPage();
const problems = [];
page.on("console", (m) => {
  if (["error", "warning"].includes(m.type())) problems.push(`${m.type()}: ${m.text()}`);
});
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));

const stored = () => page.evaluate(() => JSON.parse(localStorage.getItem("uxhot-favorites") || "[]"));

// 1. 社招卡片：点书签
await page.goto(`${BASE}/social/`, { waitUntil: "networkidle" });
const firstCard = page.locator("article.card--item").first();
const mark = firstCard.locator("button.bookmark");
ok((await mark.getAttribute("aria-pressed")) === "false", "社招卡片：初始未收藏");
const title = (await firstCard.locator(".card__title").innerText()).trim();
await mark.click();
ok((await mark.getAttribute("aria-pressed")) === "true", "社招卡片：点后变成已收藏");
let list = await stored();
ok(list.length === 1 && list[0].kind === "social" && list[0].title === title, `存储里有这条社招岗位（${list[0]?.key}）`);
ok(list[0].tags.includes("官网"), "快照里带来源标注「官网」");
ok(page.url().endsWith("/social/"), "点书签没有跳进详情页");
ok((await page.locator(".side-link__count").first().innerText()) === "1", "侧栏收藏夹旁显示 1");

// 2. 校招卡片、3. 精选里的资讯卡片
await page.goto(`${BASE}/campus/`, { waitUntil: "networkidle" });
await page.locator("article.card--item button.bookmark").nth(1).click();
await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
await page.locator("article.card--item button.bookmark").first().click();
list = await stored();
ok(list.length === 3 && new Set(list.map((e) => e.kind)).size === 3, "三类各收藏了一条");
ok(list[0].kind === "item", "最新收藏排最前");

// 4. 收藏夹页面（站内导航，不刷新）
await page.locator('a.side-link[href$="/favorites/"]').click();
await page.waitForURL(/\/favorites\/$/);
await page.waitForSelector("article.card--item");
ok((await page.locator("article.card--item").count()) === 3, "收藏夹显示 3 张卡片");
const tabText = await page.locator(".pill-tabs").innerText();
ok(/全部\s*3/.test(tabText) && /资讯\s*1/.test(tabText) && /社招\s*1/.test(tabText) && /校招\s*1/.test(tabText), `分类计数正确：${tabText.replace(/\n/g, " ")}`);
await page.locator(".pill-tabs__tab", { hasText: "社招" }).click();
ok((await page.locator("article.card--item").count()) === 1, "切到社招只剩 1 张");
await page.locator(".pill-tabs__tab", { hasText: "全部" }).click();
await page.locator(".search-box__input").fill("zzzz不存在");
ok((await page.locator("article.card--item").count()) === 0 && (await page.locator(".empty").count()) === 1, "搜不到时给空提示");
await page.locator(".search-box__input").fill("");

// 5. 刷新后仍在；标题链接指向站内详情页
await page.reload({ waitUntil: "networkidle" });
await page.waitForSelector("article.card--item");
ok((await page.locator("article.card--item").count()) === 3, "刷新后收藏还在");
const hrefs = await page.locator("article.card--item .card__title a").evaluateAll((els) => els.map((e) => e.getAttribute("href")));
ok(hrefs.every((h) => /\/(item|social|campus)\/[^/]+\/$/.test(h)), `标题链接到站内详情页：${hrefs.join(" ")}`);

// 6. 导出、清空、导入
const dir = mkdtempSync(join(tmpdir(), "urhot-e2e-"));
const file = join(dir, "export.json");
const [download] = await Promise.all([page.waitForEvent("download"), page.locator("button.link-button", { hasText: "导出" }).click()]);
await download.saveAs(file);
const exported = JSON.parse(readFileSync(file, "utf8"));
ok(exported.entries.length === 3 && exported.app === "urhot", `导出 ${exported.entries.length} 条（文件名 ${download.suggestedFilename()}）`);
page.once("dialog", (d) => d.accept());
await page.locator("button.link-button--danger").click();
await page.waitForSelector(".empty");
ok((await stored()).length === 0, "清空后存储为空");
await page.locator('input[type="file"]').setInputFiles(file);
await page.waitForSelector("article.card--item");
ok((await page.locator("article.card--item").count()) === 3, "导入后恢复 3 条");
ok(/导入了 3 条新收藏/.test(await page.locator("[role=status]").innerText()), "导入后有结果提示");
await page.locator('input[type="file"]').setInputFiles(file);
await page.waitForFunction(() => /已经在收藏夹里/.test(document.querySelector("[role=status]")?.textContent || ""));
ok((await stored()).length === 3, "重复导入不会产生重复条目");

// 7. 在收藏夹里移除一条
await page.locator("article.card--item button.bookmark").first().click();
ok((await page.locator("article.card--item").count()) === 2 && (await stored()).length === 2, "在收藏夹里点书签 = 移出");

// 8. 下架标记与恶意数据
await page.evaluate(() => {
  const now = new Date().toISOString();
  localStorage.setItem(
    "uxhot-favorites",
    JSON.stringify([
      { kind: "social", id: "ghost-123", title: "已下架的岗位", subtitle: "某公司", tags: ["北京"], url: "https://example.com/job/1", savedAt: now },
      { kind: "item", id: "evil-1", title: "恶意链接", subtitle: "x", tags: [], url: "javascript:alert(1)", savedAt: now },
      { kind: "weird", id: "x", title: "未知类型", savedAt: now },
      { kind: "item", id: "../../etc", title: "非法 id", savedAt: now },
      "not an object",
    ]),
  );
});
await page.reload({ waitUntil: "networkidle" });
await page.waitForSelector("article.card--item");
ok((await page.locator("article.card--item").count()) === 2, "非法条目（未知类型、非法 id、非对象）被丢弃");
const ghost = page.locator("article.card--item", { hasText: "已下架的岗位" });
ok((await ghost.locator(".badge--gone").innerText()) === "已下架", "站内已没有的岗位标「已下架」");
ok((await ghost.locator(".card__title a").getAttribute("href")) === "https://example.com/job/1", "已下架岗位的标题改链官方页面");
const evil = page.locator("article.card--item", { hasText: "恶意链接" });
ok((await evil.locator("a[href^='javascript']").count()) === 0 && (await evil.locator(".card__origin").count()) === 0, "javascript: 链接被清掉，不渲染成链接");

// 9. 跨标签同步
await page.evaluate(() => localStorage.removeItem("uxhot-favorites"));
const a = await ctx.newPage();
const b = await ctx.newPage();
await a.goto(`${BASE}/social/`, { waitUntil: "networkidle" });
await b.goto(`${BASE}/social/`, { waitUntil: "networkidle" });
await a.locator("article.card--item button.bookmark").first().click();
await b.waitForFunction(() => document.querySelector("article.card--item button.bookmark")?.getAttribute("aria-pressed") === "true", null, { timeout: 5000 });
ok(true, "另一个标签页里的同一张卡片跟着变成已收藏");

// 10. 控制台里没有水合不一致等报错
const real = problems.filter((p) => !/favicon|Failed to load resource/.test(p));
ok(real.length === 0, `控制台没有报错或警告${real.length ? "：" + real.join(" | ") : ""}`);

await browser.close();
server.close();
console.log(failed ? `\n${failed} 项失败` : "\n全部通过");
process.exit(failed ? 1 : 0);
