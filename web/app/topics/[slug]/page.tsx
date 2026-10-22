import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ItemCardList } from "@/components/ItemCard";
import { PageShell } from "@/components/PageShell";
import { getSite, getTopic, getTopics } from "@/lib/data";

export function generateStaticParams() {
  return getTopics().topics.map((topic) => ({ slug: topic.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const topic = getTopic(slug);
  return {
    title: topic ? `${topic.name} 主题` : "主题",
    description: topic?.definition,
  };
}

export default async function TopicDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  const topic = getTopic(slug);
  if (!topic) notFound();

  const site = getSite();
  const items = topic.items ?? [];

  return (
    <PageShell current="/topics/">
      <div className="page-head">
        <h1>{topic.name}</h1>
        <p className="page-head__desc">{topic.definition}</p>
        <p className="section__count" style={{ marginTop: "0.6rem" }}>
          {topic.count} 条 · <Link href="/topics/">全部主题</Link>
        </p>
      </div>

      <ItemCardList
        items={items}
        reasonLabel={site.reasonLabel}
        emptyText={`「${topic.name}」下还没有条目。`}
      />
    </PageShell>
  );
}
