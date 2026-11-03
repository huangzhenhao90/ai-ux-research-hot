import type { groupByDay } from "./format";
import type { PublicItem } from "./types";

type Day = ReturnType<typeof groupByDay<PublicItem>>[number];

// 聚合源用卡片上显示的原始出处。arXiv 的分类订阅与 arXiv 共用额度。
function sourceOf(item: PublicItem): string {
  const source = item.sourceName.trim().toLowerCase();
  return /^arxiv(?:\s|$)/.test(source) ? "arxiv" : source;
}

/** 保留时间顺序，让每次展开后的列表（包括不足一页的末尾）都严格低于半数。 */
export function balanceFeatured(days: Day[], pageSize: number): Day[] {
  const counts = new Map<string, number>();
  const kept: Day[] = [];
  let total = 0;
  for (const group of days) {
    const items = group.items.filter(({ item }) => {
      const source = sourceOf(item);
      const count = counts.get(source) ?? 0;
      const nextBoundary = (Math.floor(total / pageSize) + 1) * pageSize;
      if ((count + 1) * 2 >= nextBoundary) return false;
      counts.set(source, count + 1);
      total++;
      return true;
    });
    if (items.length) kept.push({ day: group.day, items });
  }
  // 一两个来源无论怎样分配，都至少有一家占半数。
  if (counts.size < 3) return [];
  // 末页按实际总数复核。某来源最多可留「其他来源合计 - 1」条，优先留新文。
  for (const [source, count] of counts) {
    if (count * 2 < total) continue;
    let remaining = total - count - 1;
    return kept.map(group => ({
      ...group,
      items: group.items.filter(({ item }) => sourceOf(item) !== source || remaining-- > 0),
    })).filter(group => group.items.length);
  }
  return kept;
}
