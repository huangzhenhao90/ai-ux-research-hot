// 极小的静态服务器：把构建好的 web/out 放在 site.json 的 basePath 下提供出来（与 GitHub Pages 一致），给 e2e 用。
// 不依赖任何包。用法见 e2e/README.md。
import { existsSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "out");
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".xml": "application/xml",
  ".txt": "text/plain; charset=utf-8",
};

export function basePathOfBuild() {
  const site = join(OUT, "data", "site.json");
  if (!existsSync(site)) throw new Error("web/out 还没构建：先 cd web && npm run build");
  return JSON.parse(readFileSync(site, "utf8")).basePath ?? "";
}

/** 起服务，返回 { base, origin, close }。base 是带 basePath 的站点根地址。 */
export function startServer() {
  const base = basePathOfBuild();
  const server = createServer((req, res) => {
    let path = decodeURIComponent(new URL(req.url, "http://x").pathname);
    if (base && path.startsWith(base)) path = path.slice(base.length) || "/";
    else if (base) return notFound(res);
    let file = normalize(join(OUT, path));
    if (file !== OUT && !file.startsWith(OUT + sep)) return notFound(res);
    if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
    if (!existsSync(file)) return notFound(res);
    res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
    res.end(readFileSync(file));
  });
  function notFound(res) {
    res.writeHead(404, { "content-type": "text/html; charset=utf-8" });
    res.end(existsSync(join(OUT, "404.html")) ? readFileSync(join(OUT, "404.html")) : "not found");
  }
  return new Promise((resolve) =>
    server.listen(0, "127.0.0.1", () => {
      const origin = `http://127.0.0.1:${server.address().port}`;
      resolve({ origin, base: origin + base, close: () => server.close() });
    }),
  );
}

/** 找 Playwright：先找 web/node_modules，再找全局（云端环境预装）。 */
export async function loadPlaywright() {
  const { createRequire } = await import("node:module");
  const require = createRequire(import.meta.url);
  try {
    return require("playwright");
  } catch {
    throw new Error("找不到 playwright：在 web/ 下 npm i --no-save playwright && npx playwright install chromium");
  }
}
