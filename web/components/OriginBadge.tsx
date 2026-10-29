import { ORIGIN_LABELS } from "@/lib/format";
import type { SocialOrigin } from "@/lib/types";

/**
 * 社招岗位的来源角标：官网 / Boss直聘 / 社群（DECISIONS D20）。
 * 官网用实心强调色（主要来源），Boss直聘与社群用各自的浅色。
 */
export function OriginBadge({ origin }: { origin: SocialOrigin }) {
  return <span className={`badge badge--origin badge--origin-${origin}`}>{ORIGIN_LABELS[origin]}</span>;
}
