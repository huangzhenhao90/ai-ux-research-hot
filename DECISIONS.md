# DECISIONS — 用户已确认的决策

> **状态**：D1–D12 已于 2026-10-21 由用户逐条确认。
> **约束**：执行模型不得自行更改下列任何一项；如需变更，须用户明确同意，并在文末「修订记录」追加。
> **确认方式**：执行模型把计划 §1 决策表逐条发给用户，用户在选项中选定。

---

## D1 站名 / 副名

**确认值**：站名 `UXHOT`，副名「AI 用研热点」

> **2026-10-28 修订**：站名改为 `URHOT`（UR = User Research），副名不变。只改对外显示的站名（页面、标题、RSS、llms.txt、采集器 UA）；仓库名、Python 包名 `uxhot`、浏览器存储键等内部标识不变。

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

**2026-10-21 修订（用户第二次确认）**：补充 3 个 web_list 源（Maze、dscout People Nerds、MRS）与 4 本对口期刊（BIT、HCI、JMMR、IJMR）。见文末「修订记录」。

- 全部信源均由执行模型实测：HTTP 200 + 有条目 + 日期可解析。
- 计划 §4.4 初稿里直接写死的地址**大部分不可用**（21 个 404/403/SSL 失败），已按实测结果替换。

> ⚠️ **注意区分两件事**：feed 地址 404 ≠ 该站点抓不到内容。计划初稿里的地址确实不存在，
> 但其中多数站点本身可达、列表页可抽，改用 `web_list` 即可。实测 10 个被点名域名中 **8 个能抓到内容**。

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

**T2 学术 — 6 个**

| id | 名称 | feed |
|---|---|---|
| `arxiv-cs-hc` | arXiv cs.HC | `https://export.arxiv.org/rss/cs.HC` |
| `frontiers-cs` | Frontiers in Computer Science | `https://www.frontiersin.org/journals/computer-science/rss` |
| `bit` | Behaviour & Information Technology（行为与信息技术，HCI/UX） | `https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=tbit20` |
| `hci-journal` | Human-Computer Interaction（人机交互） | `https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=hhci20` |
| `jmmr` | Journal of Mixed Methods Research（混合方法研究杂志） | `https://journals.sagepub.com/action/showFeed?ui=0&mi=ehikzz&ai=2b4&jc=mmra&type=etoc&feed=rss` |
| `ijmr` | International Journal of Market Research（国际市场研究杂志） | `https://journals.sagepub.com/action/showFeed?ui=0&mi=ehikzz&ai=2b4&jc=mrea&type=etoc&feed=rss` |

来源：后 4 本复用 `ur-ai-papers/config/journals.yaml` 的 `rss` 字段（计划 §4.4 指定的做法）。
实测该文件 20 条 RSS 中 10 条可用，此处只取与 HCI／研究方法学最对口的 4 本；
`JMR / JM / MktSci / JCP / JCA / JSR` 属纯营销期刊，噪声高，暂不纳入。
`IJHCS`、`JR` 虽有条目但**日期解析不出**，暂不纳入（无日期会破坏「旧文不刷屏」规则）。

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

### 入选：9 个 web_list（无 RSS，用网页列表抓取；均为 T1）

| id | 名称 | 列表页 |
|---|---|---|
| `usertesting-blog` | UserTesting Blog | `https://www.usertesting.com/blog` |
| `userinterviews-blog` | User Interviews Blog | `https://www.userinterviews.com/blog` |
| `optimalworkshop-blog` | Optimal Workshop Blog | `https://www.optimalworkshop.com/blog` |
| `greatquestion-blog` | Great Question Blog | `https://greatquestion.co/blog` |
| `sprig-blog` | Sprig Blog | `https://sprig.com/blog` |
| `strella-blog` | Strella Blog | `https://strella.io/blog` |
| `maze-blog` | Maze Blog | `https://maze.co/blog/` |
| `dscout-people-nerds` | dscout People Nerds | `https://dscout.com/people-nerds` |
| `mrs-news` | MRS（英国市场研究协会）新闻 | `https://www.mrs.org.uk/news` |

选择器（`itemSelector/titleSelector/linkSelector/dateSelector`）在阶段 3 逐个实测确定。
实测每页可抽到的文章链接数：User Interviews 32、Sprig 25、Great Question 15、UserTesting 12、
Maze 7、Optimal Workshop 7、MRS 5；dscout 用 `/people-nerds/` 前缀（非 `/blog/`）。

**合计 44 个信源**（T1 29 / T2 13 / hot_signal 2），超过计划门槛「≥30 个成功、T1 ≥10」。

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

**站点本身抓不到（非 RSS 问题，整站不可用）**

| 域名 | 实测 | 原因 |
|---|---|---|
| `dl.acm.org`（TOCHI / TiiS / CHI eTOC） | **403** | 整站 Cloudflare 拦截，不只是 RSS 失效。计划 §4.4 说「复用 journals.yaml 的 rss 字段」，该字段对 ACM 已失效 |
| `esomar.org` | 200 但 15 KB | Next.js 全客户端渲染，HTML 里没有任何文章链接，静态抓取拿不到；需无头浏览器 |

**二期候选（需无头浏览器）**：ESOMAR。`lookback.com/blog` 返回 404，博客地址待查。

**已实测但暂不纳入的期刊**：`JMR`、`JM`、`MktSci`、`JCP`、`JCA`、`JSR`（纯营销/消费者，噪声高）；`IJHCS`、`JR`（有条目但日期解析不出，会破坏「旧文不刷屏」）。

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

## D13 站点外观

**确认值**：界面改为参照 AIHOT 的版式与配色（2026-10-28，用户提出「参照它的外观，甚至完全复刻也可以」）

- 采用：左侧栏导航（手机收成顶栏）、分类胶囊 + 搜索框、按天分组的竖向时间线、卡片顶部「来源 · 分类 · 精选 · 原文」、三档外观开关、暖白底 + 青色强调色。
- 不采用：AIHOT 的名称与 Logo（不在 MIT 范围内）；站名仍是纯文字（现为 `URHOT`）。
- 暂未做（缺数据或另需功能）：「当前热点」榜（需要跨信源聚类与热度）、AI 评分角标（`showScore: false`，评分不进公开数据）、收藏与「只看未读」。
- 计划成功标准 6 不变：渲染出的页面里 AIHOT 的名字仍只出现在关于页；代码注释只写「见 NOTICE」，不写名字。

## D14 去掉日报与周报

**确认值**：不再出日报和周报，「精选」与「全部动态」都按天浏览（2026-10-28，用户提出「日报周报太繁琐，和精选、全部动态重合」）

- 依据：日报的条目就是当期 08:00–08:00 的精选，只是按规则重排成头条、看点、分节；周报 4 期总述全是模板句，从未调过模型。两者都没有精选之外的信息。
- 网站：删除 `/daily/`、`/weekly/` 页面与侧栏入口；精选改为显示**全部历史**入选条目（原来只显示近 3 期），精选与全部动态都加「跳到日期」，链接带 `?date=` 可分享。
- 流水线：删除 `uxhot/report/`、`scripts/build_daily.py`、`scripts/build_weekly.py`、`data/reports/`、`docs/report-schema.md`、周报总述提示词 `prompts/report-period.md`；发布层不再透传报告、不再生成 `rss-daily.xml`；自动运行去掉「出日报与周报」一步和 UTC 00:05 的专用定时。
- 一并删除只给报告用的配置：`taxonomy.yaml` 的 `release`、`plainTerms`，`overrides.yaml` 的 `pin`（置顶只在日报里生效过）。
- 保留：`site.editions.daily`（08:00）仍是 `latest.json` 分期的分界时刻；主 RSS `rss.xml` 不变。
- 不影响成本：日报纯规则编排、周报用模板句，都不调模型。

## D15 用研校招 tab

**确认值**：把 `huangzhenhao90/uxr-campus-2027`（2027 届用研校招岗位库）并进本站，作为侧栏「求职 → 用研校招」（2026-10-28，用户提出）

- 数据只在 uxr-campus-2027 维护，本站只读：`web/scripts/sync-campus.mjs` 从它的 `index.html` 抽出 `JOBS` / `COMPANIES`（与那个仓库自己的数据测试同一切片口径），写成 `web/content/campus.json` 快照。
- 定时更新每次运行前同步；拉取失败或页面结构变了就沿用上一版快照，不拦整次更新。内容没变时不重写文件。
- 快照不放 `web/public/data/`：发布层每次会整体替换那个目录。
- 页面：`/campus/`（岗位 / 公司库两个视图，按行业、类型、职责含 AI、招多人筛选，可搜索，筛选写进链接）与 `/campus/<id>/`（官网原文、岗位分析、投递建议、核验说明、官方投递链接）。原校招站保留不动。
- 「用研社招」当时暂不做；后来改为直接抓公司招聘官网，见 D17。

## D16 没写出中文的条目不上页面

**确认值**：只有已写好中文标题与摘要的条目才进公开页面（全部动态、分类、主题、搜索、详情）；精选本来就必须有（2026-10-28，用户看到全部动态里有只显示英文原标题的卡片）

- 之前进了页面的「英文条目」有四类：首次导入时归档的旧文（不进模型，按设计）、热度信号源（reddit，不进模型）、手动 dry-run 部署时新抓到还没处理的、以及 10-22 首次大批导入时写作步骤额度用尽的。
- 规则落在 `Item.is_publishable`：非精选没中文就不发布，写好后下一次发布自然出现；精选缺中文仍让发布校验整次失败。
- 修正一个漏洞：写作额度用尽的条目状态已定（LISTED/SELECTED），不在常规待处理集合里，以前永远不会再写，正文还会被清掉。现在 `strip_bodies` 为它们留着正文，流水线每次运行单独补写（只跑写作步骤）。正文已被清掉的老条目不补写（没原文时短写法只会抄英文标题）。
- 归档旧文如果以后想上页面，需要一次性补跑预筛与写作（约 300 条，按现有单价不到几块钱），另议。

## D17 用研社招 tab：抓公司官网 + 滑动窗口

**确认值**：侧栏「求职 → 用研社招」，岗位每天从公司招聘官网的岗位搜索接口抓一次；只收第一次看到时发布不超过 30 天的，满 90 天移出，官网下线就拿掉（2026-10-28，用户提出「收 30 天、留两个月、留三个月，之后按月轮换」，确认为按月往前挪的滑动窗口）

- 数据源：Boss 直聘等招聘平台不让抓；可行性探测（`scripts/probe_jobs.py` 等）确认 11 家官网的搜索接口可直接用：腾讯、字节跳动、阿里巴巴、百度、美团、网易，以及用字节系招聘系统的小米、蔚来、理想、小鹏、得物。京东、快手接口参数没探出来，其余公司没有可用接口，暂不收。
- 为什么要窗口：官网上很多岗位常年挂着（字节系样本里约七成发布于 90 天以前，最早 2023 年），读者分不清还招不招。每条岗位都有日期：字节系、百度、阿里给**首次发布**日期；腾讯、网易、美团只给**更新 / 刷新**日期（美团的 firstPostTime、expiredTime 字段全是空的）。
- 规则（`uxhot/social/window.py`）：
  - 起算日 = 第一次看到时官网给的日期，之后官网刷新**不重新计时**（否则 HR 点一下刷新，旧岗位就永远「新」）。
  - 收录：起算日距今 ≤ 30 天；超过的记入 retired，以后刷新了也不收。
  - 保留：起算日距今 > 90 天就移出，同样记入 retired。
  - 下线：公司这次抓成功、但连续 3 次没搜到这个岗位才拿掉（搜索按相关度翻页，偶尔排到后面不算下线）；抓取失败的公司岗位原样保留。
  - 上线头一个月岗位偏少（样本里 30 天内的不多），第二、三个月窗口填满后稳定在「最近 90 天」。
- 相关性：岗位名命中「用户研究 / 用研 / 体验研究 / 用户洞察 / 市场研究 / 人因」等且不含「实习 / 校招 / 应届」才收（`config/social.yaml` 的 include / exclude）；字节系只留招聘类型为「社招」的。
- 运行：`scripts/sync_social.py` 在 Update 里每次都调用，距上次抓取不到 20 小时就跳过，所以一天真抓一次；顺序请求、间隔 1 秒，一次约百来个请求。状态存 `data/social/jobs.json`，页面数据 `web/content/social.json`。全部失败时不写文件、沿用上一版。
- 详情页链接：9 家用无头浏览器打开验证过；阿里、百度在境外的 Actions 机器上打不开（跳首页 / 空白页，像是按地区或无头浏览器拦截），链接按它们前端路由拼的，没能实测。
- 页面：`/social/`（按 30 天内 / 31–60 天 / 61–90 天分段、按公司与城市筛选、可搜索，筛选写进链接）与 `/social/<id>/`（官网职责与要求原文、官网日期、本站收录与预计下架日期、官方投递链接）。

## 修订记录

| 日期 | 变更 | 依据 |
|---|---|---|
| 2026-10-28 | **D17 新增**：用研社招 tab，抓 11 家公司招聘官网，收 30 天、留 90 天的滑动窗口 | 用户要求做社招 tab，并提出按月轮换的保留方式 |
| 2026-10-21 | D1–D12 首次确认 | 用户在决策表选项中选择 |
| 2026-10-28 | **D16 新增**：没写出中文的条目不上页面；写作额度用尽的条目留正文并自动补写 | 用户发现全部动态有只显示英文标题的卡片 |
| 2026-10-28 | **D1 修订**：站名 UXHOT → URHOT | 用户要求 |
| 2026-10-28 | **D15 新增**：并入用研校招岗位库，侧栏新增「求职 → 用研校招」 | 用户要求把校招项目合进来 |
| 2026-10-28 | **D14 新增**：去掉日报与周报，精选与全部动态按天浏览 | 用户认为日报周报繁琐、与精选重合 |
| 2026-10-28 | **D13 新增**：站点外观改为参照 AIHOT 的版式与配色 | 用户对比 AIHOT 后要求参照其外观 |
| 2026-10-21 | **D5 修订**：新增 3 个 web_list（Maze、dscout People Nerds、MRS）+ 4 本期刊（BIT、HCI、JMMR、IJMR）；信源总数 37 → 44 | 用户就「这些站点是否真的抓不到内容」追问后，执行模型重新实测并更正误判；用户在补充选项中选定 |
