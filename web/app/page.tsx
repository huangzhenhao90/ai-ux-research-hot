import Link from "next/link";

import { FeedClient } from "@/components/FeedClient";
import { PageShell } from "@/components/PageShell";
import { getAllItems, getCategories, getSite } from "@/lib/data";

/**
 * 精选：全部入选条目，按天排成时间线。
 *
 * 日报、周报去掉之后（D14），这里同时承担「往期精选」的存档：
 * 不再只放最近 3 期，而是全部历史，靠分批展开与「跳到日期」浏览。
 */
export default function HomePage() {
  const site = getSite();
  const categories = getCategories().categories.map(({ key, label }) => ({ key, label }));
  const items = getAllItems().filter((item) => item.status === "selected");

  return (
    <PageShell current="/">
      <div className="page-head page-head--row">
        <h1>精选</h1>
        <span className="page-head__aside">
          共 <span className="num">{items.length}</span> 条
        </span>
      </div>

      <FeedClient
        items={items}
        categories={categories}
        reasonLabel={site.reasonLabel}
        searchAction={`${site.basePath}/search/`}
        pageSize={50}
        emptyText="还没有入选的条目。"
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
