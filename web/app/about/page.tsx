import { Fragment } from "react";

import type { Metadata } from "next";
import Link from "next/link";

import { groupSources, readSources } from "@/app/_lib/sources";
import { PageShell } from "@/components/PageShell";
import { getSite } from "@/lib/data";

export const metadata: Metadata = {
  title: "关于",
  description: "这个站做什么、条目怎么选出来的、信源有哪些、多久更新一次。",
};

/**
 * 中文段落整段写成一行字符串：JSX 里换行会被折成一个空格，
 * 中文标点后面多一个空格不好看，所以这里不让它换行。
 */
const WHAT_IT_IS =
  "「AI 用研」是「AI 与用户研究」的简称，两头都算：一头是用户研究本身正在被 AI 改变——AI 访谈、合成用户、自动编码与主题分析、问卷与可用性测试的自动化；另一头是 AI 产品要被人用起来，仍然得靠访谈、测试和调研来回答体验问题。本站只收这两类交叉的动态，纯模型发布、融资快讯这类不沾研究方法的，一律不进。";

const HOW_TO_READ =
  "「精选」只放入选的条目，「全部动态」放已写好中文标题和摘要的全部条目（含没入选的），两边都按天排成时间线，可以按分类筛选，也可以直接跳到某一天。";

const SCORE_NOTE_HEAD = "评分与模型打分只用来决定入选和排序，不在页面上公开显示（";
const SCORE_NOTE_TAIL = "）。每一条都能点回原文，判断留给你自己。";

export default function AboutPage() {
  const site = getSite();

  const sources = readSources();
  const { groups, excluded } = groupSources(sources);
  const active = sources.length - excluded.length;

  const rssPath = `${site.basePath}/rss.xml`;

  return (
    <PageShell current="/about/">
      <div className="page-head">
        <h1>关于 {site.name}</h1>
        <p className="page-head__desc">{site.tagline}</p>
      </div>

      <div className="prose">
        <h2>这个站做什么</h2>
        <p>{site.description}</p>
        <p>{WHAT_IT_IS}</p>
        <p>{HOW_TO_READ}</p>

        <h2>怎么选的</h2>
        <ol>
          <li>
            <strong>从信源抓取。</strong>
            {"每 4 小时扫一遍"}
            <Link href="/about/#sources">下面的信源</Link>
            {"，把新条目连同发布时间、原文地址一起入库，去重后进待筛池。"}
          </li>
          <li>
            <strong>模型预筛。</strong>
            {"先用一遍轻量判断把明显无关的条目剔掉——招聘、促销、与用户研究无关的通用 AI 新闻等，不进入评分环节。"}
          </li>
          <li>
            <strong>同一标准独立打两次分。</strong>
            {"留下来的条目用同一套标准、两次独立打分，取均值作为分数；再按信源分级设不同门槛（官方一手源门槛低一些，媒体与个人源门槛高一些）决定入选。同一事件有多个独立来源时，按来源数加权，在版面上优先展示。"}
          </li>
          <li>
            <strong>写中文标题、摘要与推荐理由。</strong>
            {"入选条目由模型补上中文标题、两三句摘要，以及一句「为什么值得看」；这一步只做翻译与提炼，不改动事实，也不增删条目。"}
          </li>
        </ol>
        <p>
          {SCORE_NOTE_HEAD}
          <code>showScore: {String(site.showScore)}</code>
          {SCORE_NOTE_TAIL}
        </p>

        <h2 id="sources">信源</h2>
        {sources.length === 0 ? (
          <p className="empty">
            构建时读不到信源名单（<code>config/sources.yaml</code>）。
            <br />
            名单以仓库里的那份配置文件为准，这里先留空。
          </p>
        ) : (
          <>
            <p>
              {`共 ${sources.length} 个信源，其中 ${active} 个参与精选。名单与分级维护在仓库的 `}
              <code>config/sources.yaml</code>
              {"，改那个文件即可，不用动代码。"}
            </p>
            <table className="source-table">
              <thead>
                <tr>
                  <th scope="col">信源</th>
                  <th scope="col">分级</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => (
                  <Fragment key={group.tier}>
                    <tr>
                      <th
                        scope="colgroup"
                        colSpan={2}
                        style={{ paddingTop: "1.1rem" }}
                      >
                        {group.label}
                      </th>
                    </tr>
                    {group.sources.map((source) => (
                      <tr key={source.id}>
                        <td>{source.name}</td>
                        <td>{group.tier}</td>
                      </tr>
                    ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
            {excluded.length > 0 ? (
              <p>
                {`另有 ${excluded.length} 个信源只用来记录热度信号，不参与精选：`}
                {excluded.map((source) => source.name).join("、")}
                {"。"}
              </p>
            ) : null}
          </>
        )}

        <h2>更新频率</h2>
        <ul>
          <li>采集：每 4 小时扫一次信源（定时任务本身会延迟，所以不承诺整点）。</li>
          <li>新入选的条目随即出现在精选里，不用等固定出刊时间。</li>
        </ul>

        <h2>订阅</h2>
        <p>
          {"RSS："}
          <a href={rssPath}>{rssPath}</a>
        </p>

        <h2>致谢</h2>
        <p>
          {"提示词、精选方法与界面样式改编自 "}
          <a
            href="https://github.com/KKKKhazix/AIHOT"
            target="_blank"
            rel="noopener noreferrer"
          >
            AIHOT
          </a>
          {"（MIT）。"}
        </p>
        <p>
          {"站上条目只展示中文摘要与原文链接，正文与图片版权归各发布方所有；如果你是被收录方并希望调整展示方式，可以通过仓库开 issue 联系。"}
        </p>
      </div>
    </PageShell>
  );
}
