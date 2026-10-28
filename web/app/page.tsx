import Link from "next/link";

import { FeedClient } from "@/components/FeedClient";
import { PageShell } from "@/components/PageShell";
import { getCategories, getDailyIndex, getLatest, getSite } from "@/lib/data";

export default function HomePage() {
  const site = getSite();
  const latest = getLatest();
  const categories = getCategories().categories.map(({ key, label }) => ({ key, label }));
  const items = latest.days.flatMap((day) => day.items);

  // 最新一期日报入口（有就显示）
  const latestDaily = getDailyIndex()?.entries?.[0]?.date ?? null;

  return (
    <PageShell current="/">
      <div className="page-head page-head--row">
        <h1>精选</h1>
        {latestDaily ? (
          <Link href={`/daily/${latestDaily}/`} className="page-head__aside">
            读最新日报 →
          </Link>
        ) : null}
      </div>

      <FeedClient
        items={items}
        categories={categories}
        reasonLabel={site.reasonLabel}
        searchAction={`${site.basePath}/search/`}
        emptyText={`最近 ${latest.windowDays} 天还没有新的精选。`}
      />

      {items.length > 0 ? (
        <p className="feed-more">
          想看更多？<Link href="/all/">全部动态</Link> ·{" "}
          <Link href="/topics/">按主题浏览</Link> ·{" "}
          <a href={`${site.basePath}/rss.xml`}>订阅 RSS</a>
        </p>
      ) : null}
    </PageShell>
  );
}
