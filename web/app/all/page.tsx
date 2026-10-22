import type { Metadata } from "next";

import { PageShell } from "@/components/PageShell";
import { getAllItems, getCategories, getSite } from "@/lib/data";

import { AllClient } from "./AllClient";

export const metadata: Metadata = {
  title: "全部动态",
  description:
    "按时间倒序浏览全部收录动态，可按分类筛选；默认只渲染最近的一批，需要时再逐批展开。",
};

/**
 * 全部动态。
 *
 * 构建期把所有月份合并成一份完整列表交给客户端组件，由它做**纯本地**的分类筛选
 * 与「加载更多」（静态导出，没有后端可以查）。
 *
 * 直接把 `PublicItem` 传下去即可：`ItemCard` 只依赖 `lib/format.ts`（纯函数），
 * 客户端组件能安全使用。
 */
export default function AllPage() {
  const site = getSite();
  const items = getAllItems();
  const categories = getCategories().categories;

  return (
    <PageShell current="/all/">
      <div className="page-head">
        <h1>全部动态</h1>
        <p className="page-head__desc">
          共收录 {items.length} 条动态，按发布时间从新到旧排列。可以先按分类筛选，
          再逐批展开。
        </p>
      </div>

      {items.length === 0 ? (
        <p className="empty">还没有收录任何动态。</p>
      ) : (
        <AllClient
          items={items}
          categories={categories.map(({ key, label }) => ({ key, label }))}
          reasonLabel={site.reasonLabel}
        />
      )}
    </PageShell>
  );
}
