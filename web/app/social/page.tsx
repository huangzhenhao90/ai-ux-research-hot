import type { Metadata } from "next";

import { PageShell } from "@/components/PageShell";
import { getSocial } from "@/lib/data";
import { beijingToday, daysBetween, formatDate, formatTime } from "@/lib/format";

import { SocialClient, type SocialListJob } from "./SocialClient";

export const metadata: Metadata = {
  title: "用研社招",
  description:
    "从公司招聘官网自动收集的用户研究、体验研究、用户洞察、市场研究方向社招岗位，只收新发布的，满 90 天自动移出。",
};

/** 卡片摘要：职责的前一段，换行压成空格。 */
function summaryOf(text: string): string {
  return text.replace(/\s*\n+\s*/g, " ").slice(0, 160);
}

/**
 * 用研社招。
 *
 * 数据由 `scripts/sync_social.py` 每天从各家招聘官网抓一次（规则见 DECISIONS D17）。
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
  // 公司按配置顺序（大致是体量），没有岗位的不出现在筛选里
  const companies = doc.companies
    .filter((c) => counts.get(c.name))
    .map((c) => ({ name: c.name, count: counts.get(c.name)! }));

  const cityCounts = new Map<string, number>();
  for (const job of jobs) for (const city of job.cities) cityCounts.set(city, (cityCounts.get(city) ?? 0) + 1);
  const cities = [...cityCounts.entries()].sort((a, b) => b[1] - a[1]).map(([name]) => name);

  const fresh = jobs.filter((job) => daysBetween(job.since, today) <= admitDays).length;
  const failing = doc.companies.filter((c) => !c.ok);

  return (
    <PageShell current="/social/">
      <div className="page-head page-head--row">
        <h1>用研社招</h1>
        <span className="page-head__aside">
          {doc.updatedAt ? `更新于 ${formatTime(doc.updatedAt)}` : ""}
        </span>
      </div>
      <p className="page-head__desc" style={{ marginTop: "-0.5rem", marginBottom: "1rem" }}>
        {`每天从 ${doc.companies.length} 家公司的招聘官网收集用户研究、体验研究、用户洞察、市场研究方向的社招岗位。` +
          `只收第一次出现时发布不超过 ${admitDays} 天的岗位，满 ${keepDays} 天自动移出，官网下线的也会拿掉——` +
          "常年挂着不招的岗位不会出现在这里。投递前请以官网为准。"}
      </p>

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
            <a href={c.careers} target="_blank" rel="noopener noreferrer nofollow">
              {c.name}
            </a>
          </span>
        ))}
        {"。腾讯、网易、美团只提供更新时间，按第一次看到时的更新日期起算，之后官网刷新不重新计时。"}
        {failing.length
          ? ` 最近一次没抓成：${failing
              .map((c) => (c.lastOkAt ? `${c.name}（显示的是 ${formatDate(c.lastOkAt)} 抓到的岗位）` : c.name))
              .join("、")}。`
          : ""}
      </p>
    </PageShell>
  );
}
