"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { IconExternal, IconSearch } from "@/components/icons";
import { daysAgoLabel, daysBetween, monthDay } from "@/lib/format";
import type { SocialJob } from "@/lib/types";

/** 列表里用不到职责 / 要求全文，只带前一段做摘要，页面数据小一些。 */
export type SocialListJob = Omit<SocialJob, "duty" | "requirement"> & { summary: string };

type Age = "all" | "m1" | "m2" | "m3";

/** 窗口按月分三段：第一个月、第二个月、第三个月（按起算日算）。 */
// 官网日期偶尔比构建时的「今天」晚一天（时区差），算作 0 天以内，不能因此从列表里消失
const AGES: { key: Age; label: string; min: number; max: number }[] = [
  { key: "all", label: "全部", min: -Infinity, max: Infinity },
  { key: "m1", label: "30 天内", min: -Infinity, max: 30 },
  { key: "m2", label: "31–60 天", min: 31, max: 60 },
  { key: "m3", label: "61–90 天", min: 61, max: Infinity },
];

function matchesQuery(job: SocialListJob, query: string): boolean {
  if (!query) return true;
  const text = [job.company, job.title, job.department, job.experience, job.summary, ...job.cities]
    .join(" ")
    .toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((term) => text.includes(term));
}

/**
 * 社招岗位的筛选：按窗口分段、公司、城市与关键词，全部在浏览器里做；筛选写进链接。
 *
 * `today` 由服务端在构建时传入，前后端用同一天算「几天前」，不会出现水合不一致。
 */
export function SocialClient({
  jobs,
  companies,
  cities,
  today,
}: {
  jobs: SocialListJob[];
  companies: { name: string; count: number }[];
  cities: string[];
  today: string;
}) {
  const [age, setAge] = useState<Age>("all");
  const [company, setCompany] = useState<string | null>(null);
  const [city, setCity] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const a = p.get("age");
    if (AGES.some((x) => x.key === a)) setAge(a as Age);
    const co = p.get("company");
    if (co && companies.some((c) => c.name === co)) setCompany(co);
    const ci = p.get("city");
    if (ci && cities.includes(ci)) setCity(ci);
    setQuery(p.get("q") ?? "");
    // 只在首次挂载时读一次链接，之后由用户操作改写
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    const set = (key: string, value: string | null) => {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    };
    set("age", age === "all" ? null : age);
    set("company", company);
    set("city", city || null);
    set("q", query.trim() || null);
    window.history.replaceState(null, "", url);
  }, [age, company, city, query]);

  const ageOf = (job: SocialListJob) => daysBetween(job.since, today);

  const ageCounts = useMemo(() => {
    const counts: Record<Age, number> = { all: jobs.length, m1: 0, m2: 0, m3: 0 };
    for (const job of jobs) {
      const days = ageOf(job);
      const bucket = AGES.find((x) => x.key !== "all" && days >= x.min && days <= x.max);
      if (bucket) counts[bucket.key] += 1;
    }
    return counts;
  }, [jobs, today]);

  const shown = useMemo(() => {
    const range = AGES.find((x) => x.key === age)!;
    return jobs.filter((job) => {
      const days = ageOf(job);
      return (
        days >= range.min &&
        days <= range.max &&
        (!company || job.company === company) &&
        (!city || job.cities.includes(city)) &&
        matchesQuery(job, query.trim())
      );
    });
  }, [jobs, age, company, city, query, today]);

  function reset() {
    setAge("all");
    setCompany(null);
    setCity("");
    setQuery("");
  }

  const filtered = !!(age !== "all" || company || city || query.trim());

  return (
    <>
      <div className="feed-bar">
        <div className="pill-tabs" role="group" aria-label="按收录时间筛选">
          {AGES.map((option) => (
            <button
              key={option.key}
              type="button"
              className="pill-tabs__tab"
              aria-pressed={age === option.key}
              onClick={() => setAge(option.key)}
            >
              {option.label} <span className="num">{ageCounts[option.key]}</span>
            </button>
          ))}
        </div>
        <div className="feed-bar__tools">
          <label className="search-box">
            <IconSearch size={15} />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜公司、岗位、职责…"
              aria-label="搜索"
              className="search-box__input"
            />
          </label>
        </div>
      </div>

      <div className="chip-row" role="group" aria-label="按公司筛选">
        <button type="button" className="chip" aria-pressed={company === null} onClick={() => setCompany(null)}>
          全部公司
        </button>
        {companies.map((c) => (
          <button
            key={c.name}
            type="button"
            className="chip"
            aria-pressed={company === c.name}
            onClick={() => setCompany(company === c.name ? null : c.name)}
          >
            {c.name} <span className="num">&nbsp;{c.count}</span>
          </button>
        ))}
        {cities.length > 1 ? (
          <>
            <span className="chip-row__sep" aria-hidden="true" />
            <select
              className="day-select chip-select"
              aria-label="城市"
              value={city}
              onChange={(event) => setCity(event.target.value)}
            >
              <option value="">全部城市</option>
              {cities.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </>
        ) : null}
      </div>

      <p className="section__count campus-count" aria-live="polite">
        <span>
          共 <span className="num">{shown.length}</span> 个岗位
        </span>
        {filtered ? (
          <button type="button" className="link-button" onClick={reset}>
            清除筛选
          </button>
        ) : null}
      </p>

      {shown.length === 0 ? (
        <p className="empty">没有符合条件的岗位，换个筛选试试。</p>
      ) : (
        <div className="card-list">
          {shown.map((job) => (
            <JobCard key={job.id} job={job} today={today} onCompany={setCompany} />
          ))}
        </div>
      )}
    </>
  );
}

function JobCard({
  job,
  today,
  onCompany,
}: {
  job: SocialListJob;
  today: string;
  onCompany: (name: string) => void;
}) {
  const refYear = today.slice(0, 4);
  const when = `${daysAgoLabel(job.postedAt, today)}${job.dateKind === "publish" ? "发布" : "更新"}`;
  const cities = job.cities.length > 2 ? `${job.cities.slice(0, 2).join("、")} 等` : job.cities.join("、");
  return (
    <article className="card card--item">
      <header className="card__head">
        <button
          type="button"
          className="card__source card__raise link-button"
          onClick={() => {
            onCompany(job.company);
            window.scrollTo({ top: 0 });
          }}
          title={`只看${job.company}的岗位`}
        >
          {job.company}
        </button>
        {cities ? <span className="badge">{cities}</span> : null}
        <span className="badge badge--accent" title={`官网${job.dateKind === "publish" ? "发布" : "更新"}于 ${job.postedAt}`}>
          {when}
        </span>
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="card__origin card__raise"
          title="打开官方岗位页"
        >
          官方投递
          <IconExternal size={12} />
        </a>
      </header>

      <h3 className="card__title">
        <Link href={`/social/${job.id}/`} className="card__link">
          {job.title}
        </Link>
      </h3>

      {job.summary ? <p className="card__summary">{job.summary}</p> : null}

      <div className="card__tags">
        {job.department ? <span>{job.department}</span> : null}
        {job.experience ? <span>{job.experience}</span> : null}
        <span>预计 {monthDay(job.expiresAt, refYear)}下架</span>
      </div>
    </article>
  );
}
