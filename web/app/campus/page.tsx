import type { Metadata } from "next";

import { PageShell } from "@/components/PageShell";
import { getCampus } from "@/lib/data";

import { CampusClient } from "./CampusClient";

export const metadata: Metadata = {
  title: "用研校招",
  description:
    "2027 届用户研究、市场研究、用户洞察与体验研究方向的正式校招岗位，附官方链接、岗位分析与投递建议。",
};

/** 类型筛选的固定顺序（与原岗位库一致），数据里没出现的类型不显示。 */
const TYPE_ORDER = ["战略/策略向", "交互/设计向", "体验管理向", "不确定"];

/**
 * 用研校招。
 *
 * 数据只在 uxr-campus-2027 仓库里维护，这里读同步过来的快照
 * （见 `web/scripts/sync-campus.mjs`，定时任务每次运行前同步）。
 */
export default function CampusPage() {
  const doc = getCampus();

  if (!doc) {
    return (
      <PageShell current="/campus/">
        <div className="page-head">
          <h1>用研校招</h1>
        </div>
        <p className="empty">校招岗位库还没有同步过来，下一次定时更新后会出现。</p>
      </PageShell>
    );
  }

  const { jobs, companies, source } = doc;
  const industries = [...new Set(companies.map((c) => c.industry))];
  const types = TYPE_ORDER.filter((t) => jobs.some((j) => j.type === t));
  const hiring = companies.filter((c) => c.jobCount > 0).length;
  const open = companies.filter((c) => c.status === "open").length;

  return (
    <PageShell current="/campus/">
      <div className="page-head page-head--row">
        <h1>用研校招</h1>
        <span className="page-head__aside">
          2027 届{source.updated ? ` · 内容更新 ${source.updated}` : ""}
        </span>
      </div>
      <p className="page-head__desc" style={{ marginTop: "-0.5rem", marginBottom: "1rem" }}>
        {"只收已确认的 2027 届正式校招研究岗：用户研究、市场研究、用户洞察、体验研究、人因研究。每个岗位附官网原文、岗位分析与投递建议；岗位变化很快，投递前请以企业官网为准。"}
      </p>

      <div className="campus-stats">
        <span>
          <b className="num">{jobs.length}</b> 个岗位
        </span>
        <span>
          <b className="num">{hiring}</b> 家公司有岗
        </span>
        <span>
          <b className="num">{companies.length}</b> 家重点公司
        </span>
        <span>
          <b className="num">{open}</b> 家已开 27 届校招
        </span>
      </div>

      <CampusClient jobs={jobs} companies={companies} industries={industries} types={types} />

      <p className="feed-more">
        {"数据来自 "}
        <a href={source.repoUrl} target="_blank" rel="noopener noreferrer">
          uxr-campus-2027 岗位库
        </a>
        {"（"}
        <a href={source.siteUrl} target="_blank" rel="noopener noreferrer">
          原站
        </a>
        {"）。公司库是重点公司观察池，不是全量榜单；「待确认」不等于不招。"}
      </p>
    </PageShell>
  );
}
