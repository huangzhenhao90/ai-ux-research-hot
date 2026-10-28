#!/usr/bin/env node
/**
 * 同步「用研校招」岗位库：从 uxr-campus-2027 仓库的 index.html 抽出岗位与公司数据，
 * 写成 `web/content/campus.json`，供 /campus/ 页面在构建期读取。
 *
 * 为什么从 HTML 里抽：那个仓库是单文件静态页，数据就是页面里的 `const JOBS = [...]`
 * 与 `const COMPANIES = [...]`（外加几行 Object.assign 补丁）。它自己的数据测试
 * （car-data.test.cjs）也是按同样的边界切片后在 vm 里求值，这里沿用同一个口径。
 * 校招数据只在那个仓库里维护，这边只读、不改。
 *
 * ⚠️ vm 不是安全沙箱，这里只执行作者本人仓库里的数据片段，并设了超时。
 *
 * 用法：
 *   node web/scripts/sync-campus.mjs                    # 从 GitHub 拉 main 分支
 *   node web/scripts/sync-campus.mjs path/to/index.html # 用本地文件
 *
 * 抽取或校验失败时退出码非 0，且**不改动**已有的 campus.json（保留上一版）。
 * 内容没变时也不重写文件，免得每次定时任务都产生一次无意义的提交。
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const REPO = "huangzhenhao90/uxr-campus-2027";
const DEFAULT_SOURCE = `https://raw.githubusercontent.com/${REPO}/main/index.html`;
const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "content", "campus.json");

// 与原站 hasAiRequirement / hasMultipleHires 同一口径
const AI_PATTERN = /AI|人工智能|大模型|AIGC/i;

async function readSource(arg) {
  if (arg && !/^https?:\/\//.test(arg)) return readFileSync(arg, "utf8");
  const url = arg || DEFAULT_SOURCE;
  const res = await fetch(url, { signal: AbortSignal.timeout(30_000) });
  if (!res.ok) throw new Error(`拉取失败：HTTP ${res.status} ${url}`);
  return res.text();
}

function extract(html) {
  const start = html.indexOf("const JOBS =");
  const end = html.indexOf("/* ---------------- 状态");
  if (start < 0 || end < 0 || end <= start) {
    throw new Error("页面结构变了：找不到 `const JOBS =` 或「状态」分隔注释");
  }
  const { jobs, companies } = vm.runInNewContext(
    `${html.slice(start, end)};({ jobs: JOBS, companies: COMPANIES })`,
    {},
    { timeout: 2000 },
  );
  // 页脚「内容更新：2026-09-18（…）」，取不到就留空
  const updated = html.match(/内容更新：\s*(\d{4}-\d{2}-\d{2})/)?.[1] ?? null;
  return { jobs, companies, updated };
}

const text = (value) => (typeof value === "string" ? value.trim() : "");
const optional = (value) => text(value) || null;

function normalize({ jobs, companies, updated }) {
  const problems = [];
  if (!Array.isArray(jobs) || jobs.length === 0) problems.push("JOBS 为空");
  if (!Array.isArray(companies) || companies.length === 0) problems.push("COMPANIES 为空");
  if (problems.length) throw new Error(problems.join("；"));

  const names = new Set(companies.map((c) => text(c.name)));
  const ids = new Set();
  const outJobs = jobs.map((j, index) => {
    const id = text(j.id);
    for (const key of ["id", "co", "title", "industry", "type", "url", "jd"]) {
      if (!text(j[key])) problems.push(`第 ${index + 1} 条岗位缺「${key}」`);
    }
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(id)) problems.push(`岗位 id 不能当路径：${id}`);
    if (ids.has(id)) problems.push(`岗位 id 重复：${id}`);
    ids.add(id);
    if (!/^https?:\/\//.test(text(j.url))) problems.push(`${id} 的链接不是 http(s)`);
    if (!names.has(text(j.co))) problems.push(`${id} 的公司「${j.co}」不在公司库里`);
    const flags = Array.isArray(j.flags) ? j.flags.map(text).filter(Boolean) : [];
    const headcount = text(j.num);
    const hires = headcount.match(/^(\d+)\s*人$/);
    return {
      id,
      company: text(j.co),
      title: text(j.title),
      industry: text(j.industry),
      type: text(j.type),
      location: optional(j.loc),
      headcount: headcount || null,
      degree: optional(j.degree),
      url: text(j.url),
      flags,
      tagline: optional(j.tagline),
      business: optional(j.business),
      jd: text(j.jd),
      analysis: optional(j.analysis),
      advice: optional(j.advice),
      cohortNote: optional(j.cohortNote),
      verificationNote: optional(j.verificationNote),
      checkedAt: optional(j.checkedAt),
      ai: flags.some((f) => AI_PATTERN.test(f)) || AI_PATTERN.test(text(j.jd)),
      multipleHires: !!hires && Number(hires[1]) > 1,
    };
  });

  const outCompanies = companies.map((c) => {
    const name = text(c.name);
    if (!name) problems.push("公司库里有一家没名字");
    if (!["open", "pending"].includes(c.status)) problems.push(`${name} 的状态未知：${c.status}`);
    return {
      name,
      mark: optional(c.mark) ?? name.slice(0, 1),
      industry: text(c.industry),
      status: c.status,
      recruitment: optional(c.recruitment),
      research: optional(c.research),
      url: optional(c.url),
      checkedAt: optional(c.checkedAt),
      jobCount: outJobs.filter((j) => j.company === name).length,
    };
  });

  if (problems.length) throw new Error(problems.join("；"));
  return {
    source: {
      repo: REPO,
      repoUrl: `https://github.com/${REPO}`,
      siteUrl: "https://huangzhenhao90.github.io/uxr-campus-2027/",
      updated,
    },
    jobs: outJobs,
    companies: outCompanies,
  };
}

async function main() {
  const doc = normalize(extract(await readSource(process.argv[2])));
  const body = `${JSON.stringify(doc, null, 2)}\n`;
  if (existsSync(OUT) && readFileSync(OUT, "utf8") === body) {
    console.log(`校招岗位库无变化（${doc.jobs.length} 个岗位 / ${doc.companies.length} 家公司）`);
    return;
  }
  mkdirSync(dirname(OUT), { recursive: true });
  writeFileSync(OUT, body);
  console.log(
    `已同步校招岗位库：${doc.jobs.length} 个岗位 / ${doc.companies.length} 家公司（内容更新 ${doc.source.updated ?? "未知"}）`,
  );
}

main().catch((error) => {
  console.error(`✗ 同步校招岗位库失败，保留上一版：${error.message}`);
  process.exitCode = 1;
});
