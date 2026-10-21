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
