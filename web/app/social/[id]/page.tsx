import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { BookmarkButton } from "@/components/BookmarkButton";
import { Crumbs } from "@/components/Crumbs";
import { IconExternal } from "@/components/icons";
import { OriginBadge } from "@/components/OriginBadge";
import { PageShell } from "@/components/PageShell";
import { getSocial, getSocialJob } from "@/lib/data";
import { socialFav } from "@/lib/favorites";
import { dateKindLabel, ORIGIN_LABELS } from "@/lib/format";

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
    description: job ? (job.duty || job.requirement).slice(0, 120) : undefined,
  };
}

/** 社招岗位详情：职责与要求原文、来源与日期、投递入口。 */
export default async function SocialJobPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const job = getSocialJob(id);
  if (!job) notFound();
  const { keepDays } = getSocial()!.window;

  const official = job.origins.includes("official");
  const kind = dateKindLabel(job.dateKind);
  const dateLabel = job.dateKind === "added" ? "收录日期" : `${official ? "官网" : ""}${kind}日期`;

  const facts: [string, string | null][] = [
    ["公司", job.company],
    ["来源", job.origins.map((o) => ORIGIN_LABELS[o]).join(" · ")],
    ["城市", job.cities.join("、") || null],
    ["部门", job.department],
    ["经验要求", job.experience],
    ["薪资", job.salary],
    [dateLabel, job.postedAt],
    // 手动收录没有发布日期时，上面那一行就是收录日，不用再写一遍
    ["本站收录", job.dateKind === "added" ? null : job.firstSeen],
  ];

  return (
    <PageShell current="/social/" narrow>
      <Crumbs
        items={[
          { href: "/social/", label: "返回用研社招" },
          { href: `/social/?company=${encodeURIComponent(job.company)}`, label: `${job.company}的全部岗位` },
        ]}
      />

      <div className="page-head">
        <div className="card__head">
          <span className="badge">{job.company}</span>
          {job.origins.map((origin) => (
            <OriginBadge key={origin} origin={origin} />
          ))}
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

      <div className="action-row">
        {job.url ? (
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="pill-button pill-button--primary"
            data-track="outbound"
            data-track-kind="job_apply"
            data-track-tab="social_detail"
          >
            {official ? "去官网投递" : "打开岗位页"}
            <IconExternal size={13} />
          </a>
        ) : null}
        <BookmarkButton entry={socialFav(job)} where="detail" variant="pill" />
      </div>
      {job.url ? null : (
        <p className="section__count" style={{ marginTop: "0.75rem" }}>
          这个岗位没有可直接打开的链接，投递请到来源平台搜索「{job.company} {job.title}」。
        </p>
      )}

      {job.duty ? (
        <section className="section">
          <h2 className="section__title">岗位职责{official ? "（官网原文）" : ""}</h2>
          <p className="lead jd-text">{job.duty}</p>
        </section>
      ) : null}

      {job.requirement ? (
        <section className="section">
          <h2 className="section__title">任职要求{official ? "（官网原文）" : ""}</h2>
          <p className="lead jd-text">{job.requirement}</p>
        </section>
      ) : null}

      <section className="section">
        <p className="section__count">
          {job.dateKind === "update"
            ? `${job.company}只提供更新时间：本站按第一次看到时的更新日期 ${job.since} 起算，满 ${keepDays} 天移出，官网刷新不重新计时。`
            : job.dateKind === "added"
              ? `没有发布日期：本站按收录日 ${job.since} 起算，满 ${keepDays} 天移出。`
              : `按${official ? "官网" : ""}发布日期 ${job.since} 起算，满 ${keepDays} 天移出${official ? "；官网先下线的话会更早拿掉" : ""}。`}
          {"岗位信息会变化，投递前请以官网为准。"}
        </p>
      </section>
    </PageShell>
  );
}
