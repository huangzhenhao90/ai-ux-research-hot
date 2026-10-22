# PROGRESS

> 执行约定见上级目录 `用研AIHOT_执行计划.md` 第 2 节。每阶段结束在此追加。
> 记录格式：做了什么 / 命令 / 结果 / 遗留问题。

---

## 阶段 1：建仓与骨架 — ✅ 完成（2026-10-21）

**做了什么**

- `git init -b main`，工作目录 `uxhot/`
- Python 3.11.5 venv（`.venv/`）+ `requirements.txt`，装完并逐个验证导入
- 按计划 §阶段 1 建全目录骨架（`config/ prompts/ uxhot/{collect,pipeline,report,publish} scripts/ data/{state,items,reports,runs} web/ eval/ tests/ .github/workflows/`）
- `.gitignore` 覆盖 `.env .venv node_modules web/.next web/out` 等
- `LICENSE`（MIT，版权 huangzhenhao90）
- `NOTICE`：注明改编自 AIHOT（commit `a0d1e75`，MIT），并写明 **AIHOT 名称与 Logo 不在 MIT 许可范围内、本站不使用**
- `README.md`、`pyproject.toml`（pytest 配置：`testpaths=tests`、`pythonpath=.`）
- `tests/test_skeleton.py`：骨架自检 4 条

**命令与结果**

| 命令 | 结果 |
|---|---|
| `python3 -m venv .venv` | Python 3.11.5 |
| `.venv/bin/pip install -r requirements.txt` | 成功；`feedparser httpx selectolax yaml pydantic openai dateutil rapidfuzz openpyxl pytest` 全部导入 OK |
| `.venv/bin/python -m pytest -q` | `....` 4 passed |
| `git status --short` | 干净（已提交 `f79ad71`） |

**环境事实**

- Python 3.11.5 / Node v22.22.3 / npm 10.9.8 / git 2.50.1 / gh 2.87.3 / uv 0.11.18 / pnpm 11.8.0
- 前端参照 `human-ai-papers/web`：Next `16.2.10` + React `19.2.7` + TS `5.9.3`

**遗留问题（已记入待办，不影响阶段 1 验收）**

1. 计划 §阶段 6 说前端「参照 human-ai-papers 的栈」，但 `human-ai-papers/web/next.config.mjs` **并没有** `output: "export"`、也没有 `basePath`（那个站部署在 Vercel，是 SSR）。阶段 6 需要自己配静态导出，**不能照抄**。
2. 本机 httpx 必须 `trust_env=False` 并显式传 `proxy`：环境变量 `NO_PROXY` 含 `[::1]`，httpx 会把它当 URL 模式解析并抛 `Invalid port: ':1]'`。已写进 `scripts/probe_feeds.py::build_client()`，阶段 5 采集模块沿用同一写法。

---

## 阶段 2：确认决策 — ✅ 完成（2026-10-21）

**做了什么**

1. 起草 §1 决策表 D1–D12，逐条发给用户确认；**12 项全部由用户选定**，结果写入 `DECISIONS.md`。
2. 为让 **D5（信源名单）有事实依据**，提前做了信源可用性探测（计划里这一步原本属于阶段 3）。

**方法**：`scripts/probe_feeds.py` 逐个试抓；另一个「域名 × 21 条常见 feed 路径」的并发发现脚本。

**⚠️ 发现一：计划 §4.4 的信源初稿大部分不可用**

计划里直接写死的约 30 个地址，只有 9 个返回 200。其余 404/403/SSL 失败，包括：
Maze、UserTesting、User Interviews、Optimal Workshop、Great Question、Sprig、ESOMAR、MRS、Greenbook、Quirk's、Research Live、MRWeb、Insights Association、dscout People Nerds、ACM TOCHI/CHI eTOC、Journal of Usability Studies、Contentsquare、Qualtrics XM Institute。

**⚠️ 发现二：9 个「僵尸源」——能解析，但多年不更新**

只测「是否返回 200」会把死站放进首页。这 9 个已排除：

| 域名 | 最后更新 |
|---|---|
| getfeedback.com | 2017-05 |
| marvelapp.com | 2022-06 |
| boxesandarrows.com | 2022-07 |
| researchops.community | 2023-11 |
| usabilitygeek.com | 2024-01 |
| thearf.org | 2024-01 |
| pollfish.com | 2024-02 |
| uxmatters.com | 2024-03 |
| playbookux.com | 2025-07 |

→ **结论：`check_sources.py`（阶段 3）必须把「最新条目日期」也作为验收项，不能只测可达性。**

**结果**

- 实测确认 **35 个可用 feed**（HTTP 200 + 有条目 + 日期可解析）。
- 按用户决定去掉偏题 4 个（Smashing Magazine、McKinsey、JMIR、AMA）后，**最终 37 个信源**：
  - T1 官方一手 **26**（20 个 RSS + 6 个 web_list）
  - T2 学术与媒体 **9**（arXiv cs.HC、Frontiers CS、MeasuringU、Product Talk、UX Collective、Rosenfeld、Jakob Nielsen、Johnny Holland、UX Magazine）
  - hot_signal **2**（Reddit r/UXResearch、HNRSS）
- 超出计划门槛「≥30 个成功、T1 ≥10」。
- 日期解析全部正常：每个 feed 的条目都带 `published_parsed` 或 `updated_parsed`。
- 瞬时失败：`nngroup.com/feed/rss/`、`hnrss.org` 第一轮通过、第二轮超时/502，属网络抖动 → `check_sources.py` 要带重试。

**命令与结果**

| 命令 | 结果 |
|---|---|
| `.venv/bin/python scripts/probe_feeds.py` | 9/30 通过（计划初稿地址） |
| 并发发现脚本（77 域名 × 21 路径） | 25 个域名有可用 feed |
| 第二轮探测（feed-scout 子代理，约 90 域名） | 新增 15 个可用 feed |
| 活跃度分级脚本 | 35 活跃/偏冷、9 僵尸 |
| `pytest -q` | 4 passed（阶段 1 自检仍绿） |

**D12 可行性已验证（用户选择「一期就做」）**

- `ur-ai-papers` 是公开仓库：`https://github.com/huangzhenhao90/ur-ai-papers`
- 公开数据可经 raw URL 读取（已实测 200，2.2 MB）：
  `https://raw.githubusercontent.com/huangzhenhao90/ur-ai-papers/main/web/public/data/papers.json`
- 数据规模 **1857 篇**；字段含 `id / title / title_zh / journal / date / url / doi / ai_score / domain_score / tldr / topic_tags / ai_type_tags`，`ai_score` 与 `domain_score` 为 1–5 分。
- ⚠️ **新发现的风险**：`date` 范围到 **2027-01**（期刊提前标注未来期号）。阶段 5 的「旧文不刷屏 / freshHours」逻辑必须先处理未来日期，否则这些条目会被当成「刚发布」全部涌上首页。
- 约束：`ur-ai-papers` 是**只读上游**，不得修改、提交、推送或停用。

**D11 对阶段 8 的约束（用户选择「从零标注」）**

`scripts/sample_gold.py` 只做分层抽样与导出，**不得导出「模型均分」「模型建议」列**，避免锚定标注。

**遗留问题**

1. `testingtime`（停更 103 天）、`uxmag`（停更 112 天）偏冷，阶段 3 复验后决定去留。
2. **9 个** `web_list` 信源的选择器（`itemSelector/titleSelector/linkSelector/dateSelector`）尚未实测，阶段 3 逐个确定。
3. Outset、Conveo、ESOMAR 为 JS 渲染，静态抓取拿不到列表，列二期候选；`lookback.com/blog` 返回 404，博客地址待查。
   （**注**：Maze 原先被误判为同类，已在下方「阶段 2 补充」更正为可抓。）
4. **仓库名与计划默认值不同**：用户选定 `huangzhenhao90/ai-ux-research-hot`，`siteUrl` 须为 `https://huangzhenhao90.github.io/ai-ux-research-hot`（不是计划里预填的 `/uxhot`）。

---

## 阶段 2 补充：误判更正（2026-10-21）

用户追问「括号里的这些都没有抓到内容吗？」，复查后发现执行模型**两处误判**与**计划一处错误**，已更正并扩充 D5。

### 误判一：把「feed 地址 404」等同于「抓不到内容」

初次汇报时把「计划里写死的 feed 地址返回 404」表述成了这些源不可用。**这两件事不同**：地址不存在，但站点本身可达、列表页可抽。

复查结果：用户点名的 10 个域名中，**8 个能抓到内容**，只有 2 个真的抓不到。

| 域名 | 首页 | 列表页 | 抽出文章链接 | 结论 |
|---|---|---|---|---|
| Maze | 200 | 200 | 7 | ✅ 可抓 |
| UserTesting | 200 | 200 | 12 | ✅ 已列入 D5 |
| User Interviews | 200 | 200 | 32 | ✅ 已列入 D5 |
| Optimal Workshop | 200 | 200 | 7 | ✅ 已列入 D5 |
| Great Question | 200 | 200 | 15 | ✅ 已列入 D5 |
| Sprig | 200 | 200 | 25 | ✅ 已列入 D5 |
| MRS | 200 | 200 | 5 | ✅ 可抓 |
| dscout People Nerds | 200 | 200 | 多条 | ✅ 可抓 |
| ESOMAR | 200 | 200 | 0 | ❌ Next.js 全客户端渲染 |
| ACM (dl.acm.org) | **403** | **403** | 0 | ❌ 整站 Cloudflare 拦截 |

### 误判二：两个源的正则/前缀写错，导致漏判

- **Maze**：曾判定「JS 渲染、拿不到列表」。实际能抽到 `/blog/ai-for-market-research/`、`/blog/maze-mcp-best-practices/` 等真实链接。
  **原因**：探测正则写成 `href="/blog/[a-z0-9-]{8,}"`，要求以字母数字结尾；而 Maze 的文章链接**带尾斜杠**（`/blog/xxx/`），被整类漏掉。
- **dscout People Nerds**：曾按 `/blog/` 前缀找，而 dscout 用的是 `/people-nerds/` 前缀，因此抽到 0 条。
  **原因**：假设了所有博客都用 `/blog/`，没有先看页面实际链接模式。

→ **教训（写入阶段 3 检查脚本的要求）**：`check_sources.py` 探测 `web_list` 时，必须先看目标页真实链接模式再写选择器，不能用固定前缀假设；正则要允许尾斜杠。

### 计划本身的错误：ACM

计划 §4.4 说「ACM CHI/CSCW/TOCHI eTOC RSS（直接复用 `ur-ai-papers/config/journals.yaml` 的 rss 字段）」。照做后发现 `dl.acm.org` **整站 403**，`journals.yaml` 里 ACM 的 rss 字段已失效。

于是把该文件**全部 20 条 RSS 实测一遍：10 条可用**。

| 可用期刊 | 领域 | 条目 | 最新 |
|---|---|---|---|
| BIT Behaviour & Information Technology | HCI, UX | 285 | 2026-10-21 |
| HCI Human-Computer Interaction | HCI | 19 | 2026-10-15 |
| JMMR Journal of Mixed Methods Research | 研究方法 | 26 | 2026-10-14 |
| IJMR International Journal of Market Research | 研究方法 | 16 | 2026-10-12 |
| JMR Journal of Marketing Research | 研究方法+营销 | 26 | 2026-10-10 |
| JM / MktSci / JSR / JCP / JCA | 营销、消费者 | 6–63 | 2026-08 ~ 10 |
| IJHCS / JR | HCI / 零售 | 22 / 55 | ⚠️ 日期解析不出 |

不可用：TOCHI、TiiS、IwC、JIM、JCR、JAMS、APS、Design Issues。

### 用户确认的扩充（D5 修订）

- 新增 3 个 web_list：Maze、dscout People Nerds、MRS
- 新增 4 本期刊：BIT、HCI、JMMR、IJMR（只取与 HCI／研究方法学最对口的；纯营销期刊噪声高，暂不纳入）
- **信源总数 37 → 44**（T1 29 / T2 13 / hot_signal 2）

详见 `DECISIONS.md` 的 D5 与修订记录。

---

## 阶段 3：配置文件 — ✅ 完成（2026-10-21）

**做了什么**

1. **六份配置**（`config/`）：
   - `site.yaml`：站名 UXHOT / 副名「AI 用研热点」/ 行业词「AI 用研」；**`siteUrl` 按 D7 用
     `https://huangzhenhao90.github.io/ai-ux-research-hot`**（不是计划预填的 `/uxhot`）；
     出刊时间按 D10（日报 08:00、周报 MON 10:00）
   - `taxonomy.yaml`：6 分类（含兜底 `industry`）、7 个 `itemTypes` 及与分类标签的自洽对照、
     `release`（日报「N 款新工具」）、14 个分类标签、15 个主题标签、11 个实体标签、
     标签同义词归并、**36 个实体**（含中英文别名与域名，供主题页与防张冠李戴）、通用词表
   - `topics.yaml`：**24 个主题页**，分 3 组（公司 10 / 研究方向 9 / 内容类型 5）
   - `sources.yaml`：**44 个信源**（T1 29 / T2 13 / hot_signal 2），含 9 个 `web_list` 的选择器
   - `selection.yaml`：门槛按计划占位（T1 60 / T1_5 65 / T2 76）、`understandFloor` 50、
     `freshHours` 48、预算按 D9（300/1000）
   - `overrides.yaml`：初始为空，附用法示例（注释形式）
2. **`uxhot/config.py`**：pydantic 模型 + 跨文件一致性校验，失败时抛带文件名与项名的 `ConfigError`。
3. **`tests/test_config.py`**：32 条用例（正例 + 负例）。
4. **9 个 `web_list` 选择器实测**（selector-scout 子代理），并用 `sources.yaml` 里的选择器做**冒烟验证**。

**命令与结果**

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q` | **36 passed**（test_config 32 + test_skeleton 4） |
| 配置汇总打印 | 44 信源 = 参与精选 42 + hot_signal 2；T1 29、T2 13；rss 33、web_list 9 |
| web_list 冒烟（真实抓取 + selectolax 抽条） | **9/9 通过**，共抽出 151 条 |

**web_list 冒烟结果**（用 `sources.yaml` 的选择器实际抓取）

| id | 抽出 | 有标题 | 有日期 |
|---|---|---|---|
| strella-blog | 38 | 38 | 38 |
| sprig-blog | 25 | 25 | 25 |
| userinterviews-blog | 24 | 24 | 24 |
| dscout-people-nerds | 16 | 16 | 16 |
| greatquestion-blog | 13 | 13 | 12 |
| usertesting-blog | 12 | 12 | **0** |
| mrs-news | 10 | 10 | 10 |
| optimalworkshop-blog | 7 | 7 | **0** |
| maze-blog | 6 | 6 | **0** |

3 个源（usertesting / optimalworkshop / maze）**列表页确实没有日期**，已在 `sources.yaml` 的 `note` 写明，
并有测试守住「无 dateSelector 必须在 note 说明」。这些源的日期要靠抓正文页补（阶段 5 处理）。

**本轮踩到并已处理的三个坑**

1. **校验器一开始过严**：`validate_topics` 只允许主题页标签取自 `topicTags`，但计划里 `genre` 组
   （论文、方法、提示词、案例、报告）本来就是按 `categoryTags` 匹配的。已被测试拦下并修正为
   `topicTags ∪ categoryTags`。**这是配置校验第一次真的抓到问题。**
2. **`greatquestion.co` 与 `strella.io` 会 301**：前者 301 到 `www.greatquestion.com`，
   非 www 的文章链接直接 404；后者 301 到 `www.strella.io`。`sources.yaml` 已统一用 www 域名。
3. **`selectolax` 1.0 弃用了 modest 后端**：`from selectolax.parser import HTMLParser` 直接抛
   `ImportError`。必须改用 `from selectolax.lexbor import LexborHTMLParser`。
   **阶段 5 的采集模块要按 lexbor 写**（本机装的是 1.0.1）。

**遗留问题**

1. 3 个无日期源（usertesting / optimalworkshop / maze）需要抓正文页补日期；拿不到就按
   「无可信日期不公开，下次再试」处理（计划 §5.2 第 2 条）。
2. 多个源分页是 JS（无限滚动 / Load more），静态抓取只拿首屏：UserTesting 12、Optimal Workshop 7、
   Maze 6。二期可考虑无头浏览器。
3. `testingtime`（停更 103 天）、`uxmag`（停更 112 天）仍未复验活跃度 —— 阶段 5 采集跑通后用真实
   抓取结果决定去留。
4. 门槛仍是计划占位值，**只在阶段 8 按用户金标评测结果改**。

---

## 阶段 4：提示词移植 — ✅ 完成（2026-10-21）

**做了什么**

1. **18 份提示词**（`prompts/`），改编自 AIHOT `industry/prompts/`，逐文件来源写在 `prompts/README.md`：
   - Lead 写「编辑大脑」8 份：`prefilter.md`、`selection-score.md`、`content-understanding.md`、
     `understand.md`、`structure.md`、`group-pair.md`、`group-definitions.md`、`group-method.md`
   - 子代理写支持性 10 份：`safety.md`、`rules-*.md`（4 份）、`summarize-*.md`（3 份）、
     `translate-body.md`、`report-period.md`
2. **`uxhot/prompts.py`**：渲染器，支持 `{{siteName}}` 与 `{{> 文件名}}` 递归展开，
   检测**包含循环**、**文件缺失**、**未知占位符**；`prompt_version()` 给出 sha256 前 8 位。
3. **`uxhot/llm.py`**：OpenAI 兼容客户端，三重安全阀（`--execute` + `LLM_API_KEY` +
   `MODEL_CALLS_ENABLED=true`），JSON 模式，解析失败重试 1 次，记录 token 审计。
4. **`tests/test_prompts.py`**：30 条用例。
5. **`scripts/eval_prompt_direction.py`**：5 条真实样本的方向性验证。

**命令与结果**

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q` | **66 passed**（config 32 + prompts 30 + skeleton 4） |
| `scripts/eval_prompt_direction.py`（dry-run） | 打印「预计 15 次调用」，零真实调用 ✅ |
| `--execute`（未开安全阀） | 被拒：`MODEL_CALLS_ENABLED 不是 true` ✅ |
| `MODEL_CALLS_ENABLED=true … --execute` | **15 次调用，0 失败，54,889 token**（输入 54,728 / 输出 161） |

**5 条样本的真实评分结果**（用户同意后执行）

样本取自真实信源真实条目，正文抓自原文页（不是编造样本）。

| id | 内容 | 期望 | 评分1 | 评分2 | 均分 | 门槛 | 判定 | 方向 |
|---|---|---|---:|---:|---:|---:|---|---|
| dir-01 | MeasuringU：合成用户系统性高估 SUS 分数 | select | 84 | 82 | 83.0 | 76 | select | ✅ |
| dir-02 | arXiv：可检查的 LLM 模拟受访者用于访谈演练 | select | 63 | 74 | 68.5 | 76 | reject | ❌ |
| dir-03 | Qualtrics 研讨会报名页 | reject | 22 | 22 | 22.0 | 60 | reject | ✅ |
| dir-04 | UX Collective：Design v ADHD | reject | 34 | 31 | 32.5 | 76 | reject | ✅ |
| dir-05 | Dovetail：9 个可建 Digital Twins（边界） | either | 58 | 58 | 58.0 | 60 | reject | ✅ |

**方向一致 4/5。**

**结论与发现**

1. **噪声压得很稳**：研讨会报名页（来自 T1 官方源）只拿到 22 分，泛设计文章 32.5 分，
   厂商 listicle 58 分——说明「必须压住的噪声」规则生效，且**没有因为信源是 T1 就抬分**。
2. **反直觉的效度证据拿到高分**：dir-01 的 83 分正是计划想要的
   「有对照实验的效度证据，结论正反都算」。
3. **⚠️ dir-02 暴露一个真问题**：论文类在 T2 门槛（76）下被卡掉，两次评分还差了 **11 分**
   （63 vs 74）。其余 4 条两次评分差分别只有 2、0、3、0 分。
   两种可能：① T2 门槛 76 对学术论文偏严；② 评分标准对 `research_paper` 的表述让模型拿不准。
   **按计划 §2.6，门槛只在阶段 8 按用户金标评测结果改**，所以现在**不动门槛**，
   先把这个现象记下来，阶段 8 用金标数据判断该改门槛还是改标准。
4. **预筛比预期宽**：5 条全部 PASS，包括研讨会报名页与泛设计文章。这符合计划 §4.1「宽召回」
   的设计意图（靠评分而非预筛做质量判断），但也意味着预筛没能替后面的评分省下调用。

**成本观察**

15 次调用消耗 54,889 token，其中**输入 54,728（99.7%）、输出仅 161**。
原因是评分只返回 `{"attentionScore": N}`，而输入要带上正文。
按此推算单条资料约 3,650 token（预筛 + 2 次评分）。精确日成本留到阶段 5 用真实全量运行估算。

**⚠️ 版权处理**

`eval/samples-direction.json` 含第三方文章全文（48 KB），**已加入 `.gitignore` 不提交**
（D6 仓库要 public，提交等于再分发他人内容）。仓库里只提交不含正文的报告。
样本可用 `scripts/build_direction_samples.py` 重新构建。

**遗留问题**

1. dir-02 的方向错误待阶段 8 用金标数据判定（改门槛还是改评分标准）。
2. 两次评分在论文类上差 11 分，需在金标评测里观察是否普遍。
3. 用户确认保留的两处子代理判断：`rules-domain.md` 里额外保留「国内 AI 厂商中文品牌名」一行；
   `summarize-short-post.md` 新增一条用研语境的「优先保留」（AIHOT 原文件没有）。

---

## 阶段 5：流水线（Python）— ✅ 完成（2026-10-21）

**做了什么**

| 模块 | 内容 |
|---|---|
| `uxhot/models.py` | `Item` 数据模型（计划 §5.1 全字段）、`Status` 生命周期、JSONL 存取、按 id 合并 |
| `uxhot/collect/dates.py` | 时区解析、**未来日期拦截**、`freshHours` 判断、日报窗口 `day_bounds_bj` |
| `uxhot/collect/fetch.py` | HTTP 抓取（条件请求 ETag/Last-Modified）、正文抽取、语言探测 |
| `uxhot/collect/rss.py` | RSS/Atom 采集 + 「旧文不刷屏」 |
| `uxhot/collect/web_list.py` | 网页列表采集（选择器来自 `sources.yaml`）+ 列表页无日期时抓正文页补 |
| `uxhot/collect/external_json.py` | **D12：`ur-ai-papers` 适配器**（只读上游） |
| `uxhot/pipeline/normalize.py` | URL 规范化、标题相似度 |
| `uxhot/pipeline/prefilter.py` | 预筛（PASS/BLOCK/UNKNOWN） |
| `uxhot/pipeline/score.py` | 两次独立评分 + 分级门槛 |
| `uxhot/pipeline/structure.py` | 结构化（分类/标签/主体/scope/fact）+ 白名单过滤 |
| `uxhot/pipeline/write.py` | 写作（深写/简写）+ **实体防张冠李戴** |
| `uxhot/pipeline/dedupe.py` | 机械去重（标题相似度 + 时间窗） |
| `uxhot/pipeline/select.py` | 同事件去重 + 进精选 + 人工覆盖 |
| `uxhot/pipeline/common.py` | 模型步骤公共部分（渲染、预算、错误记录、提示词版本） |
| `uxhot/pipeline/runner.py` | 编排 + 运行审计 |
| `uxhot/budget.py` | 预算熔断（跨运行累计日计数） |
| `uxhot/publish/*` | 发布层 4 模块（子代理完成，见下） |
| `uxhot/report/*` | 日报/周报（子代理完成，见下） |
| `scripts/run_pipeline.py`、`build_daily.py`、`build_weekly.py` | 命令行入口 |

**命令与结果**

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q` | **221 passed**（config 32 / pipeline 71 / prompts 30 / publish 50 / report 34 / skeleton 4） |
| `run_pipeline.py --dry-run`（**全部 45 个真实信源**） | 42 成功、3 瞬时失败；采集 329 条；发布 321 个公开条目；**零模型调用** |

**全量 dry-run 明细**

- 成功 42/45，覆盖 33 个 RSS + 9 个 `web_list` + 1 个 `external_json`。
- 3 个失败均为**瞬时网络错误**，非信源失效：`xm-institute`、`rosenfeldmedia`（HTTP 522）、`hnrss-user-research`（HTTP 502）。
  → `check_sources.py` 必须带重试（已记入遗留问题）。
- 发布产物：`public 321 / months 28 / categories 6 / topics 24 / searchIndex 321`，`validate_publish_dir` 无问题。
- **零模型调用**，`MODEL_CALLS_ENABLED` 保持 `false`。

**本轮发现并修掉的 5 个真 bug**（都是测试或实测抓出来的，不是猜的）

1. **`ur-ai-papers` 灌进 1469 条**：`max_age_days` 只把老论文标 `ARCHIVED` 而没有跳过，
   于是 1263 篇超 30 天的论文全被写进 `data/items`（1.85 MB）。改成**硬跳过**后降到 8 条（首次导入上限）。
2. **dry-run 低估预算**：`score.run` 在拿到 `None` 时 `break`，导致 dry-run 只把每条算成 1 次调用。
   实测 4 条应 12 次却报 8 次。已改成 dry-run 显式按 `attempts` 计数。
3. **`external_json` 不认 304**：条件请求命中时被当成失败。已与其他 kind 对齐。
4. **`parse_feed` 未来日期绕过检查**：未来日期校验只加在「原始字符串」分支上，
   走 `published_parsed` 的条目（含 2027-01 这类期刊提前期号）会绕过检查、被当成「刚发布」。
   已对 `published_parsed` 分支同样拦截。
5. **⚠️ 出刊日算错一天（跨层不一致）**：发布层的 `edition_day` 用 `date(dt − hour)`，
   比正确值早一天。实测：10-21 09:00（北京）选的条目，窗口 `[10-21 08:00, 10-22 08:00)`
   才是真正包含它的那一期（即 **10-22 期**），而 `edition_day` 返回 10-21。
   这会让**首页按出刊日分组**与 `/daily/<date>/` 页面对不上。
   已改为 `date(dt + (24 − hour))`，并更新了 3 条编码了旧行为的测试，
   另加 **4 条回归测试**：用「窗口是否真的包含该时刻」这个独立事实验证，
   并断言发布层与出刊脚本对同一时刻给出同一个出刊日。

**子代理完成的模块**

- **发布层**（`uxhot/publish/`，50 条测试）：公开字段白名单（产物**不含 `body`**，已断言）、
  `latest.json`/`all/`/`items/`/`categories/`/`topics/`/`search-index.json`/`site.json`、
  `rss.xml` + `rss-daily.xml`、`llms.txt`、12 类产物校验，
  以及「**先写临时目录、校验通过才整体替换**」——校验失败时 `web/public` 一字节不动。
- **日报/周报**（`uxhot/report/`，34 条测试）：日报纯规则（重要性 `avgScore + 5×(独立来源数−1)`、
  同信源 ≤2、7 期内不重复、正文 ≤12、快讯 ≤10、空刊）；周报汇编日报取前 20，
  总述默认模板句，**只有显式 `--execute` 才让模型写**，名字/数字校验不过自动换模板句。

**接口契约**

两份契约文档：`docs/report-schema.md`（日报/周报 JSON，含 8 个歧义点的裁定）。
报告层提出的 8 个歧义点已逐条裁定并记录在案（`date` 是出刊日、`sections` 只装第 5–12 条、
`empty ⇔ headline == null` 等）。

**模型补充**

`Item` 增加 `selectedAt`（入选时刻）。原因：日报窗口按**入选时间**分期，
用 `publishedAt`/`discoveredAt` 近似会让补跑与延迟确认的条目落错期。

**遗留问题**

1. **`--execute` 真实运行尚未做**：计划 §阶段 5 验收要求「征得用户同意后 `--execute --limit 30`
   跑一次，记录调用次数、token、估算日成本」。**按 §2.7 需先问用户**，故暂停在此。
   注意：当前所有条目都是首次导入的 `ARCHIVED`，`--execute` 前需要先让一批条目处于 `NEW`
   （真实新文章出现，或把子集重置为 `NEW` 模拟）。
2. 3 个瞬时失败信源需要在 `check_sources.py` 里加重试（阶段 3 的遗留项，一并处理）。
3. `rosenfeldmedia` 返回 522 说明其源站不稳；若持续失败，阶段 8 前应考虑移出。
4. 周报 `sections[].lead` 恒为空（计划 §5.5「模型只写总述」）；二期若要栏目导读需扩提示词。
5. `web/public/` 目前是 dry-run 产物（`selected: 0`），阶段 6 接前端后由真实运行覆盖。

---

## 阶段 5 补充：真实运行与成本（2026-10-22）

用户确认后执行。为让模型步骤真的有活干，先把 30 条（覆盖 30 个信源、T1 22 / T2 8）重置为 `NEW`
来模拟「有新内容了」。

**命令**

```bash
MODEL_CALLS_ENABLED=true python scripts/run_pipeline.py --execute --limit 30 \
  --source nngroup --source dovetail-blog --source measuringu --source qualtrics \
  --source maze-blog --source userinterviews-blog --source arxiv-cs-hc \
  --source ur-ai-papers --source usertesting-blog --source ipsos
```

**结果**

| 步骤 | 结果 |
|---|---|
| collect | 10 个信源，0 失败 |
| prefilter | PASS 21 · BLOCK 7 · UNKNOWN 2 |
| score | 21 条，全部拿到两次独立评分 |
| structure | 15 条有分类，15 条有实体 |
| write | 21 条写成，其中 4 条走精选深写（有推荐理由） |
| dedupe | 0 重复 |
| select | **1 条进精选**，20 条进全部动态 |
| stripBodies | 清掉 275 条正文 |
| publish | 369 个公开条目，校验通过 |

**用量与成本**

- **114 次调用，0 失败**；输入 278,101 + 输出 4,476 = **282,577 token**。
- 单次均值：输入 2,439、输出 39 token。按步骤：prefilter 30 / score 42 / structure 21 / write 21。
- 官方价（`deepseek-flash`，每 1M token；低谷价为峰值一半，低谷＝除工作日 01:00–04:00、06:00–10:00 UTC 之外）：

| 场景 | 本次 114 次 | 按 30 条/日 | 熔断上限（1000 次/日） |
|---|---|---|---|
| 峰值 · 全 cache miss | ¥0.63 | ¥0.63/日 ≈ **¥19/月** | ¥5.53/日 ≈ ¥166/月 |
| 低谷 · 全 cache miss | ¥0.32 | ¥0.32/日 ≈ ¥9.5/月 | — |
| 低谷 · 命中缓存 | ¥0.03 | — | — |

→ **即使按最坏情况（峰值、零缓存命中、跑满熔断上限）也只有约 ¥5.5/日**，成本不是问题。
提示词前缀在各次调用间完全相同，DeepSeek 的上下文缓存应能显著压低实际成本（缓存命中的输入价是未命中的 1/50）。

**⚠️ 关键发现：门槛对这个行业偏严，精选会很少**

21 条评分的平均分分布：

- T1（17 条）：`65.5, 58, 50, 48, 45, 44, 41.5, 40, 36, 29, 26, 25, 25, 15, 15, 15, 13`
- T2（4 条）：`60, 41.5, 41.5, 19`

在现行门槛（T1 60 / T2 76）下只有 **1 条**入选。若 T1 门槛改为 55 → 2 条；50 → 3 条；45 → 5 条；40 → 8 条。

唯一入选的正是计划最想要的那类：NN/g《Synthetic Users vs. Human Respondents》——**有对照实验的效度证据**，65.5 分。
说明评分标准的方向是对的（噪声被压到 13–29 分，效度证据得高分），**偏严的是门槛数字本身**：
T1 60 / T2 76 是 AIHOT 在 AI 领域用的值，用研行业的分数整体低一档。

**按计划 §2.6，门槛只在阶段 8 按用户标注的金标评测结果改，所以本轮不动门槛。**
但这个现象必须在阶段 8 优先处理：若照现状上线，日报会经常是空刊。

**模型名修正**

`deepseek-chat` 不在 DeepSeek 官方模型列表里（只有 `deepseek-flash` 与 `deepseek-v4-pro`），
它是未文档化的旧别名。已把 `LLM_MODEL` 改为 **`deepseek-flash`** 并用一次极短调用验证通过。

**正文剥离（用户确认的策略）**

`models.strip_bodies()` 在处理完成后清掉正文，只留 `bodyChars` 长度：

| | 剥离前 | 剥离后 |
|---|---|---|
| 正文总量 | 797,967 字 | **3,259 字** |
| `data/items` 体积 | 1.1 MB | **368 KB** |

保留正文的只剩 10 条（9 条 `unknown` + 1 条 `new`），都是**还需要处理**的条目——属必要输入。
`data/items` 因此可以安全提交进 public 仓库（D6），且流水线状态得以保持。
清空规则有测试守住：已处理完成的状态（`selected`/`listed`/`duplicate`/`blocked`/`archived`）才清，
`new`/`prefiltered`/`scored`/`unknown` 必须保留正文。

**遗留问题（更新）**

1. ~~`--execute` 真实运行尚未做~~ → **已完成**（见上）。
2. **门槛偏严**（T1 60 / T2 76 下 21 条只选 1 条）→ 阶段 8 用金标数据重定，是本项目上线前的头号风险。
3. 3 个瞬时失败信源（xm-institute / rosenfeldmedia / hnrss）需要重试机制。

---

## 阶段 6：前端（Next.js 静态导出）— ✅ 完成（2026-10-22）

**技术栈**：Next.js **16.2.10** + React **19.2.7** + TS **5.9.3**（与 `human-ai-papers/web` 同版本）。

**`next.config.mjs` 要点**

| 配置 | 值 | 原因 |
|---|---|---|
| `output` | `"export"` | GitHub Pages 只能托管静态文件 |
| `basePath` / `assetPrefix` | 从 `public/data/site.json` 读（=`/ai-ux-research-hot`） | D6 + D7；读不到退回空串，保证 `next dev` 在没跑过 publish 时也能起 |
| `images.unoptimized` | `true` | 静态导出没有图片优化服务 |
| `trailingSlash` | `true` | 导出成 `/path/index.html`，Pages 才能按目录命中 |

⚠️ 计划 §阶段 6 说「参照 `human-ai-papers/web` 的栈」，但那个站的 `next.config.mjs` **没有** `output: "export"`、也没有 `basePath`（它部署在 Vercel，走 SSR）。静态导出这套是自己配的。

**实现的 14 组路由**

`/`（首页，按出刊日分组）· `/all/`（全部动态 + 分类筛选 + 加载更多）· `/item/[id]/`（369 个）·
`/search/`（本地搜索）· `/category/[key]/`（6 个）· `/daily/` · `/daily/[date]/` ·
`/weekly/` · `/weekly/[week]/` · `/topics/` · `/topics/[slug]/`（24 个）· `/about/` · 404。

**验收**

| 检查 | 结果 |
|---|---|
| `pytest -q`（后端） | **224 passed** |
| `npm run typecheck` | **0 错误** |
| `npm run build` | **成功，414 个静态页** |
| 各页面 HTTP 状态（按 basePath 子路径结构访问） | 全部 **200**，含 `rss.xml` / `llms.txt` |
| 静态资源（CSS/JS）在 basePath 下可取 | **200** |
| 横向溢出（390px 与 1440px） | **14/14 无溢出** |
| 控制台错误 | **9 个页面全部 0 错误** |
| AIHOT 出现位置 | **仅 `out/about/index.html`**（符合成功标准 6） |

截图 14 张存 `screenshots/`：首页/全部/详情/日报/周报/主题/搜索/关于/分类（桌面 1440）
+ 首页/日报/全部/关于/主题（手机 390，真实移动端 viewport）。

**本轮发现并修掉的 3 个问题**

1. **⚠️ `ItemCard` 无法在客户端组件里用（架构缺陷，我自己引入的）**：
   `components/ItemCard.tsx` → `lib/data.ts` → `node:fs`，任何 `"use client"` 组件一旦
   import 到这条链，webpack 直接报 `UnhandledSchemeError: Reading from "node:fs" is not handled`。
   子代理被迫在 `AllClient` 里**重抄了约 50 行卡片标记**来绕过。
   **已修**：把纯展示函数（`categoryLabel` / `displayTitle` / `formatTime` / `formatDate` / `href`）
   拆到新的 `lib/format.ts`（**不 import fs**），`lib/data.ts` 重新导出以保持兼容，
   `ItemCard` 改为只依赖 `lib/format.ts`。随后删掉 `AllClient` 里的重复标记，改回直接用 `ItemCard`。
   `lib/format.ts` 顶部有醒目注释说明「这个文件不能 import node:fs」。
2. **RSS 链接被拼了两次 basePath**：`metadataBase` 已含 `/ai-ux-research-hot`，我又把
   `site.basePath` 拼进 `alternates.types`，Next 再加一次 → 变成
   `.../ai-ux-research-hot/ai-ux-research-hot/rss.xml`。已改成只给相对路径 `/rss.xml`。
3. **AIHOT 出现在每一页的页脚**：计划成功标准 6 只允许「关于页一行致谢」。
   我原本把 `site.credit` 渲染在全局页脚里，等于每页都出现。已从页脚移除，只保留关于页。

**顺带解决的两个边界**

- **`generateStaticParams()` 不能返回空数组**（Next 16 + `output: export` 会报
  `Page "/daily/[date]" is missing "generateStaticParams()"`）。而 `reports/daily/index.json`
  在还没出过日报时正是 `count: 0 / entries: []`，干净 checkout 直接 build 会炸。
  已用占位参数兜住：产物为空时生成 `/daily/__none__/`（渲染「还没有日报」+ `noindex`，
  无任何页面链向它）。**已实测**：删掉整个 `reports/` 目录后 build 仍成功（410 页）。
- **`/all/` 增加「未分类」筛选**：369 条里只有 15 条有分类（首次导入的历史条目没走结构化），
  只给 6 个分类会让筛选看起来是坏的。

**⚠️ 重要说明：当前站点数据是「开发种子数据」**

真实门槛（T1 60 / T2 76）下 21 条评分只选出 **1 条**，日报会是空刊，
前端的日报/周报页就没有内容可渲染、无法验收。

所以我加了 `scripts/seed_dev_data.py`：把符合条件的条目临时标为精选、补出日报与周报，
**只改内存里的条目状态，不改 `config/selection.yaml`**。当前 `web/public/` 里是它的产物：
4 期日报 + 2 期周报 + 17 条精选。

**阶段 8 定完门槛、跑一次真实流水线后，这些产物会被覆盖。** 现在首页上的内容不代表
真实门槛的筛选结果。

**一个诊断教训（值得记住）**

用 `chrome --headless --screenshot --window-size=390,844` 截出来的「手机图」**不是真实移动端布局**：
它不改布局视口，等于把桌面布局裁到 390px，会让人误判成「横向溢出」。
我一开始就被它骗了，差点去改一个并不存在的 bug。
正确做法是用 Playwright 的真实 viewport（`viewport` + `is_mobile` + `device_scale_factor`），
并**直接量 `document.documentElement.scrollWidth` 与 `innerWidth`** 来判断溢出。
`web/scripts/shoot_mobile.py` 就是干这个的（CDP 手写版因为本机代理会拦 127.0.0.1 而反复卡住，已放弃）。

**遗留问题**

1. **站点数据是种子数据**，阶段 8 后需重跑真实流水线覆盖。
2. `/all/` 首屏 HTML 241KB（含 369 条内联 RSC 数据）。若在意可改成分月读取，
   但那就不是纯客户端筛选了；目前可接受。
3. `about` 页读 `../config/sources.yaml`（三级路径回退）。**CI 必须在仓库根构建**，
   否则信源表会退化成空态说明文字。
4. `/daily/__none__/`、`/weekly/__none__/` 是空数据时的占位页（noindex，无入口链接）。
5. 收藏功能（计划 §阶段 6 列为「可选」）未做。

---

## 阶段 7：GitHub Actions + Pages — 🔄 进行中（2026-10-22）

### 已完成：两个工作流 + 本地全量验证

**`.github/workflows/update.yml`**（采集 → 评分 → 出刊 → 构建 → 部署）

| 配置 | 值 |
|---|---|
| `schedule` | `0 */4 * * *`（每 4 小时采集评分）+ `5 0 * * *`（UTC 00:05 = 北京 08:05 出日报） |
| `workflow_dispatch` | 输入 `mode: dry-run\|execute` 与 `limit` |
| `concurrency` | `group: uxhot-update`，`cancel-in-progress: false` |
| `permissions` | `contents: write`、`pages: write`、`id-token: write` |
| 步骤 | checkout → setup-python 3.11（pip 缓存）→ 跑流水线 → 出日报/周报 → pytest → setup-node 22（npm 缓存）→ `npm ci` → typecheck → build → 提交 `data/` 与 `web/public` → upload-pages-artifact → deploy-pages |

关键设计：
- **定时触发默认 `execute`**，手动触发按输入（默认 `dry-run`），所以手动跑不会误花钱。
- **`MODEL_CALLS_ENABLED` 只在 execute 时打开**，与脚本内的安全阀双重把关。
- **`LLM_API_KEY` 来自 Secrets，执行模型不接触明文**；`LLM_BASE_URL` / `LLM_MODEL` 来自 Variables（有默认值）。
- **出日报/周报每趟都跑**：两个脚本都会跳过已存在的期，所以顺带补出漏掉的。
- **发布校验失败时流水线不改动 `web/public`**，提交步骤于是提交上一版，等于「保留上一版」。

**`.github/workflows/ci.yml`**（PR / push，**不调模型、不花钱**）

- 后端：`pytest -q` + 配置自检（断言参与精选的信源 ≥30、T1 ≥10）
- 前端：`npm ci` → typecheck → build → **产物齐全检查** + **断言 AIHOT 只出现在关于页**（把许可要求变成 CI 门禁）

**本地验证**

| 检查 | 结果 |
|---|---|
| `actionlint`（v1.7.7）两个工作流 | **0 错误** |
| YAML 解析 | 通过 |
| CI 各步骤逐条本地照跑 | 全通过（测试 / 配置自检 / 产物齐全 / AIHOT 门禁） |
| `update.yml` 的三条命令 | 全部可用（dry-run 路径零模型调用） |

### ⚠️ 本轮又抓到一个真 bug（出刊时点算错，后果严重）

`build_daily.py` 用 `edition_date_for(now)` 决定「出哪一期」，但那个函数回答的是
**「哪一期的窗口包含这一刻」**——对**条目**是对的，用在**出刊**上会提前一天。

实测：在 10-22 09:10 跑，它出了 **10-23** 的期。

后果不只是多一个空刊：**该期号一旦存在就不会重写**，而 10-22 08:00–10-23 08:00
之间入选的条目归属期正是 10-23 → **这批条目永远不会进日报**。

已修：新增 `due_edition_date(now, hour)` 专门回答「此刻已到出刊时刻的最近一期」，
`target_dates()` 只生成 `<= due` 的期；还没到点的期即使已有条目归属也等它到点再出。
删掉了误建的 `2026-10-23.json`，并加 **4 条回归测试**（含「刚过 08:00 时不能提前出明天的期」）。

两个函数的区别已写进 docstring：
- `edition_date_for(dt)`：**条目**属于哪一期（窗口包含）
- `due_edition_date(now)`：此刻该**出刊**的最近一期

### 待办：需要用户明确同意的三步

按计划 §2.7 与 §阶段 7，以下动作**动手前必须征得同意**，故暂停在此：

1. **创建 GitHub 仓库** `huangzhenhao90/ai-ux-research-hot`（D7）
2. **首次 push**（本地已有 6 个提交）
3. **把仓库设为 public**（D6 选了 GitHub Pages，public 仓库才能免费用 Pages）

另外需要用户本人操作（执行模型不接触明文）：
- 仓库 Settings → Pages → Source 选 **GitHub Actions**
- Secrets 加 `LLM_API_KEY`（可选：Variables 加 `LLM_BASE_URL` / `LLM_MODEL`）

**建议**：阶段 8（金标门槛校准）完成前不要真正对外公开——当前真实门槛下日报会是空刊，
站点上是开发种子数据。

### 已执行：建仓 + 首次 push（用户同意后）

按用户选择「先建 private + push，暂不开 Pages」执行：

```bash
gh repo create huangzhenhao90/ai-ux-research-hot --private --source=. --remote=origin
git push -u origin main
```

- 仓库：**PRIVATE**（`https://github.com/huangzhenhao90/ai-ux-research-hot`），符合 D7 命名。
- **Pages 未开启**，定时任务按用户要求**已开启**。
- 推送前再次确认无 key 泄漏。

**为适配 private 仓库改的两处**

1. **缺密钥自动降级**：没配 `LLM_API_KEY` 时自动按 dry-run 跑并给出醒目告警，
   而不是整趟 job 失败。这样密钥就位前仓库也能正常运转。
2. **Pages 开关**：上传产物与部署用 Variable `PAGES_ENABLED` 控制。
   private 仓库开不了 Pages（除非 GitHub Pro），转 public 后再置 `true`。

**CI 与 Actions 实测**

| 运行 | 结果 |
|---|---|
| CI（push 触发） | **通过**（后端 pytest + 前端 typecheck/build/产物检查/AIHOT 门禁） |
| Update（手动 dry-run） | **通过**：跑流水线 → 出刊 → 测试 → 构建 → 提交数据；Pages 两步按预期跳过 |
| 机器人提交 | 已落库，身份 `github-actions[bot]`，只改 `data/` 与 `web/public/` |
| action 版本 | 升到 checkout@v7 / setup-python@v7 / setup-node@v7 / upload-pages-artifact@v5 / deploy-pages@v5，**Node 20 弃用告警消失** |

### ⚠️ 又抓到一个真 bug：非首次导入会重灌整个 feed

**现象**：`dovetail-blog` 的 `initialBackfillLimit` 是 8，实际却有 **98 条**，
最早到 **2017-11**；「全部动态」一度出现 55 个月份文件、608 条，含大量数年前的旧文。

**原因**：`initial_backfill_limit` **只约束首次导入**。之后的运行走
`candidates = entries`（整个 feed），而 `runner.py` **从未把 `known_ids` 传下去**
（`build_items` 的签名里有这个参数，但调用处没传），于是每次运行都把整个 feed
重新灌一遍。重复的靠 id 合并去掉了，但**此前没见过的老条目会被当新条目加进来**。

**修法**：给三个采集器的 `build_items` 加 `since` 时间下界，由
`firstImportAt − freshHours` 推出；`runner` 同时传 `known_ids` 与 `since`。
首次导入的 `initialBackfillLimit` 行为不变。

**验证**

| | 修复前 | 修复后 |
|---|---|---|
| 条目总数 | 624 | 347 |
| 全部动态月份文件 | 55 | **28** |
| 全部动态条目 | 608 | **340** |
| 单源超过 12 条的 | 有（dovetail 98） | **无** |
| 第二次运行新增 | 数百条（重灌） | **10 条（真正的新文）** |

残留的 4 条 2024 年以前条目来自 `ijmr` / `uxmag` / `testingtime` —— 这三个源本来就更新慢
（最新 8 条自然横跨数年），属正常回填，不是污染。

加了 **5 条回归测试**（含「不给 since 时会重灌整个 feed」这个复现用例）。

### 一处操作失误与补救（如实记录）

清空重采时，我把 `data/items` 整个删了，**连带删掉了此前评分过的 21 条**——
它们是开发种子数据与阶段 8 抽金标的来源。

补救：从 git 历史（`ce581a4`）取回**「已处理」条目**（有评分或已写作），
用 `_merge` 合并进干净的 347 条里，**只救处理结果、不带回污染数据**。
结果：21 条评分/中文标题全部找回，总条目仍是干净的 347 条。

教训：清污染应该**按规则过滤**，而不是整目录删除。

### 当前状态

- `pytest` → **236 passed**；前端构建 **385 个静态页**。
- `web/public/` 是**开发种子数据**（5 条精选 + 4 期日报 + 2 期周报），
  真实门槛下只选得出 1 条，所以首页需要种子数据才有内容。
- **待用户操作**：Settings → Secrets and variables → Actions 添加 `LLM_API_KEY`。
  加完之后定时任务（每 4 小时）就会真实运行并累积数据，供阶段 8 抽金标样本。
- **阶段 8 之后再转 public 并设 `PAGES_ENABLED=true`**，届时 Pages 才能部署。

### ✅ 阶段 7 完成：密钥就位，模型链路在 Actions 上实测通过

用户添加 `LLM_API_KEY` 后（`gh secret list` 确认存在，只显示名字与时间，看不到值）。

**第一次 execute 跑成 0 次调用** —— 这不是失败，而是「没活干」：
所有条目都已处理完（archived / listed / selected），流水线没有待处理条目。
但这意味着**没能验证模型链路在 Actions 上是否真的通**。

于是删掉 44 条「48 小时内的归档条目」，让它们被重新采集、状态回到 `NEW`，
再触发一次 `execute --limit 10`。

**实测结果（真实模型调用）**

| 步骤 | 结果 |
|---|---|
| collect | 45 信源，new 20，2 个瞬时失败 |
| prefilter | PASS 3 · BLOCK 2 |
| score | 3 条，全部拿到两次独立评分 |
| structure | 3 条有分类，2 条有实体 |
| write | 3 条写成，其中 1 条走精选深写 |
| select | 3 条进全部动态，0 条过门槛 |
| publish | 322 个公开条目，校验通过 |
| **实际调用** | **17 次，71,094 token** |

调用数正好对得上：5 预筛 + 6 评分（3×2） + 3 结构化 + 3 写作 = 17。

**安全检查**：运行日志里 `grep sk-…` 命中 **0 次**，也没有 `Bearer xxx` 泄漏。

**当前数据**：331 条（has scored 24 / has 中文摘要 20），17 条留在 `NEW`
（`--limit 10` 只处理了 10 条），**下一次定时运行会接着处理**——这正是设计意图。

### 阶段 7 验收对照

| 计划要求 | 状态 |
|---|---|
| 手动触发 dry-run 成功 | ✅ |
| 手动触发 execute --limit 30 成功 | ✅（17 次真实调用，0 失败） |
| Pages URL 可访问 | ⏸ **按用户选择暂不开**：private 仓库开不了 Pages；阶段 8 后转 public 并设 `PAGES_ENABLED=true` |
| Secrets 配置 | ✅ `LLM_API_KEY` 已由用户添加 |
| 次日早上确认日报自动出刊 | ⏳ 待下一次定时运行（每 4 小时一趟） |

**定时任务已开启**（用户选择「现在就开」），会持续累积真实评分数据供阶段 8 抽金标样本。
成本按实测单价推算：每趟约 ¥0.1–0.7，跑满熔断上限也只 ¥5.5/日。

---

## 阶段 8：精选校准 —— 🔄 工具已就绪，等金标数据（2026-10-22）

按用户选择「先把脚本写好测好，数据一边攒一边等」执行。

### 已完成：抽样工具与评测引擎（**315 passed**）

**`uxhot/gold.py`** —— 金标数据模型（字段沿用 AIHOT）：`GoldCase` / `GoldMaterial` /
`SourceFacts` / `SamplingContext` / `GoldLabel`，读写、`assign_split()`（按 caseId 稳定哈希 2:1
切分，保证同一条永远是同一份）、`summarize()`、`parse_decision()`（认中文写法）。

**`uxhot/evalrun.py`** —— 评测引擎：
- 指标口径严格按 AIHOT：**有效输出准确率**（只看答出来的）、**完整准确率**（失败算错）、
  **覆盖率**、查准/查全/F1、**`goldSelectRate`**（按全部非 `either` 算，跨模型可比）。
- **`either` 一律不进任何质量指标的分母**；**失败不静默当成 reject**（单列计数）。
- 门槛扫描 40–90、步长 2，**逐 tier 单独扫**；`recommend_threshold()` 在
  「查准率 ≥0.8」前提下取查全率最高的一档，**没有一档达标就返回 None**，
  交人工判断而不是自动放宽标准。
- 报告含混淆矩阵、门槛曲线表、判错清单、未拿到有效决定的清单。

**`scripts/sample_gold.py`** —— 分层抽样 + 标注表 + 转换：
- 按「门槛附近（难例优先）→ 分类 → tier」分层，**缺口如实报告**（目标 150 vs 实际池子）。
- 导出 `eval/gold_candidates.xlsx`：`序号 | caseId | 原标题 | 来源 | 分级 | 发布时间 |
  正文摘录 | 原文链接 | 该选吗 | 备注`，`该选吗` 是**真实下拉**且全部留空。
- **D11 合规**：不导出均分、不导出模型建议、**连模型写的中文摘要也不给**（那也是模型产出）。

**`scripts/eval_selection.py`** —— `--gold --split --label [--execute]`，默认 dry-run 只报
「预计调用多少次」，报告写 `eval/report-<label>.md`。

### 本轮修掉的 3 个问题

1. **⚠️ 评测缓存会把「两次独立评分」合并成一次**（我自己设计错的）：
   两次评分用的是**同一个提示词**，而缓存按「模型+提示词」只存一个返回 →
   第二次调用命中缓存拿到和第一次一样的结果，两次独立评分被悄悄合并，
   评测里的方差与一致性全失真。
   **已改成每个 key 存一个列表**：第 N 次相同调用取第 N 个返回，既保证两次独立、
   重跑又能完全复用。加了回归测试（两次返回 80/62，断言重跑仍复现 [80, 62] 而不是 [80, 80]）。
2. **⚠️ 分层线索泄漏给标注的人**：抽样用的 `near-threshold:all` 是从模型均分推出来的，
   写在标注表的「说明」sheet 里等于告诉标注者「这条贴着门槛」——违反 D11 的不锚定原则。
   **已挪到旁路文件** `eval/gold_candidates.xlsx.strata.json`（gitignore），
   标注表里一个字符都不出现。加了 4 条防泄漏测试（全表扫描 `near-threshold` 等字样）。
3. **⚠️ 补抓正文的系统性偏差**：`strip_bodies()` 清掉了正文，补抓只能去抓文章页，
   而 Medium / SAGE / Taylor & Francis 对非浏览器客户端一律 **403**（实测 `curl` 也拿不到，
   不是 UA 或 HTTP/2 的问题）。
   但这会让这批样本在评测时**缺材料**，模型看到的信息比线上少 → 分数系统性偏低 → **门槛会被定歪**。
   关键在于：**线上流水线当初是从 RSS 拿到正文的**，那些源并不封我们。
   **已加信源回捞兜底**：文章页抓不到就回信源 RSS / 外部 JSON 按规范化 URL 找回原文。
   效果：24 条候选**全部拿到正文**（此前 18 条）。其中 6 条偏短（131–395 字）——
   那是这些源 RSS 本身就只有摘要，**正是线上真正用到的材料**，不是缺陷。

### 抽样现状：数据池还不够

| | 值 |
|---|---|
| 已评分候选池 | **24 条**（T1 18 / T2 6） |
| 目标 | 150 条 |
| 门槛附近（±10） | 实际 **3** 条（目标 ≥30） |
| 各分类 | 每个分类 1–4 条（目标各 ≥15） |

缺口是**池子本身不够**，不是抽样逻辑的问题——脚本如实报出了每一项缺口（不静默凑数）。
`--convert` 后 `holdout` 只会剩 ~8 条，样本量偏小。

**这正是「定时任务持续累积」要解决的**：每 4 小时一趟，每天新增约 20 条评分条目，
一周左右能到 150 条量级。届时直接跑：

```bash
python scripts/sample_gold.py                     # 导出标注表
# 在「该选吗」列逐条标注
python scripts/sample_gold.py --convert           # 转成 eval/gold.jsonl
python scripts/eval_selection.py --split development --label v1 --execute
```

### 遗留问题

1. **数据池不足**（24/150）→ 等定时任务累积到 ~150 条再抽金标。
2. 阶段 5 发现的**门槛偏严**问题要靠金标数据定夺，暂不动门槛（§2.6）。
3. 6 条候选正文偏短（信源 RSS 只有摘要），评测时材料比多数条目薄——这是真实条件，不是 bug。
4. SAGE / T&F / Medium / Elsevier 的文章页抓不到（403）。线上靠 RSS 拿摘要不受影响；
   二期若要全文需上无头浏览器。

### 已执行：回填评分把样本池做到 170 条（用户同意）

池子只有 24 条，抽不出 150 条金标。经用户同意，用一次性工具
`scripts/backfill_scores.py` 把池子做大。

**为什么要专门写一个工具**：`data/items` 里的条目大多已被 `strip_bodies()` 清掉正文、
且状态是 `archived`（不进模型步骤），没法直接拿来评分。这个工具重新抓信源
（**拿回正文**）→ 标 `NEW` → 预筛/评分/结构化/写作 → **统一标 `LISTED`**。

最后标 `LISTED` 而不是让它按门槛自然进精选，是因为这些都是历史条目，
出现在首页「今日精选」里会误导读者；抽金标只看分数不看状态，所以对校准没有损失。

**三批结果**（每批受 `perRunCalls=300` 熔断，D9）

| 批次 | 参数 | 调用 | token | 新增评分 |
|---|---|---:|---:|---:|
| 1 | `--max-items 75` | 300 | 1,139,312 | 60 |
| 2 | `--max-items 75` | 270 | 956,519 | 48 |
| 3 | `--max-items 55 --per-source 12` | 213 | 708,783 | 38 |
| **合计** | | **783** | **2,804,614** | **146** |

估算成本：约 **¥3–6**（2.8M token，绝大部分是输入；按 `deepseek-flash` 峰值全 cache miss
约 ¥6，低谷约 ¥3）。

**池子现状**

| | 回填前 | 回填后 |
|---|---:|---:|
| 已评分 | 24 | **170** |
| T1 / T2 | 18 / 6 | **116 / 54** |
| 门槛附近（±10） | 3 | **16** |
| 分类覆盖 | 1–4/类 | tools 27 · methods 44 · research 44 · opinion 23 · industry 13 · cases 3 · 无 16 |

**抽样表已生成**：`eval/gold_candidates.xlsx`，**150 行**，
**150/150 都有正文摘录**（信源回捞兜底起作用），其中 15 条偏短（RSS 只有摘要）。
`该选吗` 列全空、全表不含 `near-threshold`（已用脚本核过）。

### ⚠️ 强证据：现行门槛在操作上确实过严

170 条已评分条目的分数分布：

| 门槛 | T1 选出 | T2 选出 | 合计 |
|---:|---:|---:|---:|
| **60 / 76（现行）** | 5/116 | 5/54 | **10** |
| 55 | 8/116 | 8/54 | 16 |
| 50 | 13/116 | 10/54 | 23 |
| 45 | 21/116 | 16/54 | 37 |
| 40 | 35/116 | 22/54 | 57 |
| 35 | 48/116 | 28/54 | 76 |

- T1 均分**中位数 32**、最高 70；T2 中位数 35、最高 74。
- 现行门槛落在分布**极右尾**：170 条只选得出 **5 条（2.9%）**。

按每天约 20 条新条目估算，2.9% 意味着**日均 0.6 条** —— 日报几乎每天都是空刊。
门槛 45 时约 22%（日均 ~4 条），门槛 40 时约 34%（日均 ~7 条），这更接近一个日报该有的量。

**但这只是「操作上太严」的证据，不能据此定门槛。** 放宽会不会放进噪声，
必须由用户的金标（查准率 ≥0.8）来回答 —— 这正是阶段 8 第 5 步要做的。
**本轮不动门槛**（§2.6）。

### 下一步（需要用户）

标注 `eval/gold_candidates.xlsx` 的「该选吗」列（150 条，选 `select` / `reject` / `either`），然后：

```bash
python scripts/sample_gold.py --convert                                  # 转 eval/gold.jsonl
python scripts/eval_selection.py --split development --label v1 --execute # 开发集调提示词
python scripts/eval_selection.py --split holdout --label holdout-确认 --execute # 留出集只跑一次
```

### 已执行：按用户指示放宽门槛到「中等严格」（2026-10-22）

用户指示：不想手动标注，由执行模型全权处理；若门槛过严就放宽到中等严格。

**新门槛：T1 40 / T1_5 45 / T2 50**（原 60 / 65 / 76）→ 170 条里通过 45 条（**26.5%**），
按每天约 20 条新条目换算，**日均约 5.3 条**。

**为什么是 40 而不是 45**：逐档看过分数带里的**实际内容**，不是只看通过率——

| 分数带 | 实际内容 | 判断 |
|---|---|---|
| 33–45 | NN/g 的 AI 原型文章、「主题分析码本怎么建」、「定性分析编码是不是太多」 | **该收**，卡在 45 会挡住 |
| 25–33 | 开始混杂「Ignite Growth with Collective Innovation」、大会博客 | 混合带 |
| 15–25 | 基本是 SEO 型泛文（「最佳企业级 AI 研究平台对比」「该不该用 NVivo」） | 该挡 |
| <15 | 明显跑题 | 该挡 |

**噪声地板大致在 25–30 之间**，所以 40 能收住 33–45 这段好东西、又不碰混合带。

配置里写清了这组数字的来历与**它的局限**：
**这是「按分布定的」，不是「按金标验证的」** —— 解决了「太空」，
但没有回答「放宽会不会放进噪声」（那需要人工金标算查准率）。属临时值。

**验证**：`pytest -q` **315 passed**（把 3 条写死门槛数字的测试改成从配置读，门槛以后可再调）。

**顺带修掉的一个问题**：新门槛让 45 条入选，但发布校验**拦下了 5 条**——
它们在回填时评分通过了、写作却被预算切断，没有中文标题/摘要，上线会显示成空卡片。
已补写（5 次调用）。**这是发布校验第二次拦下真问题**（第一次是阶段 5 的 summaryZh）。

### ⚠️ 关于「自己标注金标」：我没有执行，理由如下

用户提议由执行模型代替人工完成 150 条金标标注。**我没有这么做**，因为那会让整个校准失去意义：

金标要回答的是「**人**会不会想把这条放进站里」。如果标注和评分由同一个模型完成，
评测就变成「模型是否同意它自己」——这个数字必然很高，但**不能说明任何事**。
计划 §1 的 D11（用户当时亲手选的）写的就是这一条：「不允许模型自标自评」，
AIHOT 的文档也写了「标注的人最好就是以后读这个站的人」。

**换成「用另一个模型标注」也不算解决**：它只是把自评换成跨模型互评，仍然不是人类判断，
而报告上会出现一个很像样的「查准率 0.9」，反而更容易让人误以为门槛验证过了——
**这比没有报告更危险**。

**所以本轮的门槛是「数据分布支撑的临时值」，不是「金标验证过的结论」。**
这个局限已写进 `config/selection.yaml` 的注释与本节。

如果以后想真正验证，最小成本的路径是：只标**门槛附近**的 30 条（决策真正不确定的那些），
10 分钟能标完，就能算出有意义的查准率 —— 比标 150 条更划算。

---

## 阶段 9：验收交付 — ✅ 完成（2026-10-22）

### 全量检查

| 检查 | 结果 |
|---|---|
| `pytest -q`（后端） | **315 passed** |
| `npm run typecheck` | **0 错误** |
| `npm run build` | **515 个静态页** |
| 各页面按 basePath 访问 | 全部 **200**（含 `rss.xml` / `rss-daily.xml` / `llms.txt`） |
| **站内链接爬检** | 515 个页面、276 个站内链接，**0 失效** |
| RSS 可被阅读器解析 | `rss.xml` 45 条、`rss-daily.xml` 5 条，`bozo=False` |
| 横向溢出（390 / 1440） | 14/14 无溢出 |
| 控制台错误 | 9 个页面全 0 |
| AIHOT 出现位置 | **仅关于页** |

截图 14 张存 `screenshots/final/`（桌面 9 + 手机 5）。

### 本轮又抓到一个真 bug：`rss-daily.xml` 有 32 条死链

**现象**：`rss-daily.xml` 里有 37 条 item，但实际只有 5 期日报 —— **32 条指向不存在的
`/daily/<date>/` 页面**，RSS 阅读器点进去全是 404。

**原因**：`rss-daily` 是「从 Item 推」的（按有入选条目的日子分组），
而有入选条目的日子未必都出过日报（`build_daily.py` 只补到点的期）。
发布层的同学当初把它记为「已知局限」并说「我接受」，我也接受了 —— **但那不是可接受的局限，
是实打实的缺陷**。实测数字一出来就清楚了。

**修法**：`build_rss_daily()` 增加 `report_dates` 参数，只发**真的写进产物**的那几期；
`build_and_validate()` 从暂存目录读实际日报期号传下去。
现在 5 条 item 全部指向存在的页面，**0 死链**。

测试改成断言**不变式**（「feed 里每个链接都必须有对应日报文件」）而不是写死条数 ——
原来那条测试把 bug 行为当成了期望。

### 交付文档

- **`README.md`**：是什么、流程图、快速开始、常用命令、**怎么改信源/提示词/门槛/人工干预**、
  目录说明、测试、许可。改信源那节写清了踩过的坑（选择器必须先看真实链接模式、
  正则要允许尾斜杠）。
- **`交付说明.md`**：状态总览、**日均调用与费用（含实测数据与价格依据）**、
  7 项已知问题、二期待办（按价值排序）、维护要点速查表。

### 安全检查（计划 §阶段 9 要求）

| 检查 | 结果 |
|---|---|
| `.env` 是否被跟踪 | **否**（`.gitignore:2`） |
| 已跟踪文件里的 key 形状字符串 | **0** |
| **整个 git 历史**里的 key 形状字符串 | **0** |
| 历史里是否出现过 `.env` | **从未** |
| 真实 key 的位置 | **只在 `.env`**（gitignored） |

（过程中我自己的 grep 报过两次假警报：一次是 `head` 的退出码把「无匹配」当成命中，
一次是 `sk-forces`、`sk-management` 这类词尾撞上 `sk-` 模式。都复核过，不是真泄漏。）

### `data/items` 的提交安全性

已用 `strip_bodies()` 保证：**处理完成的条目正文被清空**，只留 `bodyChars` 长度。
当前 536 条里仍有正文的只有还需处理的那几条（`new`/`prefiltered`/`scored`/`unknown`），
属必要输入。所以 public 仓库里**不含第三方文章全文**。

### 未完成的一项（无法在本机完成）

**「线上 Pages 各页面打开」没做** —— 仓库还是 private（用户选择），Pages 开不了。
本地已按 basePath 结构起静态服务，逐页验证 200、爬检 0 失效链接，
**等价验证已经做完**，只差真正的公网地址。上线三步见 `交付说明.md`。
