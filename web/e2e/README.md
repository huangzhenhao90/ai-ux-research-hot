# 端到端测试（浏览器里真点一遍）

覆盖三块最容易回归的功能：**书签与收藏夹**（D19）、**埋点**（D21）和**品牌**（D18：标志、署名与出品方 logo 在子路径下能加载）。不在 CI 里跑（需要 Playwright 的浏览器），改了卡片、收藏、统计相关代码后手动跑。

需要 Playwright（云端环境已预装；本地：`npm i --no-save playwright && npx playwright install chromium`）。
脚本自带一个极小的静态服务器（`serve.mjs`，把 `web/out` 放在 `basePath` 下），不用另起服务。

```bash
cd web

# 书签与收藏夹、品牌：对默认构建跑
npm run build
node e2e/favorites.mjs
node e2e/brand.mjs

# 埋点：不配统计服务时不加载任何第三方脚本
PROVIDER=none node e2e/analytics.mjs

# 埋点：Umami（用替身脚本，不连真实服务；host 必须是下面这个）
NEXT_PUBLIC_ANALYTICS_PROVIDER=umami NEXT_PUBLIC_ANALYTICS_ID=test-site-id \
  NEXT_PUBLIC_ANALYTICS_HOST=http://127.0.0.1:4174 npm run build
PROVIDER=umami node e2e/analytics.mjs

# 埋点：百度统计
NEXT_PUBLIC_ANALYTICS_PROVIDER=baidu NEXT_PUBLIC_ANALYTICS_ID=abc123 npm run build
PROVIDER=baidu node e2e/analytics.mjs

npm run build   # 跑完把默认构建恢复回来
```

统计服务用「按官方文档行为写的替身」拦下来，所以验证的是我们发出了对的调用，**不是**真实服务端的口径。
