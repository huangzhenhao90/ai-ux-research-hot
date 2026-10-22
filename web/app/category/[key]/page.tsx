import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ItemCardList } from "@/components/ItemCard";
import { PageShell } from "@/components/PageShell";
import { getCategories, getCategory, getSite, href } from "@/lib/data";

/** 静态导出：构建期把 6 个分类 key 全部预渲染成 /category/<key>/index.html。 */
export function generateStaticParams() {
  return getCategories().categories.map(({ key }) => ({ key }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ key: string }>;
}): Promise<Metadata> {
  const { key } = await params;
  const doc = getCategory(key);
  if (!doc) return { title: "分类不存在" };
  return {
    title: doc.label,
    description: `${doc.label}（${doc.section}）：收录 ${doc.count} 条相关动态。`,
  };
}

/** commentary 为 true 的分类（方法/观点）多给一句说明，提醒这是评述性内容。 */
const COMMENTARY_NOTE: Record<string, string> = {
  methods:
    "这一类偏方法与实践经验，多是作者视角的总结，落到自己的研究场景时建议结合具体目标调整。",
  opinion:
    "这一类是观点与讨论，包含作者的立场和判断，不等同于事实结论，建议对照原文与多方信息一起看。",
};

const COMMENTARY_FALLBACK =
  "这一类以评述性内容为主，包含作者的观点与判断，建议对照原文自行取舍。";

/**
 * 分类页。
 *
 * 条目和「全部动态」用的是同一套卡片；这里关掉卡片上的分类角标（整页都是同一个
 * 分类，重复显示没有信息量）。
 */
export default async function CategoryPage({
  params,
}: {
  params: Promise<{ key: string }>;
}) {
  const { key } = await params;
  const doc = getCategory(key);
  if (!doc) notFound();

  const site = getSite();
  const categories = getCategories().categories;
  const note = doc.commentary
    ? (COMMENTARY_NOTE[doc.key] ?? COMMENTARY_FALLBACK)
    : null;

  return (
    <PageShell>
      <div className="page-head">
        <h1>{doc.label}</h1>
        <p className="page-head__desc">
          {doc.section} · 共收录 {doc.items.length} 条
        </p>
        {note ? <p className="page-head__desc">{note}</p> : null}
      </div>

      <div className="tag-row" style={{ marginTop: 0, marginBottom: "1.5rem" }}>
        {categories.map((category) =>
          category.key === doc.key ? (
            <span key={category.key} className="badge">
              {category.label} {category.count}
            </span>
          ) : (
            <Link
              key={category.key}
              href={href(`/category/${category.key}`)}
              className="badge badge--plain"
            >
              {category.label} {category.count}
            </Link>
          ),
        )}
      </div>

      <ItemCardList
        items={doc.items}
        reasonLabel={site.reasonLabel}
        emptyText="这个分类下还没有收录条目。"
        showCategory={false}
      />

      <section className="section">
        <p className="section__count">
          <Link href="/all/">← 全部动态</Link> ·{" "}
          <Link href="/search/">去搜索</Link>
        </p>
      </section>
    </PageShell>
  );
}
