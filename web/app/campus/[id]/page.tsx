import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { BookmarkButton } from "@/components/BookmarkButton";
import { Crumbs } from "@/components/Crumbs";
import { IconExternal } from "@/components/icons";
import { PageShell } from "@/components/PageShell";
import { getCampus, getCampusJob } from "@/lib/data";
import { campusFav } from "@/lib/favorites";

export function generateStaticParams() {
  const jobs = getCampus()?.jobs ?? [];
  // 静态导出不允许空列表：没有快照时给一个占位，页面里会 404
  return jobs.length ? jobs.map((job) => ({ id: job.id })) : [{ id: "_none" }];
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const job = getCampusJob(id);
  return {
    title: job ? `${job.company} · ${job.title}` : "用研校招",
    description: job?.tagline ?? undefined,
  };
}

/** 校招岗位详情：官网原文、岗位分析、投递建议与核验说明。 */
export default async function CampusJobPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const job = getCampusJob(id);
  if (!job) notFound();
  const source = getCampus()!.source;

  const facts: [string, string | null][] = [
    ["公司", job.company],
    ["地点", job.location],
    ["招聘人数", job.headcount],
    ["学历", job.degree],
    ["业务方向", job.business],
    ["核验日期", job.checkedAt ?? source.updated],
  ];

  return (
    <PageShell current="/campus/" narrow>
      <Crumbs
        items={[
          { href: "/campus/", label: "返回用研校招" },
          { href: `/campus/?company=${encodeURIComponent(job.company)}`, label: `${job.company}的全部岗位` },
        ]}
      />

      <div className="page-head">
        <div className="card__head">
          <span className="badge">{job.industry}</span>
          <span className="badge badge--accent">{job.type}</span>
          {job.ai ? <span className="badge badge--selected">职责含 AI</span> : null}
          {job.flags
            .filter((flag) => !/AI/.test(flag))
            .map((flag) => (
              <span key={flag} className="badge">
                {flag}
              </span>
            ))}
        </div>
        <h1 style={{ marginTop: "0.5rem" }}>{job.title}</h1>
        <p className="page-head__desc">{job.company}</p>
      </div>

      {job.tagline ? <p className="callout">{job.tagline}</p> : null}

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

      <div className="action-row">
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="pill-button pill-button--primary"
          data-track="outbound"
          data-track-kind="job_apply"
          data-track-tab="campus_detail"
        >
          去官网投递
          <IconExternal size={13} />
        </a>
        <BookmarkButton entry={campusFav(job)} where="detail" variant="pill" />
      </div>

      <section className="section">
        <h2 className="section__title">岗位描述（官网原文）</h2>
        <p className="lead jd-text">{job.jd}</p>
      </section>

      {job.analysis ? (
        <section className="section">
          <h2 className="section__title">岗位分析</h2>
          <p className="lead">{job.analysis}</p>
        </section>
      ) : null}

      {job.advice ? (
        <section className="section">
          <h2 className="section__title">投递建议</h2>
          <p className="lead">{job.advice}</p>
        </section>
      ) : null}

      {job.cohortNote || job.verificationNote ? (
        <section className="section">
          <h2 className="section__title">核验说明</h2>
          {job.cohortNote ? <p className="lead">{job.cohortNote}</p> : null}
          {job.verificationNote ? (
            <p className="lead" style={{ marginTop: "0.5rem" }}>
              {job.verificationNote}
            </p>
          ) : null}
        </section>
      ) : null}

      <section className="section">
        <p className="section__count">岗位信息会变化，投递前请以官网为准。</p>
      </section>
    </PageShell>
  );
}
