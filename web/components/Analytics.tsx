"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { dataFromElement, startAnalytics, track, trackPageview, featureOf } from "@/lib/track";

/**
 * 埋点入口，放在根布局里。没配统计服务时什么都不做（见 `lib/track.ts`）。
 *
 * 做两件事：
 * 1. 每次换页记一次页面浏览与一次 `feature_view`（`pathname` 不含 basePath，
 *    只有真正换页才会变，筛选写进链接的 replaceState 不算）；
 * 2. 一个统一的点击监听：点到带 `data-track` 的元素就记对应事件，参数取自 `data-track-*`。
 *    这样服务端渲染的页面里的外链也能埋点，不用为了埋点把它们改成客户端组件。
 */
export function Analytics() {
  const pathname = usePathname();
  const first = useRef(true);

  useEffect(() => {
    if (!startAnalytics()) return;
    trackPageview(first.current);
    track("feature_view", { feature: featureOf(pathname) });
    first.current = false;
  }, [pathname]);

  useEffect(() => {
    function onClick(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const el = target.closest<HTMLElement>("[data-track]");
      if (!el) return;
      const name = el.dataset.track;
      if (name) track(name, dataFromElement(el));
    }
    // click 只有主键；auxclick 补上中键（新标签页打开外链）
    document.addEventListener("click", onClick, true);
    document.addEventListener("auxclick", onClick, true);
    return () => {
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("auxclick", onClick, true);
    };
  }, []);

  return null;
}
