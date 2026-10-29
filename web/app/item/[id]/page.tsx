import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { BookmarkButton } from "@/components/BookmarkButton";
import { Crumbs } from "@/components/Crumbs";
import { PageShell } from "@/components/PageShell";
import { itemFav } from "@/lib/favorites";
import {
  categoryLabel,
  displayTitle,
  formatDate,
  formatTime,
  getItem,
  getSite,
  href,
  listItemIds,
} from "@/lib/data";

/** 静态导出：构建期把所有条目 id 全部预渲染成 /item/<id>/index.html。 */
export function generateStaticParams() {
  return listItemIds().map((id) => ({ id }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const item = getItem(id);
  if (!item) return { title: "条目不存在" };

  const title = displayTitle(item);
  const description = item.summaryZh?.trim() || item.reason?.trim() || undefined;
  return {
    title,
    description,
    openGraph: { title, description, type: "article" },
  };
}

/**
 * 条目详情。
 *
 * 公开产物里**没有原文全文**（见 lib/types.ts 的说明），所以这里只展示
 * 中文标题、摘要、推荐理由、标签、来源与原文外链，不做正文渲染。
 */
export default async function ItemPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const item = getItem(id);
  if (!item) notFound();

  const site = getSite();
  const title = displayTitle(item);
  // titleZh 存在时，title 是原标题，值得一并给出，方便对照原文
  const originalTitle = item.titleZh?.trim() ? item.title.trim() : "";
  const published = formatTime(item.publishedAt);
  const discovered = formatDate(item.discoveredAt);

  return (
    <PageShell narrow>
      <Crumbs
        items={[
          { href: "/all/", label: "返回全部动态" },
          { href: "/search/", label: "去搜索" },
        ]}
      />

      <div className="page-head">
        <div className="card__head">
          {item.category ? (
            <Link href={href(`/category/${item.category}`)} className="badge badge--accent">
              {categoryLabel(item.category)}
            </Link>
          ) : (
            <span className="badge badge--plain">未分类</span>
          )}
          {item.itemType === "tool_launch" ? (
            <span className="badge badge--plain">新工具</span>
          ) : null}
          {item.status === "archived" ? (
            <span className="badge badge--plain">往期</span>
          ) : null}
          {item.tier ? <span className="badge badge--plain">{item.tier}</span> : null}
        </div>

        <h1 style={{ marginTop: "0.5rem" }}>{title}</h1>

        {originalTitle ? (
          <p className="page-head__desc" lang="en">
            {originalTitle}
          </p>
        ) : null}

        <p className="section__count" style={{ marginTop: "0.5rem" }}>
          {item.sourceName}
          {published ? ` · 发布于 ${published}` : ""}
          {discovered ? ` · 收录于 ${discovered}` : ""}
        </p>
      </div>

      {item.summaryZh?.trim() ? (
        <section className="section">
          <h2 className="section__title">摘要</h2>
          <p className="lead">
            {item.summaryZh}
          </p>
        </section>
      ) : null}

      {item.reason?.trim() ? (
        <section className="section">
          <p className="callout">
            <strong>{site.reasonLabel}：</strong>
            {item.reason}
          </p>
        </section>
      ) : null}

      {item.tags.length > 0 ? (
        <div className="tag-row">
          {item.tags.map((tag) => (
            <span key={tag} className="badge badge--plain">
              {tag}
            </span>
          ))}
        </div>
      ) : null}

      {item.entities.length > 0 ? (
        <div className="tag-row">
          {item.entities.map((entity) => (
            <span key={entity} className="badge badge--plain">
              {entity}
            </span>
          ))}
        </div>
      ) : null}

      <section className="section">
        <h2 className="section__title">来源与原文</h2>
        <div className="card">
          <div className="card__meta" style={{ marginTop: 0 }}>
            <span>{item.sourceName}</span>
            {published ? <time dateTime={item.publishedAt ?? undefined}>{published}</time> : null}
          </div>
          <div className="action-row" style={{ marginTop: "0.75rem" }}>
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="text-link"
              data-track="outbound"
              data-track-kind="item_origin"
              data-track-tab="item_detail"
            >
              阅读原文 →
            </a>
            <BookmarkButton entry={itemFav(item)} where="detail" variant="pill" />
          </div>
        </div>
      </section>

      {item.related.length > 0 ? (
        <section className="section">
          <h2 className="section__title">
            同一事件的其他报道
            <span className="section__count">{item.related.length} 条</span>
          </h2>
          <div className="card-list">
            {item.related.map((ref) => (
              <article className="card" key={ref.id}>
                <h3 className="card__title">
                  <Link href={href(`/item/${ref.id}`)}>
                    {ref.titleZh?.trim() || ref.title}
                  </Link>
                </h3>
                <div className="card__meta">
                  <span>{ref.sourceName}</span>
                  {ref.relation ? <span>{ref.relation}</span> : null}
                  <a href={ref.url} target="_blank" rel="noopener noreferrer nofollow">
                    原文
                  </a>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

    </PageShell>
  );
}
