# DECISIONS — 用户已确认的决策

> **状态**：D1–D12 已于 2026-10-21 由用户逐条确认。
> **约束**：执行模型不得自行更改下列任何一项；如需变更，须用户明确同意，并在文末「修订记录」追加。
> **确认方式**：执行模型把计划 §1 决策表逐条发给用户，用户在选项中选定。

---

## D1 站名 / 副名

**确认值**：站名 `UXHOT`，副名「AI 用研热点」

- 与 AIHOT 不撞名，符合计划成功标准 6（页面与代码不出现 AIHOT 名字和 Logo）。
- 用于 `config/site.yaml` 的 `name` / `alias`，以及页面标题、页脚、文字 Logo。

## D2 行业词

**确认值**：`AI 用研`

- 用于「AI 用研日报」「全部 AI 用研动态」等所有文案，对应 `config/site.yaml` 的 `subject`。
- 注意：这是业内简称，关于页需要一句话说明「AI 用研 = AI 与用户研究」。

## D3 收录边界

**确认值**：采纳计划建议

**收**：
- AI 驱动的研究工具、方法、论文、行业事件；
- 用研行业本身的重大事件（研究/调研公司融资并购上市裁员、产品下线、合作、岗位与组织变化、隐私伦理监管、行业协会规范）。

**不收**：
- 泛 AI 模型发布（除非直接改变研究工具能力）；
- UI 设计灵感；
- 增长营销。

**影响**：`prompts/prefilter.md` 按此放宽/收紧；`prompts/selection-score.md` 的「必须压住的噪声」按此写例子。

## D4 分类

**确认值**：采纳 6 类，key 上线后不改

| key | label | section |
|---|---|---|
| `tools` | 工具 | 工具发布/更新 |
| `methods` | 方法 | 方法与实践 |
| `research` | 论文 | 研究与证据 |
| `industry` | 行业 | 行业动态（必需的兜底类，未归类的进它的分节） |
| `cases` | 案例 | 案例与落地 |
| `opinion` | 观点 | 观点与讨论 |

## D5 信源名单

**确认值**：采纳实测名单，**去掉偏题的 4 个**（Smashing Magazine、McKinsey Insights、JMIR、AMA）

- 全部信源均由执行模型实测：HTTP 200 + 有条目 + 日期可解析。
- 计划 §4.4 初稿里直接写死的地址**大部分不可用**（21 个 404/403/SSL 失败），已按实测结果替换。

### 入选：29 个 RSS（editorial）

**T1 官方一手 — 20 个**

| id | 名称 | feed | entity |
|---|---|---|---|
| `dovetail-blog` | Dovetail Blog | `https://dovetail.com/blog/rss.xml` | dovetail |
| `nngroup` | Nielsen Norman Group | `https://www.nngroup.com/feed/rss/` | nngroup |
| `medallia` | Medallia | `https://www.medallia.com/feed/` | medallia |
| `qualtrics` | Qualtrics | `https://www.qualtrics.com/rss.xml` | qualtrics |
| `xm-institute` | Qualtrics XM Institute | `https://xm-institute.com/feed/` | qualtrics |
| `listen-labs` | Listen Labs | `https://listenlabs.com/articles/feed/` | listen-labs |
| `maxqda` | MAXQDA | `https://maxqda.com/blog/feed/` | maxqda |
| `quirkos` | Quirkos | `https://quirkos.com/blog/feed/` | quirkos |
| `delve` | Delve | `https://delvetool.com/rss.xml` | delve |
| `surveycto` | SurveyCTO | `https://surveycto.com/blog/feed/` | surveycto |
| `surveymonkey` | SurveyMonkey | `https://surveymonkey.com/feed/` | surveymonkey |
| `quantilope` | quantilope | `https://quantilope.com/blog/rss.xml` | quantilope |
| `mopinion` | Mopinion | `https://mopinion.com/feed/` | mopinion |
| `dynata` | Dynata | `https://www.dynata.com/feed/` | dynata |
| `cint` | Cint | `https://www.cint.com/blog/feed/` | cint |
| `prodege` | Prodege | `https://www.prodege.com/feed/` | prodege |
| `ipsos` | Ipsos | `https://www.ipsos.com/en/rss.xml` | ipsos |
| `aapor` | AAPOR（美国民意研究协会） | `https://aapor.org/feed/` | aapor |
| `uxpa` | UXPA（用户体验专业协会） | `https://uxpa.org/feed/` | uxpa |
| `testingtime` | TestingTime | `https://www.testingtime.com/blog/feed/` | testingtime |

> ⚠️ `testingtime` 最后更新 2026-07-09（约 103 天前），偏冷。阶段 3 的 `check_sources.py` 复验；仍不更新则移出。

**T2 学术 — 2 个**

| id | 名称 | feed |
|---|---|---|
| `arxiv-cs-hc` | arXiv cs.HC | `https://export.arxiv.org/rss/cs.HC` |
| `frontiers-cs` | Frontiers in Computer Science | `https://www.frontiersin.org/journals/computer-science/rss` |

**T2 媒体与个人 — 7 个**

| id | 名称 | feed |
|---|---|---|
| `measuringu` | MeasuringU（Jeff Sauro） | `https://measuringu.com/feed/` |
| `producttalk` | Product Talk（Teresa Torres） | `https://producttalk.org/feed/` |
| `uxdesign-cc` | UX Collective | `https://uxdesign.cc/feed` |
| `rosenfeldmedia` | Rosenfeld Media | `https://rosenfeldmedia.com/feed/` |
| `jakobnielsenphd` | Jakob Nielsen on UX（Substack） | `https://jakobnielsenphd.substack.com/feed` |
| `johnnyholland` | Johnny Holland | `https://johnnyholland.org/blog/feed/` |
| `uxmag` | UX Magazine | `https://uxmag.com/feed` |

> ⚠️ `uxmag` 最后更新 2026-06-30（约 112 天前），偏冷。处理同上。

### 入选：2 个 hot_signal（只记热度，不展示、不评分）

| id | 名称 | feed |
|---|---|---|
| `reddit-uxresearch` | Reddit r/UXResearch | `https://www.reddit.com/r/UXResearch/.rss` |
| `hnrss-user-research` | HNRSS 关键词 user research | `https://hnrss.org/newest?q=user+research` |

### 入选：6 个 web_list（无 RSS，用网页列表抓取；均为 T1）

| id | 名称 | 列表页 |
|---|---|---|
| `usertesting-blog` | UserTesting Blog | `https://www.usertesting.com/blog` |
| `userinterviews-blog` | User Interviews Blog | `https://www.userinterviews.com/blog` |
| `optimalworkshop-blog` | Optimal Workshop Blog | `https://www.optimalworkshop.com/blog` |
| `greatquestion-blog` | Great Question Blog | `https://greatquestion.co/blog` |
| `sprig-blog` | Sprig Blog | `https://sprig.com/blog` |
| `strella-blog` | Strella Blog | `https://strella.io/blog` |

选择器（`itemSelector/titleSelector/linkSelector/dateSelector`）在阶段 3 逐个实测确定。

**合计 37 个信源**（T1 26 / T2 9 / hot_signal 2），超过计划门槛「≥30 个成功、T1 ≥10」。

### 明确排除，及理由

**僵尸源（能解析，但多年不更新；不可用）**

| 域名 | 最后更新 |
|---|---|
| getfeedback.com | 2017-05 |
| marvelapp.com | 2022-06 |
| boxesandarrows.com | 2022-07 |
| usabilitygeek.com | 2024-01 |
| thearf.org | 2024-01 |
| pollfish.com | 2024-02 |
| uxmatters.com | 2024-03 |
| researchops.community | 2023-11 |
| playbookux.com | 2025-07 |

**用户指定去掉的偏题源**：Smashing Magazine（前端/设计）、McKinsey Insights（泛商业咨询）、JMIR（医学信息学）、AMA（泛营销）。

**二期候选（JS 渲染，静态抓取拿不到列表，需无头浏览器）**：Maze、Outset、Conveo。`lookback.com/blog` 返回 404，博客地址待查。

## D6 托管

**确认值**：GitHub Pages

- **仓库必须设为 public**（私有仓库的 Pages 需要 GitHub Pro）。
- public 仓库的 Actions 分钟数免费。
- 部署方式：仓库 Settings → Pages → Source 选「GitHub Actions」。

## D7 仓库名

**确认值**：`huangzhenhao90/ai-ux-research-hot`

> ⚠️ **与计划默认值不同**。计划 §3.1 里预填的 `siteUrl` 是 `https://huangzhenhao90.github.io/uxhot`，必须改为：
>
> ```
> https://huangzhenhao90.github.io/ai-ux-research-hot
> ```
>
> 前端 `basePath` / `assetPrefix` 与 `config/site.yaml` 的 `siteUrl` 都取这个值（阶段 3、阶段 6）。
>
> 创建仓库与首次 push 之前，执行模型会**再次单独征求用户同意**（计划 §2.7）。

## D8 模型

**确认值**：DeepSeek（OpenAI 兼容）

- key 由用户自己填进 Actions Secret `LLM_API_KEY`；执行模型不接触 key 明文。
- 环境变量：`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`；评分步骤可用 `SCORE_MODEL` 单独覆盖。
- 本机默认零调用：只有 `--execute` + 有 `LLM_API_KEY` + `MODEL_CALLS_ENABLED=true` 才真调用。

## D9 单次运行模型调用上限（预算熔断）

**确认值**：每次运行 ≤ 300 次调用，每天 ≤ 1000 次，超出即停

- 写入 `config/selection.yaml` 的 `budget.perRunCalls` / `budget.perDayCalls`。
- `budget.py` 统一计数；超限立即停止后续调用，已完成的保留，并写进运行审计。

## D10 更新频率

**确认值**：每 4 小时采集评分一次；日报北京时间 08:00（UTC 00:00）出

- 写入 `config/site.yaml` 的 `editions`。
- 关于页如实写「每天早上 8 点后」：Actions 定时任务常延迟 5–30 分钟，实际出刊可能 08:10–08:40。

## D11 金标谁标

**确认值**：**用户从零标注，执行模型不给任何建议**

> ⚠️ **与计划默认值不同**。计划 §阶段 8 写的是「执行模型抽样并给建议，用户逐条确认」，用户改为完全由本人从零标注。
>
> **对阶段 8 的直接影响**：
> - `scripts/sample_gold.py` 只做**分层抽样与导出**：按分类、tier、门槛附近（均分 ±10）分层抽 150 条，导出 `eval/gold_candidates.xlsx`（标题、来源、tier、摘要、原文链接、`select/reject/either` 下拉、备注）。
> - **不导出「模型均分」与「模型建议」列**，避免锚定标注。
> - 用户标注期间，执行模型不参与判读、不给样例、不解释倾向。
> - 回收后由脚本转 `eval/gold.jsonl`，按 2:1 分 `development` / `holdout`。
> - 评测脚本对每条重跑两次评分，只用于算指标与门槛曲线，不参与标注。
>
> 「不允许模型自标自评」这条底线仍然成立。

## D12 与已有项目联动

**确认值**：**一期就做**——读 `ur-ai-papers` 的公开数据，把高分论文并进「论文」类

> ⚠️ **与计划默认值不同**。计划把这条放在二期。
>
> **对一期的直接影响**：
> - 阶段 3：新增 `config/sources.yaml` 里的 `ur-ai-papers` 信源条目（`kind: external_json` 或独立适配器），并确认其公开数据路径与字段。
> - 阶段 5：`collect/` 需要一个读取 `ur-ai-papers` 公开数据的适配器，与 RSS 采集统一进 normalize。
> - 约束：`ur-ai-papers` 是**只读上游**，不得修改、提交、推送或停用（见其 `AGENTS.md` 不可破坏的契约 1）。
> - 去重：同一论文可能同时来自 `ur-ai-papers` 和 arXiv cs.HC，必须走同一套 URL 规范化去重，不能重复入选。

---

## 待办（由本次确认衍生）

| # | 事项 | 阶段 |
|---|---|---|
| 1 | `siteUrl` 用 `ai-ux-research-hot`，不是 `uxhot` | 3、6 |
| 2 | `sample_gold.py` 不导出模型建议列 | 8 |
| 3 | `ur-ai-papers` 适配器与只读约束 | 3、5 |
| 4 | `check_sources.py` 复验 `testingtime`、`uxmag` 的活跃度 | 3 |
| 5 | 6 个 web_list 信源的选择器实测 | 3 |

## 修订记录

| 日期 | 变更 | 依据 |
|---|---|---|
| 2026-10-21 | D1–D12 首次确认 | 用户在决策表选项中选择 |
