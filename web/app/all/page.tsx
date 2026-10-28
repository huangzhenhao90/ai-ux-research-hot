import type { Metadata } from "next";

import { FeedClient } from "@/components/FeedClient";
import { PageShell } from "@/components/PageShell";
import { getAllItems, getCategories, getSite } from "@/lib/data";

export const metadata: Metadata = {
  title: "全部动态",
  description:
    "按时间倒序浏览全部收录动态，可按分类筛选；默认只渲染最近的一批，需要时再逐批展开。",
};

/**
 * 全部动态。
 *
 * 构建期把所有月份合并成一份完整列表交给 `FeedClient`，由它做**纯本地**的分类筛选
 * 与「加载更多」（静态导出，没有后端可以查）。
 */
export default function AllPage() {
  const site = getSite();
  const items = getAllItems();
  const categories = getCategories().categories.map(({ key, label }) => ({ key, label }));

  return (
    <PageShell current="/all/">
      <div className="page-head page-head--row">
        <h1>全部动态</h1>
        <span className="page-head__aside">
          共收录 <span className="num">{items.length}</span> 条
        </span>
      </div>

      <FeedClient
        items={items}
        categories={categories}
        reasonLabel={site.reasonLabel}
        searchAction={`${site.basePath}/search/`}
        emptyText="还没有收录任何动态。"
      />
    </PageShell>
  );
}
