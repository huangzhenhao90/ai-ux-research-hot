import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { IconExternal } from "@/components/icons";
import { PageShell } from "@/components/PageShell";
import { getSocial, getSocialJob } from "@/lib/data";

export function generateStaticParams() {
  const jobs = getSocial()?.jobs ?? [];
  // 静态导出不允许空列表：没有数据时给一个占位，页面里会 404
  return jobs.length ? jobs.map((job) => ({ id: job.id })) : [{ id: "_none" }];
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const job = getSocialJob(id);
  return {
    title: job ? `${job.company} · ${job.title}` : "用研社招",
    description: job ? job.duty.slice(0, 120) : undefined,
  };
}

/** 社招岗位详情：官网职责与要求原文、日期与本站的收录 / 下架时间。 */
export default async function SocialJobPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const job = getSocialJob(id);
  if (!job) notFound();
  const { keepDays } = getSocial()!.window;
  const kind = job.dateKind === "publish" ? "发布" : "更新";

  const facts: [string, string | null][] = [
    ["公司", job.company],
    ["城市", job.cities.join("、") || null],
    ["部门", job.department],
    ["经验要求", job.experience],
    [`官网${kind}日期`, job.postedAt],
    ["本站收录", job.firstSeen],
    ["预计下架", job.expiresAt],
  ];

  return (
    <PageShell current="/social/" narrow>
      <div className="page-head">
        <div className="card__head">
          <span className="badge">{job.company}</span>
          {job.cities.slice(0, 3).map((city) => (
            <span key={city} className="badge">
              {city}
            </span>
          ))}
        </div>
        <h1 style={{ marginTop: "0.5rem" }}>{job.title}</h1>
        <p className="page-head__desc">{[job.company, job.department].filter(Boolean).join(" · ")}</p>
      </div>

      <dl className="fact-list">
        {facts
          .filter(([, value]) => value)
          .map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
      </dl>

      <p style={{ marginTop: "1rem" }}>
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="pill-button pill-button--primary"
        >
          去官网投递
          <IconExternal size={13} />
        </a>
      </p>

      {job.duty ? (
        <section className="section">
          <h2 className="section__title">岗位职责（官网原文）</h2>
          <p className="lead jd-text">{job.duty}</p>
        </section>
      ) : null}

      {job.requirement ? (
        <section className="section">
          <h2 className="section__title">任职要求（官网原文）</h2>
          <p className="lead jd-text">{job.requirement}</p>
        </section>
      ) : null}

      <section className="section">
        <p className="section__count">
          {job.dateKind === "update"
            ? `${job.company}只提供更新时间：本站按第一次看到时的更新日期 ${job.since} 起算，满 ${keepDays} 天移出，官网刷新不重新计时。`
            : `按官网发布日期 ${job.since} 起算，满 ${keepDays} 天移出；官网先下线的话会更早拿掉。`}
        </p>
        <p className="section__count" style={{ marginTop: "0.5rem" }}>
          <Link href="/social/">← 返回用研社招</Link> ·{" "}
          <Link href={`/social/?company=${encodeURIComponent(job.company)}`}>{job.company}的全部岗位</Link>
          {" · 岗位信息会变化，投递前请以官网为准"}
        </p>
      </section>
    </PageShell>
  );
}
