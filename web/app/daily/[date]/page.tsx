import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import {
  BriefList,
  HeadlineBlock,
  ItemRefCardList,
  ReportHead,
  ReportStat,
  weekdayZh,
} from "@/app/_components/report";
import { PageShell } from "@/components/PageShell";
import { formatTime, getDaily, getDailyIndex, getSite } from "@/lib/data";

/**
 * 占位期号。
 *
 * Next 16 + `output: export` 下，动态路由的 `generateStaticParams()` **不能返回空数组**，
 * 否则构建直接失败：
 *   Error: Page "/daily/[date]" is missing "generateStaticParams()"
 *          so it cannot be used with "output: export" config.
 * 日报产物还没生成时索引就是 `entries: []`（仓库里提交的正是这个状态），
 * 所以空的时候补一个占位参数，页面见到占位渲染「还没有日报」而不是 404。
 * 这个路径没有任何地方链过去，也不会被搜索引擎收录（metadata 里标了 noindex）。
 */
const PLACEHOLDER = "__none__";

/** 用日报索引的 `entries` 生成每一期；产物为空时退化成占位参数，构建照样通过。 */
export function generateStaticParams() {
  const index = getDailyIndex();
  const dates = (index?.entries ?? []).flatMap((entry) =>
    entry.date ? [{ date: entry.date }] : [],
  );
  return dates.length > 0 ? dates : [{ date: PLACEHOLDER }];
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ date: string }>;
}): Promise<Metadata> {
  const { date } = await params;
  if (date === PLACEHOLDER) {
    return { title: "日报", robots: { index: false, follow: false } };
  }
  const report = getDaily(date);
  return {
    title: `${date} 日报`,
    description: report?.headline?.titleZh ?? undefined,
  };
}

export default async function DailyDetailPage({
  params,
}: {
  params: Promise<{ date: string }>;
}) {
  const { date } = await params;

  if (date === PLACEHOLDER) {
    return (
      <PageShell current="/daily/">
        <div className="page-head">
          <h1>日报</h1>
        </div>
        <p className="empty">
          还没有日报。
          <br />
          出刊脚本跑过之后，这里会显示最新一期。
          <br />
          <Link href="/daily/">返回日报列表</Link>
        </p>
      </PageShell>
    );
  }

  const report = getDaily(date);
  if (!report) notFound();

  const site = getSite();

  // 空分节标题不渲染
  const sections = (report.sections ?? []).filter(
    (section) => (section.items?.length ?? 0) > 0,
  );
  const highlights = report.highlights ?? [];
  const briefs = report.briefs ?? [];

  const hasContent =
    Boolean(report.headline) ||
    highlights.length > 0 ||
    sections.length > 0 ||
    briefs.length > 0;

  const weekday = weekdayZh(report.date || date);

  return (
    <PageShell current="/daily/">
      <ReportHead
        title={`${report.siteName || site.name} · AI 用研日报`}
        period={`${report.date || date}${weekday ? `（${weekday}）` : ""}`}
        note={
          report.window
            ? `覆盖 ${formatTime(report.window.start)} 至 ${formatTime(report.window.end)}（北京时间）`
            : undefined
        }
        stats={
          <>
            <ReportStat label="入选" value={report.stats.selectedCount} unit="条" />
            <ReportStat value={report.stats.newTools} unit="款新工具" />
            {briefs.length > 0 ? (
              <ReportStat label="快讯" value={briefs.length} unit="条" />
            ) : null}
          </>
        }
      />

      {report.empty || !hasContent ? (
        <p className="empty">
          今日无重要更新。
          <br />
          窗口内没有达到入选门槛的动态，下一期照常。
        </p>
      ) : (
        <>
          {report.headline ? (
            <HeadlineBlock item={report.headline} reasonLabel={site.reasonLabel} />
          ) : null}

          {highlights.length > 0 ? (
            <section className="section">
              <h2 className="section__title">
                今日看点
                <span className="section__count">{highlights.length} 条</span>
              </h2>
              <ItemRefCardList
                items={highlights}
                reasonLabel={site.reasonLabel}
              />
            </section>
          ) : null}

          {sections.map((section) => (
            <section className="section" key={section.key}>
              <h2 className="section__title">
                {section.label}
                <span className="section__count">
                  {section.items.length} 条
                </span>
              </h2>
              <ItemRefCardList
                items={section.items}
                reasonLabel={site.reasonLabel}
              />
            </section>
          ))}

          {briefs.length > 0 ? (
            <section className="section">
              <h2 className="section__title">
                快讯
                <span className="section__count">{briefs.length} 条</span>
              </h2>
              <BriefList briefs={briefs} />
            </section>
          ) : null}
        </>
      )}

      <p className="section__count" style={{ marginTop: "2.5rem" }}>
        <Link href="/daily/">全部日报</Link> ·{" "}
        <Link href="/weekly/">周报</Link> ·{" "}
        <Link href="/about/#sources">信源</Link>
      </p>
    </PageShell>
  );
}
