import type { Metadata } from "next";
import Link from "next/link";

import { EditionList } from "@/app/_components/report";
import { PageShell } from "@/components/PageShell";
import { formatTime, getDailyIndex, getSite, href } from "@/lib/data";

export const metadata: Metadata = {
  title: "日报",
  description: "每期日报的列表，按日期倒序。",
};

export default function DailyIndexPage() {
  const site = getSite();
  const index = getDailyIndex();

  // 产物已倒序，这里再排一次只是防御；`date` 缺失的条目直接丢掉
  const entries = (index?.entries ?? [])
    .flatMap((entry) => (entry.date ? [{ ...entry, date: entry.date }] : []))
    .sort((a, b) => b.date.localeCompare(a.date));

  return (
    <PageShell current="/daily/">
      <div className="page-head">
        <h1>日报</h1>
        <p className="page-head__desc">
          {`每天早上 8 点后出一期，把过去一天里最值得看的 ${site.subject} 动态挑出来。`}
        </p>
      </div>

      {entries.length === 0 ? (
        <p className="empty">
          还没有日报。
          <br />
          出刊脚本跑过之后，这里会按日期倒序列出每一期。
          <br />
          <Link href="/all/">先去看全部动态</Link>
        </p>
      ) : (
        <>
          <EditionList
            entries={entries.map((entry) => ({
              key: entry.date,
              href: href(`/daily/${entry.date}`),
              label: entry.date,
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
