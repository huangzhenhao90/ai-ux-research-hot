import type { Metadata } from "next";
import Link from "next/link";

import { PageShell } from "@/components/PageShell";
import { getSite, getTopics, href } from "@/lib/data";
import type { TopicMeta } from "@/lib/types";

export const metadata: Metadata = {
  title: "主题",
  description: "按公司与平台、研究方向、内容类型浏览全部主题。",
};

export default function TopicsPage() {
  const site = getSite();
  const { groups, topics } = getTopics();

  const known = new Set(groups.map((group) => group.key));
  const orphans = topics.filter((topic) => !known.has(topic.group));

  const renderTiles = (list: TopicMeta[]) => (
    <div className="grid-cards">
      {list.map((topic) => (
        <Link
          key={topic.slug}
          href={href(`/topics/${topic.slug}`)}
          className="tile"
          style={{ display: "block" }}
        >
          <span className="tile__name">
            <span>{topic.name}</span>
            <span
              className="tile__count"
              style={topic.count === 0 ? { opacity: 0.5 } : undefined}
            >
              {topic.count} 条
            </span>
          </span>
          <span className="tile__desc" style={{ display: "block" }}>
            {topic.definition}
          </span>
        </Link>
      ))}
    </div>
  );

  const groupNames = groups.map((group) => group.name).join("、");

  return (
    <PageShell current="/topics/">
      <div className="page-head">
        <h1>主题</h1>
        <p className="page-head__desc">
          {`按${groupNames}浏览全部 ${topics.length} 个 ${site.subject}主题；条数为 0 的主题也会列出来，方便看出哪些方向还没有积累。`}
        </p>
      </div>

      {groups.map((group) => {
        const list = topics.filter((topic) => topic.group === group.key);
        return (
          <section className="section" key={group.key}>
            <h2 className="section__title">
              {group.name}
              <span className="section__count">{list.length} 个主题</span>
            </h2>
            {group.blurb ? (
              <p
                className="page-head__desc"
                style={{ marginTop: "-0.5rem", marginBottom: "1rem" }}
              >
                {group.blurb}
              </p>
            ) : null}
            {list.length === 0 ? (
              <p className="empty">这个分组下还没有主题。</p>
            ) : (
              renderTiles(list)
            )}
          </section>
        );
      })}

      {orphans.length > 0 ? (
        <section className="section">
          <h2 className="section__title">
            其他
            <span className="section__count">{orphans.length} 个主题</span>
          </h2>
          {renderTiles(orphans)}
        </section>
      ) : null}

      {topics.length === 0 ? (
        <p className="empty">
          还没有主题。
          <br />
          <Link href="/all/">先去看全部动态</Link>
        </p>
      ) : null}
    </PageShell>
  );
}
