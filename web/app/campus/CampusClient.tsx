"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { IconExternal, IconSearch } from "@/components/icons";
import type { CampusCompany, CampusJob } from "@/lib/types";

type View = "jobs" | "companies";
type CompanyScope = "hiring" | "none" | "all";

/** 公司库视图的三档：有用研岗 / 暂无 / 全部（原站默认只看有岗的）。 */
const COMPANY_SCOPES: { key: CompanyScope; label: string }[] = [
  { key: "hiring", label: "有用研岗" },
  { key: "none", label: "暂无用研岗" },
  { key: "all", label: "全部公司" },
];

function matchesQuery(job: CampusJob, query: string): boolean {
  if (!query) return true;
  const text = [job.company, job.title, job.tagline, job.location, job.business, job.jd, ...job.flags]
    .join(" ")
    .toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((term) => text.includes(term));
}

/**
 * 校招岗位与公司库的筛选。
 *
 * 数据量很小（几十条），全部在浏览器里筛；当前视图与筛选写进 URL，分享链接能还原。
 */
export function CampusClient({
  jobs,
  companies,
  industries,
  types,
}: {
  jobs: CampusJob[];
  companies: CampusCompany[];
  industries: string[];
  types: string[];
}) {
  const [view, setView] = useState<View>("jobs");
  const [industry, setIndustry] = useState<string | null>(null);
  const [type, setType] = useState("");
  const [company, setCompany] = useState<string | null>(null);
  const [aiOnly, setAiOnly] = useState(false);
  const [multiOnly, setMultiOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<CompanyScope>("hiring");

  // 打开页面时从链接还原筛选
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    if (p.get("view") === "companies") setView("companies");
    const ind = p.get("industry");
    if (ind && industries.includes(ind)) setIndustry(ind);
    const t = p.get("type");
    if (t && types.includes(t)) setType(t);
    const co = p.get("company");
    if (co && companies.some((c) => c.name === co)) setCompany(co);
    if (p.get("ai") === "1") setAiOnly(true);
    if (p.get("multi") === "1") setMultiOnly(true);
    setQuery(p.get("q") ?? "");
    // 只在首次挂载时读一次链接，之后由用户操作改写
  }, []);

  // 筛选变化时同步到链接（replaceState，不产生历史记录）
  useEffect(() => {
    const url = new URL(window.location.href);
    const set = (key: string, value: string | null) => {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    };
    set("view", view === "companies" ? "companies" : null);
    set("industry", industry);
    set("type", type || null);
    set("company", company);
    set("ai", aiOnly ? "1" : null);
    set("multi", multiOnly ? "1" : null);
    set("q", query.trim() || null);
    window.history.replaceState(null, "", url);
  }, [view, industry, type, company, aiOnly, multiOnly, query]);

  const shownJobs = useMemo(
    () =>
      jobs.filter(
        (job) =>
          (!industry || job.industry === industry) &&
          (!type || job.type === type) &&
          (!company || job.company === company) &&
          (!aiOnly || job.ai) &&
          (!multiOnly || job.multipleHires) &&
          matchesQuery(job, query.trim()),
      ),
    [jobs, industry, type, company, aiOnly, multiOnly, query],
  );

  const shownCompanies = useMemo(() => {
    const q = query.trim().toLowerCase();
    return companies.filter(
      (c) =>
        (!industry || c.industry === industry) &&
        (scope === "all" || (scope === "hiring" ? c.jobCount > 0 : c.jobCount === 0)) &&
        (!q || [c.name, c.recruitment, c.research].join(" ").toLowerCase().includes(q)),
    );
  }, [companies, industry, scope, query]);

  function pickCompany(name: string) {
    setCompany(name);
    setView("jobs");
    window.scrollTo({ top: 0 });
  }

  function reset() {
    setIndustry(null);
    setType("");
    setCompany(null);
    setAiOnly(false);
    setMultiOnly(false);
    setQuery("");
  }

  const filtered = !!(industry || type || company || aiOnly || multiOnly || query.trim());

  return (
    <>
      <div className="feed-bar">
        <div className="pill-tabs" role="group" aria-label="切换视图">
          <button
            type="button"
            className="pill-tabs__tab"
            aria-pressed={view === "jobs"}
            onClick={() => setView("jobs")}
          >
            岗位 <span className="num">{jobs.length}</span>
          </button>
          <button
            type="button"
            className="pill-tabs__tab"
            aria-pressed={view === "companies"}
            onClick={() => setView("companies")}
          >
            公司库 <span className="num">{companies.length}</span>
          </button>
        </div>
        <div className="feed-bar__tools">
          <label className="search-box">
            <IconSearch size={15} />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={view === "jobs" ? "搜公司、岗位、职责…" : "搜公司…"}
              aria-label="搜索"
              className="search-box__input"
            />
          </label>
        </div>
      </div>

      <div className="chip-row" role="group" aria-label="按行业筛选">
        <button
          type="button"
          className="chip"
          aria-pressed={industry === null}
          onClick={() => setIndustry(null)}
        >
          全部行业
        </button>
        {industries.map((name) => (
          <button
            key={name}
            type="button"
            className="chip"
            aria-pressed={industry === name}
            onClick={() => setIndustry(industry === name ? null : name)}
          >
            {name}
          </button>
        ))}
        <span className="chip-row__sep" aria-hidden="true" />
        {view === "jobs" ? (
          <>
            <select
              className="day-select chip-select"
              aria-label="岗位类型"
              value={type}
              onChange={(event) => setType(event.target.value)}
            >
              <option value="">全部类型</option>
              {types.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="chip"
              aria-pressed={aiOnly}
              onClick={() => setAiOnly(!aiOnly)}
            >
              职责含 AI
            </button>
            <button
              type="button"
              className="chip"
              aria-pressed={multiOnly}
              onClick={() => setMultiOnly(!multiOnly)}
            >
              招多人
            </button>
          </>
        ) : (
          COMPANY_SCOPES.map((option) => (
            <button
              key={option.key}
              type="button"
              className="chip"
              aria-pressed={scope === option.key}
              onClick={() => setScope(option.key)}
            >
              {option.label}
            </button>
          ))
        )}
      </div>

      {view === "jobs" ? (
        <>
          <p className="section__count campus-count" aria-live="polite">
            {company ? (
              <button type="button" className="chip chip--active" onClick={() => setCompany(null)}>
                只看 {company} ×
              </button>
            ) : null}
            <span>
              共 <span className="num">{shownJobs.length}</span> 个岗位
            </span>
            {filtered ? (
              <button type="button" className="link-button" onClick={reset}>
                清除筛选
              </button>
            ) : null}
          </p>
          {shownJobs.length === 0 ? (
            <p className="empty">没有符合条件的岗位，换个筛选试试。</p>
          ) : (
            <div className="card-list">
              {shownJobs.map((job) => (
                <JobCard key={job.id} job={job} onCompany={pickCompany} />
              ))}
            </div>
          )}
        </>
      ) : (
        <>
          <p className="section__count campus-count" aria-live="polite">
            <span>
              共 <span className="num">{shownCompanies.length}</span> 家公司
            </span>
          </p>
          {shownCompanies.length === 0 ? (
            <p className="empty">没有符合条件的公司。</p>
          ) : (
            <div className="grid-cards">
              {shownCompanies.map((c) => (
                <CompanyTile key={c.name} company={c} onPick={pickCompany} />
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}

function JobCard({ job, onCompany }: { job: CampusJob; onCompany: (name: string) => void }) {
  const facts = [job.location, job.headcount, job.degree].filter(Boolean);
  return (
    <article className="card card--item">
      <header className="card__head">
        <button
          type="button"
          className="card__source card__raise link-button"
          onClick={() => onCompany(job.company)}
          title={`只看${job.company}的岗位`}
        >
          {job.company}
        </button>
        <span className="badge">{job.industry}</span>
        <span className="badge badge--accent">{job.type}</span>
        {job.ai ? <span className="badge badge--selected">职责含 AI</span> : null}
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
        <Link href={`/campus/${job.id}/`} className="card__link">
          {job.title}
        </Link>
      </h3>

      {job.tagline ? <p className="card__summary">{job.tagline}</p> : null}

      {facts.length > 0 || job.flags.length > 0 ? (
        <div className="card__tags">
          {facts.map((fact) => (
            <span key={fact}>{fact}</span>
          ))}
          {job.flags
            .filter((flag) => !/AI/.test(flag))
            .slice(0, 3)
            .map((flag) => (
              <span key={flag}>#{flag}</span>
            ))}
        </div>
      ) : null}
    </article>
  );
}

function CompanyTile({
  company,
  onPick,
}: {
  company: CampusCompany;
  onPick: (name: string) => void;
}) {
  return (
    <div className="tile company-tile">
      <div className="company-tile__head">
        <span className="company-tile__mark" aria-hidden="true">
          {company.mark}
        </span>
        <span className="company-tile__name">{company.name}</span>
        <span className={company.status === "open" ? "badge badge--accent" : "badge"}>
          {company.status === "open" ? "校招已开" : "待确认"}
        </span>
      </div>
      <p className="tile__desc">
        {company.industry}
        {company.recruitment ? ` · ${company.recruitment}` : ""}
      </p>
      {company.research ? <p className="tile__desc">{company.research}</p> : null}
      <div className="company-tile__foot">
        {company.jobCount > 0 ? (
          <button type="button" className="link-button" onClick={() => onPick(company.name)}>
            看 {company.jobCount} 个岗位 →
          </button>
        ) : (
          <span className="section__count">暂未收录岗位</span>
        )}
        {company.url ? (
          <a href={company.url} target="_blank" rel="noopener noreferrer nofollow" className="link-button">
            招聘官网 ↗
          </a>
        ) : null}
      </div>
    </div>
  );
}
