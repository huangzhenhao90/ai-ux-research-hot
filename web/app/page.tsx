import Link from "next/link";

import { ItemCardList } from "@/components/ItemCard";
import { PageShell } from "@/components/PageShell";
import { getDaily, getDailyIndex, getLatest, getSite } from "@/lib/data";

export default function HomePage() {
  const site = getSite();
  const latest = getLatest();

  // 最新一期日报入口（有就显示，没有就退回日报列表）
  const dailyIndex = getDailyIndex();
  const latestDailyEntry = dailyIndex?.entries?.[0];
  const latestDaily = latestDailyEntry?.date
    ? getDaily(latestDailyEntry.date)
    : null;

  const total = latest.days.reduce((sum, day) => sum + day.count, 0);

  return (
    <PageShell current="/">
      <div className="page-head">
        <h1>{site.homeTitle}</h1>
        <p className="page-head__desc">{site.description}</p>
      </div>

      {latestDaily && !latestDaily.empty ? (
        <p className="section__count" style={{ marginTop: "-0.5rem" }}>
          最新一期日报：
          <Link href={`/daily/${latestDaily.date}/`}>
            {latestDaily.date}（{latestDaily.stats.selectedCount} 条）
          </Link>
        </p>
      ) : null}

      {latest.days.length === 0 ? (
        <p className="empty">
          最近 {latest.windowDays} 天还没有新的精选。
          <br />
          <Link href="/all/">去看全部动态</Link>
        </p>
      ) : (
        latest.days.map((day) => (
          <section className="section" key={day.date}>
            <h2 className="section__title">
              {day.date}
              <span className="section__count">{day.count} 条精选</span>
            </h2>
            <ItemCardList items={day.items} reasonLabel={site.reasonLabel} />
          </section>
        ))
      )}

      {total > 0 ? (
        <section className="section">
          <p className="section__count">
            想看更多？<Link href="/all/">全部动态</Link> ·{" "}
            <Link href="/topics/">按主题浏览</Link> ·{" "}
            <a href={`${site.basePath}/rss.xml`}>订阅 RSS</a>
          </p>
        </section>
      ) : null}
    </PageShell>
  );
}
