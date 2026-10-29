import { useEffect, useRef } from "react";

import { track } from "./track";

/**
 * 搜索埋点：输入停顿 0.8 秒后记一次，同一个关键词只记一次；不记关键词本身，只记有没有结果。
 * 一两个字的输入多半还没打完，不记。
 */
export function useSearchTracking(query: string, scope: string, found: boolean): void {
  const last = useRef("");
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2 || q === last.current) return;
    const timer = window.setTimeout(() => {
      last.current = q;
      track("search", { scope, found });
    }, 800);
    return () => window.clearTimeout(timer);
  }, [query, scope, found]);
}
