import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import {
  ItemRefCardList,
  ReportHead,
  ReportStat,
} from "@/app/_components/report";
import { PageShell } from "@/components/PageShell";
import { formatDate, getSite, getWeekly, getWeeklyIndex } from "@/lib/data";

/**
 * 占位周号（理由同 `/daily/[date]`）：`output: export` 下动态路由的
 * `generateStaticParams()` 不能返回空数组，产物为空时补一个占位参数，
 * 页面见到占位渲染「还没有周报」而不是 404。
 */
const PLACEHOLDER = "__none__";

/** 用周报索引的 `entries` 生成每一期；产物为空时退化成占位参数，构建照样通过。 */
export function generateStaticParams() {
  const index = getWeeklyIndex();
  const weeks = (index?.entries ?? []).flatMap((entry) =>
    entry.week ? [{ week: entry.week }] : [],
  );
  return weeks.length > 0 ? weeks : [{ week: PLACEHOLDER }];
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ week: string }>;
}): Promise<Metadata> {
  const { week } = await params;
  if (week === PLACEHOLDER) {
    return { title: "周报", robots: { index: false, follow: false } };
  }
  return { title: `${week} 周报` };
}

export default async function WeeklyDetailPage({
  params,
}: {
  params: Promise<{ week: string }>;
}) {
  const { week } = await params;

  if (week === PLACEHOLDER) {
    return (
      <PageShell current="/weekly/">
        <div className="page-head">
          <h1>周报</h1>
        </div>
        <p className="empty">
          还没有周报。
          <br />
          日报攒够一周之后，这里会显示最新一期。
          <br />
          <Link href="/weekly/">返回周报列表</Link>
        </p>
      </PageShell>
    );
  }

  const report = getWeekly(week);
  if (!report) notFound();

  const site = getSite();

  const sections = (report.sections ?? []).filter(
    (section) => (section.items?.length ?? 0) > 0,
  );

  return (
    <PageShell current="/weekly/">
      <ReportHead
        title={`${report.siteName || site.name} · AI 用研周报`}
        period={report.week || week}
        note={
          report.window
            ? `窗口 ${formatDate(report.window.start)} 08:00 至 ${formatDate(report.window.end)} 08:00（北京时间）`
            : undefined
        }
        stats={
          <>
            <ReportStat label="入选" value={report.stats.itemCount} unit="条" />
            <ReportStat
              label="汇编日报"
              value={report.stats.dailyCount}
              unit="期"
            />
          </>
        }
      />

      {report.overview ? (
        <section className="headline">
          <p className="headline__label">本周总述</p>
          <p className="headline__summary">{report.overview}</p>
        </section>
      ) : null}

      {sections.length === 0 ? (
        <section className="section">
          <p className="empty">
            这一期周报还没有条目。
            <br />
            上一周的日报里没有达到入选门槛的动态。
          </p>
        </section>
      ) : (
        sections.map((section) => (
          <section className="section" key={section.key}>
            <h2 className="section__title">
              {section.label}
              <span className="section__count">{section.items.length} 条</span>
            </h2>
            {section.lead ? (
              <p
                className="section__count"
                style={{ marginTop: "-0.4rem", marginBottom: "0.85rem" }}
              >
                {section.lead}
              </p>
            ) : null}
            <ItemRefCardList
              items={section.items}
              reasonLabel={site.reasonLabel}
            />
          </section>
        ))
      )}

      <p className="section__count" style={{ marginTop: "2.5rem" }}>
        <Link href="/weekly/">全部周报</Link> ·{" "}
        <Link href="/daily/">日报</Link> ·{" "}
        <Link href="/about/">关于</Link>
      </p>
    </PageShell>
  );
}
