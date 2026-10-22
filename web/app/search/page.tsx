import type { Metadata } from "next";

import { PageShell } from "@/components/PageShell";
import {
  categoryLabel,
  displayTitle,
  formatDate,
  getSearchIndex,
} from "@/lib/data";

import { SearchClient, type SearchEntry } from "./SearchClient";

export const metadata: Metadata = {
  title: "搜索",
  description:
    "在已收录的 AI 用研动态里按标题、摘要、标签、实体和来源检索。搜索完全在浏览器里完成，不发任何网络请求。",
};

/**
 * 本地搜索。
 *
 * 构建期把搜索索引整理成展示就绪的结构交给客户端组件；页面打开后不再读文件、
 * 不发请求，过滤全在浏览器内存里做（静态导出，没有后端）。
 */
export default function SearchPage() {
  const index = getSearchIndex();

  const items: SearchEntry[] = index.items.map((item) => ({
    id: item.id,
    title: displayTitle(item),
    originalTitle: item.titleZh?.trim() ? item.title.trim() : null,
    summary: item.summaryZh?.trim() || null,
    tags: item.tags,
    entities: item.entities,
    categoryLabel: item.category ? categoryLabel(item.category) : null,
    sourceName: item.sourceName,
    time: formatDate(item.publishedAt),
  }));

  return (
    <PageShell current="/search/">
      <div className="page-head">
        <h1>搜索</h1>
        <p className="page-head__desc">
          在已收录的 {index.count} 条动态里查找。匹配范围：中文标题、英文原标题、
          摘要、标签、实体和来源名称；全部在浏览器里完成，不发任何请求。
        </p>
      </div>

      <SearchClient items={items} />
    </PageShell>
  );
}
