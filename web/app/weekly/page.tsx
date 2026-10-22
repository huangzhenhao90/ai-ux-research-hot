import type { Metadata } from "next";
import Link from "next/link";

import { EditionList } from "@/app/_components/report";
import { PageShell } from "@/components/PageShell";
import { formatTime, getSite, getWeeklyIndex, href } from "@/lib/data";

export const metadata: Metadata = {
  title: "周报",
  description: "每期周报的列表，按周倒序。",
};

export default function WeeklyIndexPage() {
  const site = getSite();
  const index = getWeeklyIndex();

  const entries = (index?.entries ?? [])
    .flatMap((entry) => (entry.week ? [{ ...entry, week: entry.week }] : []))
    .sort((a, b) => b.week.localeCompare(a.week));

  return (
    <PageShell current="/weekly/">
      <div className="page-head">
        <h1>周报</h1>
        <p className="page-head__desc">
          {`每周一出一期，把上一周的 ${site.subject} 动态汇编成一份，同一事件跨天只算一件。`}
        </p>
      </div>

      {entries.length === 0 ? (
        <p className="empty">
          还没有周报。
          <br />
          日报攒够一周之后，这里会按周倒序列出每一期。
          <br />
          <Link href="/daily/">先去看日报</Link>
        </p>
      ) : (
        <>
          <EditionList
            entries={entries.map((entry) => ({
              key: entry.week,
              href: href(`/weekly/${entry.week}`),
              label: entry.week,
              count: entry.count,
              note: entry.title,
            }))}
          />
          {index?.generatedAt ? (
            <p className="section__count" style={{ marginTop: "1rem" }}>
              列表更新于 {formatTime(index.generatedAt)}（北京时间）
            </p>
          ) : null}
        </>
      )}
    </PageShell>
  );
}
