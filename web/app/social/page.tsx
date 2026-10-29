import type { Metadata } from "next";

import { OriginBadge } from "@/components/OriginBadge";
import { PageShell } from "@/components/PageShell";
import { getSocial } from "@/lib/data";
import { beijingToday, daysBetween, formatDate, formatTime } from "@/lib/format";

import { SocialClient, type SocialListJob } from "./SocialClient";

export const metadata: Metadata = {
  title: "用研社招",
  description:
    "从公司招聘官网自动收集的用户研究、体验研究、用户洞察、市场研究方向社招岗位，只收新发布的，满 90 天自动移出；每个岗位标注来源。",
};

/** 卡片摘要：职责的前一段，换行压成空格。 */
function summaryOf(text: string): string {
  return text.replace(/\s*\n+\s*/g, " ").slice(0, 160);
}

/**
 * 用研社招。
 *
 * 官网岗位由 `scripts/sync_social.py` 每天从各家招聘官网抓一次（规则见 DECISIONS D17），
 * Boss 直聘截图与社群里的信息是人工整理进来的；每个岗位标来源（DECISIONS D20）。
 */
export default function SocialPage() {
  const doc = getSocial();

  if (!doc) {
    return (
      <PageShell current="/social/">
        <div className="page-head">
          <h1>用研社招</h1>
        </div>
        <p className="empty">社招岗位还没有同步过来，下一次定时更新后会出现。</p>
      </PageShell>
    );
  }

  const today = beijingToday();
  const { admitDays, keepDays } = doc.window;
  const jobs: SocialListJob[] = doc.jobs.map(({ duty, requirement, ...job }) => ({
    ...job,
    summary: summaryOf(duty || requirement),
  }));

  const counts = new Map<string, number>();
  for (const job of jobs) counts.set(job.company, (counts.get(job.company) ?? 0) + 1);
  // 公司筛选：官网公司按配置顺序（大致是体量）在前，其他来源带来的公司（如只在 Boss 直聘上看到的）按岗位数排在后面
  const order = new Map(doc.companies.map((c, index) => [c.name, index]));
  const companies = [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort(
      (a, b) =>
        (order.get(a.name) ?? Infinity) - (order.get(b.name) ?? Infinity) || b.count - a.count,
    );

  const cityCounts = new Map<string, number>();
  for (const job of jobs) for (const city of job.cities) cityCounts.set(city, (cityCounts.get(city) ?? 0) + 1);
  const cities = [...cityCounts.entries()].sort((a, b) => b[1] - a[1]).map(([name]) => name);

  const fresh = jobs.filter((job) => daysBetween(job.since, today) <= admitDays).length;
  const failing = doc.companies.filter((c) => !c.ok);
  const hasManual = jobs.some((job) => job.origins.some((o) => o !== "official"));

  return (
    <PageShell current="/social/">
      <div className="page-head page-head--row">
        <h1>用研社招</h1>
        <span className="page-head__aside">
          {doc.updatedAt ? `更新于 ${formatTime(doc.updatedAt)}` : ""}
        </span>
      </div>

      <section className="source-hero" aria-labelledby="source-hero-title">
        <p className="source-hero__kicker">数据来源</p>
        <h2 id="source-hero-title" className="source-hero__title">
          公司<span className="source-hero__em">招聘官网</span>
        </h2>
        <p className="source-hero__desc">
          {`每天直接从 ${doc.companies.length} 家公司的`}
          <strong>招聘官网</strong>
          {`收集用户研究、体验研究、用户洞察、市场研究方向的社招岗位，详情与投递入口直达官网。` +
            `只收第一次出现时发布不超过 ${admitDays} 天的岗位，满 ${keepDays} 天自动移出，官网下线的也会拿掉——` +
            "常年挂着不招的岗位不会出现在这里。投递前请以官网为准。"}
        </p>
        <p className="source-hero__legend">
          <span>来源标注</span>
          <OriginBadge origin="official" />
          <OriginBadge origin="boss" />
          <OriginBadge origin="community" />
          <span>官网和 Boss 直聘都有的岗位，只标官网。</span>
        </p>
      </section>

      <div className="campus-stats">
        <span>
          <b className="num">{jobs.length}</b> 个岗位
        </span>
        <span>
          <b className="num">{fresh}</b> 个是近 {admitDays} 天的
        </span>
        <span>
          <b className="num">{companies.length}</b> 家公司有岗
        </span>
      </div>

      <SocialClient jobs={jobs} companies={companies} cities={cities} today={today} />

      <p className="feed-more">
        {"数据来自各公司招聘官网："}
        {doc.companies.map((c, index) => (
          <span key={c.key}>
            {index ? "、" : ""}
            <a
              href={c.careers}
              target="_blank"
              rel="noopener noreferrer nofollow"
              data-track="outbound"
              data-track-kind="careers_site"
              data-track-tab="social"
            >
              {c.name}
            </a>
          </span>
        ))}
        {"。腾讯、网易、美团只提供更新时间，按第一次看到时的更新日期起算，之后官网刷新不重新计时。"}
        {hasManual ? " 标注为「Boss直聘」「社群」的岗位是人工整理进来的，不是自动抓取。" : ""}
        {failing.length
          ? ` 最近一次没抓成：${failing
              .map((c) => (c.lastOkAt ? `${c.name}（显示的是 ${formatDate(c.lastOkAt)} 抓到的岗位）` : c.name))
              .join("、")}。`
          : ""}
      </p>
    </PageShell>
  );
}
