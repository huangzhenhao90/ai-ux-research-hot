/**
 * 读仓库根目录 `config/sources.yaml` 的信源名单（只在构建期的 server component 里用）。
 *
 * 为什么不用 YAML 依赖：`web/` 只有 next/react，任务明确要求不引入新依赖；
 * 这里只需要 `- id:` / `name:` / `tier:` 三行，逐行状态机足够，
 * 比引一个 yaml 包更可控（也不用担心锚点、多行标量）。
 *
 * 文件找不到时返回空数组并打一条构建日志，**不让构建挂掉**：
 * 页面会退化成一句说明文字，比整个站点构建失败好。
 */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export interface SourceEntry {
  id: string;
  name: string;
  tier: string;
}

export interface SourceGroup {
  tier: string;
  label: string;
  sources: SourceEntry[];
}

/** 展示顺序：只列参与精选的分级。 */
const TIER_ORDER = ["T1", "T1_5", "T2"];

const TIER_LABEL: Record<string, string> = {
  T1: "T1 · 官方一手：研究工具厂商、研究机构与学术期刊",
  T1_5: "T1.5 · 官方账号与准官方",
  T2: "T2 · 媒体与个人",
};

/** 相对 `process.cwd()`（= `web/`）的候选路径，按顺序试。 */
const CANDIDATE_PATHS: string[][] = [
  ["..", "config", "sources.yaml"],
  ["config", "sources.yaml"],
  ["..", "..", "config", "sources.yaml"],
];

function unquote(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1).trim();
  }
  return trimmed;
}

/** 逐行抽 `- id:` / `    name:` / `    tier:`。 */
export function parseSources(text: string): SourceEntry[] {
  const entries: SourceEntry[] = [];
  let current: Partial<SourceEntry> | null = null;

  const flush = () => {
    if (current?.id && current.name && current.tier) {
      entries.push({
        id: current.id,
        name: current.name,
        tier: current.tier,
      });
    }
    current = null;
  };

  for (const raw of text.split(/\r?\n/)) {
    const idMatch = /^\s*-\s+id:\s*(.+)$/.exec(raw);
    if (idMatch) {
      flush();
      current = { id: unquote(idMatch[1]) };
      continue;
    }
    if (!current) continue;

    const nameMatch = /^ {4}name:\s*(.+)$/.exec(raw);
    if (nameMatch) {
      current.name = unquote(nameMatch[1]);
      continue;
    }

    const tierMatch = /^ {4}tier:\s*(.+)$/.exec(raw);
    if (tierMatch) {
      current.tier = unquote(tierMatch[1]);
    }
  }
  flush();

  return entries;
}

export function readSources(): SourceEntry[] {
  for (const parts of CANDIDATE_PATHS) {
    const file = join(process.cwd(), ...parts);
    if (!existsSync(file)) continue;
    try {
      const parsed = parseSources(readFileSync(file, "utf8"));
      if (parsed.length > 0) return parsed;
    } catch {
      // 换下一个候选路径
    }
  }

  console.warn(
    `[about] 读不到信源名单，试过：${CANDIDATE_PATHS.map((p) => p.join("/")).join("、")}`,
  );
  return [];
}

/** 按分级分组；`EXCLUDE`（只记热度、不参与精选）单独返回。 */
export function groupSources(sources: SourceEntry[]): {
  groups: SourceGroup[];
  excluded: SourceEntry[];
} {
  const byTier = new Map<string, SourceEntry[]>();
  for (const source of sources) {
    const list = byTier.get(source.tier);
    if (list) list.push(source);
    else byTier.set(source.tier, [source]);
  }

  const groups: SourceGroup[] = [];
  for (const tier of TIER_ORDER) {
    const list = byTier.get(tier);
    if (!list?.length) continue;
    groups.push({ tier, label: TIER_LABEL[tier] ?? tier, sources: list });
    byTier.delete(tier);
  }

  const excluded = byTier.get("EXCLUDE") ?? [];
  byTier.delete("EXCLUDE");

  // 兜底：配置里将来新增的分级也不要丢
  for (const [tier, list] of byTier) {
    groups.push({ tier, label: TIER_LABEL[tier] ?? `分级 ${tier}`, sources: list });
  }

  return { groups, excluded };
}
