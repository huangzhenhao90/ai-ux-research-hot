import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

/**
 * basePath 从 publish 生成的 site.json 取（它的来源是 config/site.yaml 的 siteUrl）。
 *
 * 为什么不直接读 config/site.yaml：web/ 里没有 YAML 依赖，而且 site.json 是流水线
 * 已经算好的权威结果（发布层校验过 basePath == siteUrl 的路径）。
 * 读不到就退回空串，保证 `next dev` 在还没跑过 publish 时也能起来。
 */
function readBasePath() {
  try {
    const raw = readFileSync(join(here, "public", "data", "site.json"), "utf8");
    const site = JSON.parse(raw);
    return typeof site.basePath === "string" ? site.basePath : "";
  } catch {
    return "";
  }
}

const basePath = readBasePath();

/** @type {import('next').NextConfig} */
const nextConfig = {
  // GitHub Pages 只能托管静态文件
  output: "export",
  // Pages 子路径部署（D6 + D7：仓库名 ai-ux-research-hot）
  basePath,
  assetPrefix: basePath || undefined,
  // 静态导出没有图片优化服务
  images: { unoptimized: true },
  // 导出成 /path/index.html，Pages 才能按目录直接命中
  trailingSlash: true,
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
